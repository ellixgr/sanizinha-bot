import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

logger = logging.getLogger("SanizinhaBot.xadrez")

def setup_xadrez(app: Application):
    app.add_handler(CommandHandler("xadrez", iniciar_jogo))
    app.add_handler(CallbackQueryHandler(callback_jogo, pattern=r"^xadrez_"))

async def iniciar_jogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    await message.reply_text("♟️ Jogo de Xadrez iniciado!")

async def callback_jogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
def setup_xadrez(app):
    # Insira aqui os handlers, add_handler ou comandos relacionados ao jogo
    pass
    
