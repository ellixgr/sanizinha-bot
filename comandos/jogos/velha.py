from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from pymongo import MongoClient
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
jogos_db = db["jogo_velha"]

def setup_velha(app: Application):
    app.add_handler(CommandHandler("velha", cmd_velha))
    app.add_handler(CallbackQueryHandler(iniciar_velha, pattern="^jogo_velha$"))
    app.add_handler(CallbackQueryHandler(tratar_acoes_velha, pattern="^velha_(aceitar|recusar|cancelar|reiniciar|info_pvp|modo_ia)$"))
    app.add_handler(CallbackQueryHandler(jogada_velha, pattern="^velha_pos_"))

async def cmd_velha(update: Update, context):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando de desafio PvP deve ser usado dentro de grupos!")
        return

    reply = update.message.reply_to_message
    args = context.args

    desafiado = None
    if reply:
        desafiado = reply.from_user
    elif args:
        await update.message.reply_text("⚠️ Por favor, **responda à mensagem** da pessoa que você quer desafiar com `/velha`!", parse_mode="Markdown")
        return
    else:
        await update.message.reply_text("⚠️ Responda a mensagem de um membro do grupo com `/velha` para desafiá-lo!", parse_mode="Markdown")
        return

    if desafiado.id == user.id:
        await update.message.reply_text("❌ Você não pode desafiar a si mesmo!", parse_mode="Markdown")
        return
    
    if desafiado.is_bot:
        await update.message.reply_text("❌ Você não pode desafiar um bot para o PvP. Jogue no modo contra a máquina!", parse_mode="Markdown")
        return

    # Salvar convite pendente no banco usando o chat_id como chave principal
    jogos_db.update_one(
        {"chat_id": chat.id},
        {"$set": {
            "desafiante_id": user.id,
            "desafiante_nome": user.first_name,
            "desafiado_id": desafiado.id,
            "desafiado_nome": desafiado.first_name,
            "status": "pendente"
        }},
        upsert=True
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ SIM", callback_data="velha_aceitar"), InlineKeyboardButton("❌ NÃO", callback_data="velha_recusar")],
        [InlineKeyboardButton("🚫 Cancelar Partida", callback_data="velha_cancelar")]
    ])

    await update.message.reply_text(
        f"🎮 **DESAFIO DE JOGO DA VELHA** 🎮\n\n"
        f"O usuário @{user.username or user.first_name} lhe desafiou pra uma partida eletrizante de jogo da velha, {desafiado.mention_markdown()}!\n\n"
        f"**VOCÊ ACEITA?**",
        reply_markup=teclado,
        parse_mode="Markdown"
    )

