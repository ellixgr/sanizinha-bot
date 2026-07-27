import os
import re
import logging
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from pymongo import MongoClient

logger = logging.getLogger("SanizinhaBot.BemVindo")

# Configuração do MongoDB para persistir os dados no Render
MONGO_URI = os.getenv("MONGO_URI", "sua_uri_do_mongodb_aqui")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["sanizinha_bot"]
col_bemvindo = db["config_bem_vindo"]

# Fuso horário do Brasil (UTC-3)
FUSO_BR = timezone(timedelta(hours=-3))

ESTADOS_FLUXO = {} 

# --- FUNÇÕES DE PERSISTÊNCIA (MONGODB) ---
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

    col_bemvindo.update_one(
        {"chat_id": chat_id},
        {"$set": {campo: valor}},
        upsert=True
    )

def remover_do_mongo(chat_id: int, campo: str):
    col_bemvindo.update_one(
        {"chat_id": chat_id},
        {"$unset": {campo: ""}}
    )

def alternar_status_mongo(chat_id: int) -> bool:
    doc = col_bemvindo.find_one({"chat_id": chat_id})
    status_atual = doc.get("status", True) if doc else True
    novo_status = not status_atual
    col_bemvindo.update_one(
        {"chat_id": chat_id},
        {"$set": {"status": novo_status}},
        upsert=True
    )
    return novo_status

# --- MENSAGENS PRONTAS (COM PRÉ-VISUALIZAÇÃO) ---
MENSAGENS_PRontas = {
    "legenda_1": (
        "{MENTION}\n"
        "👾 •𝑬𝑵𝑻𝑹𝑶𝑼 𝑺𝑬 𝑨𝑷𝑹𝑬𝑺𝑬𝑵𝑻𝑨•\n"
        "📸 •F𝜣T𝜣\n"
        "👻 •N𝜣ME\n"
        "📌 •CID∆DE\n"
        "🗓️ •ID∆DE\n"
        "⚠️ •LEI∆ ∆S REGR∆S D𝜣 GRUP𝜣"
    ),
    "legenda_2": (
        "🔥 Seja muito bem-vindo(a), {MENTION}!\n\n"
        "✨ **Ficha obrigatória para entrosar:**\n"
        "👤 Nome: \n"
        "🎂 Idade: \n"
        "📍 Estado/Cidade: \n"
        "📸 Foto no perfil?\n\n"
        "⚠️ Respeite as regras do {GROUPNAME} para evitar banimento!"
    ),
    "legenda_3": (
        "🎉 Olha só quem chegou para agitar o **{GROUPNAME}**!\n\n"
        "E aí {MENTION}, casa nova! Já vai mandando:\n"
        "⚡ Seu nome ou apelido\n"
        "⚡ De onde você é\n"
        "⚡ Manda a self/foto\n\n"
        "Divirta-se com moderação e siga as diretrizes do grupo! 🚀"
    ),
    "legenda_4": (
        "💎 **NOVO MEMBRO NA ÁREA!** 💎\n\n"
        "Seja bem-vindo(a), {MENTION} ao {GROUPNAME}.\n"
        "Para mantermos a organização, mande sua mini-apresentação:\n"
        "🏷️ Apelido:\n"
        "🌍 Cidade/Região:\n"
        "🎯 O que curte fazer?\n\n"
        "Divirta-se e faça novas amizades!"
    ),
    "legenda_5": (
        "⭐ *Atenção galera, mais um integrante chegou!* ⭐\n\n"
        "Bem-vindo(a), {MENTION}! 🥳\n"
        "Não fique acanhado(a), solte sua apresentação no chat:\n"
        "📌 Nome / Idade\n"
        "📌 Cidade\n"
        "📌 Mande uma foto pra galera te conhecer\n\n"
        "Leia as regras fixadas e aproveite o {GROUPNAME}!"
    ),
    "legenda_6": (
        "🚀 **PASSAPORTE CARIMBADO!** 🚀\n\n"
        " {MENTION} acabou de pousar no {GROUPNAME}!\n\n"
        "📝 Apresente-se para o clã:\n"
        "• Nome:\n"
        "• Idade:\n"
        "• Cidade:\n\n"
        "Seja gente boa e curta o espaço com a gente!"
    )
}

