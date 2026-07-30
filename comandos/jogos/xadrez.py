from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from pymongo import MongoClient
import os
import random
import chess

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
xadrez_db = db["jogo_xadrez"]

# ✅ MAPEAMENTO DAS PEÇAS (IGUAL O PROJETO PRONTO)
SIMBOLOS_PECAS = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
    ".": " "
}

# ✅ FUNÇÃO DE CONVERSÃO 100% CORRETA (DO CÓDIGO QUE VOCÊ ACHOU)
def gerar_tabuleiro_botoes(tabuleiro: chess.Board, selecionado=None, destinos_validos=None):
    # Converte o tabuleiro da biblioteca para o formato visual do Telegram
    texto_tabuleiro = str(tabuleiro).replace(" ", "").split("\n")
    botoes = []
    
    for linha in range(8):
        linha_botoes = []
        for coluna in range(8):
            peca = texto_tabuleiro[linha][coluna]
            texto_botao = SIMBOLOS_PECAS.get(peca, " ")
            
            # Marca peça selecionada e destinos
            if selecionado and (linha, coluna) == selecionado:
                texto_botao = f"[{texto_botao}]"
            elif destinos_validos and (linha, coluna) in destinos_validos:
                texto_botao = "✅" if peca == " " else f"⚔️{texto_botao}"
            
            # Callback no formato padrão do código pronto
            linha_botoes.append(InlineKeyboardButton(
                texto_botao, 
                callback_data=f"xadrez_{linha}_{coluna}"
            ))
        botoes.append(linha_botoes)
    
    # Botões de controle
    botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="xadrez_cancelar")])
    botoes.append([InlineKeyboardButton("🚫 Abandonar", callback_data="xadrez_sair")])
    return InlineKeyboardMarkup(botoes)

# ✅ REGISTRO NO SEU BOT
def setup_xadrez(app: Application):
    app.add_handler(CommandHandler("xadrez", cmd_iniciar_xadrez))
    app.add_handler(CallbackQueryHandler(menu_xadrez_handler, pattern="^jogo_xadrez$"))
    app.add_handler(CallbackQueryHandler(tratar_botoes_menu, pattern="^xadrez_"))

# ✅ MENU PRINCIPAL
async def menu_xadrez_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "♟️ **XADREZ**\nEscolha o modo de jogo:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Jogar contra Pessoa", callback_data="xadrez_pvp")],
            [InlineKeyboardButton("🤖 Jogar contra IA", callback_data="xadrez_ia")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
        ]),
        parse_mode="Markdown"
    )

# ✅ COMANDO /xadrez
async def cmd_iniciar_xadrez(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    usuario = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Use em grupos! Responda a mensagem de quem quer desafiar.")
        return

    mensagem_respondida = update.message.reply_to_message
    if not mensagem_respondida:
        await update.message.reply_text("⚠️ Use: `/xadrez` respondendo a mensagem do adversário!")
        return

    adversario = mensagem_respondida.from_user
    if adversario.id == usuario.id:
        await update.message.reply_text("❌ Não pode desafiar você mesmo!")
        return

    # Se responder ao bot, inicia contra IA direto
    if adversario.is_bot:
        tab = chess.Board()
        xadrez_db.update_one({"chat_id": chat.id}, {
            "$set": {
                "tabuleiro": tab.fen(),
                "turno": usuario.id,
                "brancas": usuario.id,
                "pretas": "IA",
                "modo": "ia",
                "selecionado": None
            }
        }, upsert=True)
        await update.message.reply_text(
            "♟️ **Jogo contra IA iniciado!** Clique em uma peça branca.",
            reply_markup=gerar_tabuleiro_botoes(tab)
        )
        return

    # Desafio PvP
    xadrez_db.update_one({"chat_id": chat.id}, {
        "$set": {
            "desafiante": usuario.id,
            "desafiante_nome": usuario.first_name,
            "desafiado": adversario.id,
            "desafiado_nome": adversario.first_name,
            "status": "aguardando"
        }
    }, upsert=True)
    await update.message.reply_text(
        f"♟️ **DESAFIO DE XADREZ**\n\n@{usuario.first_name} te desafiou!\nAceita, {adversario.mention_markdown()}?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ACEITAR", callback_data="xadrez_aceitar"),
             InlineKeyboardButton("❌ RECUSAR", callback_data="xadrez_recusar")]
        ]),
        parse_mode="Markdown"
    )

