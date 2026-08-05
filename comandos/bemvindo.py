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


# ✅ CARREGA DADOS DO BANCO — SEMPRE FRESCO
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
    if botoes_raw and isinstance(botoes_raw, list) and len(botoes_raw) > 0:
        teclado_linhas = []
        for linha in botoes_raw:
            if not isinstance(linha, list):
                continue
            linha_botoes = []
            for b in linha:
                if not isinstance(b, dict):
                    continue
                if "url" in b:
                    linha_botoes.append(InlineKeyboardButton(b["text"], url=b["url"]))
                elif "callback_data" in b:
                    linha_botoes.append(InlineKeyboardButton(b["text"], callback_data=b["callback_data"]))
            if linha_botoes:
                teclado_linhas.append(linha_botoes)
        if teclado_linhas:
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


def excluir_campo_bv(chat_id: int, campo: str):
    col_bemvindo.update_one({"chat_id": chat_id}, {"$unset": {campo: ""}})


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


# ✅ PAINEL PRINCIPAL — DADOS SEMPRE DO BANCO
async def enviar_painel_principal_bv(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message=None, query=None, aviso_extra: str = None):
    texto, midia, botoes, status_atual = carregar_dados_bv(chat_id)
    
    tem_texto = bool(texto and texto.strip() != "")
    tem_midia = bool(midia is not None)
    tem_botoes = bool(botoes is not None)
    
    txt_status = "✅" if tem_texto else "❌"
    mid_status = "✅" if tem_midia else "❌"
    bot_status = "✅" if tem_botoes else "❌"
    
    status_texto_painel = "🟢 Ativado" if status_atual else "🔴 Desativado"
    cabecalho = f"{aviso_extra}\n\n" if aviso_extra else ""

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
        try:
            await query.message.edit_text(texto_painel, reply_markup=teclado, parse_mode="Markdown")
        except Exception:
            try:
                await query.message.delete()
            except:
                pass
            await context.bot.send_message(chat_id, texto_painel, reply_markup=teclado, parse_mode="Markdown")
    elif message:
        await message.reply_text(texto_painel, reply_markup=teclado, parse_mode="Markdown")


# ✅ FORMATAÇÃO DAS VARIÁVEIS
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
        if valor:
            texto_base = texto_base.replace(chave, valor)
    return texto_base


# ✅ === ENVIAR BOAS-VINDAS ===
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
                legenda_final = f"{leg or ''}\n\n{texto_final}".strip()
                await context.bot.send_photo(chat_id, file_id, caption=legenda_final, reply_markup=botoes, parse_mode="HTML")
            elif tipo == "video":
                legenda_final = f"{leg or ''}\n\n{texto_final}".strip()
                await context.bot.send_video(chat_id, file_id, caption=legenda_final, reply_markup=botoes, parse_mode="HTML")
            elif tipo == "sticker":
                await context.bot.send_sticker(chat_id, file_id)
                await context.bot.send_message(chat_id, texto_final, reply_markup=botoes, parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id, texto_final, reply_markup=botoes, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Erro boas-vindas: {e}")
        try:
            await context.bot.send_message(chat_id, texto_final, reply_markup=botoes, parse_mode="HTML")
        except:
            pass


async def boas_vindas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.new_chat_members:
        return
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await enviar_mensagem_boas_vindas(context, update.effective_chat.id, member)


# ✅ === EDITAR TEXTO — VOLTA PRO PAINEL, NÃO PRO MENU ADM ===
async def cb_edit_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_texto_bv", query.message.message_id)
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]])
    texto = (
        "📄 Agora envie a mensagem que você quer definir!\n\n"
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


# ✅ === EDITAR MÍDIA — VOLTA PRO PAINEL ===
async def cb_edit_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_midia_bv", query.message.message_id)
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]])
    texto = "👉🏻 Envie agora a mídia (fotos, vídeos, figurinhas...)\nVocê também pode colocar uma legenda junto!"
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")


# ✅ === EDITAR BOTÕES — VOLTA PRO PAINEL ===
async def cb_edit_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    ESTADOS_FLUXO[(chat_id, user_id)] = ("aguardando_botoes_bv", query.message.message_id)
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]])
    texto = (
        "👉🏻 Configure os botões abaixo da mensagem\n"
        "Formato: `Título - Link`\n\n"
        "Exemplo:\n`Entrar no Grupo - t.me/seugrupo`\n`Regras - rules`"
    )
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")


# ✅ === VOLTAR AO PAINEL — LIMPA ESTADO E RECARREGA DO BANCO ===
async def cb_voltar_painel_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    ESTADOS_FLUXO.pop((chat_id, user_id), None)
    await enviar_painel_principal_bv(context, chat_id, query=query)


