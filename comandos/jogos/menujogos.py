from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# ✅ Imports corretos
from comandos.jogos.xadrez import menu_xadrez_handler
from comandos.jogos.velha import menu_velha_handler
from comandos.jogos.memoria import iniciar_memoria  # ✅ Adicionado
from comandos.jogos.minado import iniciar_minado     # ✅ Adicionado

async def menu_jogos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    texto_jogos = (
        "🎮 **CENTRAL DE JOGOS** 🎮\n\n"
        "Escolha um dos jogos abaixo:"
    )

    teclado_jogos = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭕ Jogo da Velha", callback_data="jogo_velha"),
         InlineKeyboardButton("🧠 Memória", callback_data="jogo_memoria")],
        [InlineKeyboardButton("💣 Campo Minado", callback_data="jogo_minado"),
         InlineKeyboardButton("♟️ Xadrez", callback_data="jogo_xadrez")],
        [InlineKeyboardButton("🔴 Damas — Em Breve", callback_data="jogo_dama")],
        [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="menu_membros")]
    ])

    await query.message.edit_text(texto_jogos, reply_markup=teclado_jogos, parse_mode="Markdown")


async def processar_callback_jogos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data

    if dados == "menu_jogos_atalho":
        await menu_jogos_handler(update, context)
        return

    if dados == "jogo_velha":
        await query.answer("Abrindo Jogo da Velha...")
        await menu_velha_handler(update, context)
        return

    if dados == "jogo_memoria":
        await query.answer("Abrindo Memória...")
        await iniciar_memoria(update, context)
        return

    if dados == "jogo_minado":
        await query.answer("Abrindo Campo Minado...")
        from comandos.jogos.minado import iniciar_minado
        await iniciar_minado(update, context)
        return

    if dados == "jogo_xadrez":
        await query.answer("Abrindo Xadrez...")
        await menu_xadrez_handler(update, context)
        return

    if dados == "jogo_dama":
        await query.answer("🎮 Damas em breve!", show_alert=True)
        return