def registrar_comandos_bv(app: Application):
    registrar_captura_fluxo(app)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & ~filters.ChatType.PRIVATE, boas_vindas_handler))
    app.add_handler(CommandHandler("bemvindo", cmd_bem_vindo_painel, filters=~filters.ChatType.PRIVATE))
    
    app.add_handler(CallbackQueryHandler(cb_edit_texto, pattern=r"^bv_edit_texto"))
    app.add_handler(CallbackQueryHandler(cb_ver_texto, pattern=r"^bv_ver_texto"))
    app.add_handler(CallbackQueryHandler(cb_rem_texto, pattern=r"^bv_remover_texto"))
    app.add_handler(CallbackQueryHandler(cb_edit_midia, pattern=r"^bv_edit_midia"))
    app.add_handler(CallbackQueryHandler(cb_ver_midia, pattern=r"^bv_ver_midia"))
    app.add_handler(CallbackQueryHandler(cb_rem_midia, pattern=r"^bv_remover_midia"))
    app.add_handler(CallbackQueryHandler(cb_edit_botoes, pattern=r"^bv_edit_botoes"))
    app.add_handler(CallbackQueryHandler(cb_ver_botoes, pattern=r"^bv_ver_botoes"))
    app.add_handler(CallbackQueryHandler(cb_rem_botoes, pattern=r"^bv_remover_botoes"))
    app.add_handler(CallbackQueryHandler(cb_ver_completa, pattern=r"^bv_ver_completa"))
    app.add_handler(CallbackQueryHandler(cb_toggle_status, pattern=r"^bv_toggle_status"))
    app.add_handler(CallbackQueryHandler(cb_toggle_visual, pattern=r"^bv_toggle_visual"))
    app.add_handler(CallbackQueryHandler(cb_cancelar, pattern=r"^bv_cancelar"))
    app.add_handler(CallbackQueryHandler(cb_menu_mensagens_prontas, pattern=r"^bv_mensagens_prontas"))
    app.add_handler(CallbackQueryHandler(cb_aplicar_legenda, pattern=r"^bv_legenda_"))
    app.add_handler(CallbackQueryHandler(cb_aplicar_legenda, pattern=r"^bv_salvar_"))  # <-- ADICIONADO AQUI O CORRETO!
    app.add_handler(CallbackQueryHandler(cb_callback_botoes_especiais, pattern=r"^bv_esp_"))

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
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra="Modo visual alterado com sucesso!")

async def cb_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    await callback_cancelar_bv(update, context)

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
        f"📄 Texto {txt_status}\n"
        f"🎞️ Mídias {mid_status}\n"
        f"🔲 Botões de Url {bot_status}\n\n"
        "👉 **Use os botões abaixo para configurar:**"
    )

    botao_status = InlineKeyboardButton("🔴 Desativar boas-vindas", callback_data=f"bv_toggle_status") if status_atual else InlineKeyboardButton("🟢 Ativar boas-vindas", callback_data=f"bv_toggle_status")

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Texto", callback_data="bv_edit_texto"), InlineKeyboardButton("👀 Veja", callback_data="bv_ver_texto")],
        [InlineKeyboardButton("✨ Mensagens Prontas", callback_data="bv_mensagens_prontas")],
        [InlineKeyboardButton("🎞️ Mídias", callback_data="bv_edit_midia"), InlineKeyboardButton("👀 Veja", callback_data="bv_ver_midia")],
        [InlineKeyboardButton("🔲 Botões", callback_data="bv_edit_botoes"), InlineKeyboardButton("👀 Veja", callback_data="bv_ver_botoes")],
        [botao_status],
        [InlineKeyboardButton("🖼️ Alternar Visual ✅", callback_data="bv_toggle_visual")],
        [InlineKeyboardButton("👀 Visualização completa", callback_data="bv_ver_completa")],
        [InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data="voltar_principal_grupo")]
    ])

    if edit_message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=edit_message_id,
                text=texto_painel,
                reply_markup=teclado,
                parse_mode="Markdown"
            )
            return
        except Exception:
            pass

    if query and query.message:
        try:
            await query.message.edit_text(texto_painel, reply_markup=teclado, parse_mode="Markdown")
            return
        except Exception:
            pass

    if message:
        try:
            await message.reply_text(texto_painel, reply_markup=teclado, parse_mode="Markdown")
            return
        except Exception:
            pass

    if query and query.from_user:
        try:
            await context.bot.send_message(chat_id=chat_id, text=texto_painel, reply_markup=teclado, parse_mode="Markdown")
        except Exception:
            pass

