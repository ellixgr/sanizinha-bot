from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
from pymongo import MongoClient
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
jogos_db = db["jogo_velha"]

def setup_velha(app: Application):
    app.add_handler(CallbackQueryHandler(iniciar_velha, pattern="^jogo_velha$"))
    app.add_handler(CallbackQueryHandler(jogada_velha, pattern="^velha_"))

async def iniciar_velha(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Jogar PvP (Dois Jogadores)", callback_data="velha_modo_pvp")],
        [InlineKeyboardButton("🤖 Jogar Contra a Máquina", callback_data="velha_modo_ia")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text("⭕ **Jogo da Velha**\n\nEscolha o modo de jogo:", reply_markup=teclado, parse_mode="Markdown")

async def jogada_velha(update: Update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user_id = query.effective_user.id

    if data == "velha_modo_pvp" or data == "velha_modo_ia":
        modo = "pvp" if data == "velha_modo_pvp" else "ia"
        tabuleiro = [" " for _ in range(9)]
        jogos_db.update_one(
            {"chat_id": chat_id},
            {"$set": {"tabuleiro": tabuleiro, "turno": user_id, "modo": modo, "X": user_id, "O": None}},
            upsert=True
        )
        await atualizar_tabuleiro(query, tabuleiro, "🎮 Jogo iniciado! Vez de X.", chat_id)
        return

    # Ações do tabuleiro (velha_pos_0 até velha_pos_8)
    if data.startswith("velha_pos_"):
        pos = int(data.split("_")[2])
        estado = jogos_db.find_one({"chat_id": chat_id})
        
        if not estado:
            await query.answer("⚠️ Jogo expirado ou não encontrado. Inicie um novo!", show_alert=True)
            return

        modo = estado.get("modo", "pvp")
        turno = estado.get("turno")
        tabuleiro = estado.get("tabuleiro")

        if modo == "pvp":
            if user_id != turno:
                await query.answer("❌ Não é a sua vez!", show_alert=True)
                return
            if tabuleiro[pos] != " ":
                await query.answer("⚠️ Espaço ocupado!", show_alert=True)
                return

            simbolo = "X" if user_id == estado["X"] else "O"
            tabuleiro[pos] = simbolo
            
            # Próximo turno
            proximo_turno = estado["O"] if user_id == estado["X"] else estado["X"]
            if proximo_turno is None:
                # Se o segundo jogador ainda não entrou no PvP
                jogos_db.update_one({"chat_id": chat_id}, {"$set": {"O": user_id}})
                proximo_turno = estado["X"] # alternância simples se for a mesma pessoa testando sozinha

            vencedor = verificar_vencedor(tabuleiro)
            if vencedor or " " not in tabuleiro:
                await finalizar_jogo(query, tabuleiro, vencedor)
                jogos_db.delete_one({"chat_id": chat_id})
                return

            jogos_db.update_one({"chat_id": chat_id}, {"$set": {"tabuleiro": tabuleiro, "turno": proximo_turno}})
            await atualizar_tabuleiro(query, tabuleiro, f"Vez de {'X' if simbolo == 'O' else 'O'}", chat_id)

        elif modo == "ia":
            if tabuleiro[pos] != " ":
                await query.answer("⚠️ Espaço ocupado!", show_alert=True)
                return
            
            tabuleiro[pos] = "X"
            if verificar_vencedor(tabuleiro) or " " not in tabuleiro:
                await finalizar_jogo(query, tabuleiro, verificar_vencedor(tabuleiro))
                jogos_db.delete_one({"chat_id": chat_id})
                return

            # Jogada da IA (simples aleatória/estratégica)
            vazias = [i for i, x in enumerate(tabuleiro) if x == " "]
            if vazias:
                import random
                ai_pos = random.choice(vazias)
                tabuleiro[ai_pos] = "O"

            vencedor = verificar_vencedor(tabuleiro)
            if vencedor or " " not in tabuleiro:
                await finalizar_jogo(query, tabuleiro, vencedor)
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
    botoes.append([InlineKeyboardButton("❌ Abandonar Jogo", callback_data="menu_jogos_atalho")])
    
    await query.message.edit_text(f"⭕ **Jogo da Velha**\nStatus: {texto_status}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")

async def finalizar_jogo(query, tabuleiro, vencedor):
    msg = f"🎉 **Fim de Jogo! Vencedor: {vencedor}**" if vencedor else "🤝 **Deu Velha! Empate!**"
    botoes = []
    for i in range(0, 9, 3):
        botoes.append([
            InlineKeyboardButton(tabuleiro[i], callback_data="none"),
            InlineKeyboardButton(tabuleiro[i+1], callback_data="none"),
            InlineKeyboardButton(tabuleiro[i+2], callback_data="none"),
        ])
    botoes.append([InlineKeyboardButton("🔙 Voltar aos Jogos", callback_data="menu_jogos_atalho")])
    await query.message.edit_text(f"⭕ **Jogo da Velha**\n\n{msg}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
