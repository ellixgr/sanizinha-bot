# ==============================================
# 📜 LISTA DE COMANDOS DO BOT
# ==============================================

comandos_membros = """📜 **COMANDOS PARA MEMBROS**

👤 `/ping` — Verifica status do bot
👤 `/perfil` — Ver suas estatísticas
🆔 `/id` — Mostra seu ID e do grupo
📊 `/rank` — Ranking de atividade do grupo
🎵 `/play` — Baixa músicas e vídeos
______________________________
🎮 **JOGOS**

♟️ `/xadrez` — Jogo de Xadrez
❌ `/velha` — Jogo da Velha
👁️ `/memoria` — Jogo da Memória
💣 `/minado` — Campo Minado
"""

comandos_adm = """🛡️ **COMANDOS PARA ADMINISTRADORES**

🔨 `/ban` — Bane um usuário
🔓 `/desbanir` — Desbane um usuário
🔇 `/mutar` — Silencia um usuário
🔊 `/desmutar` — Remove silêncio de um usuário
⭐ `/promover` — Promove a administrador
📉 `/rebaixar` — Rebaixa administrador a membro
📢 `/marcar` — Marca todos do grupo
💬 `/citar` — Cita/reenvia uma mensagem
🛡️ `/protecao` — Configura proteções do grupo
👋 `/bemvindo` — Configura mensagem de boas-vindas
"""

def ler_comandos_membros():
    return comandos_membros

def ler_comandos_adm():
    return comandos_adm