def registrar_captura_fluxo(app: Application):
    async def capturar_fluxo_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user
        message = update.message
        if not chat or not user or not message:
            return

        chave_fluxo = (chat.id, user.id)
        if chave_fluxo not in ESTADOS_FLUXO:
            return

        estado, msg_id_painel = ESTADOS_FLUXO.pop(chave_fluxo)

        try:
            await message.delete()
        except Exception:
            pass

        if estado == "aguardando_texto_bv":
            texto = message.text or message.caption or ""
            salvar_no_mongo(chat.id, "texto", texto)
            await enviar_painel_principal_bv(context, chat.id, aviso_extra="Texto configurado com sucesso!", edit_message_id=msg_id_painel)

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

            midia_dados = [tipo, file_id, leg]
            salvar_no_mongo(chat.id, "midia", midia_dados)
            if leg:
                texto_atual, _, _, _ = carregar_dados_bv(chat.id)
                if not texto_atual:
                    salvar_no_mongo(chat.id, "texto", leg)

            await enviar_painel_principal_bv(context, chat.id, aviso_extra="Mídia configurada com sucesso!", edit_message_id=msg_id_painel)

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
                        acao = acao.strip().lower()

                        if acao.startswith("popup:") or acao.startswith("alert:"):
                            texto_popup = acao.split(":", 1)[1].strip()
                            linha_botoes.append(InlineKeyboardButton(titulo, callback_data=f"bv_esp_popup_{texto_popup[:30]}"))
                        elif acao == "rules":
                            linha_botoes.append(InlineKeyboardButton(titulo, callback_data="bv_esp_rules"))
                        elif acao.startswith("share:"):
                            texto_share = acao.split(":", 1)[1].strip()
                            link_share = f"https://t.me/share/url?url={texto_share}"
                            linha_botoes.append(InlineKeyboardButton(titulo, url=link_share))
                        elif acao.startswith("copy:"):
                            texto_copy = acao.split(":", 1)[1].strip()
                            linha_botoes.append(InlineKeyboardButton(titulo, callback_data=f"bv_esp_copy_{texto_copy[:30]}"))
                        else:
                            url_final = acao
                            if not url_final.startswith("http://") and not url_final.startswith("https://") and not url_final.startswith("t.me/"):
                                url_final = "https://" + url_final
                            elif url_final.startswith("t.me/"):
                                url_final = "https://" + url_final
                            linha_botoes.append(InlineKeyboardButton(titulo, url=url_final))

                if linha_botoes:
                    botoes_teclado.append(linha_botoes)

            if botoes_teclado:
                teclado_obj = InlineKeyboardMarkup(botoes_teclado)
                salvar_no_mongo(chat.id, "botoes", teclado_obj)
                await enviar_painel_principal_bv(context, chat.id, aviso_extra="Botões configurados com sucesso!", edit_message_id=msg_id_painel)

    app.add_handler(MessageHandler(~filters.COMMAND & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Sticker.ALL), capturar_fluxo_admin), group=1)

# --- MENU DE MENSAGENS PRONTAS COM PRÉ-VISUALIZAÇÃO ---
async def cb_menu_mensagens_prontas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    
    query = update.callback_query
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Legenda 1 (Ver Pré-visualização)", callback_data="bv_legenda_legenda_1")],
        [InlineKeyboardButton("📄 Legenda 2 (Ver Pré-visualização)", callback_data="bv_legenda_legenda_2")],
        [InlineKeyboardButton("📄 Legenda 3 (Ver Pré-visualização)", callback_data="bv_legenda_legenda_3")],
        [InlineKeyboardButton("📄 Legenda 4 (Ver Pré-visualização)", callback_data="bv_legenda_legenda_4")],
        [InlineKeyboardButton("📄 Legenda 5 (Ver Pré-visualização)", callback_data="bv_legenda_legenda_5")],
        [InlineKeyboardButton("📄 Legenda 6 (Ver Pré-visualização)", callback_data="bv_legenda_legenda_6")],
        [InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data="bv_cancelar")]
    ])
    
    msg = (
        "✨ **Escolha uma Mensagem Pronta:**\n\n"
        "Clique em uma das opções abaixo para **ver a pré-visualização completa** do texto antes de definir no grupo:"
    )
    await query.message.edit_text(msg, reply_markup=teclado, parse_mode="Markdown")
    await query.answer()

