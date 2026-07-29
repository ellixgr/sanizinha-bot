from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

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

    # Voltar para a central de jogos
    if data == "menu_jogos_atalho":
        await menu_jogos_handler(update, context)
        return

    # ABRIR O MENU DO XADREZ DIRETO DAQUI — se o handler externo não pegar, esse resolve
    if data == "jogo_xadrez":
        # Importa a função do menu do xadrez (ajuste o caminho se seu arquivo tiver nome diferente)
        from xadrez import menu_xadrez_handler
        await menu_xadrez_handler(update, context)
        return

    # Aqui depois você adiciona os outros jogos quando eles estiverem prontos:
    # if data == "jogo_velha": ...
    # if data == "jogo_memoria": ...
