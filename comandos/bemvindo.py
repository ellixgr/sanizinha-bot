import os
import re
import logging
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from pymongo import MongoClient

logger = logging.getLogger("SanizinhaBot.BemVindo")

MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
db = mongo_client["sanizinhabot_db"]
col_bemvindo = db["config_bem_vindo"]

FUSO_BR = timezone(timedelta(hours=-3))
ESTADOS_FLUXO = {}

# ✅ FUNÇÃO AUXILIAR DE PERMISSÃO
async def is_user_admin(update: Update, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        if chat_id > 0:
            return True
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ["creator", "administrator"]
    except Exception:
        return False

def carregar_dados_bv(chat_id: int):
    doc = col_bemvindo.find_one({"chat_id": chat_id})
    if not doc:
        return None, None, None, True
    texto = doc.get("texto")
    midia = doc.get("midia")
    if midia:
        midia = tuple(midia)
    botoes_raw = doc.get("botoes")
    botoes = None
    if botoes_raw:
        teclado_linhas = []
        for linha in botoes_raw:
            linha_botoes = []
            for b in linha:
                if "url" in b:
                    linha_botoes.append(InlineKeyboardButton(b["text"], url=b["url"]))
                elif "callback_data" in b:
                    linha_botoes.append(InlineKeyboardButton(b["text"], callback_data=b["callback_data"]))
            teclado_linhas.append(linha_botoes)
        botoes = InlineKeyboardMarkup(teclado_linhas)
    status = doc.get("status", True)
    return texto, midia, botoes, status

def salvar_no_mongo(chat_id: int, campo: str, valor):
    if campo == "botoes" and isinstance(valor, InlineKeyboardMarkup):
        serializavel = []
        for linha in valor.inline_keyboard:
            linha_s = []
            for b in linha:
                item = {"text": b.text}
                if b.url:
                    item["url"] = b.url
                elif b.callback_data:
                    item["callback_data"] = b.callback_data
                linha_s.append(item)
            serializavel.append(linha_s)
        valor = serializavel
    col_bemvindo.update_one({"chat_id": chat_id}, {"$set": {campo: valor}}, upsert=True)

def remover_do_mongo(chat_id: int, campo: str):
    col_bemvindo.update_one({"chat_id": chat_id}, {"$unset": {campo: ""}})

def alternar_status_mongo(chat_id: int) -> bool:
    doc = col_bemvindo.find_one({"chat_id": chat_id})
    status_atual = doc.get("status", True) if doc else True
    novo_status = not status_atual
    col_bemvindo.update_one({"chat_id": chat_id}, {"$set": {"status": novo_status}}, upsert=True)
    return novo_status

MENSAGENS_PRONTAS = {
    "legenda_1": "{MENTION}\n👾 •𝑬𝑵𝑻𝑹𝑶𝑼 𝑺𝑬 𝑨𝑷𝑹𝑬𝑺𝑬𝑵𝑻𝑨•\n📸 •F𝜣T𝜣\n👻 •N𝜣ME\n📌 •CID∆DE\n🗓️ •ID∆DE\n⚠️ •LEI∆ ∆S REGR∆S D𝜣 GRUP𝜣",
    "legenda_2": "🔥 Seja muito bem-vindo(a), {MENTION}!\n\n✨ **Ficha obrigatória:**\n👤 Nome: \n🎂 Idade: \n📍 Estado/Cidade: \n📸 Foto no perfil?\n\n⚠️ Respeite as regras do {GROUPNAME}!",
    "legenda_3": "🎉 Olha só quem chegou ao {GROUPNAME}!\n\nE aí {MENTION}, já vai mandando:\n⚡ Seu nome/apelido\n⚡ De onde você é\n⚡ Manda uma foto\n\nDivirta-se! 🚀",
    "legenda_4": "💎 **NOVO MEMBRO!** 💎\n\nSeja bem-vindo(a), {MENTION} ao {GROUPNAME}.\nApresente-se:\n🏷️ Apelido:\n🌍 Cidade:\n🎯 O que curte?\n\nDivirta-se!",
    "legenda_5": "⭐ Mais um integrante chegou! ⭐\n\nBem-vindo(a), {MENTION}! 🥳\nApresente-se:\n📌 Nome / Idade\n📌 Cidade\n📌 Mande uma foto\n\nLeia as regras e aproveite!",
    "legenda_6": "🚀 **PASSAPORTE CARIMBADO!** 🚀\n\n{MENTION} acabou de pousar no {GROUPNAME}!\n\n📝 Apresente-se:\n• Nome:\n• Idade:\n• Cidade:\n\nSeja gente boa!"
}

# ✅ FUNÇÃO CHAMADA PELO MENU ADM
async def menu_bemvindo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas Administradores!", show_alert=True)
        return

    await enviar_painel_principal_bv(context, chat_id, query=query)

async def verificar_permissao_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await update.callback_query.answer("⚠️ Apenas administradores!", show_alert=True)
        return False
    return True

async def cmd_bem_vindo_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_user_admin(update, chat_id, user_id, context):
        await update.message.reply_text("⚠️ Apenas administradores podem configurar boas-vindas!")
        return

    try:
        await update.message.delete()
    except Exception:
        pass

    await enviar_painel_principal_bv(context, chat_id, message=update.message)

async def enviar_painel_principal_bv(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message=None, query=None, aviso_extra: str = None, edit_message_id=None):
    texto, midia, botoes, status_atual = carregar_dados_bv(chat_id)
    tem_texto = bool(texto)
    tem_midia = bool(midia)
    tem_botoes = bool(botoes)
    txt_status = "✅" if tem_texto else "❌"
    mid_status = "✅" if tem_midia else "❌"
    bot_status = "✅" if tem_botoes else "❌"
    status_texto_painel = "🟢 Ativado" if status_atual else "🔴 Desativado"
    cabecalho = f"✅ **{aviso_extra}**\n\n" if aviso_extra else ""

    texto_painel = (
        f"{cabecalho}"
        f"💬 **Mensagem de boas-vindas** (Status: {status_texto_painel})\n\n"
        f"📄 Texto {txt_status}\n🎞️ Mídias {mid_status}\n🔲 Botões {bot_status}\n\n👉 Use os botões abaixo:"
    )

    botao_status = InlineKeyboardButton("🔴 Desativar", callback_data="bv_toggle_status") if status_atual else InlineKeyboardButton("🟢 Ativar", callback_data="bv_toggle_status")
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Texto", callback_data="bv_edit_texto"), InlineKeyboardButton("👀 Ver", callback_data="bv_ver_texto")],
        [InlineKeyboardButton("✨ Mensagens Prontas", callback_data="bv_mensagens_prontas")],
        [InlineKeyboardButton("🎞️ Mídias", callback_data="bv_edit_midia"), InlineKeyboardButton("👀 Ver", callback_data="bv_ver_midia")],
        [InlineKeyboardButton("🔲 Botões", callback_data="bv_edit_botoes"), InlineKeyboardButton("👀 Ver", callback_data="bv_ver_botoes")],
        [botao_status],
        [InlineKeyboardButton("👀 Visualização completa", callback_data="bv_ver_completa")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_adm")]
    ])

    if query and query.message:
        await query.message.edit_text(texto_painel, reply_markup=teclado, parse_mode="Markdown")
    elif message:
        await message.reply_text(texto_painel, reply_markup=teclado, parse_mode="Markdown")

