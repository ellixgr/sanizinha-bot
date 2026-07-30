import os
import asyncio
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes, ChatMemberHandler, CallbackQueryHandler

# Importação de todos os módulos de proteção atualizados
from protecao.antilink import executar_antilink
from protecao.antimencao import executar_antimencao
from protecao.antiimagem import executar_antiimagem
from protecao.antifigu import executar_antifigu
from protecao.antitrava import executar_antitrava
from protecao.antiflod import executar_antiflod
from protecao.antiencaminhar import executar_antiencaminhar
from protecao.antienquete import executar_antienquete

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
        "antiflood": True,
        "antiencaminhar": True,
        "antienquete": True
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

async def obter_mencao_admins_str(chat, context: ContextTypes.DEFAULT_TYPE) -> str:
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

async def obter_menção_admins(chat, context: ContextTypes.DEFAULT_TYPE) -> str:
    return await obter_mencao_admins_str(chat, context)

async def apagar_aviso_futuro(context, mensagem):
    await asyncio.sleep(8)
    try:
        await mensagem.delete()
    except Exception:
        pass

def gerar_teclado_protecoes(cfg, chat_id_grupo=None):
    s_link = "🟢 Ligado" if cfg.get("antilink", True) else "🔴 Desligado"
    s_mencao = "🟢 Ligado" if cfg.get("antimencao", True) else "🔴 Desligado"
    s_foto = "🟢 Ligado" if cfg.get("antifoto", False) else "🔴 Desligado"
    s_figu = "🟢 Ligado" if cfg.get("antifigu", False) else "🔴 Desligado"
    s_trav = "🟢 Ligado" if cfg.get("antitravas", True) else "🔴 Desligado"
    s_flood = "🟢 Ligado" if cfg.get("antiflood", True) else "🔴 Desligado"
    s_encam = "🟢 Ligado" if cfg.get("antiencaminhar", True) else "🔴 Desligado"
    s_enq = "🟢 Ligado" if cfg.get("antienquete", True) else "🔴 Desligado"

    texto = "🛡️ **PAINEL DE STATUS E PROTEÇÕES DO GRUPO**"

    if chat_id_grupo:
        prefix = f"prot_priv_toggle_{chat_id_grupo}_"
        voltar_btn = InlineKeyboardButton("🔙 Voltar às Configurações", callback_data=f"config_grupo_{chat_id_grupo}")
    else:
        prefix = "prot_toggle_"
        voltar_btn = InlineKeyboardButton("🔙 Fechar Painel", callback_data="menu_fechar")

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔗 Anti-Link: {s_link}", callback_data=f"{prefix}antilink")],
        [InlineKeyboardButton(f"📢 Anti-Menção: {s_mencao}", callback_data=f"{prefix}antimencao")],
        [InlineKeyboardButton(f"📸 Anti-Foto: {s_foto}", callback_data=f"{prefix}antifoto")],
        [InlineKeyboardButton(f"🖼️ Anti-Figurinha: {s_figu}", callback_data=f"{prefix}antifigu")],
        [InlineKeyboardButton(f"⚠️ Anti-Travas: {s_trav}", callback_data=f"{prefix}antitravas")],
        [InlineKeyboardButton(f"⚡ Anti-Flood: {s_flood}", callback_data=f"{prefix}antiflood")],
        [InlineKeyboardButton(f"📤 Anti-Encaminhar: {s_encam}", callback_data=f"{prefix}antiencaminhar")],
        [InlineKeyboardButton(f"📊 Anti-Enquete: {s_enq}", callback_data=f"{prefix}antienquete")],
        [InlineKeyboardButton("⚙️ Configurar Punição", callback_data=(f"pun_priv_menu_{chat_id_grupo}" if chat_id_grupo else "menu_config_punicao"))],
        [voltar_btn]
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
    data = query.data

    # ========== PRIVADO: Alternar proteções ==========
    if data.startswith("prot_priv_toggle_"):
        partes = data.split("_")
        chat_id_grupo = int(partes[3])
        chave = partes[4]

        if not await is_admin(update, context, user_id, chat_id_grupo):
            await query.answer("⚠️ Apenas administradores!", show_alert=True)
            return

        cfg = obter_configs(chat_id_grupo)
        if chave in cfg:
            cfg[chave] = not cfg[chave]
            salvar_configs(chat_id_grupo, cfg)
            await query.answer("✅ Alterado!")
            texto, teclado = gerar_teclado_protecoes(cfg, chat_id_grupo)
            await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        return

    # ========== PRIVADO: Abrir menu punição ==========
    if data.startswith("pun_priv_menu_"):
        chat_id_grupo = int(data.split("_")[-1])
        if not await is_admin(update, context, user_id, chat_id_grupo):
            await query.answer("⚠️ Apenas administradores!", show_alert=True)
            return
        await enviar_painel_punicao_privado(update, context, chat_id_grupo)
        return

    # ========== GRUPO: Ações normais ==========
    if not await is_admin(update, context, user_id, chat_id):
        await query.answer("⚠️ Apenas administradores podem alterar as configurações!", show_alert=True)
        return

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

    if await is_admin(update, context, user.id, chat.id):
        return

    cfg = obter_configs(chat.id)

    if cfg.get("antiflood", True):
        if await executar_antiflod(update, context, chat, user, message, get_db, is_admin, obter_punicao, obter_menção_admins):
            return

    if cfg.get("antilink", True):
        if await executar_antilink(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    if cfg.get("antimencao", True):
        if await executar_antimencao(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    if cfg.get("antifoto", False):
        if await executar_antiimagem(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    if cfg.get("antifigu", False):
        if await executar_antifigu(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    if cfg.get("antitravas", True):
        if await executar_antitrava(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    if cfg.get("antiencaminhar", True):
        if await executar_antiencaminhar(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
            return

    if cfg.get("antienquete", True):
        if await executar_antienquete(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
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

# ═══════════════════════════════════════════
# ✅ FUNÇÕES DE CONFIGURAÇÃO PELO PRIVADO
# ═══════════════════════════════════════════

async def enviar_painel_protecoes_privado(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id_grupo: int):
    """Abre painel de proteções de um grupo pelo privado do bot"""
    query = update.callback_query
    uid = update.effective_user.id

    if not await is_admin(update, context, uid, chat_id_grupo):
        await query.answer("⚠️ Apenas administradores!", show_alert=True)
        return

    cfg = obter_configs(chat_id_grupo)
    texto, teclado = gerar_teclado_protecoes(cfg, chat_id_grupo)
    
    await query.answer()
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def enviar_painel_punicao_privado(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id_grupo: int):
    """Abre painel de punição de um grupo pelo privado do bot"""
    query = update.callback_query
    uid = update.effective_user.id

    if not await is_admin(update, context, uid, chat_id_grupo):
        await query.answer("⚠️ Apenas administradores!", show_alert=True)
        return

    punicao = obter_punicao(chat_id_grupo)
    acoes_nomes = {
        "aviso_ban": "⚠️ 1º Aviso, 2º Banimento",
        "remover": "🔨 Remover / Banir Direto",
        "silenciar": "🔇 Silenciar (Mute)"
    }
    nome_acao_atual = acoes_nomes.get(punicao["acao"], "⚠️ 1º Aviso, 2º Banimento")
    status_apagar = "🟢 Sim" if punicao["apagar_msg"] else "🔴 Não"
    tempo_str = f"{punicao['tempo_mute']} minuto(s)"

    texto = (
        f"⚙️ **CONFIGURAR PUNIÇÃO**\n\n"
        f"📌 **Tipo de Punição:** `{nome_acao_atual}`\n"
        f"🗑️ **Apagar Mensagem:** `{status_apagar}`\n"
        f"⏱️ **Tempo de Silenciamento:** `{tempo_str}`"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📌 Tipo: {nome_acao_atual}", callback_data=f"pun_priv_trocar_{chat_id_grupo}")],
        [InlineKeyboardButton(f"🗑️ Apagar: {status_apagar}", callback_data=f"pun_priv_apagar_{chat_id_grupo}")],
        [
            InlineKeyboardButton("➖", callback_data=f"pun_priv_menos_{chat_id_grupo}"),
            InlineKeyboardButton(f"⏱️ {punicao['tempo_mute']}min", callback_data="pun_ignorar"),
            InlineKeyboardButton("➕", callback_data=f"pun_priv_mais_{chat_id_grupo}")
        ],
        [InlineKeyboardButton("🔙 Voltar", callback_data=f"config_grupo_{chat_id_grupo}")]
    ])

    await query.answer()
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def processar_callback_punicao_privado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    uid = update.effective_user.id

    partes = data.split("_")
    chat_id_grupo = int(partes[-1])
    acao = "_".join(partes[:-1])

    if not await is_admin(update, context, uid, chat_id_grupo):
        await query.answer("⚠️ Apenas administradores!", show_alert=True)
        return

    if acao == "pun_priv_trocar":
        p = obter_punicao(chat_id_grupo)
        ciclo = {"aviso_ban": "remover", "remover": "silenciar", "silenciar": "aviso_ban"}
        p["acao"] = ciclo.get(p["acao"], "aviso_ban")
        salvar_punicao(chat_id_grupo, p)
        await query.answer("✅ Tipo alterado!")
        await enviar_painel_punicao_privado(update, context, chat_id_grupo)

    elif acao == "pun_priv_apagar":
        p = obter_punicao(chat_id_grupo)
        p["apagar_msg"] = not p["apagar_msg"]
        salvar_punicao(chat_id_grupo, p)
        await query.answer("✅ Alterado!")
        await enviar_painel_punicao_privado(update, context, chat_id_grupo)

    elif acao == "pun_priv_menos":
        p = obter_punicao(chat_id_grupo)
        if p["tempo_mute"] > 1:
            p["tempo_mute"] -= 1
            salvar_punicao(chat_id_grupo, p)
            await query.answer(f"⏱️ {p['tempo_mute']} min")
        else:
            await query.answer("Mínimo 1 min!", show_alert=True)
        await enviar_painel_punicao_privado(update, context, chat_id_grupo)

    elif acao == "pun_priv_mais":
        p = obter_punicao(chat_id_grupo)
        if p["tempo_mute"] < 1440:
            p["tempo_mute"] += 1
            salvar_punicao(chat_id_grupo, p)
            await query.answer(f"⏱️ {p['tempo_mute']} min")
        else:
            await query.answer("Máximo 1440 min!", show_alert=True)
        await enviar_painel_punicao_privado(update, context, chat_id_grupo)

def registrar_protecoes(app):
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stts", cmd_status))
    app.add_handler(MessageHandler(~filters.StatusUpdate.ALL, monitorar_seguranca), group=1)
    app.add_handler(ChatMemberHandler(limpar_dados_grupo_removido, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(processar_callback_protecao, pattern="^(prot_toggle_|menu_|pun_tempo_|pun_toggle_|pun_trocar_|prot_priv_toggle_|pun_priv_menu_)"))
    app.add_handler(CallbackQueryHandler(processar_callback_punicao_privado, pattern="^pun_priv_"))
