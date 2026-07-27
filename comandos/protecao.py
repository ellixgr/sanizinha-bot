import time
import re
from datetime import timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

# Dicionários de estado por chat_id
CONFIGS_PROTECAO = {}
CONFIGS_PUNICAO = {}
REGISTRO_FLOOD = {}
REGISTRO_AVISADOS = {}

def obter_configs(chat_id: int):
    if chat_id not in CONFIGS_PROTECAO:
        CONFIGS_PROTECAO[chat_id] = {
            "antilink": False,
            "antifoto": False,
            "antifigu": False,
            "antitravas": False,
            "antiflood": True
        }
    return CONFIGS_PROTECAO[chat_id]

def obter_punicao(chat_id: int):
    if chat_id not in CONFIGS_PUNICAO:
        CONFIGS_PUNICAO[chat_id] = {
            "acao": "aviso_ban",  # Opções: "aviso_ban", "remover", "silenciar"
            "apagar_msg": True,   # Apagar a mensagem infratora
            "tempo_mute": 1       # Corrigido: chave com aspas corretas
        }
    return CONFIGS_PUNICAO[chat_id]

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
        [InlineKeyboardButton("⚙️ Configurar Punição", callback_data="menu_config_punicao")],
        [InlineKeyboardButton("🔙 Voltar ao Menu ADM", callback_data="menu_adm")]
    ])

    if query:
        await query.answer()
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def enviar_painel_punicao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(update, context, user_id, chat_id):
        await query.answer("⚠️ Apenas administradores podem configurar punições!", show_alert=True)
        return

    punicao = obter_punicao(chat_id)

    acoes_nomes = {
        "aviso_ban": "⚠️ 1º Aviso, 2º Banimento",
        "remover": "🔨 Remover / Banir Direto",
        "silenciar": "🔇 Silenciar (Mute)"
    }
    nome_acao_atual = acoes_nomes.get(punicao["acao"], "⚠️ 1º Aviso, 2º Banimento")
    status_apagar = "🟢 Sim" if punicao["apagar_msg"] else "🔴 Não"
    tempo_str = f"{punicao['tempo_mute']} minuto(s)"

    texto = (
        f"⚙️ **CONFIGURAR PUNIÇÃO DAS PROTEÇÕES**\n\n"
        f"Defina o que o bot deve fazer quando um membro violar as regras de segurança:\n\n"
        f"📌 **Tipo de Punição:** `{nome_acao_atual}`\n"
        f"🗑️ **Apagar Mensagem Infratora:** `{status_apagar}`\n"
        f"⏱️ **Tempo de Silenciamento:** `{tempo_str}` (Aplicado se o modo Mute estiver ativo)"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📌 Tipo: {nome_acao_atual}", callback_data="pun_trocar_acao")],
        [InlineKeyboardButton(f"🗑️ Apagar Msg: {status_apagar}", callback_data="pun_toggle_apagar")],
        [
            InlineKeyboardButton("➖ Menos", callback_data="pun_tempo_menos"),
            InlineKeyboardButton(f"⏱️ {punicao['tempo_mute']} min", callback_data="pun_ignorar"),
            InlineKeyboardButton("➕ Mais", callback_data="pun_tempo_mais")
        ],
        [InlineKeyboardButton("🔙 Voltar às Proteções", callback_data="menu_protecoes")]
    ])

    await query.answer()
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def processar_callback_protecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(update, context, user_id, chat_id):
        await query.answer("⚠️ Apenas administradores podem alterar as configurações!", show_alert=True)
        return

    data = query.data

    if data.startswith("prot_toggle_"):
        acao = data.replace("prot_toggle_", "")
        cfg = obter_configs(chat_id)
        if acao in cfg:
            cfg[acao] = not cfg[acao]
            await query.answer("Status alterado com sucesso!")
            await enviar_painel_protecoes(update, context)

    elif data == "menu_config_punicao":
        await enviar_painel_punicao(update, context)

    elif data == "menu_protecoes":
        await enviar_painel_protecoes(update, context)

    elif data == "pun_toggle_apagar":
        p = obter_punicao(chat_id)
        p["apagar_msg"] = not p["apagar_msg"]
        await query.answer("Configuração alterada!")
        await enviar_painel_punicao(update, context)

    elif data == "pun_trocar_acao":
        p = obter_punicao(chat_id)
        ciclo = {"aviso_ban": "remover", "remover": "silenciar", "silenciar": "aviso_ban"}
        p["acao"] = ciclo.get(p["acao"], "aviso_ban")
        await query.answer("Modo de punição alterado!")
        await enviar_painel_punicao(update, context)

    elif data == "pun_tempo_menos":
        p = obter_punicao(chat_id)
        if p["tempo_mute"] > 1:
            p["tempo_mute"] -= 1
            await query.answer(f"Tempo reduzido para {p['tempo_mute']} min")
        else:
            await query.answer("O tempo mínimo é 1 minuto!", show_alert=False)
        await enviar_painel_punicao(update, context)

    elif data == "pun_tempo_mais":
        p = obter_punicao(chat_id)
        if p["tempo_mute"] < 1440:
            p["tempo_mute"] += 1
            await query.answer(f"Tempo aumentado para {p['tempo_mute']} min")
        else:
            await query.answer("O tempo máximo é 1440 minutos!", show_alert=False)
        await enviar_painel_punicao(update, context)

    elif data == "pun_ignorar":
        await query.answer("Use os botões ➕ e ➖ para ajustar.", show_alert=False)

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

    # Administradores são imunes
    if await is_admin(update, context, user.id, chat.id):
        return

    cfg = obter_configs(chat.id)
    punicao = obter_punicao(chat.id)
    texto_conteudo = message.text or message.caption or ""
    violacao_detectada = None
    motivo_violacao = ""
    eh_flood = False

    # 1. Verificação de Anti-Flood (Mensagens e comandos em massa rápidos)
    if cfg["antiflood"]:
        agora = time.time()
        chave = (chat.id, user.id)
        if chave not in REGISTRO_FLOOD:
            REGISTRO_FLOOD[chave] = []
        
        REGISTRO_FLOOD[chave] = [t for t in REGISTRO_FLOOD[chave] if agora - t < 5]
        REGISTRO_FLOOD[chave].append(agora)

        if len(REGISTRO_FLOOD[chave]) > 3:  # Mais de 3 msgs em 5 segundos = Flood
            eh_flood = True
            violacao_detectada = True
            motivo_violacao = "flood de mensagens/comandos"

    # 2. Demais proteções se não for flood
    if not eh_flood:
        # Anti-Link corrigido para pegar links normais, t.me, @canais e domínios com segurança
        if cfg["antilink"]:
            # Ignora comando /start direcionado ao próprio bot
            ignorar_chatbot = f"@{context.bot.username}" in texto_conteudo and message.text and message.text.startswith("/start")
            if not ignorar_chatbot:
                padrao_link = r"(https?://\S+|t\.me/\S+|www\.\S+|@[A-Za-z0-9_]{5,}|tg://\S+)"
                if message.forward_origin or re.search(padrao_link, texto_conteudo, re.IGNORECASE):
                    violacao_detectada = True
                    motivo_violacao = "link, canal ou menção externa"

        if not violacao_detectada and cfg["antifoto"] and message.photo:
            violacao_detectada = True
            motivo_violacao = "foto"

        if not violacao_detectada and cfg["antifigu"] and message.sticker:
            violacao_detectada = True
            motivo_violacao = "figurinha"

        if not violacao_detectada and cfg["antitravas"] and len(texto_conteudo) > 600:
            violacao_detectada = True
            motivo_violacao = "trava de caracteres / golpe em massa"

    if violacao_detectada:
        # Apaga a mensagem se configurado
        if punicao["apagar_msg"]:
            try:
                await message.delete()
            except Exception:
                pass

        chave_aviso = (chat.id, user.id)

        # Se for Flood, aplica o tempo configurado no painel de punição
        if eh_flood:
            try:
                liberar_ate = timedelta(minutes=punicao["tempo_mute"])
                await chat.restrict_member(user.id, permissions=False, until_date=liberar_ate)
            except Exception:
                pass

            aviso = await chat.send_message(
                f"⚠️ {user.mention_html()}, você foi silenciado por **{punicao['tempo_mute']} minuto(s)** devido a flood!",
                parse_mode="HTML"
            )
            context.job_queue.run_once(apagar_aviso_futuro, 8, data=aviso)
            return

        # Aplica a punição escolhida pelo ADM no painel geral
        tipo_acao = punicao["acao"]

        if tipo_acao == "remover":
            try:
                await chat.ban_member(user.id)
                aviso = await chat.send_message(
                    f"🚨 {user.mention_html()} foi banido por enviar {motivo_violacao}.",
                    parse_mode="HTML"
                )
                context.job_queue.run_once(apagar_aviso_futuro, 8, data=aviso)
            except Exception:
                pass

        elif tipo_acao == "silenciar":
            try:
                liberar_ate = timedelta(minutes=punicao["tempo_mute"])
                await chat.restrict_member(user.id, permissions=False, until_date=liberar_ate)
                aviso = await chat.send_message(
                    f"🔇 {user.mention_html()} foi silenciado por **{punicao['tempo_mute']} minuto(s)** por enviar {motivo_violacao}.",
                    parse_mode="HTML"
                )
                context.job_queue.run_once(apagar_aviso_futuro, 8, data=aviso)
            except Exception:
                pass

        else:  # Modo padrão: "aviso_ban" (1º aviso, reincidente bane)
            if chave_aviso not in REGISTRO_AVISADOS:
                REGISTRO_AVISADOS[chave_aviso] = True
                aviso = await chat.send_message(
                    f"⚠️ {user.mention_html()}, não pode mandar {motivo_violacao}! "
                    f"Este foi o primeiro e último aviso, próxima você vai de Vasco kkkk",
                    parse_mode="HTML"
                )
                context.job_queue.run_once(apagar_aviso_futuro, 8, data=aviso)
            else:
                try:
                    await chat.ban_member(user.id)
                    aviso = await chat.send_message(
                        f"🚨 {user.mention_html()} foi de Vasco kkkk (Ignorou o aviso anterior e mandou {motivo_violacao} novamente).",
                        parse_mode="HTML"
                    )
                    context.job_queue.run_once(apagar_aviso_futuro, 8, data=aviso)
                except Exception:
                    pass

async def apagar_aviso_futuro(context):
    try:
        await context.job.data.delete()
    except Exception:
        pass

def registrar_protecoes(app):
    app.add_handler(CommandHandler("protecao", cmd_protecao))
    app.add_handler(MessageHandler(
        ~filters.StatusUpdate.ALL, 
        monitorar_seguranca
    ), group=2)
