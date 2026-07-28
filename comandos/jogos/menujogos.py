from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def menu_jogos_handler(update, context):
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

async def processar_callback_jogos(update, context):
    query = update.callback_query
    data = query.data

    if data == "jogo_velha":
        await query.answer("⭕ Jogo da Velha em desenvolvimento!", show_alert=True)
    elif data == "jogo_memoria":
        await query.answer("🧠 Jogo da Memória em desenvolvimento!", show_alert=True)
    elif data == "jogo_xadrez":
        await query.answer("♟️ Xadrez em desenvolvimento!", show_alert=True)
    elif data == "jogo_dama":
        await query.answer("🔴 Dama em desenvolvimento!", show_alert=True)