# ✅ TRATA TODOS OS CLIQUES
async def tratar_botoes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data
    chat_id = query.message.chat.id
    uid = update.effective_user.id

    # Aceitar/Recusar desafio
    if dados == "xadrez_aceitar":
        jogo = xadrez_db.find_one({"chat_id": chat_id})
        if not jogo or jogo["status"] != "aguardando" or uid != jogo["desafiado"]:
            await query.answer("Não é para você!", show_alert=True)
            return
        tab = chess.Board()
        xadrez_db.update_one({"chat_id": chat_id}, {
            "$set": {
                "tabuleiro": tab.fen(),
                "turno": jogo["desafiante"],
                "brancas": jogo["desafiante"],
                "pretas": jogo["desafiado"],
                "modo": "pvp",
                "status": "ativo",
                "selecionado": None
            }
        })
        await query.message.edit_text(
            f"♟️ **PARTIDA INICIADA!** Vez de {jogo['desafiante_nome']}",
            reply_markup=gerar_tabuleiro_botoes(tab)
        )
        return

    if dados == "xadrez_recusar":
        xadrez_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("❌ Desafio recusado!")
        return

    # Controles gerais
    if dados == "xadrez_cancelar":
        jogo = xadrez_db.find_one({"chat_id": chat_id})
        if not jogo: return
        tab = chess.Board(jogo["tabuleiro"])
        xadrez_db.update_one({"chat_id": chat_id}, {"$set": {"selecionado": None}})
        await query.message.edit_text(
            "Seleção cancelada",
            reply_markup=gerar_tabuleiro_botoes(tab)
        )
        return

    if dados == "xadrez_sair":
        xadrez_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("🚫 Partida encerrada!")
        return

    # Iniciar modo IA
    if dados == "xadrez_ia":
        tab = chess.Board()
        xadrez_db.update_one({"chat_id": chat_id}, {
            "$set": {
                "tabuleiro": tab.fen(),
                "turno": uid,
                "brancas": uid,
                "pretas": "IA",
                "modo": "ia",
                "selecionado": None
            }
        }, upsert=True)
        await query.message.edit_text(
            "♟️ Clique em uma peça branca sua!",
            reply_markup=gerar_tabuleiro_botoes(tab)
        )
        return

    # Clique em casa do tabuleiro
    if dados.startswith("xadrez_") and len(dados.split("_")) == 3:
        _, linha, coluna = dados.split("_")
        linha, coluna = int(linha), int(coluna)
        jogo = xadrez_db.find_one({"chat_id": chat_id})
        
        if not jogo or jogo["status"] != "ativo":
            await query.answer("Partida não existe!", show_alert=True)
            return
        if uid != jogo["turno"]:
            await query.answer("Não é sua vez!", show_alert=True)
            return

        tab = chess.Board(jogo["tabuleiro"])
        selecionado = jogo.get("selecionado")

        # Primeiro clique: seleciona peça
        if not selecionado:
            # CONVERSÃO EXATA DO CÓDIGO PRONTO
            casa = chess.square(coluna, 7 - linha)
            peca = tab.piece_at(casa)
            
            if not peca:
                return await query.answer("Escolha uma peça!", show_alert=True)
            if peca.color != tab.turn:
                return await query.answer("Essa peça não é sua!", show_alert=True)

            movimentos_validos = [m for m in tab.legal_moves if m.from_square == casa]
            if not movimentos_validos:
                return await query.answer("Sem movimentos possíveis!", show_alert=True)

            # Marca destinos
            destinos = []
            for mov in movimentos_validos:
                c = chess.square_file(mov.to_square)
                l = 7 - chess.square_rank(mov.to_square)
                destinos.append((l, c))

            xadrez_db.update_one({"chat_id": chat_id}, {"$set": {"selecionado": (linha, coluna)}})
            await query.message.edit_text(
                "✅ Peça selecionada! Clique no destino marcado",
                reply_markup=gerar_tabuleiro_botoes(tab, (linha, coluna), destinos)
            )
            return

        # Segundo clique: faz o movimento
        l1, c1 = selecionado
        origem = chess.square(c1, 7 - l1)
        destino = chess.square(coluna, 7 - linha)
        movimento = chess.Move(origem, destino)

        if movimento not in tab.legal_moves:
            await query.answer("❌ Movimento inválido!", show_alert=True)
            return

        tab.push(movimento)

        # Verifica fim de jogo
        if tab.is_checkmate():
            xadrez_db.delete_one({"chat_id": chat_id})
            return await query.message.edit_text("🏆 **XEQUE-MATE!** Você venceu!")
        if tab.is_game_over():
            xadrez_db.delete_one({"chat_id": chat_id})
            return await query.message.edit_text("🤝 **EMPATE!** Partida finalizada.")

        # Turno da IA
        if jogo["modo"] == "ia" and tab.turn == chess.BLACK:
            todos_movs = list(tab.legal_moves)
            if todos_movs:
                tab.push(random.choice(todos_movs))
                if tab.is_game_over():
                    xadrez_db.delete_one({"chat_id": chat_id})
                    return await query.message.edit_text("🤖 A IA venceu!")
                await query.message.edit_text(
                    "Sua vez! Clique em uma peça branca",
                    reply_markup=gerar_tabuleiro_botoes(tab)
                )
                xadrez_db.update_one({"chat_id": chat_id}, {"$set": {"tabuleiro": tab.fen(), "selecionado": None}})
                return

        # Salva e passa o turno
        proximo = jogo["pretas"] if tab.turn == chess.BLACK else jogo["brancas"]
        xadrez_db.update_one({"chat_id": chat_id}, {
            "$set": {"tabuleiro": tab.fen(), "turno": proximo, "selecionado": None}
        })
        aviso = "⚠️ **XEQUE!** " if tab.is_check() else ""
        await query.message.edit_text(
            f"{aviso}Vez das {'Brancas' if tab.turn == chess.WHITE else 'Pretas'}",
            reply_markup=gerar_tabuleiro_botoes(tab)
        )
