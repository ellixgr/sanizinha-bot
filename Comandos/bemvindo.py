import os
import re
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

logger = logging.getLogger("SanizinhaBot.BemVindo")

# Estruturas de dados em memória por chat_id
TEXTOS_BV = {}
MIDIAS_BV = {}
BOTOES_BV = {}
STATUS_BV = {}  
ESTADOS_FLUXO = {} 

def registrar_comandos_bv(app: Application):
    registrar_captura_fluxo(app)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & ~filters.ChatType.PRIVATE, boas_vindas_handler))

    app.add_handler(CommandHandler("bemvindo", cmd_bem_vindo_painel, filters=~filters.ChatType.PRIVATE))
    
    app.add_handler(CallbackQueryHandler(cb_edit_texto, pattern=r"^bv_edit_texto_"))
    app.add_handler(CallbackQueryHandler(cb_ver_texto, pattern=r"^bv_ver_texto_"))
    app.add_handler(CallbackQueryHandler(cb_rem_texto, pattern=r"^bv_remover_texto_"))
    app.add_handler(CallbackQueryHandler(cb_edit_midia, pattern=r"^bv_edit_midia_"))
    app.add_handler(CallbackQueryHandler(cb_ver_midia, pattern=r"^bv_ver_midia_"))
    app.add_handler(CallbackQueryHandler(cb_rem_midia, pattern=r"^bv_remover_midia_"))
    app.add_handler(CallbackQueryHandler(cb_edit_botoes, pattern=r"^bv_edit_botoes_"))
    app.add_handler(CallbackQueryHandler(cb_ver_botoes, pattern=r"^bv_ver_botoes_"))
    app.add_handler(CallbackQueryHandler(cb_rem_botoes, pattern=r"^bv_remover_botoes_"))
    app.add_handler(CallbackQueryHandler(cb_ver_completa, pattern=r"^bv_ver_completa_"))
    app.add_handler(CallbackQueryHandler(cb_toggle_status, pattern=r"^bv_toggle_status_"))
    app.add_handler(CallbackQueryHandler(cb_toggle_visual, pattern=r"^bv_toggle_visual_"))
    app.add_handler(CallbackQueryHandler(cb_cancelar, pattern=r"^bv_cancelar_"))

async def is_user_admin(update_or_client, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE = None) -> bool:
    try:
        if chat_id > 0:
            return True
        if context:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ["creator", "administrator"]:
                return True
    except Exception:
        pass
    return False

async def verificar_permissao_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_user_admin(update, chat_id, user_id, context):
        await update.callback_query.answer("⚠️ Apenas administradores podem mexer nisso!", show_alert=True)
        return False
    return True

async def cmd_bem_vindo_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_user_admin(update, chat_id, user_id, context):
        await update.message.reply_text("⚠️ Apenas administradores podem configurar as boas-vindas!")
        return

    try:
        await update.message.delete()
    except Exception:
        pass

    await enviar_painel_principal_bv(context, chat_id, message=update.message)

async def cb_edit_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_edit_texto_bv(update, context)

async def cb_ver_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_ver_texto_bv(update, context)

async def cb_rem_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_remover_texto_bv(update, context)

async def cb_edit_midia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_edit_midia_bv(update, context)

async def cb_ver_midia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_ver_midia_bv(update, context)

async def cb_rem_midia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_remover_midia_bv(update, context)

async def cb_edit_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_edit_botoes_bv(update, context)

async def cb_ver_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_ver_botoes_bv(update, context)

async def cb_rem_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_remover_botoes_bv(update, context)

async def cb_ver_completa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_ver_completa_bv(update, context)

async def cb_toggle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_toggle_status_bv(update, context)

async def cb_toggle_visual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    chat_id = update.effective_chat.id
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra="Modo visual alterado!")
    await update.callback_query.answer("Visual atualizado!")

async def cb_painel_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_painel_bv(update, context)

async def cb_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_cancelar_bv(update, context)

