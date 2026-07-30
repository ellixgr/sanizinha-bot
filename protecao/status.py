# ==============================================
# STATUS.PY — CORRIGIDO E COMPLETO
# ==============================================

# ✅ IMPORTA TODAS AS FUNÇÕES DE PROTEÇÃO
from protecao.antilink import executar_antilink
from protecao.antifigu import executar_antifigu
from protecao.antiimagem import executar_antiimagem
from protecao.antienquete import executar_antienquete
from protecao.antiencaminhar import executar_antiencaminhar
from protecao.antimencao import executar_antimencao
from protecao.antiflod import executar_antiflod, REGISTRO_FLOOD, BLOQUEADOS

import time
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# ==============================================
# FUNÇÃO PRINCIPAL: OBTER PUNIÇÃO DO GRUPO
# ==============================================
def obter_punicao(chat_id, get_db=None):
    """Retorna as regras de punição configuradas para o grupo"""
    if not get_db:
        return {
            "apagar_msg": True,
            "acao": "aviso_ban",
            "tempo_mute": 5
        }
    db = get_db()
    cfg = db["configuracoes_grupo"].find_one({"chat_id": chat_id}) or {}
    return {
        "apagar_msg": cfg.get("apagar_msg", True),
        "acao": cfg.get("acao_padrao", "aviso_ban"),
        "tempo_mute": cfg.get("tempo_mute_padrao", 5)
    }

# ==============================================
# SALVAR CONFIGURAÇÃO DE PUNIÇÃO
# ==============================================
def salvar_punicao(chat_id, dados, get_db):
    """Salva/atualiza as regras de punição do grupo"""
    db = get_db()
    db["configuracoes_grupo"].update_one(
        {"chat_id": chat_id},
        {"$set": dados},
        upsert=True
    )

# ==============================================
# MONTAR MENÇÃO DE ADMINS
# ==============================================
def obter_mencao_admins_str(chat_id, context, limite=5):
    """Retorna lista de menções dos administradores do grupo"""
    mencoes = []
    try:
        administradores = context.bot.get_chat_administrators(chat_id)
        for adm in administradores:
            if adm.user.is_bot:
                continue
            if adm.user.username:
                mencoes.append(f"@{adm.user.username}")
            else:
                mencoes.append(adm.user.mention_html())
            if len(mencoes) >= limite:
                break
    except Exception:
        pass
    return ", ".join(mencoes) if mencoes else ""

# ==============================================
# FUNÇÃO PARA APAGAR AVISO APÓS TEMPO
# ==============================================
async def apagar_aviso_futuro(context, mensagem, segundos=30):
    """Apaga mensagem de aviso após X segundos"""
    import asyncio
    await asyncio.sleep(segundos)
    try:
        await mensagem.delete()
    except Exception:
        pass

# ==============================================
# VERIFICAR TODAS AS PROTEÇÕES DE UMA VEZ
# ==============================================
async def verificar_todas_protecoes(update, context, chat, user, message, get_db, is_admin):
    """Executa TODAS as verificações de proteção na mensagem"""
    agora = time.time()
    punicao = obter_punicao(chat.id, get_db)

    # ✅ ANTI-FLOOD
    bloqueado = await executar_antiflod(
        update, context, chat, user, message,
        get_db, is_admin, obter_punicao, obter_mencao_admins_str
    )
    if bloqueado:
        return True

    # ✅ ANTI-LINK
    bloqueado = await executar_antilink(
        update, context, chat, user, message,
        get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro
    )
    if bloqueado:
        return True

    # ✅ ANTI-FIGURINHA
    bloqueado = await executar_antifigu(
        update, context, chat, user, message,
        get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro
    )
    if bloqueado:
        return True

    # ✅ ANTI-IMAGEM/FOTO
    bloqueado = await executar_antiimagem(
        update, context, chat, user, message,
        get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro
    )
    if bloqueado:
        return True

    # ✅ ANTI-ENQUETE
    bloqueado = await executar_antienquete(
        update, context, chat, user, message,
        get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro
    )
    if bloqueado:
        return True

    # ✅ ANTI-ENCAMINHAMENTO
    bloqueado = await executar_antiencaminhar(
        update, context, chat, user, message,
        get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro
    )
    if bloqueado:
        return True

    # ✅ ANTI-MENÇÃO DE BOTS EXTERNOS
    bloqueado = await executar_antimencao(
        update, context, chat, user, message,
        get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro
    )
    if bloqueado:
        return True

    # Nenhuma proteção acionada
    return False

