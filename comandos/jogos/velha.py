from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from pymongo import MongoClient
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
jogos_db = db["jogo_velha"]

def setup_velha(app: Application):
    app.add_handler(CommandHandler("velha", cmd_velha))
    app.add_handler(CallbackQueryHandler(menu_velha_handler, pattern="^jogo_velha$"))
    app.add_handler(CallbackQueryHandler(tratar_botoes_velha, pattern="^v_"))
    app.add_handler(CallbackQueryHandler(jogada_velha, pattern="^vpos_"))

async def cmd_velha(update: Update, context):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando de desafio PvP deve ser usado dentro de grupos!")
        return

    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Responda a mensagem de um membro do grupo com `/velha` para desafiá-lo!", parse_mode="Markdown")
        return

    desafiado = reply.from_user

    if desafiado.id == user.id:
        await update.message.reply_text("❌ Você não pode desafiar a si mesmo!", parse_mode="Markdown")
        return
    
    if desafiado.is_bot:
        await update.message.reply_text("❌ Você não pode desafiar um bot para o PvP. Jogue contra a máquina!", parse_mode="Markdown")
        return

    # Salva o desafio no banco vinculado ao chat
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
        [InlineKeyboardButton("✅ SIM", callback_data="v_aceitar"), InlineKeyboardButton("❌ NÃO", callback_data="v_recusar")],
        [InlineKeyboardButton("🚫 Cancelar Partida", callback_data="v_cancelar")]
    ])

    await update.message.reply_text(
        f"🎮 **DESAFIO DE JOGO DA VELHA** 🎮\n\n"
        f"O usuário @{user.username or user.first_name} lhe desafiou pra uma partida eletrizante de jogo da velha, {desafiado.mention_markdown()}!\n\n"
        f"**VOCÊ ACEITA?**",
        reply_markup=teclado,
        parse_mode="Markdown"
    )

async def menu_velha_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Jogar PvP (Use /velha respondendo alguém)", callback_data="v_infopvp")],
        [InlineKeyboardButton("🤖 Jogar Contra a Máquina", callback_data="v_modoia")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text(
        "⭕ **Jogo da Velha**\n\nEscolha o modo de jogo:\n_(Para PvP, vá no chat do grupo e responda alguém com `/velha`)_",
        reply_markup=teclado,
        parse_mode="Markdown"
    )

async def tratar_botoes_velha(update: Update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user_id = query.effective_user.id
    user_name = query.effective_user.first_name

    if data == "v_infopvp":
        await query.answer("💡 Para jogar PvP, responda a mensagem de um membro no grupo usando o comando /velha!", show_alert=True)
        return

    if data == "v_modoia":
        tabuleiro = [" " for _ in range(9)]
        jogos_db.update_one(
            {"chat_id": chat_id},
            {"$set": {"tabuleiro": tabuleiro, "turno": user_id, "modo": "ia", "X": user_id, "O": "IA", "status": "ativo"}},
            upsert=True
        )
        await atualizar_tabuleiro(query, tabuleiro, f"🤖 Jogo contra a Máquina iniciado! Sua vez ({user_name} - X).")
        return

    estado = jogos_db.find_one({"chat_id": chat_id})

    if data == "v_aceitar":
        if not estado or estado.get("status") != "pendente":
            await query.answer("⚠️ Este convite expirou ou não existe.", show_alert=True)
            return
        
        # BLOQUEIO: Se quem clicou NÃO for o desafiado
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
        await atualizar_tabuleiro(query, tabuleiro, f"⚔️ Partida iniciada! Vez de {estado['desafiante_nome']} (X).")
        return

    if data == "v_recusar":
        if not estado:
            await query.answer("⚠️ Convite não encontrado.", show_alert=True)
            return
        
        # BLOQUEIO: Se quem clicou NÃO for o desafiado
        if user_id != estado["desafiado_id"]:
            await query.answer("❌ Apenas o usuário desafiado pode recusar este convite!", show_alert=True)
            return
        
        jogos_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("❌ **Desafio recusado!** A partida foi cancelada.", parse_mode="Markdown")
        return

    if data == "v_cancelar":
        if not estado:
            await query.answer("⚠️ Nenhuma partida ativa.", show_alert=True)
            return
        
        dono_id = int(os.environ.get("DONO_ID", 0))
        if user_id != estado.get("desafiante_id") and user_id != estado.get("desafiado_id") and user_id != dono_id:
            await query.answer("❌ Apenas os participantes podem cancelar a partida!", show_alert=True)
            return
        
        jogos_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("🚫 **Partida cancelada** com sucesso.", parse_mode="Markdown")
        return

    if data == "v_reiniciar":
        tabuleiro = [" " for _ in range(9)]
        jogos_db.update_one(
            {"chat_id": chat_id},
            {"$set": {"tabuleiro": tabuleiro, "turno": user_id, "modo": "ia", "X": user_id, "O": "IA", "status": "ativo"}},
            upsert=True
        )
        await atualizar_tabuleiro(query, tabuleiro, "🎮 Novo jogo contra a IA iniciado! Sua vez (X).")
        return

async def jogada_velha(update: Update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user_id = query.effective_user.id

    pos = int(data.split("_")[1])
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
        await atualizar_tabuleiro(query, tabuleiro, f"Vez de {proximo_nome} ({'X' if proximo_turno == estado['X'] else 'O'})")

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
        await atualizar_tabuleiro(query, tabuleiro, "Sua vez (X)")

def verificar_vencedor(t):
    linhas = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,b,c in linhas:
        if t[a] == t[b] == t[c] and t[a] != " ":
            return t[a]
    return None

async def atualizar_tabuleiro(query, tabuleiro, texto_status):
    botoes = []
    for i in range(0, 9, 3):
        linha = [
            InlineKeyboardButton(tabuleiro[i] if tabuleiro[i] != " " else "➖", callback_data=f"vpos_{i}"),
            InlineKeyboardButton(tabuleiro[i+1] if tabuleiro[i+1] != " " else "➖", callback_data=f"vpos_{i+1}"),
            InlineKeyboardButton(tabuleiro[i+2] if tabuleiro[i+2] != " " else "➖", callback_data=f"vpos_{i+2}"),
        ]
        botoes.append(linha)
    botoes.append([InlineKeyboardButton("🚫 Cancelar Partida", callback_data="v_cancelar")])
    
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
    botoes.append([InlineKeyboardButton("🎮 Jogar de Novo", callback_data="v_reiniciar")])
    botoes.append([InlineKeyboardButton("🔙 Voltar aos Jogos", callback_data="menu_jogos_atalho")])
    
    await query.message.edit_text(f"⭕ **Jogo da Velha**\n\n{msg}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
