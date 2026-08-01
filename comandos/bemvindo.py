import os
import logging
import re
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
DONO_ID = os.getenv("DONO_ID", "0").strip()
mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
db = mongo_client["sanizinhabot_db"]
col_bemvindo = db["config_bem_vindo"]

FUSO_BR = timezone(timedelta(hours=-3))
ESTADOS_FLUXO = {}

# ✅ VERIFICA SE É ADMINISTRADOR
async def is_user_admin(update: Update, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        if DONO_ID and str(user_id) == str(DONO_ID):
            return True
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

def alternar_status_mongo(chat_id: int) -> bool:
    doc = col_bemvindo.find_one({"chat_id": chat_id})
    status_atual = doc.get("status", True) if doc else True
    novo_status = not status_atual
    col_bemvindo.update_one({"chat_id": chat_id}, {"$set": {"status": novo_status}}, upsert=True)
    return novo_status

# ✅ CHAMADO PELO MENU ADM
async def menu_bemvindo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas Administradores!", show_alert=True)
        return

    await enviar_painel_principal_bv(context, chat_id, query=query)

# ✅ COMANDO /bemvindo
async def cmd_bemvindo_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_user_admin(update, chat_id, user_id, context):
        await update.message.reply_text("❌ Você precisa ser ADMINISTRADOR para usar esse comando!")
        return

    await enviar_painel_principal_bv(context, chat_id, message=update.message)

async def enviar_painel_principal_bv(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message=None, query=None, aviso_extra: str = None):
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

# ✅ FORMATAÇÃO COMPLETA COM TODAS AS VARIÁVEIS
async def montar_texto_formatado(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user) -> str:
    try:
        chat_info = await context.bot.get_chat(chat_id)
        chat_title = chat_info.title or "Grupo"
    except Exception:
        chat_title = "Grupo"
    agora = datetime.now(FUSO_BR)
    dia_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"][agora.weekday()]
    texto, _, _, _ = carregar_dados_bv(chat_id)
    texto_base = texto or "Olá {MENTION}, seja bem-vindo(a) ao {GROUPNAME}!"
    
    usuario_nome = user.first_name or ""
    usuario_sobrenome = user.last_name or ""
    usuario_nome_completo = f"{usuario_nome} {usuario_sobrenome}".strip()
    usuario_id = user.id
    idioma = (user.language_code or "pt").upper()
    username = f"@{user.username}" if user.username else "Sem usuário"
    
    regras_link = f"\nLeia as regras do grupo: t.me/{context.bot.username}?startgroup=regras"
    
    for chave, valor in {
        "{ID}": str(usuario_id),
        "{NAME}": usuario_nome,
        "{SURNAME}": usuario_sobrenome,
        "{NAMESURNAME}": usuario_nome_completo,
        "{LANG}": idioma,
        "{DATE}": agora.strftime("%d/%m/%Y"),
        "{TIME}": agora.strftime("%H:%M"),
        "{WEEKDAY}": dia_semana,
        "{MENTION}": user.mention_html(),
        "{USERNAME}": username,
        "{GROUPNAME}": chat_title,
        "{RULES}": regras_link
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
            legenda_final = f"{leg}\n\n{texto_final}" if leg else texto_final
            if tipo == "photo":
                await context.bot.send_photo(chat_id, file_id, caption=legenda_final, reply_markup=botoes, parse_mode="HTML")
            elif tipo == "video":
                await context.bot.send_video(chat_id, file_id, caption=legenda_final, reply_markup=botoes, parse_mode="HTML")
            elif tipo == "sticker":
                await context.bot.send_sticker(chat_id, file_id, reply_markup=botoes)
                if leg:
                    await context.bot.send_message(chat_id, legenda_final, reply_markup=botoes, parse_mode="HTML")
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

# ✅ === EDITAR TEXTO ===
async def cb_edit_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_texto_bv", query.message.message_id)
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]])
    texto = (
        "📄 **Lyhh**, agora envie a mensagem que você quer definir!\n\n"
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
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

# ✅ === EDITAR MÍDIA ===
async def cb_edit_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_midia_bv", query.message.message_id)
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]])
    texto = (
        "👉🏻 Envie agora a mídia (fotos, vídeos, figurinhas...) que você deseja definir.\n"
        "Você também pode inserir uma legenda."
    )
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