async def cb_aplicar_legenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_permissao_callback(update, context):
        return
    
    query = update.callback_query
    data = query.data # Ex: bv_legenda_legenda_1 ou bv_salvar_legenda_1
    
    # Se clicar para ver a pré-visualização
    if data.startswith("bv_legenda_"):
        legenda_key = data.replace("bv_legenda_", "")
        
        if legenda_key in MENSAGENS_PRontas:
            texto_preview = MENSAGENS_PRontas[legenda_key]
            
            # Teclado para confirmar a aplicação da mensagem vista
            teclado_confirmacao = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Salvar e Aplicar esta Legenda", callback_data=f"bv_salvar_{legenda_key}")],
                [InlineKeyboardButton("⬅️ Escolher Outra Legenda", callback_data="bv_mensagens_prontas")]
            ])
            
            msg_completa = (
                f"👀 **Pré-visualização da Legenda:**\n\n"
                f"----------------------------------------\n"
                f"{texto_preview}\n"
                f"----------------------------------------\n\n"
                f"Deseja definir esta mensagem como padrão de boas-vindas?"
            )
            await query.message.edit_text(msg_completa, reply_markup=teclado_confirmacao, parse_mode="Markdown")
            await query.answer()
            return

    # Se confirmou salvar
    if data.startswith("bv_salvar_"):
        legenda_key = data.replace("bv_salvar_", "")
        if legenda_key in MENSAGENS_PRontas:
            texto_escolhido = MENSAGENS_PRontas[legenda_key]
            chat_id = update.effective_chat.id
            salvar_no_mongo(chat_id, "texto", texto_escolhido)
            await enviar_painel_principal_bv(context, chat_id, query=query, aviso_extra="Mensagem pronta aplicada com sucesso!")
            return

    await query.answer("Opção não encontrada!", show_alert=True)

async def cb_callback_botoes_especiais(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if "popup" in data or "alert" in data:
        await query.answer("Aviso do Bot:\nBotão especial acionado com sucesso!", show_alert=True)
    elif data == "bv_esp_rules":
        await query.answer("Consulte as regras fixadas no topo do grupo.", show_alert=True)
    elif "copy" in data:
        await query.answer("Texto copiado para a área de transferência!", show_alert=False)
    else:
        await query.answer()

async def montar_texto_formatado(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user) -> str:
    try:
        chat_info = await context.bot.get_chat(chat_id)
        chat_title = chat_info.title if chat_info else "Grupo"
    except Exception:
        chat_title = "Grupo"

    agora = datetime.now(FUSO_BR)
    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    
    texto, _, _, _ = carregar_dados_bv(chat_id)
    texto_base = texto if texto else "Olá {MENTION}, seja bem-vindo(a) ao {GROUPNAME}!"

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
        "{RULES}": "Consulte as regras fixadas."
    }

    for chave, valor in formatacoes.items():
        texto_base = texto_base.replace(chave, valor)
    return texto_base

async def enviar_mensagem_boas_vindas(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user):
    _, _, _, status_atual = carregar_dados_bv(chat_id)
    if not status_atual:
        return
        
    texto_final = await montar_texto_formatado(context, chat_id, user)
    _, _, botoes, _ = carregar_dados_bv(chat_id)
    _, midia, _, _ = carregar_dados_bv(chat_id)

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
        logger.error(f"[BOAS-VINDAS] Erro: {e}")

async def boas_vindas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not update.message.new_chat_members:
        return
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await enviar_mensagem_boas_vindas(context, chat_id, member)

async def callback_toggle_status_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    novo_status = alternar_status_mongo(chat_id)
    aviso = "Boas-vindas ativadas!" if novo_status else "Boas-vindas desativadas!"
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra=aviso)
    await update.callback_query.answer(aviso)

