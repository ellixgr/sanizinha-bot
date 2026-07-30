from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from pymongo import MongoClient
import os
import chess

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
xadrez_db = db["jogo_xadrez"]

# ✅ MAPEIA AS PEÇAS PARA OS SÍMBOLOS DO TELEGRAM
SIMBOLOS = {
    "K":"♔", "Q":"♕", "R":"♖", "B":"♗", "N":"♘", "P":"♙",
    "k":"♚", "q":"♛", "r":"♜", "b":"♝", "n":"♞", "p":"♟",
    ".":" "
}

def tabuleiro_para_botoes(tab: chess.Board, selecionado=None, destinos=None):
    botoes = []
    for l in range(8):
        linha = []
        for c in range(8):
            casa = chess.square(c, 7 - l)
            peca_obj = tab.piece_at(casa)
            peca = SIMBOLOS.get(peca_obj.symbol(), " ") if peca_obj else " "
            
            if selecionado and (l,c) == selecionado:
                peca = f"[{peca}]"
            elif destinos and (l,c) in destinos:
                peca = "✅" if peca == " " else f"⚔️{peca}"
            
            linha.append(InlineKeyboardButton(peca, callback_data=f"xp_{l}_{c}"))
        botoes.append(linha)
    botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="xc")])
    botoes.append([InlineKeyboardButton("🚫 Sair", callback_data="xs")])
    return botoes

# ✅ FUNÇÃO QUE O BOT.PY ESTÁ PEDINDO
def setup_xadrez(app: Application):
    app.add_handler(CommandHandler("xadrez", cmd_xadrez))
    app.add_handler(CallbackQueryHandler(menu_xadrez_handler, pattern="^jogo_xadrez$"))
    app.add_handler(CallbackQueryHandler(tratar_botoes, pattern="^x"))
    app.add_handler(CallbackQueryHandler(fazer_jogada, pattern="^xp_"))

# ✅ FUNÇÃO COM O NOME CERTO PARA O MENUJOGOS.PY
async def menu_xadrez_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text("♟️ **XADREZ**\nEscolha o modo de jogo:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Jogar contra IA", callback_data="xi")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ]), parse_mode="Markdown")

async def cmd_xadrez(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("⚠️ Use esse comando em grupos!")
        return
    
    tab = chess.Board()
    xadrez_db.update_one({"chat_id": chat.id}, {"$set":{
        "tabuleiro_fen": tab.fen(), "turno": user.id, "brancas": user.id,
        "pretas": "IA", "status": "ativo", "sel": None
    }}, upsert=True)
    
    await update.message.reply_text(
        "♟️ Jogo iniciado! Clique em uma peça branca sua",
        reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab))
    )

async def fazer_jogada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    dados = q.data.split("_")
    l, c = int(dados[1]), int(dados[2])
    chat_id = q.message.chat.id
    uid = update.effective_user.id

    estado = xadrez_db.find_one({"chat_id": chat_id})
    if not estado or estado["status"] != "ativo":
        return await q.answer("Partida não encontrada!", show_alert=True)
    if uid != estado["turno"]:
        return await q.answer("Não é sua vez!", show_alert=True)

    tab = chess.Board(estado["tabuleiro_fen"])
    selecionado = estado.get("sel")

    def posicao_para_casa(l,c):
        return chess.square(c, 7 - l)

    if not selecionado:
        casa = posicao_para_casa(l,c)
        peca = tab.piece_at(casa)
        if not peca:
            return await q.answer("Escolha uma peça!", show_alert=True)
        if peca.color != tab.turn:
            return await q.answer("Essa peça não é sua!", show_alert=True)

        movimentos_validos = [m for m in tab.legal_moves if m.from_square == casa]
        if not movimentos_validos:
            return await q.answer("Essa peça não tem movimentos válidos!", show_alert=True)

        destinos = []
        for mov in movimentos_validos:
            coluna = chess.square_file(mov.to_square)
            linha = 7 - chess.square_rank(mov.to_square)
            destinos.append((linha, coluna))

        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"sel": (l,c)}})
        await q.message.edit_text(
            "✅ Peça selecionada! Clique no destino marcado",
            reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab, (l,c), destinos))
        )
        return

    l1, c1 = selecionado
    movimento = chess.Move(posicao_para_casa(l1,c1), posicao_para_casa(l,c))

    if movimento not in tab.legal_moves:
        await q.answer("❌ Movimento inválido!", show_alert=True)
        return

    tab.push(movimento)

    if tab.is_checkmate():
        xadrez_db.delete_one({"chat_id": chat_id})
        return await q.message.edit_text("🏆 **XEQUE-MATE!** Partida finalizada!", reply_markup=None)
    if tab.is_game_over():
        xadrez_db.delete_one({"chat_id": chat_id})
        return await q.message.edit_text("🤝 **EMPATE!** Partida finalizada!", reply_markup=None)

    novo_turno = estado["pretas"] if tab.turn == chess.BLACK else estado["brancas"]
    xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"tabuleiro_fen": tab.fen(), "turno": novo_turno, "sel": None}})

    msg = "⚠️ **XEQUE!**" if tab.is_check() else "Sua vez!"
    await q.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab)))

async def tratar_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    chat_id = q.message.chat.id
    if d == "xc":
        estado = xadrez_db.find_one({"chat_id": chat_id})
        tab = chess.Board(estado["tabuleiro_fen"])
        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"sel":None}})
        await q.message.edit_text("Seleção cancelada", reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab)))
    elif d == "xs":
        xadrez_db.delete_one({"chat_id": chat_id})
        await q.message.edit_text("🚫 Partida encerrada", reply_markup=None)
    elif d == "xi":
        tab = chess.Board()
        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"tabuleiro_fen":tab.fen(),"turno":update.effective_user.id,"sel":None}}, upsert=True)
        await q.message.edit_text("♟️ Clique em uma peça branca", reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab)))
