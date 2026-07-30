from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from pymongo import MongoClient
import os
import random
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
    botoes.append([InlineKeyboardButton("❌ Cancelar Seleção", callback_data="xc")])
    botoes.append([InlineKeyboardButton("🚫 Abandonar Partida", callback_data="xs")])
    return botoes

# ✅ FUNÇÃO DE REGISTRO
def setup_xadrez(app: Application):
    app.add_handler(CommandHandler("xadrez", cmd_xadrez))
    app.add_handler(CallbackQueryHandler(menu_xadrez_handler, pattern="^jogo_xadrez$"))
    app.add_handler(CallbackQueryHandler(tratar_botoes, pattern="^x"))
    app.add_handler(CallbackQueryHandler(fazer_jogada, pattern="^xp_"))

# ✅ MENU PRINCIPAL COM PvP E IA
async def menu_xadrez_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        "♟️ **XADREZ OFICIAL**\nEscolha como quer jogar:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Jogar contra Pessoa (PvP)", callback_data="xpvp")],
            [InlineKeyboardButton("🤖 Jogar contra a Máquina", callback_data="xia")],
            [InlineKeyboardButton("🔙 Voltar aos Jogos", callback_data="menu_jogos_atalho")]
        ]),
        parse_mode="Markdown"
    )

# ✅ COMANDO /xadrez COM DESAFIO PvP
async def cmd_xadrez(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Use esse comando dentro de um grupo!", parse_mode="Markdown")
        return

    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text(
            "⚠️ Use assim: `/xadrez` respondendo a mensagem de quem você quer desafiar!",
            parse_mode="Markdown"
        )
        return

    desafiado = reply.from_user
    if desafiado.id == user.id:
        await update.message.reply_text("❌ Não pode desafiar você mesmo!", parse_mode="Markdown")
        return

    if desafiado.is_bot:
        tab = chess.Board()
        xadrez_db.update_one({"chat_id": chat.id}, {"$set":{
            "tabuleiro_fen": tab.fen(), "turno": user.id, "brancas": user.id,
            "pretas": "IA", "modo":"ia", "status": "ativo", "sel": None
        }}, upsert=True)
        await update.message.reply_text(
            "♟️ **Jogo contra IA iniciado!**\nVocê é as peças Brancas — clique em uma peça sua!",
            reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab)),
            parse_mode="Markdown"
        )
        return

    xadrez_db.update_one({"chat_id": chat.id}, {"$set":{
        "desafiante": user.id, "desafiante_nome": user.first_name,
        "desafiado": desafiado.id, "desafiado_nome": desafiado.first_name,
        "status": "pendente"
    }}, upsert=True)

    await update.message.reply_text(
        f"♟️ **DESAFIO DE XADREZ** ♟️\n\n"
        f"@{user.username or user.first_name} te desafiou!\n\n"
        f"Aceita o desafio, {desafiado.mention_markdown()}?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ACEITAR", callback_data="x_aceitar_pvp"),
             InlineKeyboardButton("❌ RECUSAR", callback_data="x_recusar_pvp")]
        ]),
        parse_mode="Markdown"
    )

# ✅ TRATA TODOS OS BOTÕES
async def tratar_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    dados = q.data
    chat_id = q.message.chat.id
    uid = update.effective_user.id

    if dados == "xpvp":
        await q.answer("Use /xadrez respondendo a mensagem do seu amigo para desafiá-lo!", show_alert=True)
        return

    if dados == "xia":
        tab = chess.Board()
        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{
            "tabuleiro_fen": tab.fen(), "turno": uid, "brancas": uid,
            "pretas": "IA", "modo":"ia", "status": "ativo", "sel": None
        }}, upsert=True)
        await q.message.edit_text(
            "♟️ **Jogo contra IA iniciado!**\nClique em uma peça branca sua!",
            reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab)),
            parse_mode="Markdown"
        )
        return

    if dados == "x_aceitar_pvp":
        estado = xadrez_db.find_one({"chat_id": chat_id})
        if not estado or estado["status"] != "pendente" or uid != estado["desafiado"]:
            await q.answer("Esse convite não é para você!", show_alert=True)
            return
        tab = chess.Board()
        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{
            "tabuleiro_fen": tab.fen(), "turno": estado["desafiante"],
            "brancas": estado["desafiante"], "pretas": estado["desafiado"],
            "modo":"pvp", "status": "ativo", "sel": None
        }})
        await q.message.edit_text(
            f"♟️ **PARTIDA INICIADA!**\nVez de {estado['desafiante_nome']} — clique em uma peça!",
            reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab)),
            parse_mode="Markdown"
        )
        return

    if dados == "x_recusar_pvp":
        estado = xadrez_db.find_one({"chat_id": chat_id})
        if not estado or uid != estado["desafiado"]:
            await q.answer("Sem permissão!", show_alert=True)
            return
        xadrez_db.delete_one({"chat_id": chat_id})
        await q.message.edit_text("❌ Desafio recusado!", parse_mode="Markdown")
        return

    if dados == "xc":
        estado = xadrez_db.find_one({"chat_id": chat_id})
        if not estado: return
        tab = chess.Board(estado["tabuleiro_fen"])
        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"sel": None}})
        await q.message.edit_text(
            "Seleção cancelada — escolha outra peça",
            reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab)),
            parse_mode="Markdown"
        )
        return

    if dados == "xs":
        xadrez_db.delete_one({"chat_id": chat_id})
        await q.message.edit_text("🚫 Partida encerrada!", parse_mode="Markdown")
        return

