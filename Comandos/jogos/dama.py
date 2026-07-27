import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

logger = logging.getLogger("SanizinhaBot.Dama")

def setup_dama(app: Application):
    # Registra os comandos e callbacks do jogo de damas
    app.add_handler(CommandHandler("dama", iniciar_dama))
    app.add_handler(CallbackQueryHandler(callback_dama, pattern=r"^dama_"))

async def iniciar_dama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    
    # Lógica do comando /dama aqui
    await message.reply_text("🎮 O modo de Damas ainda está em desenvolvimento!")

async def callback_dama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Lógica dos botões de damas aqui
    await query.answer("Botão clicado!")
