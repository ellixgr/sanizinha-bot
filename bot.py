import os
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from flask import Flask
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, TypeHandler, ContextTypes, filters, MessageHandler
from comandos.jogos.menujogos import menu_jogos_handler, processar_callback_jogos

# Importações dos módulos de proteção para o interceptador global
from protecao.antiflod import executar_antiflod
from protecao.status import obter_punicao, obter_mencao_admins_str

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
DONO_ID = os.environ.get("DONO_ID")

# Fuso horário do Brasil (UTC-3)
FUSO_BR = timezone(timedelta(hours=-3))

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot online e operacional!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

_mongo_client = None
def get_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(
            MONGO_URI, 
            serverSelectionTimeoutMS=1000, 
            connectTimeoutMS=1000,
            maxPoolSize=50,
            tlsAllowInvalidCertificates=True
        )
    return _mongo_client["sanizinhabot_db"]

async def cmd_registrar_aluguel_dono(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if not chat or chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado dentro de grupos ou canais!")
        return

    if not DONO_ID or str(user.id) != str(DONO_ID):
        await update.message.reply_text("❌ Apenas o dono do bot pode utilizar este comando.")
        return

    db = get_db()
    agora = time.time()
    expira_em = agora + (10 * 365 * 24 * 60 * 60)

    db["grupos_autorizados"].update_one(
        {"chat_id": chat.id},
        {
            "$set": {
                "chat_id": chat.id,
                "chat_title": chat.title,
                "registrado_por": user.id,
                "expira_em": expira_em,
                "ativo": True
            }
        },
        upsert=True
    )

    db["avisos_grupos_piratas"].delete_one({"chat_id": chat.id})

    await update.message.reply_text(
        f"✅ **Grupo Registrado com Sucesso!**\n\n"
        f"Este chat (`{chat.id}`) foi definido como alugado pelo Dono. "
        f"Os avisos de cobrança foram desativados e o bot funcionará normalmente aqui!",
        parse_mode="Markdown"
    )

async def verificar_se_e_adm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat = update.effective_chat

    if DONO_ID and str(user_id) == str(DONO_ID):
        return True

    if chat.type in ["group", "supergroup"]:
        try:
            membro = await chat.get_member(user_id)
            if membro.status in ["administrator", "creator"]:
                return True
        except Exception:
            pass
        return False
    
    return False

# Interceptador Global de Proteções rodando no group=-1 (Prioridade máxima)
async def interceptador_geral_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    message = update.message or update.effective_message
    
    if not chat or not user or chat.type == "private" or not message:
        return

    passou_flood = await executar_antiflod(
        update, context, chat, user, message, 
        get_db, verificar_se_e_adm, obter_punicao, obter_mencao_admins_str
    )
    if passou_flood:
        raise ApplicationHandlerStop  # Interrompe totalmente o fluxo para o flood não passar

async def interceptador_estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    message = update.message
    if not message or chat.type == "private":
        return

    tipo_incremento = {"total_mensagens": 1}
    if message.photo:
        tipo_incremento["fotos"] = 1
    elif message.video:
        tipo_incremento["videos"] = 1
    elif message.voice or message.audio:
        tipo_incremento["audios"] = 1
    elif message.sticker:
        tipo_incremento["stickers"] = 1

    try:
        db = get_db()
        db["mensagens_usuarios"].update_one(
            {"chat_id": chat.id, "user_id": user.id},
            {"$inc": tipo_incremento},
            upsert=True
        )
    except Exception:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    agora = datetime.now(FUSO_BR)
    hora_atual = agora.strftime("%H:%M:%S")
    data_atual = agora.strftime("%d/%m/%Y")

    texto_menu = (
        "✪\\▁▁▁▁▁▁▁▁▁▁▁▁\\\n"
        f"✰┃👤 : {user.first_name}\n"
        f"✰┃🆔 : `{user.id}`\n"
        f"✰┃🕘 : {hora_atual}\n"
        f"✰┃☀️ : {data_atual}\n"
        "✰┃ 🤖 **BOT**\n"
        "✪/ 🌬️ **Sanizinha** ®\n\n"
        "┌──────────┐\n"
        "   ≡  **M E N U S**  ≡\n"
        "└──────────┘"
    )

    botoes = [
        [InlineKeyboardButton("📜 Comandos & Membro", callback_data="menu_membros")],
        [InlineKeyboardButton("👑 Comandos & Adm", callback_data="menu_adm")],
        [InlineKeyboardButton("🤖 Alugar Bot", callback_data="menu_aluguel")],
        [InlineKeyboardButton("🤖 Adicionar ao seu Grupo", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ]

    if DONO_ID and str(user.id) == str(DONO_ID):
        botoes.insert(3, [InlineKeyboardButton("🛠️ Painel do Dono (Deploy)", callback_data="menu_dono")])

    teclado_painel = InlineKeyboardMarkup(botoes)

    await update.message.reply_text(
        texto_menu,
        reply_markup=teclado_painel,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    chat = query.message.chat

    if query.data == "menu_membros":
        await query.answer()
        texto_membros = (
            "📜 **Comandos para Membros:**\n\n"
            "🏓 `/ping` - Status de hardware, RAM e latência\n"
            "👤 `/perfil` - Suas estatísticas completas, bio e mídias\n"
            "🆔 `/id` - Mostra seu ID e do chat\n"
            "📥 `/play` ou `/dl` - Baixa vídeos e músicas do YouTube"
        )
        teclado_membros = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏓 Ping", callback_data="botao_ping"), InlineKeyboardButton("👤 Perfil", callback_data="menu_perfil_atalho")],
            [InlineKeyboardButton("🆔 ID", callback_data="menu_id_atalho"), InlineKeyboardButton("🎮 Jogos", callback_data="menu_jogos_atalho")],
            [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]
        ])
        await query.message.edit_text(texto_membros, reply_markup=teclado_membros, parse_mode="Markdown")
        
    elif query.data == "menu_adm":
        await query.answer()
        texto_adm = (
            "🛡️ **Comandos para Administradores:**\n\n"
            "🔨 `/ban` - Bane o usuário respondido\n"
            "🔇 `/mutar` / `/desmutar` - Silencia ou libera o usuário\n"
            "⭐ `/promover` - Promove a administrador\n"
            "📉 `/rebaixar` - Rebaixa administrador\n"
            "📢 `/marcar` - Marca todos do grupo\n"
            "📌 `/citar` - Cita mídias/textos marcando todos\n"
            "⚙️ `/status` - Configura as travas de segurança\n"
            "👋 Configurar Bem-Vindo abaixo:"
        )
        teclado_adm = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛡️ Proteções do Grupo", callback_data="menu_protecoes")],
            [InlineKeyboardButton("👋 Configurar Bem-Vindo", callback_data="config_bemvindo")],
            [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]
        ])
        await query.message.edit_text(texto_adm, reply_markup=teclado_adm, parse_mode="Markdown")

    elif query.data == "menu_dono":
        if not DONO_ID or str(user_id) != str(DONO_ID):
            await query.answer("⚠️ Acesso negado!", show_alert=True)
            return
        await query.answer()
        texto_dono = (
            "🛠️ **Painel Exclusivo do Dono**\n\n"
            "Gerencie atualizações e compilações completas do bot diretamente por aqui:"
        )
        teclado_dono = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Clear Build Cache & Deploy", callback_data="executar_deploy")],
            [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]
        ])
        await query.message.edit_text(texto_dono, reply_markup=teclado_dono, parse_mode="Markdown")

    elif query.data == "executar_deploy":
        if not DONO_ID or str(user_id) != str(DONO_ID):
            await query.answer("⚠️ Acesso negado!", show_alert=True)
            return
        from comandos.deploy import executar_clear_deploy
        await executar_clear_deploy(update, context)

    elif query.data == "config_bemvindo":
        if not await verificar_se_e_adm(update, context):
            await query.answer("⚠️ Apenas administradores do grupo podem configurar o Bem-Vindo!", show_alert=True)
            return
        await query.answer()
        try:
            from comandos.bemvindo import enviar_painel_principal_bv
            await enviar_painel_principal_bv(context, update.effective_chat.id, query=query)
        except Exception as e:
            await query.message.reply_text(f"⚠️ Erro ao abrir o painel de boas-vindas: {e}")

    elif query.data == "menu_protecoes":
        if not await verificar_se_e_adm(update, context):
            await query.answer("⚠️ Apenas administradores do grupo podem configurar as Proteções!", show_alert=True)
            return
        await query.answer()
        try:
            from protecao.status import enviar_painel_protecoes
            await enviar_painel_protecoes(update, context)
        except Exception as e:
            await query.message.reply_text(f"⚠️ Erro ao abrir o painel de proteções: {e}")

    elif query.data == "menu_config_punicao":
        if not await verificar_se_e_adm(update, context):
            await query.answer("⚠️ Apenas administradores do grupo podem configurar as punições!", show_alert=True)
            return
        try:
            from protecao.status import enviar_painel_punicao
            await enviar_painel_punicao(update, context)
        except Exception as e:
            await query.message.reply_text(f"⚠️ Erro ao abrir o painel de punições: {e}")

    elif query.data.startswith(("prot_", "pun_", "menu_fechar")):
        if not await verificar_se_e_adm(update, context):
            await query.answer("⚠️ Apenas administradores podem alterar estas opções!", show_alert=True)
            return
        try:
            from protecao.status import processar_callback_protecao
            await processar_callback_protecao(update, context)
        except Exception as e:
            await query.answer(f"⚠️ Erro: {e}", show_alert=True)

    elif query.data == "botao_ping":
        await query.answer("Calculando ping...", show_alert=False)
        from comandos.ping import ping_cmd
        await ping_cmd(update, context)

    elif query.data == "menu_perfil_atalho":
        await query.answer()
        if chat.type == "private":
            await query.message.reply_text("⚠️ Use este comando dentro de um grupo para ver suas estatísticas completas!")
            return
        
        total_msgs, fotos, videos, audios, stickers = 1, 0, 0, 0, 0
        try:
            db = get_db()
            doc = db["mensagens_usuarios"].find_one({"chat_id": chat.id, "user_id": user_id})
            if doc:
                total_msgs = doc.get("total_mensagens", 1)
                fotos = doc.get("fotos", 0)
                videos = doc.get("videos", 0)
                audios = doc.get("audios", 0)
                stickers = doc.get("stickers", 0)
            
            total_grupo = db["mensagens_usuarios"].aggregate([
                {"$match": {"chat_id": chat.id}},
                {"$group": {"_id": None, "soma": {"$sum": "$total_mensagens"}}}
            ])
            soma_doc = list(total_grupo)
            total_geral_grupo = soma_doc[0]["soma"] if soma_doc else 1
            atividade_pct = min((total_msgs / total_geral_grupo) * 100, 100.0)
        except Exception:
            atividade_pct = 0.0

        bio = "Não configurada ou oculta."
        try:
            chat_info = await context.bot.get_chat(user_id)
            if chat_info.bio:
                bio = chat_info.bio
        except Exception:
            pass

        user_obj = update.effective_user
        texto_perfil = (
            f"👤 **PERFIL DE {user_obj.first_name.upper()}**\n\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"💬 **Bio:** _{bio}_\n\n"
            f"📊 **ESTATÍSTICAS NO GRUPO:**\n"
            f"💬 Mensagens Totais: `{total_msgs}`\n"
            f"📸 Fotos Enviadas: `{fotos}`\n"
            f"🎥 Vídeos Enviados: `{videos}`\n"
            f"🎙️ Áudios/Voz: `{audios}`\n"
            f"🎭 Figurinhas: `{stickers}`\n"
            f"⚡ Índice de Atividade: `{atividade_pct:.1f}%`"
        )
        teclado_voltar = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_membros")]])
        await query.message.edit_text(texto_perfil, reply_markup=teclado_voltar, parse_mode="Markdown")

    elif query.data == "menu_id_atalho":
        await query.answer()
        texto = f"🆔 **Seu ID:** `{user_id}`\n"
        if chat.type in ["group", "supergroup"]:
            texto += f"🏢 **ID do Grupo:** `{chat.id}`"
        teclado_voltar = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_membros")]])
        await query.message.edit_text(texto, reply_markup=teclado_voltar, parse_mode="Markdown")

    elif query.data == "menu_jogos_atalho":
        await menu_jogos_handler(update, context)

    elif query.data in ["jogo_velha", "jogo_memoria", "jogo_xadrez", "jogo_dama"]:
        await processar_callback_jogos(update, context)

    elif query.data in ["voltar_menu", "ver_comandos", "voltar_principal_grupo"]:
        await query.answer()
        
        agora = datetime.now(FUSO_BR)
        hora_atual = agora.strftime("%H:%M:%S")
        data_atual = agora.strftime("%d/%m/%Y")

        texto_ajuda = (
            "✪\\▁▁▁▁▁▁▁▁▁▁▁▁\\\n"
            f"✰┃👤 : {update.effective_user.first_name}\n"
            f"✰┃🆔 : `{update.effective_user.id}`\n"
            f"✰┃🕘 : {hora_atual}\n"
            f"✰┃☀️ : {data_atual}\n"
            "✰┃ 🤖 **BOT**\n"
            "✪/ 🌬️ **Sanizinha** ®\n\n"
            "┌──────────┐\n"
            "   ≡  **M E N U S**  ≡\n"
            "└──────────┘"
        )
        
        botoes_voltar = [
            [InlineKeyboardButton("📜 Ver todos comandos de membros", callback_data="menu_membros")],
            [InlineKeyboardButton("🛡️ Ver todos comandos de ADM", callback_data="menu_adm")],
            [InlineKeyboardButton("🤖 Alugar Bot", callback_data="menu_aluguel")],
            [InlineKeyboardButton("🏓 Ping do Bot", callback_data="botao_ping")],
            [InlineKeyboardButton("🤖 Adicionar ao seu Grupo", url=f"https://t.me/{context.bot.username}?startgroup=true")]
        ]
        if DONO_ID and str(user_id) == str(DONO_ID):
            botoes_voltar.insert(3, [InlineKeyboardButton("🛠️ Painel do Dono (Deploy)", callback_data="menu_dono")])

        await query.message.edit_text(texto_ajuda, reply_markup=InlineKeyboardMarkup(botoes_voltar), parse_mode="Markdown")

