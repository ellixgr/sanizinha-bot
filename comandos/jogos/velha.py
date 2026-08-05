from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from pymongo import MongoClient
import os
import random

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
        await update.message.reply_text("⚠️ Para jogar PvP com amigos use /velha @usuario ou marque alguém com /velha respondendo a mensagem dele!", parse_mode="Markdown")
        return

    desafiado = reply.from_user

    if desafiado.id == user.id:
        await update.message.reply_text("❌ Você não pode desafiar a si mesmo!", parse_mode="Markdown")
        return
    
    if desafiado.is_bot:
        tabuleiro = [" " for _ in range(9)]
        jogos_db.update_one(
            {"chat_id": chat.id},
            {"$set": {
                "chat_id": chat.id,
                "tabuleiro": tabuleiro,
                "turno": user.id,
                "modo": "ia",
                "X": user.id,
                "O": "IA",
                "status": "ativo",
                "voto_revanche": []
            }},
            upsert=True
        )
        botoes = []
        for i in range(0, 9, 3):
            botoes.append([
                InlineKeyboardButton("⬜", callback_data=f"vpos_{i}"),
                InlineKeyboardButton("⬜", callback_data=f"vpos_{i+1}"),
                InlineKeyboardButton("⬜", callback_data=f"vpos_{i+2}"),
            ])
        botoes.append([InlineKeyboardButton("🚫 Cancelar Partida", callback_data="v_cancelar")])
        
        await update.message.reply_text(
            f"🤖 Jogo contra a Máquina iniciado por {user.mention_markdown()}! Sua vez (❌).\n*(Apenas {user.first_name} pode jogar nesta partida)*",
            reply_markup=InlineKeyboardMarkup(botoes),
            parse_mode="Markdown"
        )
        return

    jogos_db.update_one(
        {"chat_id": chat.id},
        {"$set": {
            "chat_id": chat.id,
            "desafiante_id": user.id,
            "desafiante_nome": user.first_name,
            "desafiado_id": desafiado.id,
            "desafiado_nome": desafiado.first_name,
            "status": "pendente",
            "voto_revanche": []
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
    chat_id = query.message.chat_id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    await query.answer()
    
    estado = jogos_db.find_one({"chat_id": chat_id})
    if estado and estado.get("status") == "ativo":
        await query.answer("⚠️ Já existe uma partida ativa neste grupo!", show_alert=True)
        return

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Jogar PvP", callback_data="v_infopvp")],
        [InlineKeyboardButton("🤖 Jogar Contra a Máquina", callback_data="v_modoia")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text(
        "⭕ **Jogo da Velha**\n\nEscolha o modo de jogo:",
        reply_markup=teclado,
        parse_mode="Markdown"
    )

async def tratar_botoes_velha(update: Update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user = update.effective_user
    user_id = user.id
    user_name = user.first_name

    if data == "v_infopvp":
        await query.answer("Para jogar PvP com amigos use /velha @usuario ou responda alguém", show_alert=True)
        return

    if data == "v_modoia":
        estado_atual = jogos_db.find_one({"chat_id": chat_id})
        if estado_atual and estado_atual.get("status") == "ativo":
            await query.answer("⚠️ Já existe uma partida ativa neste grupo!", show_alert=True)
            return

        tabuleiro = [" " for _ in range(9)]
        jogos_db.update_one(
            {"chat_id": chat_id},
            {"$set": {
                "chat_id": chat_id,
                "tabuleiro": tabuleiro,
                "turno": user_id,
                "modo": "ia",
                "X": user_id,
                "O": "IA",
                "status": "ativo",
                "voto_revanche": []
            }},
            upsert=True
        )
        await query.answer()
        
        botoes = []
        for i in range(0, 9, 3):
            botoes.append([
                InlineKeyboardButton("⬜", callback_data=f"vpos_{i}"),
                InlineKeyboardButton("⬜", callback_data=f"vpos_{i+1}"),
                InlineKeyboardButton("⬜", callback_data=f"vpos_{i+2}"),
            ])
        botoes.append([InlineKeyboardButton("🚫 Cancelar Partida", callback_data="v_cancelar")])

        await query.message.edit_text(
            f"⭕ **Jogo da Velha** (Contra IA)\nStatus: 🤖 Jogo contra a Máquina iniciado! Sua vez ({user_name} - ❌).\n*(Apenas {user_name} pode jogar nesta partida)*",
            reply_markup=InlineKeyboardMarkup(botoes),
            parse_mode="Markdown"
        )
        return

    estado = jogos_db.find_one({"chat_id": chat_id})

    if data == "v_aceitar":
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
                "status": "ativo",
                "voto_revanche": []
            }}
        )
        await query.answer()
        await atualizar_tabuleiro(query, tabuleiro, f"⚔️ Partida iniciada! Vez de {estado['desafiante_nome']} (❌).")
        return

    if data == "v_recusar":
        if not estado:
            await query.answer("⚠️ Convite não encontrado.", show_alert=True)
            return
        
        if user_id != estado["desafiado_id"]:
            await query.answer("❌ Apenas o usuário desafiado pode recusar este convite!", show_alert=True)
            return
        
        jogos_db.delete_one({"chat_id": chat_id})
        await query.answer()
        await query.message.edit_text("❌ **Desafio recusado!** A partida foi cancelada.", parse_mode="Markdown")
        return

    if data == "v_cancelar":
        if not estado:
            await query.answer("⚠️ Nenhuma partida ativa neste grupo.", show_alert=True)
            return
        
        dono_id = int(os.environ.get("DONO_ID", 0))
        is_participante = (
            user_id == estado.get("desafiante_id") or 
            user_id == estado.get("desafiado_id") or 
            user_id == estado.get("X")
        )
        if not is_participante and user_id != dono_id:
            await query.answer("❌ Apenas os participantes podem cancelar a partida!", show_alert=True)
            return
        
        jogos_db.delete_one({"chat_id": chat_id})
        await query.answer()
        await query.message.edit_text("🚫 **Partida cancelada** com sucesso.", parse_mode="Markdown")
        return

    if data == "v_reiniciar":
        if not estado:
            await query.answer("⚠️ Jogo não encontrado.", show_alert=True)
            return
        
        modo = estado.get("modo")
        
        if modo == "ia":
            if user_id != estado.get("X"):
                await query.answer("❌ Você não está participando desta partida contra a IA!", show_alert=True)
                return

            tabuleiro = [" " for _ in range(9)]
            jogos_db.update_one(
                {"chat_id": chat_id},
                {"$set": {
                    "tabuleiro": tabuleiro,
                    "turno": user_id,
                    "X": user_id,
                    "O": "IA",
                    "status": "ativo",
                    "voto_revanche": []
                }}
            )
            await query.answer("✅ Novo jogo iniciado!")
            await atualizar_tabuleiro(query, tabuleiro, "🎮 Novo jogo contra a IA iniciado! Sua vez (❌).")
            return
            
        elif modo == "pvp":
            desafiante_id = estado.get("desafiante_id")
            desafiado_id = estado.get("desafiado_id")
            
            if user_id != desafiante_id and user_id != desafiado_id:
                await query.answer("❌ Apenas os jogadores da partida podem pedir revanche!", show_alert=True)
                return
            
            votos = estado.get("voto_revanche", [])
            if user_id in votos:
                await query.answer("⚠️ Você já votou para jogar de novo! Aguardando o oponente.", show_alert=True)
                return
            
            votos.append(user_id)
            jogos_db.update_one({"chat_id": chat_id}, {"$set": {"voto_revanche": votos}})
            
            desafiante_nome = estado.get("desafiante_nome")
            desafiado_nome = estado.get("desafiado_nome")
            
            if len(votos) >= 2:
                tabuleiro = [" " for _ in range(9)]
                novo_x = estado.get("O")
                novo_o = estado.get("X")
                
                jogos_db.update_one(
                    {"chat_id": chat_id},
                    {"$set": {
                        "tabuleiro": tabuleiro,
                        "turno": novo_x,
                        "X": novo_x,
                        "O": novo_o,
                        "status": "ativo",
                        "voto_revanche": []
                    }}
                )
                await query.answer("⚔️ Ambos aceitaram! Nova partida iniciada!")
                nome_comeca = desafiante_nome if novo_x == desafiante_id else desafiado_nome
                await atualizar_tabuleiro(query, tabuleiro, f"⚔️ Revanche iniciada! Vez de {nome_comeca} (❌).")
            else:
                await query.answer("✅ Voto registrado! Aguardando o oponente.")
                falta_id = desafiado_id if user_id == desafiante_id else desafiante_id
                nome_falta = desafiado_nome if user_id == desafiante_id else desafiante_nome
                nome_votou = desafiante_nome if user_id == desafiante_id else desafiado_nome
                
                msg_base = query.message.text.split("\n\n⏳")[0].split("\n\n🎮")[0].split("\n\n🤝")[0]
                
                teclado_revanche = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎮 JOGAR DE NOVO", callback_data="v_reiniciar")],
                    [InlineKeyboardButton("🔙 Voltar aos Jogos", callback_data="menu_jogos_atalho")]
                ])
                
                await query.message.edit_text(
                    f"{msg_base}\n\n⏳ O usuário **{nome_votou}** quer jogar de novo! O usuário **{nome_falta}** tem que aceitar.",
                    reply_markup=teclado_revanche,
                    parse_mode="Markdown"
                )
            return