# ✅ === VER TEXTO ===
async def cb_ver_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    
    texto_salvo, _, _, _ = carregar_dados_bv(chat_id)
    
    if not texto_salvo or texto_salvo.strip() == "":
        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]])
        await query.message.edit_text("❌ Nenhum texto salvo.", reply_markup=teclado, parse_mode="Markdown")
        return
    
    class SimuladoUser:
        first_name = "Nome"
        last_name = "Sobrenome"
        id = user_id
        language_code = "pt"
        username = "usuario_teste"
        def mention_html(self):
            return f"<a href='tg://user?id={self.id}'>{self.first_name}</a>"
    
    usuario_simulado = SimuladoUser()
    texto_formatado = await montar_texto_formatado(context, chat_id, usuario_simulado)
    
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Apagar Texto", callback_data="bv_excluir_texto")],
        [InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]
    ])
    
    await query.message.edit_text(
        f"📄 **PRÉVIA DO TEXTO:**\n\n{texto_formatado}",
        reply_markup=teclado,
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ✅ === VER MÍDIA ===
async def cb_ver_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    
    _, midia, _, _ = carregar_dados_bv(chat_id)
    if not midia:
        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]])
        await query.message.edit_text("❌ Nenhuma mídia salva.", reply_markup=teclado, parse_mode="Markdown")
        return
    
    tipo, file_id, leg = midia
    teclado_acoes = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Apagar Mídia", callback_data="bv_excluir_midia")],
        [InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]
    ])
    
    if tipo == "photo":
        await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=f"📸 **Prévia da foto:**\n{leg or 'Sem legenda'}", reply_markup=teclado_acoes, parse_mode="Markdown")
    elif tipo == "video":
        await context.bot.send_video(chat_id=chat_id, video=file_id, caption=f"🎬 **Prévia do vídeo:**\n{leg or 'Sem legenda'}", reply_markup=teclado_acoes, parse_mode="Markdown")
    elif tipo == "sticker":
        await context.bot.send_sticker(chat_id=chat_id, sticker=file_id)
        await context.bot.send_message(chat_id=chat_id, text="🏷️ **Figurinha salva**", reply_markup=teclado_acoes, parse_mode="Markdown")
    
    try:
        await query.message.delete()
    except:
        pass


# ✅ === VER BOTÕES ===
async def cb_ver_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    
    _, _, botoes, _ = carregar_dados_bv(chat_id)
    
    if not botoes:
        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]])
        await query.message.edit_text("❌ Nenhum botão salvo.", reply_markup=teclado, parse_mode="Markdown")
        return
    
    await query.message.edit_text("🔲 **PRÉVIA DOS BOTÕES:**", reply_markup=botoes, parse_mode="Markdown")
    teclado_acoes = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Apagar Botões", callback_data="bv_excluir_botoes")],
        [InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]
    ])
    await query.message.reply_text("⬆️ Estes são os botões salvos!", reply_markup=teclado_acoes, parse_mode="Markdown")


# ✅ === EXCLUIR TEXTO — VOLTA COM AVISO ===
async def cb_excluir_texto_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    excluir_campo_bv(chat_id, "texto")
    await cb_voltar_painel_bv(update, context)


# ✅ === EXCLUIR MÍDIA — VOLTA COM AVISO ===
async def cb_excluir_midia_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    excluir_campo_bv(chat_id, "midia")
    await enviar_painel_principal_bv(context, chat_id, aviso_extra="✅ **MÍDIA APAGADA COM SUCESSO!**")


# ✅ === EXCLUIR BOTÕES — VOLTA COM AVISO ===
async def cb_excluir_botoes_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    excluir_campo_bv(chat_id, "botoes")
    await enviar_painel_principal_bv(context, chat_id, aviso_extra="✅ **BOTÕES APAGADOS COM SUCESSO!**")