# ==============================================
# EXTRAIR DADOS DE STATUS DAS PROTEÇÕES
# ==============================================
def coletar_dados_status(chat_id, get_db):
    """Coleta todos os dados de proteção para exibir no painel"""
    db = get_db()
    agora = time.time()

    # Configurações do grupo
    cfg = db["configuracoes_grupo"].find_one({"chat_id": chat_id}) or {}

    # Contagem de avisos por usuário
    avisos = list(db["avisos_usuarios"].find({"chat_id": chat_id}))
    total_avisos = len(avisos)
    usuarios_com_avisos = [a["user_id"] for a in avisos]

    # Usuários bloqueados no momento (anti-flood)
    bloqueados_agora = [
        {"user_id": chave[1], "expira_em": expira}
        for chave, expira in BLOQUEADOS.items()
        if chave[0] == chat_id and agora < expira
    ]

    return {
        "configuracoes": cfg,
        "total_avisos_registrados": total_avisos,
        "usuarios_com_avisos": usuarios_com_avisos,
        "usuarios_bloqueados_agora": bloqueados_agora,
        "qtd_bloqueados": len(bloqueados_agora)
    }

# ==============================================
# COMANDO /STTS — PAINEL DE PROTEÇÕES
# ==============================================
async def cmd_stts(update: Update, context: ContextTypes.DEFAULT_TYPE, get_db, verificar_se_e_adm):
    """Comando /stts — Exibe e gerencia configurações do grupo"""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ Use este comando no grupo!")
        return

    if not await verificar_se_e_adm(update, context):
        await update.message.reply_text("⚠️ Apenas administradores podem usar este comando!")
        return

    db = get_db()
    cfg = db["configuracoes_grupo"].find_one({"chat_id": chat.id}) or {}
    dados = coletar_dados_status(chat.id, get_db)

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
        "remover": "🚫 Remover/Banir Direto",
        "silenciar": "🔇 Silenciar"
    }.get(acao, acao)
    tempo_mute = cfg.get("tempo_mute_padrao", 5)

    texto = (
        "🛡️ **PAINEL DE PROTEÇÕES DO GRUPO**\n\n"
        f"🔗 Anti-Link: {antilink_status}\n"
        f"🖼️ Anti-Figurinha: {antifigu_status}\n"
        f"📷 Anti-Imagem: {antiimagem_status}\n"
        f"📊 Anti-Enquete: {antienquete_status}\n"
        f"➡️ Anti-Encaminhar: {antiencaminhar_status}\n"
        f"👤 Anti-Menção Bot: {antimencao_status}\n"
        f"🔊 Anti-Flood: {antiflod_status}\n\n"
        f"⚖️ **Punição Padrão:** {acao_texto}\n"
        f"⏱️ **Tempo de Mute:** {tempo_mute} minutos\n\n"
        f"📊 Usuários com avisos: {dados['total_avisos_registrados']}\n"
        f"🚫 Bloqueados agora: {dados['qtd_bloqueados']}"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Anti-Link", callback_data="toggle_antilink"),
         InlineKeyboardButton("🖼️ Figurinha", callback_data="toggle_antifigu")],
        [InlineKeyboardButton("📷 Imagem", callback_data="toggle_antiimagem"),
         InlineKeyboardButton("📊 Enquete", callback_data="toggle_antienquete")],
        [InlineKeyboardButton("➡️ Encaminhar", callback_data="toggle_antiencaminhar"),
         InlineKeyboardButton("👤 Menção", callback_data="toggle_antimencao")],
        [InlineKeyboardButton("🔊 Flood", callback_data="toggle_antiflod")],
        [InlineKeyboardButton("⚙️ Escolher Punição", callback_data="menu_punicao")],
        [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu_principal")]
    ])
    await update.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")