async def iniciar_velha(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Jogar PvP (Use /velha respondendo alguém)", callback_data="velha_info_pvp")],
        [InlineKeyboardButton("🤖 Jogar Contra a Máquina", callback_data="velha_modo_ia")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text("⭕ **Jogo da Velha**\n\nEscolha o modo de jogo:\n_(Para PvP, responda um usuário no chat com `/velha`)_", reply_markup=teclado, parse_mode="Markdown")

async def tratar_acoes_velha(update: Update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user_id = query.effective_user.id
    user_name = query.effective_user.first_name

    if data == "velha_info_pvp":
        await query.answer("💡 Para jogar PvP, vá no chat do grupo e digite /velha respondendo a mensagem da pessoa que deseja desafiar!", show_alert=True)
        return

    if data == "velha_modo_ia":
        tabuleiro = [" " for _ in range(9)]
        jogos_db.update_one(
            {"chat_id": chat_id},
            {"$set": {"tabuleiro": tabuleiro, "turno": user_id, "modo": "ia", "X": user_id, "O": "IA", "status": "ativo"}},
            upsert=True
        )
        await atualizar_tabuleiro(query, tabuleiro, f"🤖 Jogo contra a Máquina iniciado! Sua vez ({user_name} - X).", chat_id)
        return

    estado = jogos_db.find_one({"chat_id": chat_id})

    if data == "velha_aceitar":
        if not estado or estado.get("status") != "pendente":
            await query.answer("⚠️ Este convite expirou ou não existe.", show_alert=True)
            return
        if user_id != estado["desafiado_id"]:
            await query.answer("❌ Apenas o usuário desafiado pode aceitar este convite!", show_alert=True)
            return
        
        tabuleiro = [" " for _ in range(9)]
        jogos_db.update_one(
            {"chat_id": chat_id},
            {"$set": {
                "tabuleiro": tabuleiro,
                "turno": estado["desafiante_id"],
                "modo": "pvp",
                "X": estado["desafiante_id"],
                "O": estado["desafiado_id"],
                "status": "ativo"
            }}
        )
        await atualizar_tabuleiro(query, tabuleiro, f"⚔️ Partida iniciada! Vez de {estado['desafiante_nome']} (X).", chat_id)
        return

    if data == "velha_recusar":
        if not estado:
            await query.answer("⚠️ Convite não encontrado.", show_alert=True)
            return
        if user_id != estado["desafiado_id"]:
            await query.answer("❌ Apenas o usuário desafiado pode recusar!", show_alert=True)
            return
        
        jogos_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("❌ **Desafio recusado!** A partida foi cancelada.", parse_mode="Markdown")
        return

    if data == "velha_cancelar":
        if not estado:
            await query.answer("⚠️ Nenhuma partida ativa ou pendente.", show_alert=True)
            return
        
        dono_id = int(os.environ.get("DONO_ID", 0))
        desafiante = estado.get("desafiante_id")
        desafiado = estado.get("desafiado_id")
        
        if user_id != desafiante and user_id != desafiado and user_id != dono_id:
            await query.answer("❌ Apenas os participantes podem cancelar a partida!", show_alert=True)
            return
        
        jogos_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("🚫 **Partida cancelada** com sucesso.", parse_mode="Markdown")
        return

    if data == "velha_reiniciar":
        tabuleiro = [" " for _ in range(9)]
        jogos_db.update_one(
            {"chat_id": chat_id},
            {"$set": {"tabuleiro": tabuleiro, "turno": user_id, "modo": "ia", "X": user_id, "O": "IA", "status": "ativo"}},
            upsert=True
        )
        await atualizar_tabuleiro(query, tabuleiro, f"🎮 Novo jogo iniciado! Sua vez.", chat_id)

async def jogada_velha(update: Update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user_id = query.effective_user.id

    pos = int(data.split("_")[2])
    estado = jogos_db.find_one({"chat_id": chat_id})
    
    if not estado or estado.get("status") != "ativo":
        await query.answer("⚠️ Jogo expirado ou não encontrado. Inicie um novo!", show_alert=True)
        return

    modo = estado.get("modo")
    turno = estado.get("turno")
    tabuleiro = estado.get("tabuleiro")

    if modo == "pvp":
        if user_id != turno:
            await query.answer("❌ Não é a sua vez de jogar!", show_alert=True)
            return
        if tabuleiro[pos] != " ":
            await query.answer("⚠️ Este espaço já está ocupado!", show_alert=True)
            return

        simbolo = "X" if user_id == estado["X"] else "O"
        tabuleiro[pos] = simbolo
        
        vencedor = verificar_vencedor(tabuleiro)
        if vencedor or " " not in tabuleiro:
            vencedor_nome = estado["desafiante_nome"] if vencedor == "X" else estado["desafiado_nome"] if vencedor == "O" else None
            await finalizar_jogo(query, tabuleiro, vencedor, vencedor_nome)
            jogos_db.delete_one({"chat_id": chat_id})
            return

        proximo_turno = estado["O"] if user_id == estado["X"] else estado["X"]
        proximo_nome = estado["desafiado_nome"] if user_id == estado["X"] else estado["desafiante_nome"]
        
        jogos_db.update_one({"chat_id": chat_id}, {"$set": {"tabuleiro": tabuleiro, "turno": proximo_turno}})
        await atualizar_tabuleiro(query, tabuleiro, f"Vez de {proximo_nome} ({'X' if proximo_turno == estado['X'] else 'O'})", chat_id)

    elif modo == "ia":
        if tabuleiro[pos] != " ":
            await query.answer("⚠️ Este espaço já está ocupado!", show_alert=True)
            return
        
        tabuleiro[pos] = "X"
        vencedor = verificar_vencedor(tabuleiro)
        if vencedor or " " not in tabuleiro:
            await finalizar_jogo(query, tabuleiro, vencedor, "Você" if vencedor == "X" else "Máquina")
            jogos_db.delete_one({"chat_id": chat_id})
            return

        vazias = [i for i, x in enumerate(tabuleiro) if x == " "]
        if vazias:
            import random
            ai_pos = random.choice(vazias)
            tabuleiro[ai_pos] = "O"

        vencedor = verificar_vencedor(tabuleiro)
        if vencedor or " " not in tabuleiro:
            await finalizar_jogo(query, tabuleiro, vencedor, "Você" if vencedor == "X" else "Máquina")
            jogos_db.delete_one({"chat_id": chat_id})
            return

        jogos_db.update_one({"chat_id": chat_id}, {"$set": {"tabuleiro": tabuleiro}})
        await atualizar_tabuleiro(query, tabuleiro, "Sua vez (X)", chat_id)

def verificar_vencedor(t):
    linhas = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,b,c in linhas:
        if t[a] == t[b] == t[c] and t[a] != " ":
            return t[a]
    return None

async def atualizar_tabuleiro(query, tabuleiro, texto_status, chat_id):
    botoes = []
    for i in range(0, 9, 3):
        linha = [
            InlineKeyboardButton(tabuleiro[i] if tabuleiro[i] != " " else "➖", callback_data=f"velha_pos_{i}"),
            InlineKeyboardButton(tabuleiro[i+1] if tabuleiro[i+1] != " " else "➖", callback_data=f"velha_pos_{i+1}"),
            InlineKeyboardButton(tabuleiro[i+2] if tabuleiro[i+2] != " " else "➖", callback_data=f"velha_pos_{i+2}"),
        ]
        botoes.append(linha)
    botoes.append([InlineKeyboardButton("🚫 Cancelar Partida", callback_data="velha_cancelar")])
    
    await query.message.edit_text(f"⭕ **Jogo da Velha**\nStatus: {texto_status}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")

async def finalizar_jogo(query, tabuleiro, vencedor, nome_vencedor=None):
    if vencedor:
        msg = f"🎉 **Fim de Jogo! Vencedor: {nome_vencedor} ({vencedor})!**"
    else:
        msg = "🤝 **Deu Velha! Empate!**"

    botoes = []
    for i in range(0, 9, 3):
        botoes.append([
            InlineKeyboardButton(tabuleiro[i], callback_data="none"),
            InlineKeyboardButton(tabuleiro[i+1], callback_data="none"),
            InlineKeyboardButton(tabuleiro[i+2], callback_data="none"),
        ])
    botoes.append([InlineKeyboardButton("🎮 Jogar de Novo", callback_data="velha_reiniciar")])
    botoes.append([InlineKeyboardButton("🔙 Voltar aos Jogos", callback_data="menu_jogos_atalho")])
    
    await query.message.edit_text(f"⭕ **Jogo da Velha**\n\n{msg}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
