from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await update.message.reply_text(f"🆔 **Seu ID:** `{user.id}`\n📌 **ID do Chat:** `{chat.id}`", parse_mode="Markdown")

async def menu_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "menu_id":
        await query.answer()
        user = query.from_user
        chat = query.message.chat
        await query.message.reply_text(f"🆔 **ID:** `{user.id}` | **Chat ID:** `{chat.id}`", parse_mode="Markdown")

def registrar_id(app):
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CallbackQueryHandler(menu_id_callback, pattern="^menu_id$"))
