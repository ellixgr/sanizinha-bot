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

    # Atalho para voltar para a central de jogos a partir de qualquer partida
    if data == "menu_jogos_atalho":
        await menu_jogos_handler(update, context)
        return

    # Removidos os alertas de "em desenvolvimento" pois os jogos agora estão ativos.
    # Os arquivos de cada jogo (velha.py, memoria.py, etc.) vão capturar esses callbacks.
