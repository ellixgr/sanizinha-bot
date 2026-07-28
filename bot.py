import os
import logging
import threading
import time
from flask import Flask
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, TypeHandler, ContextTypes, filters, MessageHandler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
DONO_ID = os.environ.get("DONO_ID")

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot online e operacional!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

def get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
    return client["sanizinhabot_db"]

# --- FUNÇÃO DE VALIDAÇÃO DE LICENÇA DO GRUPO ---
async def verificar_licenca_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    
    if not chat or chat.type == "private":
        return True

    # Se for o dono do bot, libera automático
    if DONO_ID and user and str(user.id) == str(DONO_ID):
        return True

    db = get_db()
    agora = time.time()

    # Verifica se o grupo está registrado em alguma licença ativa e válida de algum usuário
    licenca = db["licencas_aluguel"].find_one({
        "chat_id": chat.id,
        "ativo": True,
        "expira_em": {"$gt": agora}
    })

    # Alternativa: se a licença for salva por usuário, checa se há pelo menos uma licença válida no bot ou ligada ao criador
    if not licenca:
        # Verifica se o bot tem qualquer licença global ativa associada ao grupo
        licenca_geral = db["licencas_aluguel"].find_one({
            "ativo": True,
            "expira_em": {"$gt": agora}
        })
        # Se quiser travar estritamente pelo chat_id vinculado ao pagamento:
        chat_registrado = db["grupos_autorizados"].find_one({"chat_id": chat.id, "expira_em": {"$gt": agora}})
        if chat_registrado:
            return True
        
        # Sistema de controle de avisos (Máximo 5 avisos, 1 minuto de intervalo)
        controle_aviso = db["avisos_grupos_piratas"].find_one({"chat_id": chat.id}) or {"avisos": 0, "ultimo_aviso": 0}
        
        if agora - controle_aviso.get("ultimo_aviso", 0) > 60: # Intervalo de 1 minuto
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

    return True

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

    # Bloqueia grupos sem licença antes de processar qualquer coisa
    if chat.type in ["group", "supergroup"]:
        valido = await verificar_licenca_grupo(update, context)
        if not valido:
            return # <--- APENAS PARA A EXECUÇÃO SEM MATAR O BOTECO 


    message = update.message
    if not message:
        return

    username_str = f"@{user.username}" if user.username else user.first_name

    if chat.type == "private":
        logger.info(
            f"\n__________________\n"
            f"Tipo : Privado\n"
            f"Usuário : {username_str} (ID: {user.id})\n"
            f"Msg : {message.text or '[Mídia/Outro]'}\n"
            f"__________________"
        )
    elif chat.type in ["group", "supergroup"]:
        logger.info(
            f"\n__________________\n"
            f"Grupo : {chat.title} (ID: {chat.id})\n"
            f"Usuário : {username_str} (ID: {user.id})\n"
            f"Msg : {message.text or '[Mídia/Outro]'}\n"
            f"__________________"
        )

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

    botoes = [
        [InlineKeyboardButton("📜 Ver todos comandos de membros", callback_data="menu_membros")],
        [InlineKeyboardButton("🛡️ Ver todos comandos de ADM", callback_data="menu_adm")],
        [InlineKeyboardButton("🤖 Alugar Bot", callback_data="menu_aluguel")],
        [InlineKeyboardButton("🏓 Ping do Bot", callback_data="botao_ping")],
        [InlineKeyboardButton("🤖 Adicionar ao seu Grupo", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ]

    if DONO_ID and str(user.id) == str(DONO_ID):
        botoes.insert(3, [InlineKeyboardButton("🛠️ Painel do Dono (Deploy)", callback_data="menu_dono")])

    teclado_painel = InlineKeyboardMarkup(botoes)

    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            f"🔥 **Eae, {user.first_name}!** O bot está ativo neste grupo.\nEscolha uma das categorias abaixo para ver os comandos:",
            reply_markup=teclado_painel,
            parse_mode="Markdown"
        )
        return
    
    await update.message.reply_text(
        f"🔥 **Eae, {user.first_name}!** Escolha o que deseja fazer abaixo:",
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
        chat_registrado = db["grupos_autorizados"].find_one({"chat_id": chat.id, "expira_em": {"$gt": agora}})
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
        teclado_voltar = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]
        ])
        await query.message.edit_text(texto_membros, reply_markup=teclado_voltar, parse_mode="Markdown")
        
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

    elif query.data == "voltar_menu" or query.data == "ver_comandos" or query.data == "voltar_principal_grupo":
        await query.answer()
        botoes_voltar = [
            [InlineKeyboardButton("📜 Ver todos comandos de membros", callback_data="menu_membros")],
            [InlineKeyboardButton("🛡️ Ver todos comandos de ADM", callback_data="menu_adm")],
            [InlineKeyboardButton("🤖 Alugar Bot", callback_data="menu_aluguel")],
            [InlineKeyboardButton("🏓 Ping do Bot", callback_data="botao_ping")],
            [InlineKeyboardButton("🤖 Adicionar ao seu Grupo", url=f"https://t.me/{context.bot.username}?startgroup=true")]
        ]
        if DONO_ID and str(user_id) == str(DONO_ID):
            botoes_voltar.insert(3, [InlineKeyboardButton("🛠️ Painel do Dono (Deploy)", callback_data="menu_dono")])

        texto_ajuda = (
            "🔥 **Painel Principal:**\n"
            "Escolha uma das categorias abaixo:"
        )
        await query.message.edit_text(texto_ajuda, reply_markup=InlineKeyboardMarkup(botoes_voltar), parse_mode="Markdown")

def main():
    threading.Thread(target=run_web, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

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

    app.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, capturar_membros_handler), group=2)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & ~filters.ChatType.PRIVATE, capturar_membros_handler), group=2)
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER & ~filters.ChatType.PRIVATE, remover_membro_saiu_handler), group=3)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("🤖 Bot rodando com sucesso e módulos separados!")
    app.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    main()