async def montar_texto_formatado(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user) -> str:
    try:
        chat_info = await context.bot.get_chat(chat_id)
        chat_title = chat_info.title or "Grupo"
    except Exception:
        chat_title = "Grupo"
    agora = datetime.now(FUSO_BR)
    dias_semana = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
    texto, _, _, _ = carregar_dados_bv(chat_id)
    texto_base = texto or "Olá {MENTION}, seja bem-vindo(a) ao {GROUPNAME}!"
    for chave, valor in {
        "{MENTION}": user.mention_html(),
        "{GROUPNAME}": chat_title,
        "{NAME}": user.first_name or "",
        "{DATE}": agora.strftime("%d/%m/%Y"),
        "{TIME}": agora.strftime("%H:%M")
    }.items():
        texto_base = texto_base.replace(chave, valor)
    return texto_base

async def enviar_mensagem_boas_vindas(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user):
    _, _, _, status_atual = carregar_dados_bv(chat_id)
    if not status_atual:
        return
    texto_final = await montar_texto_formatado(context, chat_id, user)
    _, midia, botoes, _ = carregar_dados_bv(chat_id)
    try:
        if midia:
            tipo, file_id, leg = midia
            if tipo == "photo":
                await context.bot.send_photo(chat_id, file_id, caption=texto_final, reply_markup=botoes, parse_mode="HTML")
            elif tipo == "video":
                await context.bot.send_video(chat_id, file_id, caption=texto_final, reply_markup=botoes, parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id, texto_final, reply_markup=botoes, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Erro boas-vindas: {e}")

async def boas_vindas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.new_chat_members:
        return
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await enviar_mensagem_boas_vindas(context, update.effective_chat.id, member)

async def cb_toggle_status_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    chat_id = update.effective_chat.id
    novo_status = alternar_status_mongo(chat_id)
    aviso = "✅ Boas-vindas ATIVADAS!" if novo_status else "🔴 Boas-vindas DESATIVADAS!"
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra=aviso)
    await update.callback_query.answer(aviso)

