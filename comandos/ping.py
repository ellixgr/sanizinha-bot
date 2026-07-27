import os
import time
import platform
try:
    import psutil
except ImportError:
    psutil = None

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
    uptime_seg = int(time.time() - TEMPO_INICIAL)
    
    horas = uptime_seg // 3600
    minutos = (uptime_seg % 3600) // 60

    # Indicador de status por latência
    if latencia < 200:
        status_sinal = "🟢 Excelente"
    elif latencia < 500:
        status_sinal = "🟡 Médio"
    else:
        status_sinal = "🔴 Ruim"

    # Hardware e Hospedagem
    sistema = platform.system() + " " + platform.release()
    memoria_info = "Não disponível"
    
    if psutil:
        mem = psutil.virtual_memory()
        ram_usada = mem.used / (1024 ** 3)
        ram_total = mem.total / (1024 ** 3)
        memoria_info = f"{ram_usada:.2f}GB / {ram_total:.2f}GB ({mem.percent}%)"

    texto = (
        f"🖥️ **STATUS DO SISTEMA E HDS**\n\n"
        f"📡 **Latência:** `{latencia}ms` ({status_sinal})\n"
        f"⏱️ **Uptime:** `{horas}h {minutos}m`\n"
        f"💻 **Hospedagem / OS:** `{sistema}`\n"
        f"🧠 **Memória RAM:** `{memoria_info}`\n"
        f"🚀 **Estado:** `Online e Operacional`"
    )
    await msg.edit_text(texto, parse_mode="Markdown")

def registrar_ping(app):
    app.add_handler(CommandHandler("ping", ping_cmd))
