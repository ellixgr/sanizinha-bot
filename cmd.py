# ==============================================
# 📜 LISTA DE COMANDOS DO BOT
# ==============================================

comandos_membros = """📜 **COMANDOS PARA MEMBROS**

👤 `/ping` — Verifica status do bot
👤 `/perfil` — Ver suas estatísticas
🆔 `/id` — Mostra seu ID e do grupo
🎵 `/play` — Baixa músicas e vídeos
______________________________
🎮 **JOGOS**

♟️ Xadrez
⚫ Dama
❌ Jogo da Velha
👁️ Memória
💣 Campo Minado
"""

comandos_adm = """🛡️ **COMANDOS PARA ADMINISTRADORES**

🔨 `/ban` — Bane um usuário
🔇 `/mutar` — Silencia um usuário
⭐ `/promover` — Promove a administrador
📢 `/marcar` — Marca todos do grupo
🛡️ `/protecao` — Configura proteções do grupo
👋 `/bemvindo` — Configura mensagem de boas-vindas
"""

def ler_comandos_membros():
    return comandos_membros

def ler_comandos_adm():
    return comandos_adm