# ==============================================
# TRATAR BOTÕES DE CONFIGURAÇÃO DO GRUPO
# ==============================================
async def tratar_botoes_config(update: Update, context: ContextTypes.DEFAULT_TYPE, get_db, verificar_se_e_adm):
    """Trata todos os cliques nos botões de configuração do grupo"""
    query = update.callback_query
    dados = query.data
    chat = update.effective_chat

    if not await verificar_se_e_adm(update, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return

    db = get_db()

    # ✅ LIGA/DESLIGA PROTEÇÕES
    if dados.startswith("toggle_"):
        tipo = dados.replace("toggle_", "")
        cfg = db["configuracoes_grupo"].find_one({"chat_id": chat.id}) or {}
        novo = not cfg.get(tipo, True)
        db["configuracoes_grupo"].update_one(
            {"chat_id": chat.id},
            {"$set": {tipo: novo}},
            upsert=True
        )
        status = "✅ ATIVADO" if novo else "❌ DESATIVADO"
        await query.answer(f"{tipo.upper()} {status}!")
        # Recarrega exibição
        cfg = db["configuracoes_grupo"].find_one({"chat_id": chat.id}) or {}
        antilink_status = "✅ Ativo" if cfg.get("antilink", True) else "❌ Desativado"
        antifigu_status = "✅ Ativo" if cfg.get("antifigu", True) else "❌ Desativado"
        antiimagem_status = "✅ Ativo" if cfg.get("antiimagem", True) else "❌ Desativado"
        antienquete_status = "✅ Ativo" if cfg.get("antienquete", True) else "❌ Desativado"
        antiencaminhar_status = "✅ Ativo" if cfg.get("antiencaminhar", True) else "❌ Desativado"
        antimencao_status = "✅ Ativo" if cfg.get("antimencao", True) else "❌ Desativado"
        antiflod_status = "✅ Ativo" if cfg.get("antiflod", True) else "❌ Desativado"
        texto = (
            "🛡️ **CONFIGURAÇÕES DO GRUPO**\n\n"
            f"🔗 Anti-Link: {antilink_status}\n"
            f"🖼️ Anti-Figurinha: {antifigu_status}\n"
            f"📷 Anti-Imagem: {antiimagem_status}\n"
            f"📊 Anti-Enquete: {antienquete_status}\n"
            f"➡️ Anti-Encaminhar: {antiencaminhar_status}\n"
            f"👤 Anti-Menção: {antimencao_status}\n"
            f"🔊 Anti-Flood: {antiflod_status}"
        )
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Link", callback_data="toggle_antilink"), InlineKeyboardButton("🖼️ Figurinha", callback_data="toggle_antifigu")],
            [InlineKeyboardButton("📷 Imagem", callback_data="toggle_antiimagem"), InlineKeyboardButton("📊 Enquete", callback_data="toggle_antienquete")],
            [InlineKeyboardButton("➡️ Encaminhar", callback_data="toggle_antiencaminhar"), InlineKeyboardButton("👤 Menção", callback_data="toggle_antimencao")],
            [InlineKeyboardButton("🔊 Flood", callback_data="toggle_antiflod")],
            [InlineKeyboardButton("⚙️ Escolher Punição", callback_data="menu_punicao")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="menu_adm")]
        ])
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        return

    # ✅ MENU DE PUNIÇÃO
    if dados == "menu_punicao":
        await query.answer()
        texto = "⚖️ **ESCOLHA A PUNIÇÃO PADRÃO:**\n\nQual ação o bot vai aplicar quando alguém descumprir as regras:"
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ Aviso → Banir", callback_data="definir_punicao_aviso_ban")],
            [InlineKeyboardButton("🚫 Banir Direto", callback_data="definir_punicao_remover")],
            [InlineKeyboardButton("🔇 Silenciar", callback_data="definir_punicao_silenciar")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="menu_config_grupo")]
        ])
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        return

    # ✅ DEFINIR PUNIÇÃO
    if dados.startswith("definir_punicao_"):
        tipo = dados.replace("definir_punicao_", "")
        mapa = {
            "aviso_ban": "aviso_ban",
            "remover": "remover",
            "silenciar": "silenciar"
        }
        acao = mapa.get(tipo, "aviso_ban")
        db["configuracoes_grupo"].update_one(
            {"chat_id": chat.id},
            {"$set": {"acao_padrao": acao, "tempo_mute_padrao": 5}},
            upsert=True
        )
        await query.answer("✅ Punição definida!", show_alert=True)
        await tratar_botoes_config(update, context, get_db, verificar_se_e_adm)
        return
