from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from pymongo import MongoClient
import os
import random
import chess

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
xadrez_db = db["jogo_xadrez"]

SIMBOLOS_PECAS = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
    ".": " "
}

def montar_capturas(lista):
    return " ".join(lista) if lista else ""

def gerar_tabuleiro_botoes(tabuleiro: chess.Board, selecionado=None, destinos_validos=None):
    texto_tabuleiro = str(tabuleiro).replace(" ", "").split("\n")
    botoes = []
    
    for linha in range(8):
        linha_botoes = []
        for coluna in range(8):
            peca = texto_tabuleiro[linha][coluna]
            texto_botao = SIMBOLOS_PECAS.get(peca, " ")
            
            if selecionado and (linha, coluna) == selecionado:
                texto_botao = f"[{texto_botao}]"
            elif destinos_validos and (linha, coluna) in destinos_validos:
                texto_botao = "✅" if peca == " " else f"⚔️{texto_botao}"
            
            linha_botoes.append(InlineKeyboardButton(texto_botao, callback_data=f"xadrez_{linha}_{coluna}"))
        botoes.append(linha_botoes)
    
    botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="xadrez_cancelar")])
    botoes.append([InlineKeyboardButton("🚫 Abandonar", callback_data="xadrez_sair")])
    return InlineKeyboardMarkup(botoes)

def setup_xadrez(app: Application):
    app.add_handler(CommandHandler("xadrez", cmd_iniciar_xadrez))
    app.add_handler(CallbackQueryHandler(menu_xadrez_handler, pattern="^jogo_xadrez$"))
    app.add_handler(CallbackQueryHandler(tratar_botoes_menu, pattern="^xadrez_"))

async def menu_xadrez_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "♟️ **XADREZ**\nEscolha o modo de jogo:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Modo PvP", callback_data="xadrez_pvp")],
            [InlineKeyboardButton("🤖 Jogar contra IA", callback_data="xadrez_ia")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
        ]),
        parse_mode="Markdown"
    )