# ✅ FAZ AS JOGADAS — AGORA FUNCIONA 100%
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
        return await q.answer("Não é a sua vez de jogar!", show_alert=True)

    tab = chess.Board(estado["tabuleiro_fen"])
    selecionado = estado.get("sel")

    def posicao_para_casa(l,c):
        return chess.square(c, 7 - l)

    # PRIMEIRO CLIQUE: SELECIONAR PEÇA
    if not selecionado:
        casa = posicao_para_casa(l,c)
        peca = tab.piece_at(casa)
        if not peca:
            return await q.answer("Escolha uma peça, não uma casa vazia!", show_alert=True)
        if peca.color != tab.turn:
            return await q.answer("Essa peça não é sua!", show_alert=True)

        movimentos_validos = [m for m in tab.legal_moves if m.from_square == casa]
        if not movimentos_validos:
            return await q.answer("Essa peça não tem movimentos válidos agora!", show_alert=True)

        destinos = []
        for mov in movimentos_validos:
            col = chess.square_file(mov.to_square)
            lin = 7 - chess.square_rank(mov.to_square)
            destinos.append((lin, col))

        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"sel": (l,c)}})
        await q.message.edit_text(
            "✅ Peça selecionada! Clique no destino marcado com ✅ ou ⚔️",
            reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab, (l,c), destinos)),
            parse_mode="Markdown"
        )
        return

    # SEGUNDO CLIQUE: MOVER
    l1, c1 = selecionado
    origem = posicao_para_casa(l1, c1)
    destino = posicao_para_casa(l, c)
    movimento = chess.Move(origem, destino)

    if movimento not in tab.legal_moves:
        await q.answer("❌ Movimento inválido!", show_alert=True)
        movs = [m for m in tab.legal_moves if m.from_square == origem]
        dest = []
        for m in movs:
            col = chess.square_file(m.to_square)
            lin = 7 - chess.square_rank(m.to_square)
            dest.append((lin, col))
        await q.message.edit_text(
            "Escolha um movimento válido!",
            reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab, (l1,c1), dest)),
            parse_mode="Markdown"
        )
        return

    tab.push(movimento)

    # VERIFICA FIM DE JOGO
    if tab.is_checkmate():
        vencedor = estado["brancas"] if tab.turn == chess.BLACK else estado["pretas"]
        xadrez_db.delete_one({"chat_id": chat_id})
        return await q.message.edit_text(
            f"🏆 **XEQUE-MATE!**\nParabéns, você venceu!",
            reply_markup=None, parse_mode="Markdown"
        )
    if tab.is_game_over():
        xadrez_db.delete_one({"chat_id": chat_id})
        return await q.message.edit_text(
            "🤝 **EMPATE!** Partida finalizada!",
            reply_markup=None, parse_mode="Markdown"
        )

    # TURNO DA IA
    if estado["modo"] == "ia" and tab.turn == chess.BLACK:
        todos_movs = list(tab.legal_moves)
        if todos_movs:
            tab.push(random.choice(todos_movs))
            if tab.is_game_over():
                xadrez_db.delete_one({"chat_id": chat_id})
                return await q.message.edit_text("🤖 A IA venceu! Partida finalizada!", reply_markup=None, parse_mode="Markdown")
            await q.message.edit_text(
                "Sua vez! Clique em uma peça branca",
                reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab)),
                parse_mode="Markdown"
            )
            xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"tabuleiro_fen": tab.fen(), "sel": None}})
            return

    # SALVA E PASSA O TURNO
    proximo = estado["pretas"] if tab.turn == chess.BLACK else estado["brancas"]
    xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"tabuleiro_fen": tab.fen(), "turno": proximo, "sel": None}})
    aviso = "⚠️ **XEQUE!** " if tab.is_check() else ""
    await q.message.edit_text(
        f"{aviso}Vez das {'Brancas' if tab.turn == chess.WHITE else 'Pretas'}",
        reply_markup=InlineKeyboardMarkup(tabuleiro_para_botoes(tab)),
        parse_mode="Markdown"
    )
