import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

TEMPO_INICIAL = time.time()

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inicio = time.time()
    msg = await update.message.reply_text("pong 🏓...")
    latencia = int((time.time() - inicio) * 1000)
    uptime = int(time.time() - TEMPO_INICIAL)
    await msg.edit_text(f"🏓 **Latência:** `{latencia}ms` | **Online:** `{uptime//3600}h`", parse_mode="Markdown")

async def menu_ping_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "menu_ping":
        await query.answer()
        inicio = time.time()
        latencia = int((time.time() - inicio) * 1000)
        await query.message.reply_text(f"🏓 **Latência:** `{latencia}ms`", parse_mode="Markdown")

def registrar_ping(app):
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CallbackQueryHandler(menu_ping_callback, pattern="^menu_ping$"))