# --- PAINEL PRINCIPAL ---
async def enviar_painel_principal_bv(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message=None, query=None, painel_msg_id: int = None, aviso_extra: str = None):
    tem_texto = chat_id in TEXTOS_BV and bool(TEXTOS_BV[chat_id])
    tem_midia = chat_id in MIDIAS_BV and bool(MIDIAS_BV[chat_id])
    tem_botoes = chat_id in BOTOES_BV and bool(BOTOES_BV[chat_id])
    
    status_atual = STATUS_BV.get(chat_id, True)

    txt_status = "✅" if tem_texto else "❌"
    mid_status = "✅" if tem_midia else "❌"
    bot_status = "✅" if tem_botoes else "❌"
    
    status_texto_painel = "🟢 Ativado" if status_atual else "🔴 Desativado"

    cabecalho = f"✅ **{aviso_extra}**\n\n" if aviso_extra else ""

    texto_painel = (
        f"{cabecalho}"
        f"💬 **Mensagem de boas-vindas** (Status: {status_texto_painel})\n\n"
        f"📄 Texto {txt_status}\n"
        f"🎞️ Mídias {mid_status}\n"
        f"🔲 Botões de Url {bot_status}\n\n"
        "👉 **Use os botões abaixo para escolher o que você deseja definir**"
    )

    if status_atual:
        botao_status = InlineKeyboardButton("🔴 Desativar boas-vindas", callback_data=f"bv_toggle_status_{chat_id}")
    else:
        botao_status = InlineKeyboardButton("🟢 Ativar boas-vindas", callback_data=f"bv_toggle_status_{chat_id}")

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Texto", callback_data=f"bv_edit_texto_{chat_id}"), InlineKeyboardButton("👀 Veja", callback_data=f"bv_ver_texto_{chat_id}")],
        [InlineKeyboardButton("🎞️ Mídias", callback_data=f"bv_edit_midia_{chat_id}"), InlineKeyboardButton("👀 Veja", callback_data=f"bv_ver_midia_{chat_id}")],
        [InlineKeyboardButton("🔲 Botões de Url", callback_data=f"bv_edit_botoes_{chat_id}"), InlineKeyboardButton("👀 Veja", callback_data=f"bv_ver_botoes_{chat_id}")],
        [botao_status],
        [InlineKeyboardButton("🖼️ Definir como visualização ✅", callback_data=f"bv_toggle_visual_{chat_id}")],
        [InlineKeyboardButton("👀 Visualização completa", callback_data=f"bv_ver_completa_{chat_id}")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="cmd_adm")]
    ])

    if query:
        try:
            await query.edit_message_text(texto_painel, reply_markup=teclado, parse_mode="Markdown")
        except Exception:
            await query.message.reply_text(texto_painel, reply_markup=teclado, parse_mode="Markdown")
    elif painel_msg_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=painel_msg_id, text=texto_painel, reply_markup=teclado, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=texto_painel, reply_markup=teclado, parse_mode="Markdown")
    elif message:
        await message.reply_text(texto_painel, reply_markup=teclado, parse_mode="Markdown")

# --- CAPTURA DE FLUXO E DISPAROS ---

def registrar_captura_fluxo(app: Application):
    async def capturar_fluxo_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        if not message or not message.from_user:
            return

        chat_id = message.chat.id
        user_id = message.from_user.id
        chave_fluxo = (chat_id, user_id)

        if chave_fluxo not in ESTADOS_FLUXO:
            return

        if not await is_user_admin(update, chat_id, user_id, context):
            ESTADOS_FLUXO.pop(chave_fluxo, None)
            await message.reply_text("⚠️ Apenas administradores podem configurar as boas-vindas!")
            return

        estado_info = ESTADOS_FLUXO.pop(chave_fluxo, None)
        if not estado_info:
            return

        estado, painel_msg_id = estado_info

        if painel_msg_id:
            try:
                await context.bot.delete_message(chat_id, painel_msg_id)
            except Exception:
                pass

        if estado == "aguardando_texto_bv":
            texto = message.text or message.caption or ""
            TEXTOS_BV[chat_id] = texto
            await enviar_painel_principal_bv(context, chat_id, message=message, aviso_extra="Texto de boas-vindas configurado com sucesso!")

        elif estado == "aguardando_midia_bv":
            tipo = None
            file_id = None
            leg = message.caption or message.text or ""

            if message.photo:
                tipo = "photo"
                file_id = message.photo[-1].file_id
            elif message.video:
                tipo = "video"
                file_id = message.video.file_id
            elif message.sticker:
                tipo = "sticker"
                file_id = message.sticker.file_id
            else:
                return

            MIDIAS_BV[chat_id] = (tipo, file_id, leg)
            if leg and chat_id not in TEXTOS_BV:
                TEXTOS_BV[chat_id] = leg

            await enviar_painel_principal_bv(context, chat_id, message=message, aviso_extra="Mídia de boas-vindas configurada com sucesso!")

        elif estado == "aguardando_botoes_bv":
            if not message.text:
                return

            linhas_texto = message.text.split("\n")
            botoes_teclado = []

            for linha in linhas_texto:
                if not linha.strip():
                    continue
                partes_linha = linha.split("&&")
                linha_botoes = []
                for parte in partes_linha:
                    if "-" in parte:
                        titulo, acao = parte.split("-", 1)
                        titulo = titulo.strip()
                        acao = acao.strip()

                        if acao.startswith("popup:"):
                            popup_txt = acao.replace("popup:", "").strip()
                            linha_botoes.append(InlineKeyboardButton(titulo, callback_data=f"popup_msg_{popup_txt[:30]}"))
                        elif acao.startswith("alert:"):
                            alert_txt = acao.replace("alert:", "").strip()
                            linha_botoes.append(InlineKeyboardButton(titulo, callback_data=f"alert_msg_{alert_txt[:30]}"))
                        elif acao == "rules":
                            linha_botoes.append(InlineKeyboardButton(titulo, url="https://t.me/"))
                        elif acao.startswith("share:"):
                            share_txt = acao.replace("share:", "").strip()
                            linha_botoes.append(InlineKeyboardButton(titulo, url=f"https://t.me/share/url?url={share_txt}"))
                        elif acao.startswith("copy:"):
                            linha_botoes.append(InlineKeyboardButton(titulo, callback_data="btn_copy"))
                        else:
                            if not acao.startswith("http://") and not acao.startswith("https://") and not acao.startswith("t.me/"):
                                acao = "https://" + acao
                            linha_botoes.append(InlineKeyboardButton(titulo, url=acao))
                if linha_botoes:
                    botoes_teclado.append(linha_botoes)

            if botoes_teclado:
                BOTOES_BV[chat_id] = InlineKeyboardMarkup(botoes_teclado)
                await enviar_painel_principal_bv(context, chat_id, message=message, aviso_extra="Botões de boas-vindas configurados com sucesso!")

    app.add_handler(MessageHandler(~filters.COMMAND & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Sticker.ALL), capturar_fluxo_admin), group=1)

