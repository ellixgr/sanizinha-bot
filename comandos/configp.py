import os
import time  # ✅ FALTAVA ESSE IMPORT!
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

MONGO_URI = os.environ.get("MONGO_URI")
DONO_ID = os.environ.get("DONO_ID")

def get_db():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)["sanizinhabot_db"]


# ==============================================
# ✅ VERIFICA SE O USUÁRIO TEM LICENÇA ATIVA
# ==============================================
async def tem_licenca_ativa(user_id: int) -> bool:
    try:
        db = get_db()
        agora = time.time()
        licenca = db["licencas_aluguel"].find_one({"user_id": user_id, "ativo": True, "expira_em": {"$gt": agora}})
        return bool(licenca)
    except Exception:
        return False


# ==============================================
# ✅ VERIFICA SE USUÁRIO É ADM EM UM CHAT
# ==============================================
async def e_adm_no_chat(bot, chat_id: int, user_id: int) -> bool:
    try:
        membro = await bot.get_chat_member(chat_id, user_id)
        return membro.status in ["administrator", "creator"]
    except Exception:
        return False


# ==============================================
# ✅ LISTA GRUPOS: CADASTRO + ONDE É ADM
# ==============================================
async def listar_grupos_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    bot = context.bot

    # ✅ VERIFICA LICENÇA (exceto DONO)
    eh_dono = (DONO_ID and str(user_id) == str(DONO_ID))
    if not eh_dono and not await tem_licenca_ativa(user_id):
        await query.answer("⚠️ Você precisa alugar o bot para usar essa função!", show_alert=True)
        return

    db = get_db()
    agora = time.time()

    # ✅ PEGA GRUPOS CADASTRADOS E ATIVOS DO USUÁRIO
    grupos_cadastrados = list(db["grupos_autorizados"].find({
        "registrado_por": user_id,
        "ativo": True,
        "expira_em": {"$gt": agora}
    }))

    if not grupos_cadastrados:
        texto = (
            "📋 **Nenhum grupo encontrado!**\n\n"
            "Use o comando /addgrupo dentro do seu grupo para cadastrar e poder configurá-lo aqui."
        )
        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]])
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        await query.answer()
        return

    # ✅ FILTRA SÓ OS QUE O USUÁRIO AINDA É ADM
    grupos_validos = []
    for g in grupos_cadastrados:
        chat_id = g["chat_id"]
        if await e_adm_no_chat(bot, chat_id, user_id):
            grupos_validos.append(g)

    if not grupos_validos:
        texto = (
            "⚠️ **Você não é mais administrador em nenhum grupo cadastrado.**\n\n"
            "Verifique suas permissões nos grupos ou cadastre novos."
        )
        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]])
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        await query.answer()
        return

    # ✅ MONTA A LISTA COM BOTÕES
    texto = f"⚙️ **SEUS GRUPOS ({len(grupos_validos)}) — ONDE VOCÊ É ADM:**\n\nEscolha um grupo abaixo:\n"
    botoes = []

    for grupo in grupos_validos:
        chat_id = grupo["chat_id"]
        nome = grupo.get("nome_grupo", f"Grupo {chat_id}")
        botoes.append([InlineKeyboardButton(f"🏢 {nome}", callback_data=f"config_grupo_{chat_id}")])

    botoes.append([InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu_principal")])
    teclado = InlineKeyboardMarkup(botoes)

    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    await query.answer()


# ==============================================
# ✅ PAINEL DO GRUPO ESCOLHIDO
# ==============================================
async def painel_config_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data
    user_id = update.effective_user.id

    chat_id = int(dados.replace("config_grupo_", ""))
    eh_dono = (DONO_ID and str(user_id) == str(DONO_ID))

    if not eh_dono and not await tem_licenca_ativa(user_id):
        await query.answer("⚠️ Licença necessária!", show_alert=True)
        return

    db = get_db()
    grupo = db["grupos_autorizados"].find_one({"chat_id": chat_id, "registrado_por": user_id})
    if not grupo:
        await query.answer("⚠️ Grupo não encontrado ou não pertence a você!", show_alert=True)
        return

    nome_grupo = grupo.get("nome_grupo", f"Grupo {chat_id}")

    texto = (
        f"⚙️ **CONFIGURANDO: {nome_grupo}**\n\n"
        "Escolha o que deseja configurar:"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👋 Mensagem de Bem-Vindo", callback_data=f"config_bemvindo_{chat_id}")],
        [InlineKeyboardButton("🛡️ Configurar Proteções", callback_data=f"config_protecao_{chat_id}")],
        [InlineKeyboardButton("🔙 Voltar aos Grupos", callback_data="menu_config_grupos")]
    ])

    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    await query.answer()


# ==============================================
# ✅ ABRIR CONFIGURAÇÃO DE BOAS-VINDAS
# ==============================================
async def abrir_bemvindo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data
    chat_id = int(dados.replace("config_bemvindo_", ""))

    await query.answer("Abrindo configuração de Boas-Vindas...")
    from comandos.bemvindo import enviar_painel_principal_bv
    await enviar_painel_principal_bv(context, chat_id, query=query)


# ==============================================
# ✅ ABRIR CONFIGURAÇÃO DE PROTEÇÕES
# ==============================================
async def abrir_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data
    chat_id = int(dados.replace("config_protecao_", ""))

    await query.answer("Abrindo configuração de Proteções...")

    db = get_db()
    cfg = db["configuracoes_grupo"].find_one({"chat_id": chat_id}) or {}

    antilink_status = "✅ Ativo" if cfg.get("antilink", True) else "❌ Desativado"
    antifigu_status = "✅ Ativo" if cfg.get("antifigu", True) else "❌ Desativado"
    antiimagem_status = "✅ Ativo" if cfg.get("antiimagem", True) else "❌ Desativado"
    antienquete_status = "✅ Ativo" if cfg.get("antienquete", True) else "❌ Desativado"
    antiencaminhar_status = "✅ Ativo" if cfg.get("antiencaminhar", True) else "❌ Desativado"
    antimencao_status = "✅ Ativo" if cfg.get("antimencao", True) else "❌ Desativado"
    antiflod_status = "✅ Ativo" if cfg.get("antiflod", True) else "❌ Desativado"

    acao = cfg.get("acao_padrao", "aviso_ban")
    acao_texto = {
        "aviso_ban": "⚠️ Aviso → Banir",
        "remover": "🚫 Banir Direto",
        "silenciar": "🔇 Silenciar"
    }.get(acao, acao)
    tempo_mute = cfg.get("tempo_mute_padrao", 5)

    texto = (
        "🛡️ **CONFIGURAÇÕES DE PROTEÇÃO**\n\n"
        f"🔗 Anti-Link: {antilink_status}\n"
        f"🖼️ Anti-Figurinha: {antifigu_status}\n"
        f"📷 Anti-Imagem: {antiimagem_status}\n"
        f"📊 Anti-Enquete: {antienquete_status}\n"
        f"➡️ Anti-Encaminhar: {antiencaminhar_status}\n"
        f"👤 Anti-Menção: {antimencao_status}\n"
        f"🔊 Anti-Flood: {antiflod_status}\n\n"
        f"⚖️ Punição: {acao_texto}\n⏱️ Tempo Mute: {tempo_mute}min"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Link", callback_data=f"toggle_priv_antilink_{chat_id}"),
         InlineKeyboardButton("🖼️ Figurinha", callback_data=f"toggle_priv_antifigu_{chat_id}")],
        [InlineKeyboardButton("📷 Imagem", callback_data=f"toggle_priv_antiimagem_{chat_id}"),
         InlineKeyboardButton("📊 Enquete", callback_data=f"toggle_priv_antienquete_{chat_id}")],
        [InlineKeyboardButton("➡️ Encaminhar", callback_data=f"toggle_priv_antiencaminhar_{chat_id}"),
         InlineKeyboardButton("👤 Menção", callback_data=f"toggle_priv_antimencao_{chat_id}")],
        [InlineKeyboardButton("🔊 Flood", callback_data=f"toggle_priv_antiflod_{chat_id}")],
        [InlineKeyboardButton("⚙️ Escolher Punição", callback_data=f"menu_punicao_priv_{chat_id}")],
        [InlineKeyboardButton("🔙 Voltar ao Grupo", callback_data=f"config_grupo_{chat_id}")]
    ])

    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")