# ✅ === EDITAR BOTÕES ===
async def cb_edit_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_botoes_bv", query.message.message_id)
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]])
    texto = (
        "👉🏻 Configure os botões a serem colocados abaixo da mensagem\n"
        "Envie uma mensagem estruturada da forma a seguir:\n\n"
        "• **Um botão:**\n`Título do botão - t.me/LinkExemplar`\n\n"
        "• **Vários na mesma linha:**\n`Título - Link && Título - Link`\n\n"
        "• **Várias linhas:**\n`Título - Link`\n`Título - Link`\n\n"
        "🔹 **Botões especiais:**\n"
        "• Popup: `Texto - popup: Mensagem`\n"
        "• Alert: `Texto - alert: Mensagem`\n"
        "• Regras: `Texto - rules`\n"
        "• Compartilhar: `Texto - share: Conteúdo`\n"
        "• Copiar: `Texto - copy: Texto copiado`"
    )
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

# ✅ === VER FUNÇÕES ===
async def cb_ver_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    texto, _, _, _ = carregar_dados_bv(chat_id)
    txt = texto or "Nenhum texto salvo."
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]])
    await query.message.edit_text(f"📄 Texto atual:\n\n{txt}", reply_markup=teclado, parse_mode="Markdown")

async def cb_ver_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    _, midia, _, _ = carregar_dados_bv(chat_id)
    if midia:
        tipo = midia[0]
        txt = f"✅ Mídia salva: {tipo.upper()}"
    else:
        txt = "❌ Nenhuma mídia salva."
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]])
    await query.message.edit_text(f"🎞️ Mídia atual:\n\n{txt}", reply_markup=teclado, parse_mode="Markdown")

async def cb_ver_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    _, _, botoes, _ = carregar_dados_bv(chat_id)
    txt = f"✅ Botões configurados!" if botoes else "❌ Nenhum botão salvo."
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bv_cancelar")]])
    await query.message.edit_text(f"🔲 Botões atuais:\n\n{txt}", reply_markup=teclado, parse_mode="Markdown")

async def cb_toggle_status_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    novo_status = alternar_status_mongo(chat_id)
    aviso = "✅ Boas-vindas ATIVADAS!" if novo_status else "🔴 Boas-vindas DESATIVADAS!"
    await enviar_painel_principal_bv(context, chat_id, query=query, aviso_extra=aviso)

async def cb_cancelar_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    ESTADOS_FLUXO.pop((chat_id, user_id), None)
    await enviar_painel_principal_bv(context, chat_id, query=query)

# ✅ === PARSEADOR DE BOTÕES ===
def parsear_botoes(texto: str, username_bot: str = ""):
    linhas = texto.strip().split("\n")
    teclado = []
    regras_link = f"https://t.me/{username_bot}?startgroup=regras" if username_bot else ""
    
    for linha in linhas:
        botoes_linha = []
        itens = linha.split(" && ")
        for item in itens:
            if " - " not in item:
                continue
            titulo, link = item.split(" - ", 1)
            titulo = titulo.strip()
            link = link.strip()
            
            if link.startswith("popup:") or link.startswith("alert:"):
                txt_popup = link[6:].strip()
                botoes_linha.append(InlineKeyboardButton(titulo, callback_data=f"popup:{txt_popup}"))
            elif link.startswith("share:"):
                conteudo = link[6:].strip()
                botoes_linha.append(InlineKeyboardButton(titulo, switch_inline_query=conteudo))
            elif link.startswith("copy:"):
                texto_copia = link[5:].strip()
                botoes_linha.append(InlineKeyboardButton(titulo, callback_data=f"copy:{texto_copia}"))
            elif link.lower() == "rules":
                botoes_linha.append(InlineKeyboardButton(titulo, url=regras_link))
            else:
                botoes_linha.append(InlineKeyboardButton(titulo, url=link))
        if botoes_linha:
            teclado.append(botoes_linha)
    return InlineKeyboardMarkup(teclado) if teclado else None