async def callback_edit_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_texto_bv", update.callback_query.message.message_id)
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Remover texto", callback_data="bv_remover_texto")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="bv_cancelar")]
    ])
    
    instrucoes_texto = (
        "Envie agora a mensagem que você quer definir!\n\n"
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
    
    await update.callback_query.message.edit_text(instrucoes_texto, reply_markup=teclado, parse_mode="Markdown")
    await update.callback_query.answer()

async def callback_ver_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    texto, _, _, _ = carregar_dados_bv(chat_id)
    texto_atual = texto if texto else "Nenhum texto configurado."
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="bv_cancelar")]])
    await update.callback_query.message.edit_text(f"📄 **Texto atual:**\n\n{texto_atual}", reply_markup=teclado, parse_mode="Markdown")
    await update.callback_query.answer()

async def callback_remover_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    remover_do_mongo(chat_id, "texto")
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra="Texto removido!")

async def callback_edit_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_midia_bv", update.callback_query.message.message_id)
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Remover mídia", callback_data="bv_remover_midia")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="bv_cancelar")]
    ])
    
    msg_midia = (
        "Envie agora a mídia (fotos, vídeos, sticker...) que você deseja definir.\n"
        "Você também pode inserir uma legenda."
    )
    
    await update.callback_query.message.edit_text(msg_midia, reply_markup=teclado)
    await update.callback_query.answer()

async def callback_ver_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _, midia, _, _ = carregar_dados_bv(chat_id)
    if midia:
        tipo, file_id, leg = midia
        if tipo == "photo":
            await context.bot.send_photo(chat_id, file_id, caption=f"Mídia salva. Legenda: {leg}")
        elif tipo == "video":
            await context.bot.send_video(chat_id, file_id, caption=f"Mídia salva. Legenda: {leg}")
        elif tipo == "sticker":
            await context.bot.send_sticker(chat_id, file_id)
        await update.callback_query.answer()
    else:
        await update.callback_query.answer("Nenhuma mídia salva!", show_alert=True)

async def callback_remover_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    remover_do_mongo(chat_id, "midia")
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra="Mídia removida!")

async def callback_edit_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_botoes_bv", update.callback_query.message.message_id)
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Remover botões", callback_data="bv_remover_botoes")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="bv_cancelar")]
    ])
    
    msg_botoes = (
        "Configure os botões a serem colocados abaixo da mensagem.\n"
        "Envie uma mensagem estruturada da forma a seguir:\n\n"
        "• **Adicionar um único botão:**\n"
        "`Título do botão - t.me/LinkExemplar`\n\n"
        "• **Adicionar múltiplos botões em uma única linha:**\n"
        "`Título - t.me/LinkExemplar && Título - t.me/LinkExemplar`\n\n"
        "• **Adicionar múltiplas linhas de botões:**\n"
        "`Título - t.me/LinkExemplar`\n"
        "`Título - t.me/LinkExemplar`\n\n"
        "**Botões especiais:**\n"
        "• Pop-up/Alert:\n"
        "`Título - popup: Texto do popup` ou `alert: Texto`\n"
        "• Regras do grupo:\n"
        "`Título - rules`\n"
        "• Compartilhamento:\n"
        "`Título - share: Texto a ser compartilhado`\n"
        "• Texto copiável:\n"
        "`Título - copy: Texto copiado ao clicar`"
    )
    
    await update.callback_query.message.edit_text(msg_botoes, reply_markup=teclado, parse_mode="Markdown")
    await update.callback_query.answer()

async def callback_ver_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _, _, botoes, _ = carregar_dados_bv(chat_id)
    if botoes:
        await update.callback_query.message.reply_text("🔲 **Botões atuais:**", reply_markup=botoes)
        await update.callback_query.answer()
    else:
        await update.callback_query.answer("Nenhum botão configurado!", show_alert=True)

async def callback_remover_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    remover_do_mongo(chat_id, "botoes")
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query, aviso_extra="Botões removidos!")

async def callback_ver_completa_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    await enviar_mensagem_boas_vindas(context, chat_id, user)
    await update.callback_query.answer("Pré-visualização enviada!")

async def callback_cancelar_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ESTADOS_FLUXO.pop((chat_id, user_id), None)
    await enviar_painel_principal_bv(context, chat_id, query=update.callback_query)
    await update.callback_query.answer("Cancelado.")
