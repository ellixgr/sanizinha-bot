from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from pymongo import MongoClient
import os, random, asyncio

MONGO_URI = os.environ.get("MONGO_URI", "")
db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000, connectTimeoutMS=1000, tlsAllowInvalidCertificates=True)["sanizinhabot_db"]
jogos_db = db["jogo_memoria"]

ICONS = ["🍎", "🍌", "🍇", "🍓", "🍊", "🍑"]
TOTAL_PARES = 3

def setup_memoria(app):
    app.add_handler(CallbackQueryHandler(iniciar_memoria, pattern="^jogo_memoria$"))
    app.add_handler(CallbackQueryHandler(tratar_botoes_memoria, pattern="^mem_"))
    app.add_handler(CommandHandler("memory", cmd_desafio_memoria))


async def cmd_desafio_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    remetente = update.effective_user
    alvo = None

    if update.message.reply_to_message:
        alvo = update.message.reply_to_message.from_user
    elif context.args:
        alvo_nome = context.args[0].replace("@", "")
        membros = await context.bot.get_chat_administrators(chat.id)
        for m in membros:
            if m.user.username and m.user.username.lower() == alvo_nome.lower():
                alvo = m.user
                break
        if not alvo:
            await update.message.reply_text("⚠️ Usuário não encontrado no chat!")
            return
    else:
        await update.message.reply_text("ℹ️ Use: `/memory @jogador` ou responda alguém")
        return

    if alvo.id == remetente.id:
        await update.message.reply_text("⚠️ Não pode desafiar a si mesmo!")
        return

    if jogos_db.find_one({"chat_id": chat.id, "ativo": True}):
        await update.message.reply_text("⚠️ Já existe partida em andamento!")
        return

    jogos_db.update_one({"chat_id": chat.id}, {"$set": {
        "tipo": "desafio_pendente", "desafiante_id": remetente.id,
        "desafiante_nome": remetente.first_name, "desafiado_id": alvo.id,
        "desafiado_nome": alvo.first_name, "ativo": True
    }}, upsert=True)

    botoes = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Aceitar Desafio", callback_data="mem_aceitar_pvp")],
        [InlineKeyboardButton("❌ Recusar", callback_data="mem_recusar_pvp")]
    ])
    await update.message.reply_text(
        f"🎮 **DESAFIO DE MEMÓRIA** 🎮\n\n{remetente.first_name} te desafiou!",
        reply_markup=botoes, parse_mode="Markdown"
    )