def main():
    threading.Thread(target=run_web, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()

    from telegram.ext import ApplicationHandlerStop

    # Interceptador global rodando em group=-1 pegando textos, comandos e mídias
    app.add_handler(MessageHandler((filters.TEXT | filters.COMMAND | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Sticker.ALL) & ~filters.ChatType.PRIVATE, interceptador_geral_protecoes), group=-1)

    app.add_handler(TypeHandler(Update, interceptador_estatisticas), group=3)

    from comandos.ping import registrar_ping
    from comandos.id import registrar_id
    from comandos.perfil import registrar_perfil
    from comandos.ban import registrar_ban
    from comandos.mutar import registrar_mutar
    from comandos.bemvindo import registrar_comandos_bv
    from comandos.promover import registrar_promover
    from comandos.marcar import registrar_marcar, capturar_membros_handler, remover_membro_saiu_handler
    from comandos.citar import registrar_citar
    from protecao.status import registrar_protecoes
    from comandos.play import setup_play
    from comandos.deploy import registrar_deploy
    from comandos.rank import registrar_rank
    from comandos.figurinha import registrar_figurinha
    from comandos.aluguel import registrar_aluguel

    from comandos.jogos.velha import setup_velha
    from comandos.jogos.memoria import setup_memoria
    from comandos.jogos.dama import setup_dama
    from comandos.jogos.xadrez import setup_xadrez

    setup_velha(app)
    setup_memoria(app)
    setup_dama(app)
    setup_xadrez(app)
    
    registrar_figurinha(app)
    registrar_promover(app)
    registrar_rank(app)
    registrar_marcar(app)
    registrar_citar(app)
    registrar_protecoes(app)
    registrar_comandos_bv(app)
    registrar_ping(app)
    registrar_id(app)
    registrar_perfil(app)
    registrar_ban(app)
    setup_play(app)
    registrar_mutar(app)
    registrar_deploy(app)
    registrar_aluguel(app)

    app.add_handler(CommandHandler("lw", cmd_registrar_aluguel_dono))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, capturar_membros_handler), group=2)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & ~filters.ChatType.PRIVATE, capturar_membros_handler), group=2)
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER & ~filters.ChatType.PRIVATE, remover_membro_saiu_handler), group=3)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("🤖 Bot rodando com alta performance e módulos separados!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
