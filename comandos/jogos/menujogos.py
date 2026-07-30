from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# ✅ IMPORTA A FUNÇÃO DO MENU DO XADREZ
from comandos.jogos.xadrez import menu_xadrez_handler

async def menu_jogos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    texto_jogos = (
        "🎮 **CENTRAL DE JOGOS** 🎮\n\n"
        "Escolha um dos jogos abaixo para se divertir no chat:"
    )

    teclado_jogos = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭕ Jogo da Velha", callback_data="jogo_velha"), InlineKeyboardButton("🧠 Memória", callback_data="jogo_memoria")],
        [InlineKeyboardButton("♟️ Xadrez", callback_data="jogo_xadrez"), InlineKeyboardButton("🔴 Dama", callback_data="jogo_dama")],
        [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="menu_membros")]
    ])

    await query.message.edit_text(texto_jogos, reply_markup=teclado_jogos, parse_mode="Markdown")

async def processar_callback_jogos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "menu_jogos_atalho":
        await menu_jogos_handler(update, context)
        return

    if data == "jogo_velha":
        await query.answer("Jogo da Velha em breve!")
    elif data == "jogo_memoria":
        await query.answer("Jogo da Memória em breve!")
    elif data == "jogo_xadrez":
        # ✅ AGORA CHAMA DIREITO O MENU DO XADREZ
        await query.answer("Abrindo Xadrez...")
        await menu_xadrez_handler(update, context)
    elif data == "jogo_dama":
        await query.answer("Jogo de Damas em breve!")