async def montar_texto_formatado(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user) -> str:
    try:
        chat_info = await context.bot.get_chat(chat_id)
        chat_title = chat_info.title if chat_info else "Grupo"
    except Exception:
        chat_title = "Grupo"

    agora = datetime.now()
    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    
    texto_base = TEXTOS_BV.get(chat_id, "Olá {MENTION}, seja bem-vindo(a) ao {GROUPNAME}!")

    formatacoes = {
        "{ID}": str(user.id),
        "{NAME}": user.first_name or "",
        "{SURNAME}": user.last_name or "",
        "{NAMESURNAME}": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "{LANG}": user.language_code or "pt",
        "{DATE}": agora.strftime("%d/%m/%Y"),
        "{TIME}": agora.strftime("%H:%M"),
        "{WEEKDAY}": dias_semana[agora.weekday()],
        "{MENTION}": user.mention_html(),
        "{USERNAME}": f"@{user.username}" if user.username else user.first_name,
        "{GROUPNAME}": chat_title,
        "{RULES}": "Consulte as regras fixadas no grupo."
    }

    for chave, valor in formatacoes.items():
        texto_base = texto_base.replace(chave, valor)

    return texto_base

async def enviar_mensagem_boas_vindas(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user):
    if not STATUS_BV.get(chat_id, True):
        return

    texto_final = await montar_texto_formatado(context, chat_id, user)
    botoes = BOTOES_BV.get(chat_id)
    midia = MIDIAS_BV.get(chat_id)

    try:
        if midia:
            tipo, file_id, _ = midia
            if tipo == "photo":
                await context.bot.send_photo(chat_id, file_id, caption=texto_final, reply_markup=botoes, parse_mode="HTML")
            elif tipo == "video":
                await context.bot.send_video(chat_id, file_id, caption=texto_final, reply_markup=botoes, parse_mode="HTML")
            elif tipo == "sticker":
                await context.bot.send_sticker(chat_id, file_id)
                if texto_final:
                    await context.bot.send_message(chat_id, texto_final, reply_markup=botoes, parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id, texto_final, reply_markup=botoes, parse_mode="HTML")
    except Exception as e:
        logger.error(f"[BOAS-VINDAS] Erro ao enviar mensagem para {chat_id}: {e}")

async def boas_vindas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not update.message.new_chat_members:
        return
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await enviar_mensagem_boas_vindas(context, chat_id, member)

# --- FUNÇÕES DE CALLBACK ---

async def callback_painel_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query)
    await update.callback_query.answer()

async def callback_toggle_status_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    status_atual = STATUS_BV.get(chat_id, True)
    
    novo_status = not status_atual
    STATUS_BV[chat_id] = novo_status
    
    aviso = "Boas-vindas ativadas com sucesso!" if novo_status else "Boas-vindas desativadas com sucesso!"
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra=aviso)
    await update.callback_query.answer(aviso)

