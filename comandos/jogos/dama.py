from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
from pymongo import MongoClient
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
jogos_db = db["jogo_dama"]

def setup_dama(app: Application):
    app.add_handler(CallbackQueryHandler(iniciar_dama, pattern="^jogo_dama$"))
    app.add_handler(CallbackQueryHandler(jogada_dama, pattern="^dama_"))

async def iniciar_dama(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Jogar Dama vs Máquina", callback_data="dama_iniciar")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text("🔴 **Jogo de Dama (Mini 4x4)**\n\nEscolha o modo:", reply_markup=teclado, parse_mode="Markdown")

async def jogada_dama(update: Update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    
    if query.data == "dama_iniciar":
        # Tabuleiro 4x4 simplificado para Telegram
        # O = Peças brancas/player, X = Peças pretas/IA, . = Vazio
        tabuleiro = [
            [".", "X", ".", "X"],
            ["X", ".", "X", "."],
            [".", "O", ".", "O"],
            ["O", ".", "O", "."]
        ]
        jogos_db.update_one({"chat_id": chat_id}, {"$set": {"tabuleiro": tabuleiro}}, upsert=True)
        await desenhar_dama(query, tabuleiro, "Jogo iniciado! Suas peças são **O**.")

async def desenhar_dama(query, tabuleiro, texto):
    botoes = []
    for r in range(4):
        linha = []
        for c in range(4):
            val = tabuleiro[r][c]
            linha.append(InlineKeyboardButton(val if val != "." else "▫️", callback_data=f"dama_pos_{r}_{c}"))
        botoes.append(linha)
    botoes.append([InlineKeyboardButton("❌ Sair", callback_data="menu_jogos_atalho")])
    await query.message.edit_text(f"🔴 **Dama**\n{texto}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
