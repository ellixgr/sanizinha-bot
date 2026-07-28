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

# Conexão otimizada e reaproveitável com MongoDB para acelerar queries
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

# --- COMANDO /lw PARA O DONO REGISTRAR O GRUPO COMO ALUGADO ---
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

# --- FUNÇÃO DE VALIDAÇÃO DE LICENÇA DO GRUPO ---
async def verificar_licenca_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    
    if not chat or chat.type == "private":
        return True

    if DONO_ID and user and str(user.id) == str(DONO_ID):
        return True

    db = get_db()
    agora = time.time()

    chat_registrado = db["grupos_autorizados"].find_one({
        "chat_id": chat.id,
        "ativo": True,
        "expira_em": {"$gt": agora}
    }, {"_id": 1})
    if chat_registrado:
        return True

    licenca = db["licencas_aluguel"].find_one({
        "chat_id": chat.id,
        "ativo": True,
        "expira_em": {"$gt": agora}
    }, {"_id": 1})
    if licenca:
        return True

    controle_aviso = db["avisos_grupos_piratas"].find_one({"chat_id": chat.id}) or {"avisos": 0, "ultimo_aviso": 0}
    
    if agora - controle_aviso.get("ultimo_aviso", 0) > 60:
        novos_avisos = controle_aviso.get("avisos", 0) + 1
        db["avisos_grupos_piratas"].update_one(
            {"chat_id": chat.id},
            {"$set": {"avisos": novos_avisos, "ultimo_aviso": agora}},
            upsert=True
        )
        
        link_privado = f"https://t.me/{context.bot.username}?start=aluguel"
        teclado_assinar = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Assinar Plano no Privado", url=link_privado)]
        ])
        
        try:
            if novos_avisos >= 5:
                await chat.send_message(
                    "🚨 **Limite de Avisos Atingidos!**\nEste grupo não possui aluguel ativo e os 5 avisos esgotaram. O bot está se retirando do grupo.",
                    parse_mode="Markdown"
                )
                await context.bot.leave_chat(chat.id)
                db["avisos_grupos_piratas"].delete_one({"chat_id": chat.id})
            else:
                await chat.send_message(
                    f"⚠️ **Aviso ({novos_avisos}/5):** Este grupo não possui um aluguel ativo!\nPara o bot funcionar aqui, o responsável precisa assinar o plano:",
                    reply_markup=teclado_assinar,
                    parse_mode="Markdown"
                )
        except Exception:
            pass
            
    return False

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

async def interceptador_estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    if chat.type in ["group", "supergroup"]:
        valido = await verificar_licenca_grupo(update, context)
        if not valido:
            return 

    message = update.message
    if not message:
        return

    if chat.type == "private":
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

    if chat.type in ["group", "supergroup"]:
        valido = await verificar_licenca_grupo(update, context)
        if not valido:
            return

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
    
    if chat and chat.type in ["group", "supergroup"]:
        db = get_db()
        agora = time.time()
        chat_registrado = db["grupos_autorizados"].find_one({"chat_id": chat.id, "expira_em": {"$gt": agora}}, {"_id": 1})
        if not chat_registrado and (not DONO_ID or str(user_id) != str(DONO_ID)):
            await query.answer("❌ Este grupo não possui aluguel ativo!", show_alert=True)
            return

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
            "⚙️ `/protecao` - Configura as travas de segurança\n"
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
            from comandos.protecao import enviar_painel_protecoes
            update.callback_query = query
            await enviar_painel_protecoes(update, context)
        except Exception as e:
            await query.message.reply_text(f"⚠️ Erro ao abrir o painel de proteções: {e}")

    elif query.data.startswith("prot_"):
        if not await verificar_se_e_adm(update, context):
            await query.answer("⚠️ Apenas administradores podem alterar as proteções!", show_alert=True)
            return
        try:
            from comandos.protecao import processar_callback_protecao
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
    
    # Configuração de performance com connection pools e threads ajustadas
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()

    app.add_handler(TypeHandler(Update, interceptador_estatisticas), group=-1)

    from comandos.ping import registrar_ping
    from comandos.id import registrar_id
    from comandos.perfil import registrar_perfil
    from comandos.ban import registrar_ban
    from comandos.mutar import registrar_mutar
    from comandos.bemvindo import registrar_comandos_bv
    from comandos.promover import registrar_promover
    from comandos.marcar import registrar_marcar, capturar_membros_handler, remover_membro_saiu_handler
    from comandos.citar import registrar_citar
    from comandos.protecao import registrar_protecoes
    from comandos.play import setup_play
    from comandos.deploy import registrar_deploy
    from comandos.rank import registrar_rank
    from comandos.figurinha import registrar_figurinha
    from comandos.aluguel import registrar_aluguel

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