async def cmd_iniciar_xadrez(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    usuario = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Use em grupos! Responda a mensagem de quem quer desafiar.")
        return

    mensagem_respondida = update.message.reply_to_message
    adversario = mensagem_respondida.from_user if mensagem_respondida else None

    if adversario and adversario.is_bot:
        tab = chess.Board()
        xadrez_db.update_one({"chat_id": chat.id}, {
            "$set": {
                "tabuleiro": tab.fen(),
                "turno": usuario.id,
                "brancas": usuario.id,
                "brancas_nome": usuario.first_name,
                "pretas": "IA",
                "pretas_nome": "Sanizinha Bot",
                "modo": "ia",
                "selecionado": None,
                "capturas_brancas": [],
                "capturas_pretas": []
            }
        }, upsert=True)
        await update.message.reply_text(
            f"♟️ **JOGO INICIADO!**\n\n𝘝𝘌𝘡 𝘋𝘖(𝘈) @{usuario.first_name}\n\n𝘊𝘈𝘗𝘛𝘜𝘙𝘈𝘚:\n@{usuario.first_name} : {montar_capturas([])}\nSanizinha Bot : {montar_capturas([])}",
            reply_markup=gerar_tabuleiro_botoes(tab),
            parse_mode="Markdown"
        )
        return

    if not adversario:
        await update.message.reply_text(
            "⚠️ Para jogar com amigos: envie `/xadrez` **respondendo a mensagem da pessoa** que quer desafiar!",
            parse_mode="Markdown"
        )
        return

    if adversario.id == usuario.id:
        await update.message.reply_text("❌ Não pode desafiar você mesmo!")
        return

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

async def tratar_botoes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data
    chat_id = query.message.chat.id
    uid = update.effective_user.id

    if dados == "xadrez_pvp":
        await query.answer("Modo PvP!", show_alert=True)
        await query.message.edit_text(
            "👥 **MODO PvP**\n\nPara jogar com amigos:\nEnvie `/xadrez` **respondendo a mensagem da pessoa** que quer desafiar!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="jogo_xadrez")]]),
            parse_mode="Markdown"
        )
        return

    if dados == "xadrez_ia":
        tab = chess.Board()
        xadrez_db.update_one({"chat_id": chat_id}, {
            "$set": {
                "tabuleiro": tab.fen(),
                "turno": uid,
                "brancas": uid,
                "brancas_nome": update.effective_user.first_name,
                "pretas": "IA",
                "pretas_nome": "Sanizinha Bot",
                "modo": "ia",
                "selecionado": None,
                "capturas_brancas": [],
                "capturas_pretas": []
            }
        }, upsert=True)
        await query.message.edit_text(
            f"♟️ **JOGO VS IA INICIADO!**\n\n𝘝𝘌𝘡 𝘋𝘖(𝘈) @{update.effective_user.first_name}\n\n𝘊𝘈𝘗𝘛𝘜𝘙𝘈𝘚:\n@{update.effective_user.first_name} : {montar_capturas([])}\nSanizinha Bot : {montar_capturas([])}",
            reply_markup=gerar_tabuleiro_botoes(tab),
            parse_mode="Markdown"
        )
        return

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
                "brancas_nome": jogo["desafiante_nome"],
                "pretas": jogo["desafiado"],
                "pretas_nome": jogo["desafiado_nome"],
                "modo": "pvp",
                "status": "ativo",
                "selecionado": None,
                "capturas_brancas": [],
                "capturas_pretas": []
            }
        })
        await query.message.edit_text(
            f"♟️ **PARTIDA INICIADA!**\n\n𝘝𝘌𝘡 𝘋𝘖(𝘈) @{jogo['desafiante_nome']}\n\n𝘊𝘈𝘗𝘛𝘜𝘙𝘈𝘚:\n@{jogo['desafiante_nome']} : {montar_capturas([])}\n@{jogo['desafiado_nome']} : {montar_capturas([])}",
            reply_markup=gerar_tabuleiro_botoes(tab),
            parse_mode="Markdown"
        )
        return

    if dados == "xadrez_recusar":
        xadrez_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("❌ Desafio recusado!")
        return

    if dados == "xadrez_cancelar":
        jogo = xadrez_db.find_one({"chat_id": chat_id})
        if not jogo: return
        tab = chess.Board(jogo["tabuleiro"])
        xadrez_db.update_one({"chat_id": chat_id}, {"$set": {"selecionado": None}})
        await query.message.edit_text(
            f"𝘝𝘌𝘡 𝘋𝘖(𝘈) @{jogo['brancas_nome'] if tab.turn == chess.WHITE else jogo['pretas_nome']}\n\n𝘊𝘈𝘗𝘛𝘜𝘙𝘈𝘚:\n@{jogo['brancas_nome']} : {montar_capturas(jogo.get('capturas_brancas',[]))}\n@{jogo['pretas_nome']} : {montar_capturas(jogo.get('capturas_pretas',[]))}",
            reply_markup=gerar_tabuleiro_botoes(tab),
            parse_mode="Markdown"
        )
        return

    if dados == "xadrez_sair":
        xadrez_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("🚫 Partida encerrada!")
        return

    if dados.startswith("xadrez_") and len(dados.split("_")) == 3:
        _, linha, coluna = dados.split("_")
        linha, coluna = int(linha), int(coluna)
        jogo = xadrez_db.find_one({"chat_id": chat_id})
        
        if not jogo or jogo.get("status", "ativo") != "ativo":
            await query.answer("Partida não existe!", show_alert=True)
            return
        if uid != jogo["turno"]:
            await query.answer("Não é sua vez!", show_alert=True)
            return

        tab = chess.Board(jogo["tabuleiro"])
        selecionado = jogo.get("selecionado")

        if not selecionado:
            casa = chess.square(coluna, 7 - linha)
            peca = tab.piece_at(casa)
            
            if not peca:
                return await query.answer("Escolha uma peça!", show_alert=True)
            if peca.color != tab.turn:
                return await query.answer("Essa peça não é sua!", show_alert=True)

            movimentos_validos = [m for m in tab.legal_moves if m.from_square == casa]
            if not movimentos_validos:
                return await query.answer("Sem movimentos possíveis!", show_alert=True)

            destinos = []
            for mov in movimentos_validos:
                c = chess.square_file(mov.to_square)
                l = 7 - chess.square_rank(mov.to_square)
                destinos.append((l, c))

            xadrez_db.update_one({"chat_id": chat_id}, {"$set": {"selecionado": (linha, coluna)}})
            await query.message.edit_text(
                f"✅ Peça selecionada! Clique no destino marcado\n\n𝘝𝘌𝘡 𝘋𝘖(𝘈) @{jogo['brancas_nome'] if tab.turn == chess.WHITE else jogo['pretas_nome']}",
                reply_markup=gerar_tabuleiro_botoes(tab, (linha, coluna), destinos),
                parse_mode="Markdown"
            )
            return

        l1, c1 = selecionado
        origem = chess.square(c1, 7 - l1)
        destino = chess.square(coluna, 7 - linha)
        movimento = chess.Move(origem, destino)

        if movimento not in tab.legal_moves:
            await query.answer("❌ Movimento inválido!", show_alert=True)
            return

        peca_capturada = tab.piece_at(destino)
        tab.push(movimento)

        if peca_capturada:
            simbolo = SIMBOLOS_PECAS.get(peca_capturada.symbol(), "♟️")
            if tab.turn == chess.BLACK:
                novas = jogo.get("capturas_brancas", []) + [simbolo]
                xadrez_db.update_one({"chat_id": chat_id}, {"$set": {"capturas_brancas": novas}})
            else:
                novas = jogo.get("capturas_pretas", []) + [simbolo]
                xadrez_db.update_one({"chat_id": chat_id}, {"$set": {"capturas_pretas": novas}})

        if tab.is_checkmate():
            vencedor = jogo["brancas_nome"] if tab.turn == chess.BLACK else jogo["pretas_nome"]
            xadrez_db.delete_one({"chat_id": chat_id})
            return await query.message.edit_text(f"🏆 **XEQUE-MATE!** @{vencedor} venceu!", parse_mode="Markdown")
        if tab.is_game_over():
            xadrez_db.delete_one({"chat_id": chat_id})
            return await query.message.edit_text("🤝 **EMPATE!** Partida finalizada.", parse_mode="Markdown")

        if jogo["modo"] == "ia" and tab.turn == chess.BLACK:
            todos_movs = list(tab.legal_moves)
            if todos_movs:
                mov_ia = random.choice(todos_movs)
                peca_cap_ia = tab.piece_at(mov_ia.to_square)
                tab.push(mov_ia)

                if peca_cap_ia:
                    cap_ia = jogo.get("capturas_pretas", []) + [SIMBOLOS_PECAS.get(peca_cap_ia.symbol(), "♟️")]
                    xadrez_db.update_one({"chat_id": chat_id}, {"$set": {"capturas_pretas": cap_ia}})

                if tab.is_game_over():
                    xadrez_db.delete_one({"chat_id": chat_id})
                    return await query.message.edit_text("🤖 A IA venceu!", parse_mode="Markdown")

                aviso = "⚠️ **XEQUE!** " if tab.is_check() else ""
                await query.message.edit_text(
                    f"{aviso}𝘝𝘌𝘡 𝘋𝘖(𝘈) @{jogo['brancas_nome']}\n\n𝘊𝘈𝘗𝘛𝘜𝘙𝘈𝘚:\n@{jogo['brancas_nome']} : {montar_capturas(jogo.get('capturas_brancas',[]))}\n@{jogo['pretas_nome']} : {montar_capturas(jogo.get('capturas_pretas',[]))}",
                    reply_markup=gerar_tabuleiro_botoes(tab),
                    parse_mode="Markdown"
                )
                xadrez_db.update_one({"chat_id": chat_id}, {"$set": {"tabuleiro": tab.fen(), "selecionado": None}})
                return

        proximo_nome = jogo["pretas_nome"] if tab.turn == chess.BLACK else jogo["brancas_nome"]
        proximo_id = jogo["pretas"] if tab.turn == chess.BLACK else jogo["brancas"]
        aviso = "⚠️ **XEQUE!** " if tab.is_check() else ""

        await query.message.edit_text(
            f"{aviso}𝘝𝘌𝘡 𝘋𝘖(𝘈) @{proximo_nome}\n\n𝘊𝘈𝘗𝘛𝘜𝘙𝘈𝘚:\n@{jogo['brancas_nome']} : {montar_capturas(jogo.get('capturas_brancas',[]))}\n@{jogo['pretas_nome']} : {montar_capturas(jogo.get('capturas_pretas',[]))}",
            reply_markup=gerar_tabuleiro_botoes(tab),
            parse_mode="Markdown"
        )
        xadrez_db.update_one({"chat_id": chat_id}, {
            "$set": {"tabuleiro": tab.fen(), "turno": proximo_id, "selecionado": None}
        })