async def callback_edit_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_texto_bv", update.callback_query.message.message_id)
    user_mention = update.callback_query.from_user.mention_html()
    texto_instrucao = (
        f"{user_mention}, agora envie a mensagem que você quer definir!\n\n"
        "Você pode usar HTML e:\n"
        "• `{ID}` = ID do usuário\n"
        "• `{NAME}` = nome do usuário\n"
        "• `{SURNAME}` = sobrenome do usuário\n"
        "• `{NAMESURNAME}` = nome e sobrenome do usuário\n"
        "• `{LANG}` = idioma do usuário\n"
        "• `{DATE}` = data de entrada\n"
        "• `{TIME}` = horário de entrada\n"
        "• `{WEEKDAY}` = dia da semana\n"
        "• `{MENTION}` = menção ao usuário\n"
        "• `{USERNAME}` = nome de usuário\n"
        "• `{GROUPNAME}` = nome do grupo\n"
        "• `{RULES}` = regras do grupo"
    )
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Remover mensagem", callback_data=f"bv_remover_texto_{chat_id}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data=f"bv_cancelar_{chat_id}")]
    ])
    await update.callback_query.message.edit_text(texto_instrucao, reply_markup=teclado, parse_mode="HTML")
    await update.callback_query.answer()

async def callback_ver_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    texto = TEXTOS_BV.get(chat_id, "Nenhum texto configurado.")
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data=f"bv_cancelar_{chat_id}")]])
    await update.callback_query.message.edit_text(f"📄 **Texto atual:**\n\n{texto}", reply_markup=teclado, parse_mode="Markdown")
    await update.callback_query.answer()

async def callback_remover_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in TEXTOS_BV:
        del TEXTOS_BV[chat_id]
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra="Texto de boas-vindas removido com sucesso!")

async def callback_edit_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_midia_bv", update.callback_query.message.message_id)
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Remover mídia", callback_data=f"bv_remover_midia_{chat_id}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data=f"bv_cancelar_{chat_id}")]
    ])
    await update.callback_query.message.edit_text(
        "👉 **Envie agora a mídia** (fotos, vídeos, sticker...) que você deseja definir.\n"
        "Envie apenas 1 item e ele será configurado na hora.",
        reply_markup=teclado
    )
    await update.callback_query.answer()

async def callback_ver_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in MIDIAS_BV:
        tipo, file_id, leg = MIDIAS_BV[chat_id]
        if tipo == "photo":
            await context.bot.send_photo(chat_id, file_id, caption=f"Legenda salva: {leg}")
        elif tipo == "video":
            await context.bot.send_video(chat_id, file_id, caption=f"Legenda salva: {leg}")
        elif tipo == "sticker":
            await context.bot.send_sticker(chat_id, file_id)
        await update.callback_query.answer()
    else:
        await update.callback_query.answer("Nenhuma mídia salva!", show_alert=True)

async def callback_remover_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in MIDIAS_BV:
        del MIDIAS_BV[chat_id]
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra="Mídia de boas-vindas removida com sucesso!")

async def callback_edit_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_botoes_bv", update.callback_query.message.message_id)
    texto_botoes_instrucao = (
        "👉 **Configure os botões** a serem colocados abaixo da mensagem\n"
        "Envie uma única mensagem estruturada da forma a seguir:\n\n"
        "• **Adicionar um único botão:**\n"
        "`Título do botão - t.me/LinkExemplar`\n\n"
        "• **Adicionar múltiplos botões em uma única linha:**\n"
        "`Título do botão - t.me/LinkExemplar && Título do botão - t.me/LinkExemplar`\n\n"
        "• **Adicionar múltiplas linhas de botões:**\n"
        "`Título do botão - t.me/LinkExemplar`\n"
        "`Título do botão - t.me/LinkExemplar`"
    )
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Remover botões", callback_data=f"bv_remover_botoes_{chat_id}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data=f"bv_cancelar_{chat_id}")]
    ])
    await update.callback_query.message.edit_text(texto_botoes_instrucao, reply_markup=teclado, parse_mode="Markdown")
    await update.callback_query.answer()

async def callback_ver_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in BOTOES_BV:
        await update.callback_query.message.reply_text("🔲 **Visualização dos botões salvos:**", reply_markup=BOTOES_BV[chat_id])
        await update.callback_query.answer()
    else:
        await update.callback_query.answer("Nenhum botão configurado!", show_alert=True)

async def callback_remover_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in BOTOES_BV:
        del BOTOES_BV[chat_id]
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra="Botões de boas-vindas removidos com sucesso!")

async def callback_ver_completa_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    await enviar_mensagem_boas_vindas(context, chat_id, user)
    await update.callback_query.answer("Pré-visualização enviada no chat!")

async def callback_cancelar_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO.pop((chat_id, user_id), None)
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query)
    await update.callback_query.answer("Operação cancelada.")