# ✅ === VISUALIZAÇÃO COMPLETA ===
async def cb_ver_completa_bv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_user_admin(update, chat_id, user_id, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return
    
    class SimuladoUser:
        first_name = "Maria"
        last_name = "Silva"
        id = user_id
        language_code = "pt"
        username = "maria_silva"
        def mention_html(self):
            return f"<a href='tg://user?id={self.id}'>{self.first_name}</a>"
    
    usuario_simulado = SimuladoUser()
    texto_final = await montar_texto_formatado(context, chat_id, usuario_simulado)
    _, midia, botoes, _ = carregar_dados_bv(chat_id)
    
    teclado_voltar = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="bv_voltar_painel")]])
    
    if midia:
        tipo, file_id, leg = midia
        legenda = f"{leg or ''}\n\n{texto_final}".strip()
        if tipo == "photo":
            await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=legenda, reply_markup=botoes, parse_mode="HTML")
        elif tipo == "video":
            await context.bot.send_video(chat_id=chat_id, video=file_id, caption=legenda, reply_markup=botoes, parse_mode="HTML")
        elif tipo == "sticker":
            await context.bot.send_sticker(chat_id=chat_id, sticker=file_id)
            await context.bot.send_message(chat_id=chat_id, text=texto_final, reply_markup=botoes, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat_id, text=texto_final, reply_markup=botoes, parse_mode="HTML")
    
    await context.bot.send_message(chat_id=chat_id, text="✅ **Prévia COMPLETA enviada!**", reply_markup=teclado_voltar, parse_mode="Markdown")
    try:
        await query.message.delete()
    except:
        pass


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


# ✅ === CAPTURA E SALVA — AGORA SEMPRE VOLTA COM AVISO ===
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
    aviso = None
    
    if estado == "aguardando_texto_bv":
        texto = message.text or message.caption or ""
        salvar_no_mongo(chat.id, "texto", texto)
        aviso = "✅ **TEXTO SALVO COM SUCESSO!**"
    
    elif estado == "aguardando_midia_bv":
        legenda = message.caption or ""
        if message.photo:
            arquivo = message.photo[-1]
            salvar_no_mongo(chat.id, "midia", ("photo", arquivo.file_id, legenda))
            aviso = "✅ **FOTO SALVA COM SUCESSO!**" + (f"\n📝 Legenda: {legenda}" if legenda else "")
        elif message.video:
            arquivo = message.video
            salvar_no_mongo(chat.id, "midia", ("video", arquivo.file_id, legenda))
            aviso = "✅ **VÍDEO SALVO COM SUCESSO!**" + (f"\n📝 Legenda: {legenda}" if legenda else "")
        elif message.sticker:
            arquivo = message.sticker
            salvar_no_mongo(chat.id, "midia", ("sticker", arquivo.file_id, legenda))
            aviso = "✅ **FIGURINHA SALVA COM SUCESSO!**"
    
    elif estado == "aguardando_botoes_bv":
        texto = message.text or ""
        botoes = parsear_botoes(texto, context.bot.username)
        if botoes:
            salvar_no_mongo(chat.id, "botoes", botoes)
            aviso = "✅ **BOTÕES SALVOS COM SUCESSO!**"
        else:
            aviso = "⚠️ **Formato inválido!** Use: `Título - Link`"
    
    # ✅ APAGA A MENSAGEM DO USUÁRIO E MOSTRA O PAINEL COM AVISO
    try:
        await message.delete()
    except:
        pass
    
    if aviso:
        await enviar_painel_principal_bv(context, chat.id, aviso_extra=aviso)


# ✅ === TRATA TODOS OS BOTÕES ===
async def tratar_botoes_bemvindo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dados = update.callback_query.data
    
    if dados == "menu_adm":
        try:
            from comandos.menus import menu_adm_handler
            await menu_adm_handler(update, context)
        except Exception as e:
            logger.error(f"Erro voltando ao menu ADM: {e}")
            await update.callback_query.answer("❌ Voltando ao menu...", show_alert=False)
        return
    
    if dados == "bv_voltar_painel":
        await cb_voltar_painel_bv(update, context)
        return
    
    if dados == "bv_excluir_texto":
        await cb_excluir_texto_bv(update, context)
        return
    if dados == "bv_excluir_midia":
        await cb_excluir_midia_bv(update, context)
        return
    if dados == "bv_excluir_botoes":
        await cb_excluir_botoes_bv(update, context)
        return
    
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
    elif dados == "bv_ver_completa":
        await cb_ver_completa_bv(update, context)
    elif dados == "bv_cancelar":
        await cb_voltar_painel_bv(update, context)
    else:
        await update.callback_query.answer("❌ Função não encontrada!", show_alert=True)


def registrar_comandos_bv(application):
    application.add_handler(CommandHandler("bemvindo", cmd_bemvindo_painel, filters=~filters.ChatType.PRIVATE))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & ~filters.ChatType.PRIVATE, boas_vindas_handler))
    application.add_handler(MessageHandler(
        ~filters.COMMAND & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Sticker.ALL),
        capturar_fluxo_admin
    ))
    application.add_handler(CallbackQueryHandler(tratar_botoes_bemvindo, pattern="^(bv_|menu_adm)$"))
