import os
import asyncio
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes, ChatMemberHandler

# Importação dos módulos antis autônomos
from antilink import executar_antilink
from antimencao import executar_antimencao
from antiimagem import executar_antiimagem
from antifigu import executar_antifigu
from antitrava import executar_antitrava
from antiflod import executar_antiflod

def get_db():
    mongo_uri = os.environ.get("MONGO_URI")
    client = MongoClient(
        mongo_uri, 
        serverSelectionTimeoutMS=1000, 
        connectTimeoutMS=1000,
        tlsAllowInvalidCertificates=True
    )
    return client["sanizinhabot_db"]

def obter_configs(chat_id: int):
    padrao = {
        "antilink": True,
        "antimencao": True,
        "antifoto": False,
        "antifigu": False,
        "antitravas": True,
        "antiflood": True
    }
    try:
        db = get_db()
        doc = db["configs_protecao"].find_one({"chat_id": chat_id})
        if doc and "configs" in doc:
            cfg = doc["configs"]
            for k, v in padrao.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception:
        pass
    return padrao

def salvar_configs(chat_id: int, cfg: dict):
    try:
        db = get_db()
        db["configs_protecao"].update_one(
            {"chat_id": chat_id},
            {"$set": {"configs": cfg}},
            upsert=True
        )
    except Exception:
        pass

def obter_punicao(chat_id: int):
    padrao = {
        "acao": "aviso_ban",
        "apagar_msg": True,
        "tempo_mute": 1
    }
    try:
        db = get_db()
        doc = db["configs_protecao"].find_one({"chat_id": chat_id})
        if doc and "punicao" in doc:
            p = doc["punicao"]
            for k, v in padrao.items():
                if k not in p:
                    p[k] = v
            return p
    except Exception:
        pass
    return padrao

def salvar_punicao(chat_id: int, punicao: dict):
    try:
        db = get_db()
        db["configs_protecao"].update_one(
            {"chat_id": chat_id},
            {"$set": {"punicao": punicao}},
            upsert=True
        )
    except Exception:
        pass

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int) -> bool:
    if chat_id > 0:  
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ["creator", "administrator"]:
            return True
    except Exception:
        pass
    return False

async def obter_menção_admins(chat, context: ContextTypes.DEFAULT_TYPE) -> str:
    try:
        admins = await chat.get_administrators()
        mencoes = []
        for adm in admins:
            if not adm.user.is_bot:
                mencoes.append(adm.user.mention_html("adm"))
        if mencoes:
            return " ".join(mencoes)
    except Exception:
        pass
    return "@adm"

async def apagar_aviso_futuro(context, mensagem):
    await asyncio.sleep(8)
    try:
        await mensagem.delete()
    except Exception:
        pass

def gerar_teclado_protecoes(cfg):
    s_link = "🟢 Ligado" if cfg.get("antilink", True) else "🔴 Desligado"
    s_mencao = "🟢 Ligado" if cfg.get("antimencao", True) else "🔴 Desligado"
    s_foto = "🟢 Ligado" if cfg.get("antifoto", False) else "🔴 Desligado"
    s_figu = "🟢 Ligado" if cfg.get("antifigu", False) else "🔴 Desligado"
    s_trav = "🟢 Ligado" if cfg.get("antitravas", True) else "🔴 Desligado"
    s_flood = "🟢 Ligado" if cfg.get("antiflood", True) else "🔴 Desligado"

    texto = "🛡️ **PAINEL DE STATUS E PROTEÇÕES DO GRUPO**"

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔗 Anti-Link: {s_link}", callback_data="prot_toggle_antilink")],
        [InlineKeyboardButton(f"📢 Anti-Menção: {s_mencao}", callback_data="prot_toggle_antimencao")],
        [InlineKeyboardButton(f"📸 Anti-Foto: {s_foto}", callback_data="prot_toggle_antifoto")],
        [InlineKeyboardButton(f"🖼️ Anti-Figurinha: {s_figu}", callback_data="prot_toggle_antifigu")],
        [InlineKeyboardButton(f"⚠️ Anti-Travas: {s_trav}", callback_data="prot_toggle_antitravas")],
        [InlineKeyboardButton(f"⚡ Anti-Flood: {s_flood}", callback_data="prot_toggle_antiflood")],
        [InlineKeyboardButton("⚙️ Configurar Punição", callback_data="menu_config_punicao")],
        [InlineKeyboardButton("🔙 Fechar Painel", callback_data="menu_fechar")]
    ])
    return texto, teclado

