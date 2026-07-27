import time
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

# Dicionários de estado por chat_id
# Antiflood vem ligado por padrão (True), as outras começam desligadas (False)
CONFIGS_PROTECAO = {}
REGISTRO_FLOOD = {}

def obter_configs(chat_id: int):
    if chat_id not in CONFIGS_PROTECAO:
        CONFIGS_PROTECAO[chat_id] = {
            "antilink": False,
            "antifoto": False,
            "antifigu": False,
            "antitravas": False,
            "antiflood": True  # Sempre começa ligada por segurança
        }
    return CONFIGS_PROTECAO[chat_id]

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int) -> bool:
    if chat_id > 0:  # Chat privado
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ["creator", "administrator"]:
            return True
    except Exception:
        pass
    return False

async def enviar_painel_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(update, context, user_id, chat_id):
        if query:
            await query.answer("⚠️ Apenas administradores podem mexer nas proteções!", show_alert=True)
        return

    cfg = obter_configs(chat_id)

    s_link = "🟢 Ligado" if cfg["antilink"] else "🔴 Desligado"
    s_foto = "🟢 Ligado" if cfg["antifoto"] else "🔴 Desligado"
    s_figu = "🟢 Ligado" if cfg["antifigu"] else "🔴 Desligado"
    s_trav = "🟢 Ligado" if cfg["antitravas"] else "🔴 Desligado"
    s_flood = "🟢 Ligado" if cfg["antiflood"] else "🔴 Desligado"

    texto = (
        f"🛡️ **PAINEL DE PROTEÇÕES DO GRUPO**\n\n"
        f"Gerencie os sistemas de segurança e bloqueio abaixo. Apenas administradores podem alterar estes ajustes.\n\n"
        f"🔗 **Anti-Link/Grupos/Canais:** `{s_link}`\n"
        f"📸 **Anti-Foto:** `{s_foto}`\n"
        f"🖼️ **Anti-Figurinha:** `{s_figu}`\n"
        f"⚠️ **Anti-Travas/Golpes (Caracteres):** `{s_trav}`\n"
        f"⚡ **Anti-Flood (Spam):** `{s_flood}`"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔗 Anti-Link: {s_link}", callback_data="prot_toggle_antilink")],
        [InlineKeyboardButton(f"📸 Anti-Foto: {s_foto}", callback_data="prot_toggle_antifoto")],
        [InlineKeyboardButton(f"🖼️ Anti-Figurinha: {s_figu}", callback_data="prot_toggle_antifigu")],
        [InlineKeyboardButton(f"⚠️ Anti-Travas: {s_trav}", callback_data="prot_toggle_antitravas")],
        [InlineKeyboardButton(f"⚡ Anti-Flood: {s_flood}", callback_data="prot_toggle_antiflood")],
        [InlineKeyboardButton("🔙 Voltar ao Menu ADM", callback_data="menu_adm")]
    ])

    if query:
        await query.answer()
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def processar_callback_protecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(update, context, user_id, chat_id):
        await query.answer("⚠️ Apenas administradores podem alterar as proteções!", show_alert=True)
        return

    acao = query.data.replace("prot_toggle_", "")
    cfg = obter_configs(chat_id)

    if acao in cfg:
        cfg[acao] = not cfg[acao]
        await query.answer(f"Status alterado com sucesso!")
        await enviar_painel_protecoes(update, context)

async def cmd_protecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if chat_id > 0:
        await update.message.reply_text("⚠️ Este comando só pode ser usado em grupos.")
        return
    if not await is_admin(update, context, user_id, chat_id):
        await update.message.reply_text("⚠️ Apenas administradores podem usar este comando.")
        return
    await enviar_painel_protecoes(update, context)

async def monitorar_seguranca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    message = update.message

    if not chat or not user or chat.type == "private":
        return

    # Se for admin, o bot não bloqueia nada dele
    if await is_admin(update, context, user.id, chat.id):
        return

    cfg = obter_configs(chat.id)
    texto_conteudo = message.text or message.caption or ""
    violacao_detectada = None
    motivo_violacao = ""

    # 1. Anti-Link / Canais / Grupos / Menções / Encaminhamentos
    if cfg["antilink"]:
        # Verifica se encaminhou de canal/grupo ou se tem link/t.me/menções
        padrao_link = r"(https?://\S+|t\.me/\S+|www\.\S+|@\w+|tg://\S+)"
        if message.forward_origin or re.search(padrao_link, texto_conteudo, re.IGNORECASE):
            violacao_detectada = True
            motivo_violacao = "link, canal ou menção externa"

    # 2. Anti-Foto
    if not violacao_detectada and cfg["antifoto"] and message.photo:
        violacao_detectada = True
        motivo_violacao = "foto"

    # 3. Anti-Figurinha
    if not violacao_detectada and cfg["antifigu"] and message.sticker:
        violacao_detectada = True
        motivo_violacao = "figurinha"

    # 4. Anti-Travas / Golpes (muitos caracteres / caracteres estranhos em excesso)
    if not violacao_detectada and cfg["antitravas"] and len(texto_conteudo) > 600:
        violacao_detectada = True
        motivo_violacao = "trava de caracteres / golpe em massa"

    # 5. Anti-Flood
    if not violacao_detectada and cfg["antiflood"]:
        agora = time.time()
        chave = (chat.id, user.id)
        if chave not in REGISTRO_FLOOD:
            REGISTRO_FLOOD[chave] = []
        
        # Limpa mensagens com mais de 5 segundos
        REGISTRO_FLOOD[chave] = [t for t in REGISTRO_FLOOD[chave] if agora - t < 5]
        REGISTRO_FLOOD[chave].append(agora)

        if len(REGISTRO_FLOOD[chave]) > 4:  # Mais de 4 mensagens/comandos em 5 segundos = Flood
            violacao_detectada = True
            motivo_violacao = "flood de mensagens"

    # Se houve infração, apaga e envia o aviso exato solicitado
    if violacao_detectada:
        try:
            await message.delete()
        except Exception:
            pass

        aviso = await chat.send_message(
            f"⚠️ {user.mention_html()}, não pode mandar {motivo_violacao}! "
            f"Este foi o primeiro e último aviso, próxima você vai de Vasco kkkk",
            parse_mode="HTML"
        )
        
        # Opcional: apagar o aviso do bot após 8 segundos para não lotar o chat
        context.job_queue.run_once(apagar_aviso_futuro, 8, data=aviso)

async def apagar_aviso_futuro(context):
    try:
        await context.job.data.delete()
    except Exception:
        pass

def registrar_protecoes(app):
    app.add_handler(CommandHandler("protecao", cmd_protecao))
    app.add_handler(MessageHandler(
        ~filters.COMMAND & ~filters.StatusUpdate.ALL, 
        monitorar_seguranca
    ), group=2)