async def iniciar_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    partida = jogos_db.find_one({"chat_id": chat_id, "ativo": True})
    if partida:
        participantes = [partida.get("jogador1_id"), partida.get("jogador2_id"),
                         partida.get("desafiante_id"), partida.get("desafiado_id")]
        if uid not in participantes:
            await query.answer("⚠️ Partida em andamento!", show_alert=True)
            return
        if partida.get("tipo") == "desafio_pendente" and uid == partida.get("desafiante_id"):
            await query.answer("⚠️ Aguarde o jogador aceitar!", show_alert=True)
            return

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Contra a Máquina", callback_data="mem_modo_ia")],
        [InlineKeyboardButton("⚔️ Jogador vs Jogador", callback_data="mem_modo_pvp")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text(
        "🧠 **Jogo da Memória**\n\nEncontre os pares! Escolha o modo:",
        reply_markup=teclado, parse_mode="Markdown"
    )


async def tratar_botoes_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data
    chat_id = query.message.chat_id
    uid = update.effective_user.id

    if dados == "mem_aceitar_pvp":
        partida = jogos_db.find_one({"chat_id": chat_id, "ativo": True, "tipo": "desafio_pendente"})
        if not partida or uid != partida["desafiado_id"]:
            await query.answer("⚠️ Não é pra você!", show_alert=True)
            return
        await query.answer("✅ Desafio aceito!")
        await iniciar_partida_pvp(query, partida["desafiante_id"], partida["desafiante_nome"],
                                   partida["desafiado_id"], partida["desafiado_nome"], chat_id)
        return

    if dados == "mem_recusar_pvp":
        partida = jogos_db.find_one({"chat_id": chat_id, "ativo": True, "tipo": "desafio_pendente"})
        if not partida or uid != partida["desafiado_id"]: return
        await query.answer("❌ Recusado.")
        jogos_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text(f"❌ {partida['desafiado_nome']} recusou.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]]))
        return

    if dados == "mem_modo_ia":
        await iniciar_partida_ia(query, uid, update.effective_user.first_name, chat_id)
        return

    if dados == "mem_modo_pvp":
        await query.answer("ℹ️ Use `/memory @jogador` ou responda alguém!")
        return

    if dados.startswith("mem_pos_"):
        pos = int(dados.split("_")[2])
        partida = jogos_db.find_one({"chat_id": chat_id, "ativo": True})
        if not partida:
            await query.answer("⚠️ Inicie um jogo!", show_alert=True)
            return

        if partida.get("modo") == "pvp" and uid != partida.get("vez"):
            await query.answer("⚠️ Não é sua vez!", show_alert=True)
            return
        if partida.get("modo") == "ia" and uid != partida.get("jogador1_id"):
            await query.answer("⚠️ Não é sua vez!", show_alert=True)
            return

        cartas = partida["cartas"]
        if cartas[pos] != "❓":
            await query.answer("⚠️ Carta já aberta!", show_alert=True)
            return

        icones = partida["icones"]
        cartas[pos] = icones[pos]
        primeira = partida.get("selecionada")

        if primeira is None:
            jogos_db.update_one({"chat_id": chat_id}, {"$set": {"cartas": cartas, "selecionada": pos}})
            await mostrar_painel(query, partida, "🔍 Escolha a segunda carta...")
            return

        acertou = (icones[primeira] == icones[pos])
        jogador_vez = partida["vez_nome"]

        if acertou:
            pontos = partida.get("pontos_vez", 0) + 1
            max_pares = partida.get("total_pares", TOTAL_PARES)
            jogos_db.update_one({"chat_id": chat_id}, {"$set": {
                "cartas": cartas, "selecionada": None, "pontos_vez": pontos
            }})
            if pontos >= max_pares:
                await finalizar_jogo(query, partida, vencedor=jogador_vez)
                return
            await mostrar_painel(query, partida, f"✅ {jogador_vez} ACERTOU! Jogue de novo!")
        else:
            cartas[primeira] = "❓"
            cartas[pos] = "❓"
            await mostrar_painel(query, partida, f"❌ {jogador_vez} ERROU! Passando a vez...")
            if partida["modo"] == "ia":
                await asyncio.sleep(1.2)
                await jogada_ia(query, partida)
                return
            else:
                novo_vez_id = partida["jogador2_id"] if partida["vez"] == partida["jogador1_id"] else partida["jogador1_id"]
                novo_vez_nome = partida["jogador2_nome"] if partida["vez"] == partida["jogador1_id"] else partida["jogador1_nome"]
                jogos_db.update_one({"chat_id": chat_id}, {"$set": {
                    "cartas": cartas, "selecionada": None, "vez": novo_vez_id,
                    "vez_nome": novo_vez_nome, "pontos_vez": partida.get("pontos_outro", 0)
                }})
                await asyncio.sleep(1)
                await mostrar_painel(query, partida, f"🔄 Vez de {novo_vez_nome}!")
        return


async def iniciar_partida_ia(query, jog_id, jog_nome, chat_id):
    icones = ICONS[:TOTAL_PARES] * 2
    random.shuffle(icones)
    cartas = ["❓"] * 6
    jogos_db.update_one({"chat_id": chat_id}, {"$set": {
        "modo": "ia", "ativo": True, "icones": icones, "cartas": cartas,
        "selecionada": None, "jogador1_id": jog_id, "jogador1_nome": jog_nome,
        "vez": jog_id, "vez_nome": jog_nome, "pontos_vez": 0, "total_pares": TOTAL_PARES
    }})
    await mostrar_painel(query, jogos_db.find_one({"chat_id": chat_id}), "Sua vez! Escolha uma carta.")


async def iniciar_partida_pvp(query, j1_id, j1_nome, j2_id, j2_nome, chat_id):
    icones = ICONS[:TOTAL_PARES] * 2
    random.shuffle(icones)
    cartas = ["❓"] * 6
    jogos_db.update_one({"chat_id": chat_id}, {"$set": {
        "modo": "pvp", "ativo": True, "icones": icones, "cartas": cartas,
        "selecionada": None, "jogador1_id": j1_id, "jogador1_nome": j1_nome,
        "jogador2_id": j2_id, "jogador2_nome": j2_nome,
        "vez": j1_id, "vez_nome": j1_nome, "pontos_vez": 0, "pontos_outro": 0, "total_pares": TOTAL_PARES
    }})
    await mostrar_painel(query, jogos_db.find_one({"chat_id": chat_id}), f"🎮 Vez de {j1_nome}!")


async def jogada_ia(query, partida):
    icones = partida["icones"]
    cartas = partida["cartas"]
    desconhecidas = [i for i,c in enumerate(cartas) if c == "❓"]
    if len(desconhecidas) < 2: return

    a, b = random.sample(desconhecidas, 2)
    cartas[a] = icones[a]
    cartas[b] = icones[b]
    acertou = (icones[a] == icones[b])

    if acertou:
        pts = partida.get("pontos_ia", 0) + 1
        jogos_db.update_one({"chat_id": partida["chat_id"]}, {"$set": {
            "cartas": cartas, "pontos_ia": pts, "selecionada": None
        }})
        if pts >= TOTAL_PARES:
            await finalizar_jogo(query, partida, vencedor="🤖 Máquina")
            return
        await mostrar_painel(query, partida, "🤖 Máquina ACERTOU! Sua vez...")
    else:
        await mostrar_painel(query, partida, "🤖 Máquina ERROU! Sua vez...")
        await asyncio.sleep(1.2)
        cartas[a] = "❓"
        cartas[b] = "❓"
        jogos_db.update_one({"chat_id": partida["chat_id"]}, {"$set": {
            "cartas": cartas, "selecionada": None, "vez": partida["jogador1_id"],
            "vez_nome": partida["jogador1_nome"], "pontos_vez": partida.get("pontos_jogador", 0)
        }})
        await mostrar_painel(query, partida, "🔄 Sua vez!")


async def mostrar_painel(query, partida, texto):
    cartas = partida["cartas"]
    botoes = [
        [InlineKeyboardButton(cartas[0], callback_data="mem_pos_0"),
         InlineKeyboardButton(cartas[1], callback_data="mem_pos_1"),
         InlineKeyboardButton(cartas[2], callback_data="mem_pos_2")],
        [InlineKeyboardButton(cartas[3], callback_data="mem_pos_3"),
         InlineKeyboardButton(cartas[4], callback_data="mem_pos_4"),
         InlineKeyboardButton(cartas[5], callback_data="mem_pos_5")],
        [InlineKeyboardButton("❌ Sair", callback_data="menu_jogos_atalho")]
    ]
    if partida["modo"] == "ia":
        pts_j = partida.get("pontos_vez", 0)
        pts_m = partida.get("pontos_ia", 0)
        placar = f"📊 Você {pts_j} × {pts_m} 🤖"
    else:
        pts1 = partida.get("pontos_vez", 0) if partida["vez"] == partida["jogador1_id"] else partida.get("pontos_outro", 0)
        pts2 = partida.get("pontos_vez", 0) if partida["vez"] == partida["jogador2_id"] else partida.get("pontos_outro", 0)
        placar = f"📊 {partida['jogador1_nome']} {pts1} × {pts2} {partida['jogador2_nome']}"

    await query.message.edit_text(
        f"🧠 **Jogo da Memória**\n{placar}\n\n{texto}",
        reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown"
    )


async def finalizar_jogo(query, partida, vencedor):
    jogos_db.delete_one({"chat_id": partida["chat_id"]})
    botoes = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]])
    await query.message.edit_text(
        f"🏆 **FIM DE JOGO!**\n\nVencedor: {vencedor} 🎉",
        reply_markup=botoes, parse_mode="Markdown"
    )