async def enviar_painel_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    query = update.callback_query

    if not await is_admin(update, context, user_id, chat_id):
        if query:
            await query.answer("⚠️ Apenas administradores podem mexer nas proteções!", show_alert=True)
        return

    cfg = obter_configs(chat_id)
    texto, teclado = gerar_teclado_protecoes(cfg)

    if query:
        await query.answer()
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    else:
        if update.message:
            await update.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def enviar_painel_punicao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(update, context, user_id, chat_id):
        if query:
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
        f"📌 **Tipo de Punição:** `{nome_acao_atual}`\n"
        f"🗑️ **Apagar Mensagem Infratora:** `{status_apagar}`\n"
        f"⏱️ **Tempo de Silenciamento:** `{tempo_str}`"
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

    if query:
        await query.answer()
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def processar_callback_protecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

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
            salvar_configs(chat_id, cfg)
            await query.answer("Status alterado com sucesso!")
            texto, teclado = gerar_teclado_protecoes(cfg)
            await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

    elif data == "menu_config_punicao":
        await enviar_painel_punicao(update, context)

    elif data == "menu_protecoes":
        await enviar_painel_protecoes(update, context)

    elif data == "menu_fechar":
        try:
            await query.message.delete()
        except Exception:
            await query.answer("Painel fechado!")

    elif data == "pun_toggle_apagar":
        p = obter_punicao(chat_id)
        p["apagar_msg"] = not p["apagar_msg"]
        salvar_punicao(chat_id, p)
        await query.answer("Configuração alterada!")
        await enviar_painel_punicao(update, context)

    elif data == "pun_trocar_acao":
        p = obter_punicao(chat_id)
        ciclo = {"aviso_ban": "remover", "remover": "silenciar", "silenciar": "aviso_ban"}
        p["acao"] = ciclo.get(p["acao"], "aviso_ban")
        salvar_punicao(chat_id, p)
        await query.answer("Modo de punição alterado!")
        await enviar_painel_punicao(update, context)

    elif data == "pun_tempo_menos":
        p = obter_punicao(chat_id)
        if p["tempo_mute"] > 1:
            p["tempo_mute"] -= 1
            salvar_punicao(chat_id, p)
            await query.answer(f"Tempo reduzido para {p['tempo_mute']} min")
        else:
            await query.answer("O tempo mínimo é 1 minuto!", show_alert=False)
        await enviar_painel_punicao(update, context)

    elif data == "pun_tempo_mais":
        p = obter_punicao(chat_id)
        if p["tempo_mute"] < 1440:
            p["tempo_mute"] += 1
            salvar_punicao(chat_id, p)
            await query.answer(f"Tempo aumentado para {p['tempo_mute']} min")
        else:
            await query.answer("O tempo máximo é 1440 minutos!", show_alert=False)
        await enviar_painel_punicao(update, context)

    elif data == "pun_ignorar":
        await query.answer("Use os botões ➕ e ➖ para ajustar.", show_alert=False)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    if not chat or not user or chat.type == "private" or not message:
        return

    # Admins passam livremente
    if await is_admin(update, context, user.id, chat.id):
        return

    cfg = obter_configs(chat.id)

    # 1. Anti-Flood
    if cfg.get("antiflood", True):
        if await executar_antiflod(update, context, chat, user, message, get_db, is_admin, obter_punicao, obter_menção_admins):
            return

    # 2. Anti-Link
    if cfg.get("antilink", True):
        if await executar_antilink(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    # 3. Anti-Menção
    if cfg.get("antimencao", True):
        if await executar_antimencao(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    # 4. Anti-Foto
    if cfg.get("antifoto", False):
        if await executar_antiimagem(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    # 5. Anti-Figurinha
    if cfg.get("antifigu", False):
        if await executar_antifigu(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    # 6. Anti-Travas
    if cfg.get("antitravas", True):
        if await executar_antitrava(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

async def limpar_dados_grupo_removido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    
    chat = update.effective_chat
    novo_status = result.new_chat_member.status
    
    if novo_status in ["left", "kicked"]:
        try:
            db = get_db()
            db["configs_protecao"].delete_one({"chat_id": chat.id})
            db["avisos_usuarios"].delete_many({"chat_id": chat.id})
        except Exception:
            pass

def registrar_protecoes(app):
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stts", cmd_status))
    app.add_handler(MessageHandler(~filters.StatusUpdate.ALL, monitorar_seguranca), group=1)
    app.add_handler(ChatMemberHandler(limpar_dados_grupo_removido, ChatMemberHandler.MY_CHAT_MEMBER))
