from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from pymongo import MongoClient
import os, random, asyncio

MONGO_URI = os.environ.get("MONGO_URI", "")
db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000, connectTimeoutMS=1000, tlsAllowInvalidCertificates=True)["sanizinhabot_db"]
jogos_db = db["jogo_minado"]

TAMANHO = 5
BOMBAS = 5

def setup_minado(app):
    app.add_handler(CallbackQueryHandler(iniciar_minado, pattern="^jogo_minado$"))
    app.add_handler(CallbackQueryHandler(tratar_botoes_minado, pattern="^min_"))
    app.add_handler(CommandHandler("minado", cmd_desafio_minado))


async def cmd_desafio_minado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    remetente = update.effective_user
    alvo = None

    if update.message.reply_to_message:
        alvo = update.message.reply_to_message.from_user
    elif context.args:
        alvo_nome = context.args[0].replace("@", "")
        admins = await context.bot.get_chat_administrators(chat.id)
        for m in admins:
            if m.user.username and m.user.username.lower() == alvo_nome.lower():
                alvo = m.user
                break
        if not alvo:
            await update.message.reply_text("⚠️ Usuário não encontrado!")
            return
    else:
        await update.message.reply_text("ℹ️ Use: `/minado @jogador` ou responda alguém")
        return

    if alvo.id == remetente.id:
        await update.message.reply_text("⚠️ Não pode desafiar a si mesmo!")
        return

    if jogos_db.find_one({"chat_id": chat.id, "ativo": True}):
        await update.message.reply_text("⚠️ Já existe partida em andamento!")
        return

    jogos_db.update_one({"chat_id": chat.id}, {"$set": {
        "tipo": "desafio_pendente", "ativo": True,
        "d1_id": remetente.id, "d1_nome": remetente.first_name,
        "d2_id": alvo.id, "d2_nome": alvo.first_name
    }}, upsert=True)

    botoes = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Aceitar", callback_data="min_aceitar")],
        [InlineKeyboardButton("❌ Recusar", callback_data="min_recusar")]
    ])
    await update.message.reply_text(
        f"💣 **DESAFIO CAMPO MINADO**\n\n{remetente.first_name} te desafiou!",
        reply_markup=botoes
    )


