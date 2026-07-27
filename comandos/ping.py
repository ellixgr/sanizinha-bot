import os
import time
import platform
try:
    import psutil
    processo = psutil.Process(os.getpid())
except ImportError:
    psutil = None
    processo = None

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

TEMPO_INICIAL = time.time()

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inicio = time.time()
    
    # Compatibilidade tanto para comando quanto para botão do painel
    if update.callback_query:
        mensagem_alvo = update.callback_query.message
    else:
        mensagem_alvo = update.message

    msg = await mensagem_alvo.reply_text("⚡ Verificando sistema...")
    latencia = int((time.time() - inicio) * 1000)
    
    # Cálculo detalhado do Tempo Online (Uptime) do Bot
    uptime_seg = int(time.time() - TEMPO_INICIAL)
    dias = uptime_seg // 86400
    horas = (uptime_seg % 86400) // 3600
    minutos = (uptime_seg % 3600) // 60
    
    if dias > 0:
        tempo_online = f"{dias}d {horas}h {minutos}m"
    else:
        tempo_online = f"{horas}h {minutos}m"

    # Indicador de status por latência
    if latencia < 200:
        status_sinal = "🟢 Excelente"
    elif latencia < 500:
        status_sinal = "🟡 Médio"
    else:
        status_sinal = "🔴 Ruim"

    # Hardware, Hospedagem, Memória do Bot e CPU
    sistema = platform.system() + " " + platform.release()
    memoria_info = "Não disponível"
    cpu_info = "Não disponível"
    
    if psutil and processo:
        # Memória RAM usada pelo processo do bot vs total do servidor/plano
        mem_bot = processo.memory_info().rss / (1024 ** 2) # em MB
        mem_total_servidor = psutil.virtual_memory().total / (1024 ** 3) # em GB
        mem_percentual_servidor = psutil.virtual_memory().percent
        memoria_info = f"{mem_bot:.1f}MB usados ({mem_percentual_servidor}% de {mem_total_servidor:.1f}GB)"

        # Uso de CPU do bot e núcleos disponíveis
        cpu_bot = processo.cpu_percent(interval=0.1)
        cpu_nucleos = psutil.cpu_count(logical=True)
        cpu_info = f"{cpu_bot}% (Servidor com {cpu_nucleos} núcleos)"

    texto = (
        f"🖥️ **STATUS DO SISTEMA E HDS**\n\n"
        f"📡 **Latência:** `{latencia}ms` ({status_sinal})\n"
        f"⏱️ **Tempo Online:** `{tempo_online}`\n"
        f"💻 **Hospedagem / OS:** `{sistema}`\n"
        f"🧠 **Memória RAM:** `{memoria_info}`\n"
        f"⚙️ **Uso de CPU:** `{cpu_info}`\n"
        f"🚀 **Estado:** `Online e Operacional`"
    )
    await msg.edit_text(texto, parse_mode="Markdown")

def registrar_ping(app):
    app.add_handler(CommandHandler("ping", ping_cmd))
