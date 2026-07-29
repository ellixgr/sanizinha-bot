from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
from pymongo import MongoClient
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
jogos_db = db["jogo_xadrez"]

def setup_xadrez(app: Application):
    app.add_handler(CallbackQueryHandler(iniciar_xadrez, pattern="^jogo_xadrez$"))
    app.add_handler(CallbackQueryHandler(jogada_xadrez, pattern="^xadrez_"))

async def iniciar_xadrez(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("♟️ Iniciar Xadrez (Modo Simulado)", callback_data="xadrez_iniciar")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text("♟️ **Xadrez**\n\nDevido à complexidade do tabuleiro completo no chat, esta versão foca em partidas dinâmicas e posicionamento rápido.", reply_markup=teclado, parse_mode="Markdown")

async def jogada_xadrez(update: Update, context):
    query = update.callback_query
    if query.data == "xadrez_iniciar":
        await query.message.edit_text(
            "♟️ **Partida de Xadrez Iniciada!**\n\nSuas peças brancas estão posicionadas. Envie sua jogada (ex: `e2 para e4` em texto ou aguarde atualizações).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]])
        )