async def iniciar_minado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    partida = jogos_db.find_one({"chat_id": chat_id, "ativo": True})
    if partida:
        participantes = [partida.get("p1_id"), partida.get("p2_id"), partida.get("d1_id"), partida.get("d2_id")]
        if uid not in participantes:
            await query.answer("⚠️ Partida em andamento!", show_alert=True)
            return

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Contra a Máquina", callback_data="min_modo_ia")],
        [InlineKeyboardButton("⚔️ Jogador vs Jogador", callback_data="min_modo_pvp")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text(
        "💣 **CAMPO MINADO**\n\nClique nas células. Evite as bombas!\n"
        "O que abrir mais células sem explodir, vence!",
        reply_markup=teclado, parse_mode="Markdown"
    )


async def tratar_botoes_minado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data
    chat_id = query.message.chat_id
    uid = update.effective_user.id

    if dados == "min_aceitar":
        p = jogos_db.find_one({"chat_id": chat_id, "ativo": True, "tipo": "desafio_pendente"})
        if not p or uid != p["d2_id"]:
            await query.answer("⚠️ Não é pra você!", show_alert=True)
            return
        await query.answer("✅ Partida iniciada!")
        await iniciar_tabuleiro(query, "pvp", p["d1_id"], p["d1_nome"], p["d2_id"], p["d2_nome"], chat_id)
        return

    if dados == "min_recusar":
        p = jogos_db.find_one({"chat_id": chat_id, "ativo": True, "tipo": "desafio_pendente"})
        if not p or uid != p["d2_id"]: return
        await query.answer("❌ Recusado.")
        jogos_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text(f"❌ {p['d2_nome']} recusou o desafio.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]]))
        return

    if dados == "min_modo_ia":
        await iniciar_tabuleiro(query, "ia", uid, update.effective_user.first_name, None, None, chat_id)
        return

    if dados == "min_modo_pvp":
        await query.answer("ℹ️ Use `/minado @jogador` ou responda alguém para desafiar!")
        return

    if dados.startswith("min_pos_"):
        pos = int(dados.split("_")[2])
        partida = jogos_db.find_one({"chat_id": chat_id, "ativo": True})
        if not partida:
            await query.answer("⚠️ Inicie um jogo!", show_alert=True)
            return

        if partida["modo"] == "pvp" and uid != partida["vez"]:
            await query.answer("⚠️ Não é sua vez!", show_alert=True)
            return
        if partida["modo"] == "ia" and uid != partida["p1_id"]:
            await query.answer("⚠️ Não é sua vez!", show_alert=True)
            return

        if partida["aberto"][pos] != "❔":
            await query.answer("⚠️ Já foi!", show_alert=True)
            return

        if partida["bombas"][pos]:
            await explodir(query, partida, uid)
            return

        b = contar_bombas_vizinhas(partida["bombas"], pos)
        partida["aberto"][pos] = "✅" if b == 0 else str(b)
        jogos_db.update_one({"chat_id": chat_id}, {"$set": {"aberto": partida["aberto"]}})

        fechadas = partida["aberto"].count("❔")
        if fechadas == BOMBAS:
            await vitoria(query, partida)
            return

        if partida["modo"] == "pvp":
            novo_vez = partida["p2_id"] if partida["vez"] == partida["p1_id"] else partida["p1_id"]
            novo_nome = partida["p2_nome"] if partida["vez"] == partida["p1_id"] else partida["p1_nome"]
            jogos_db.update_one({"chat_id": chat_id}, {"$set": {"vez": novo_vez, "vez_nome": novo_nome}})
            await mostrar_tabuleiro(query, partida, f"🔄 Vez de {novo_nome}!")
        else:
            await mostrar_tabuleiro(query, partida, "✅ Continue!")
        return


def criar_tabuleiro():
    bombas = [False] * TAMANHO * TAMANHO
    escolhidas = random.sample(range(TAMANHO*TAMANHO), BOMBAS)
    for i in escolhidas: bombas[i] = True
    return bombas

def contar_bombas_vizinhas(bombas, pos):
    l = pos // TAMANHO
    c = pos % TAMANHO
    cnt = 0
    for dl in (-1,0,1):
        for dc in (-1,0,1):
            if dl==0 and dc==0: continue
            nl, nc = l+dl, c+dc
            if 0<=nl<TAMANHO and 0<=nc<TAMANHO:
                if bombas[nl*TAMANHO + nc]: cnt += 1
    return cnt

async def iniciar_tabuleiro(query, modo, p1_id, p1_nome, p2_id, p2_nome, chat_id):
    bombas = criar_tabuleiro()
    aberto = ["❔"] * (TAMANHO*TAMANHO)
    dados = {
        "modo": modo, "ativo": True, "bombas": bombas, "aberto": aberto,
        "p1_id": p1_id, "p1_nome": p1_nome,
        "p2_id": p2_id, "p2_nome": p2_nome,
        "vez": p1_id, "vez_nome": p1_nome, "chat_id": chat_id
    }
    jogos_db.update_one({"chat_id": chat_id}, {"$set": dados})
    await mostrar_tabuleiro(query, dados, f"🎮 Vez de {p1_nome}! Escolha uma célula.")

async def mostrar_tabuleiro(query, partida, mensagem):
    botoes = []
    for l in range(TAMANHO):
        linha = []
        for c in range(TAMANHO):
            i = l*TAMANHO + c
            linha.append(InlineKeyboardButton(partida["aberto"][i], callback_data=f"min_pos_{i}"))
        botoes.append(linha)
    botoes.append([InlineKeyboardButton("❌ Sair", callback_data="menu_jogos_atalho")])
    await query.message.edit_text(
        f"💣 **CAMPO MINADO** — {partida['vez_nome']} joga\n\n{mensagem}",
        reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown"
    )

async def explodir(query, partida, uid):
    perdedor_nome = partida["vez_nome"]
    revelado = ["💥" if b else ("❔" if a=="❔" else a) for a,b in zip(partida["aberto"], partida["bombas"])]
    botoes = []
    for l in range(TAMANHO):
        linha = []
        for c in range(TAMANHO):
            i = l*TAMANHO + c
            linha.append(InlineKeyboardButton(revelado[i], callback_data="min_pos_0"))
        botoes.append(linha)
    botoes.append([InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")])

    if partida["modo"]=="pvp":
        vencedor_nome = partida["p2_nome"] if uid==partida["p1_id"] else partida["p1_nome"]
    else:
        vencedor_nome = "🤖 Máquina"

    jogos_db.delete_one({"chat_id": partida["chat_id"]})
    await query.message.edit_text(
        f"💥 **EXPLODIU!** 💥\n\n{perdedor_nome} pisou numa bomba!\n🏆 Vencedor: {vencedor_nome}",
        reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown"
    )

async def vitoria(query, partida):
    jogos_db.delete_one({"chat_id": partida["chat_id"]})
    botoes = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]])
    await query.message.edit_text(
        f"🏆 **VITÓRIA!** 🏆\n\nTodas as células seguras foram abertas!\nParabéns, {partida['vez_nome']}!",
        reply_markup=botoes, parse_mode="Markdown"
    )
