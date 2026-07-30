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
        "configuracoes": {
            "apagar_msg": cfg.get("apagar_msg", True),
            "acao_padrao": cfg.get("acao_padrao", "aviso_ban"),
            "tempo_mute_padrao": cfg.get("tempo_mute_padrao", 5)
        },
        "total_avisos_registrados": total_avisos,
        "usuarios_com_avisos": usuarios_com_avisos,
        "usuarios_bloqueados_agora": bloqueados_agora,
        "qtd_bloqueados": len(bloqueados_agora)
    }