async def jogada_velha(update: Update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user_id = update.effective_user.id

    pos = int(data.split("_")[1])
    estado = jogos_db.find_one({"chat_id": chat_id})
    
    if not estado or estado.get("status") != "ativo":
        await query.answer("⚠️ Jogo expirado ou não encontrado. Inicie um novo!", show_alert=True)
        return

    modo = estado.get("modo")
    turno = estado.get("turno")
    tabuleiro = estado.get("tabuleiro")

    if modo == "pvp":
        if user_id != estado.get("X") and user_id != estado.get("O"):
            await query.answer("❌ Você não está participando desta partida!", show_alert=True)
            return
        if user_id != turno:
            await query.answer("❌ Não é a sua vez de jogar!", show_alert=True)
            return
        if tabuleiro[pos] != " ":
            await query.answer("⚠️ Este espaço já está ocupado!", show_alert=True)
            return

        simbolo = "❌" if user_id == estado["X"] else "⭕"
        tabuleiro[pos] = simbolo
        
        vencedor = verificar_vencedor(tabuleiro)
        if vencedor or " " not in tabuleiro:
            vencedor_nome = estado["desafiante_nome"] if vencedor == "❌" else estado["desafiado_nome"] if vencedor == "⭕" else None
            await query.answer()
            await finalizar_jogo(query, tabuleiro, vencedor, vencedor_nome, modo="pvp")
            return

        proximo_turno = estado["O"] if user_id == estado["X"] else estado["X"]
        proximo_nome = estado["desafiado_nome"] if user_id == estado["X"] else estado["desafiante_nome"]
        simbolo_prox = "❌" if proximo_turno == estado["X"] else "⭕"
        
        jogos_db.update_one({"chat_id": chat_id}, {"$set": {"tabuleiro": tabuleiro, "turno": proximo_turno}})
        await query.answer()
        await atualizar_tabuleiro(query, tabuleiro, f"Vez de {proximo_nome} ({simbolo_prox})")

    elif modo == "ia":
        if user_id != estado.get("X"):
            await query.answer("❌ Você não está jogando nesta partida!", show_alert=True)
            return
        if tabuleiro[pos] != " ":
            await query.answer("⚠️ Este espaço já está ocupado!", show_alert=True)
            return
        
        tabuleiro[pos] = "❌"
        vencedor = verificar_vencedor(tabuleiro)
        if vencedor or " " not in tabuleiro:
            await query.answer()
            await finalizar_jogo(query, tabuleiro, vencedor, "Você" if vencedor == "❌" else "Máquina", modo="ia")
            return

        vazias = [i for i, x in enumerate(tabuleiro) if x == " "]
        if vazias:
            ai_pos = random.choice(vazias)
            tabuleiro[ai_pos] = "⭕"

        vencedor = verificar_vencedor(tabuleiro)
        if vencedor or " " not in tabuleiro:
            await query.answer()
            await finalizar_jogo(query, tabuleiro, vencedor, "Você" if vencedor == "❌" else "Máquina", modo="ia")
            return

        jogos_db.update_one({"chat_id": chat_id}, {"$set": {"tabuleiro": tabuleiro}})
        await query.answer()
        await atualizar_tabuleiro(query, tabuleiro, "Sua vez (❌)")

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
            InlineKeyboardButton(tabuleiro[i] if tabuleiro[i] != " " else "⬜", callback_data=f"vpos_{i}"),
            InlineKeyboardButton(tabuleiro[i+1] if tabuleiro[i+1] != " " else "⬜", callback_data=f"vpos_{i+1}"),
            InlineKeyboardButton(tabuleiro[i+2] if tabuleiro[i+2] != " " else "⬜", callback_data=f"vpos_{i+2}"),
        ]
        botoes.append(linha)
    botoes.append([InlineKeyboardButton("🚫 Cancelar Partida", callback_data="v_cancelar")])
    
    await query.message.edit_text(f"⭕ **Jogo da Velha**\nStatus: {texto_status}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")

async def finalizar_jogo(query, tabuleiro, vencedor, nome_vencedor=None, modo="ia"):
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
    
    botoes.append([InlineKeyboardButton("🎮 JOGAR DE NOVO", callback_data="v_reiniciar")])
    botoes.append([InlineKeyboardButton("🔙 Voltar aos Jogos", callback_data="menu_jogos_atalho")])
    
    await query.message.edit_text(f"⭕ **Jogo da Velha** ({'PvP' if modo == 'pvp' else 'Contra IA'})\n\n{msg}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
