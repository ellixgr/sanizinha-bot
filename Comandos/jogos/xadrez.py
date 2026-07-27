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

def setup_nome_do_jogo(app: Application):
    app.add_handler(CommandHandler("comando_jogo", iniciar_jogo))
    app.add_handler(CallbackQueryHandler(callback_jogo, pattern=r"^prefixo_callback_"))

async def iniciar_jogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    # Sua lógica do jogo aqui...
    await message.reply_text("🎮 Jogo iniciado!")

async def callback_jogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Sua lógica de botões aqui...
    await query.answer()