async def cb_edit_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_texto_bv", update.callback_query.message.message_id)
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="bv_cancelar")]])
    texto = "📄 Envie a mensagem de boas-vindas agora!\nUse: {MENTION}, {GROUPNAME}, {NAME}, {DATE}, {TIME}"
    await update.callback_query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def cb_ver_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    texto, _, _, _ = carregar_dados_bv(update.effective_chat.id)
    txt = texto or "Nenhum texto salvo."
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]])
    await update.callback_query.message.edit_text(f"📄 Texto atual:\n\n{txt}", reply_markup=teclado, parse_mode="Markdown")

async def cb_menu_mensagens_prontas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Legenda 1", callback_data="bv_legenda_legenda_1")],
        [InlineKeyboardButton("📄 Legenda 2", callback_data="bv_legenda_legenda_2")],
        [InlineKeyboardButton("📄 Legenda 3", callback_data="bv_legenda_legenda_3")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]
    ])
    await update.callback_query.message.edit_text("✨ Escolha uma mensagem pronta:", reply_markup=teclado, parse_mode="Markdown")

async def cb_aplicar_legenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    dados = update.callback_query.data
    chat_id = update.effective_chat.id
    if dados.startswith("bv_legenda_"):
        chave = dados.replace("bv_legenda_", "")
        if chave in MENSAGENS_PRONTAS:
            texto = MENSAGENS_PRONTAS[chave]
            teclado = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Usar esta mensagem", callback_data=f"bv_salvar_{chave}")],
                [InlineKeyboardButton("🔙 Voltar", callback_data="bv_mensagens_prontas")]
            ])
            await update.callback_query.message.edit_text(f"Pré-visualização:\n\n{texto}", reply_markup=teclado, parse_mode="Markdown")
    elif dados.startswith("bv_salvar_"):
        chave = dados.replace("bv_salvar_", "")
        if chave in MENSAGENS_PRONTAS:
            salvar_no_mongo(chat_id, "texto", MENSAGENS_PRONTAS[chave])
            await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra="✅ Mensagem salva!")

async def cb_cancelar_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO.pop((chat_id, user_id), None)
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query)

async def cb_ver_completa_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    user = update.effective_user
    await enviar_mensagem_boas_vindas(context, update.effective_chat.id, user)
    await update.callback_query.answer("✅ Pré-visualização enviada!")

async def capturar_fluxo_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    if not chat or not user or not message:
        return
    chave = (chat.id, user.id)
    if chave not in ESTADOS_FLUXO:
        return
    estado, msg_id = ESTADOS_FLUXO.pop(chave)
    try:
        await message.delete()
    except Exception:
        pass
    if estado == "aguardando_texto_bv":
        texto = message.text or message.caption or ""
        salvar_no_mongo(chat.id, "texto", texto)
        await enviar_painel_principal_bv(context, chat.id, aviso_extra="✅ Texto salvo!", edit_message_id=msg_id)

def registrar_comandos_bv(application):
    application.add_handler(CommandHandler("bemvindo", cmd_bem_vindo_painel, filters=~filters.ChatType.PRIVATE))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & ~filters.ChatType.PRIVATE, boas_vindas_handler))
    application.add_handler(CallbackQueryHandler(cb_toggle_status_bv, pattern=r"^bv_toggle_status$"))
    application.add_handler(CallbackQueryHandler(cb_edit_texto_bv, pattern=r"^bv_edit_texto$"))
    application.add_handler(CallbackQueryHandler(cb_ver_texto_bv, pattern=r"^bv_ver_texto$"))
    application.add_handler(CallbackQueryHandler(cb_menu_mensagens_prontas, pattern=r"^bv_mensagens_prontas$"))
    application.add_handler(CallbackQueryHandler(cb_aplicar_legenda, pattern=r"^bv_legenda_|^bv_salvar_"))
    application.add_handler(CallbackQueryHandler(cb_cancelar_bv, pattern=r"^bv_cancelar$"))
    application.add_handler(CallbackQueryHandler(cb_ver_completa_bv, pattern=r"^bv_ver_completa$"))
    application.add_handler(MessageHandler(~filters.COMMAND & filters.TEXT, capturar_fluxo_admin), group=1)