# ==============================================
# ✅ CENTRAL DE BOTÕES DO CONFIGP.PY
# ==============================================
async def tratar_botoes_configp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dados = update.callback_query.data

    if dados == "menu_config_grupos":
        await listar_grupos_usuario(update, context)
        return

    if dados.startswith("config_grupo_"):
        await painel_config_grupo(update, context)
        return

    if dados.startswith("config_bemvindo_"):
        await abrir_bemvindo(update, context)
        return

    if dados.startswith("config_protecao_"):
        await abrir_protecoes(update, context)
        return

    # ✅ ALTERNAR PROTEÇÕES
    if dados.startswith("toggle_priv_"):
        partes = dados.replace("toggle_priv_", "").rsplit("_", 1)
        tipo = partes[0]
        chat_id = int(partes[1])
        db = get_db()
        cfg = db["configuracoes_grupo"].find_one({"chat_id": chat_id}) or {}
        novo = not cfg.get(tipo, True)
        db["configuracoes_grupo"].update_one({"chat_id": chat_id}, {"$set": {tipo: novo}}, upsert=True)
        await abrir_protecoes(update, context)
        return

    # ✅ ESCOLHER PUNIÇÃO
    if dados.startswith("menu_punicao_priv_"):
        chat_id = int(dados.replace("menu_punicao_priv_", ""))
        texto = "⚖️ **ESCOLHA A PUNIÇÃO:**"
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ Aviso → Banir", callback_data=f"def_pun_aviso_{chat_id}")],
            [InlineKeyboardButton("🚫 Banir Direto", callback_data=f"def_pun_remover_{chat_id}")],
            [InlineKeyboardButton("🔇 Silenciar", callback_data=f"def_pun_mutar_{chat_id}")],
            [InlineKeyboardButton("🔙 Voltar", callback_data=f"config_protecao_{chat_id}")]
        ])
        await update.callback_query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        return

    # ✅ DEFINIR PUNIÇÃO
    if dados.startswith("def_pun_"):
        partes = dados.replace("def_pun_", "").rsplit("_", 1)
        tipo = partes[0]
        chat_id = int(partes[1])
        mapa = {"aviso": "aviso_ban", "remover": "remover", "mutar": "silenciar"}
        acao = mapa.get(tipo, "aviso_ban")
        db = get_db()
        db["configuracoes_grupo"].update_one(
            {"chat_id": chat_id},
            {"$set": {"acao_padrao": acao, "tempo_mute_padrao": 5}},
            upsert=True
        )
        await update.callback_query.answer("✅ Punição definida!", show_alert=True)
        await abrir_protecoes(update, context)
        return


def registrar_configp(app):
    app.add_handler(CallbackQueryHandler(
        tratar_botoes_configp,
        pattern="^(menu_config_grupos|config_grupo_|config_bemvindo_|config_protecao_|toggle_priv_|menu_punicao_priv_|def_pun_)"
    ))