# ✅ === CAPTURA O QUE O USUÁRIO ENVIA — CORRIGIDO COM CONFIRMAÇÃO ===
async def capturar_fluxo_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    if not chat or not user or not message:
        return
    chave = (chat.id, user.id)
    
    # ⚠️ SE NÃO ESTÁ AGUARDANDO NADA → IGNORA
    if chave not in ESTADOS_FLUXO:
        return
    
    # ✅ ESTÁ AGUARDANDO → PROCESSA E SALVA
    estado, msg_id = ESTADOS_FLUXO.pop(chave)
    
    if estado == "aguardando_texto_bv":
        texto = message.text or message.caption or ""
        salvar_no_mongo(chat.id, "texto", texto)
        await enviar_painel_principal_bv(context, chat.id, aviso_extra="✅ TEXTO SALVO!")
    
    elif estado == "aguardando_midia_bv":
        legenda = message.caption or ""
        
        # ✅ FOTO
        if message.photo:
            arquivo = message.photo[-1]
            salvar_no_mongo(chat.id, "midia", ("photo", arquivo.file_id, legenda))
            await enviar_painel_principal_bv(context, chat.id, aviso_extra="✅ FOTO SALVA com legenda!" if legenda else "✅ FOTO SALVA!")
        
        # ✅ VÍDEO
        elif message.video:
            arquivo = message.video
            salvar_no_mongo(chat.id, "midia", ("video", arquivo.file_id, legenda))
            await enviar_painel_principal_bv(context, chat.id, aviso_extra="✅ VÍDEO SALVO com legenda!" if legenda else "✅ VÍDEO SALVO!")
        
        # ✅ FIGURINHA/STICKER
        elif message.sticker:
            arquivo = message.sticker
            salvar_no_mongo(chat.id, "midia", ("sticker", arquivo.file_id, legenda))
            await enviar_painel_principal_bv(context, chat.id, aviso_extra="✅ FIGURINHA SALVA!")
    
    elif estado == "aguardando_botoes_bv":
        texto = message.text or ""
        botoes = parsear_botoes(texto, context.bot.username)
        if botoes:
            salvar_no_mongo(chat.id, "botoes", botoes)
            await enviar_painel_principal_bv(context, chat.id, aviso_extra="✅ BOTÕES SALVOS!")
        else:
            await enviar_painel_principal_bv(context, chat.id, aviso_extra="⚠️ Formato inválido! Tente novamente.")

# ✅ === TRATA TODOS OS BOTÕES ===
async def tratar_botoes_bemvindo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dados = update.callback_query.data
    if dados == "bv_toggle_status":
        await cb_toggle_status_bv(update, context)
    elif dados == "bv_edit_texto":
        await cb_edit_texto_bv(update, context)
    elif dados == "bv_edit_midia":
        await cb_edit_midia_bv(update, context)
    elif dados == "bv_edit_botoes":
        await cb_edit_botoes_bv(update, context)
    elif dados == "bv_ver_texto":
        await cb_ver_texto_bv(update, context)
    elif dados == "bv_ver_midia":
        await cb_ver_midia_bv(update, context)
    elif dados == "bv_ver_botoes":
        await cb_ver_botoes_bv(update, context)
    elif dados == "bv_cancelar":
        await cb_cancelar_bv(update, context)
    elif dados == "menu_adm":
        from comandos.menus import menu_adm_handler
        await menu_adm_handler(update, context)
    else:
        await update.callback_query.answer("❌ Função não encontrada!", show_alert=True)

def registrar_comandos_bv(application):
    application.add_handler(CommandHandler("bemvindo", cmd_bemvindo_painel, filters=~filters.ChatType.PRIVATE))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & ~filters.ChatType.PRIVATE, boas_vindas_handler))
    # ✅ SEM GROUP=1 — PRIMEIRO A SER VERIFICADO + INCLUI STICKER
    application.add_handler(MessageHandler(
        ~filters.COMMAND & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Sticker.ALL),
        capturar_fluxo_admin
    ))
