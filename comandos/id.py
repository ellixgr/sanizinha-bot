from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    texto = f"🆔 **Seu ID:** `{user.id}`\n"
    if chat.type in ["group", "supergroup"]:
        texto += f"🏢 **ID do Grupo:** `{chat.id}`"
        
    if update.message.reply_to_message:
        alvo = update.message.reply_to_message.from_user
        texto += f"\n👤 **ID de {alvo.first_name}:** `{alvo.id}`"
        
    await update.message.reply_text(texto, parse_mode="Markdown")

def registrar_id(app):
    app.add_handler(CommandHandler("id", id_cmd))
