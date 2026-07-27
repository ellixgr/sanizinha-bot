import random
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

logger = logging.getLogger("SanizinhaBot.Velha")

partidas = {}
convites = {}

def setup_velha(app: Application):
    app.add_handler(CommandHandler("velha", iniciar_velha))
    app.add_handler(CommandHandler("resetvelha", resetar_velha))
    app.add_handler(CommandHandler("infovelha", info_velha))
    app.add_handler(CallbackQueryHandler(callback_velha, pattern=r"^velha_"))

async def iniciar_velha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    if not message or not user:
        return
        
    user_id = user.id
    user_name = user.first_name

    alvo_mencionado = None
    if message.reply_to_message and message.reply_to_message.from_user:
        alvo_mencionado = message.reply_to_message.from_user
    elif context.args:
        alvo_mencionado = context.args[0]

    if alvo_mencionado:
        if hasattr(alvo_mencionado, "id"):
            alvo_id = alvo_mencionado.id
            alvo_nome = alvo_mencionado.first_name
            alvo_mention = alvo_mencionado.mention_html()
        else:
            alvo_id = 999999
            alvo_nome = str(alvo_mencionado)
            alvo_mention = str(alvo_mencionado)

        if alvo_id == user_id:
            await message.reply_text("Você não pode jogar contra si mesmo!")
            return

        convites[user_id] = {
            "desafiante_id": user_id,
            "desafiante_nome": user_name,
            "alvo_id": alvo_id,
            "alvo_nome": alvo_nome,
            "chat_id": message.chat_id
        }

        botoes = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Sim 👍", callback_data=f"velha_aceitar_{user_id}"),
                InlineKeyboardButton("Não 👎", callback_data=f"velha_recusar_{user_id}")
            ]
        ])

        await message.reply_text(
            f"O usuário {user.mention_html()} está te desafiando para uma partida de Jogo da Velha, {alvo_mention}.\nVocê aceita?",
            reply_markup=botoes,
            parse_mode="HTML"
        )
        return

    chat_id = message.chat_id
    tabuleiro = [["⬜", "⬜", "⬜"], 
                 ["⬜", "⬜", "⬜"], 
                 ["⬜", "⬜", "⬜"]]

    partidas[chat_id] = {
        "modo": "solo",
        "tabuleiro": tabuleiro,
        "turno": "jogador",
        "jogador_id": user_id,
        "jogador_nome": user_name,
        "simbolo_jogador": "❌",
        "simbolo_maquina": "⭕"
    }

    texto = f"🎮 **Modo Solo** vs 🤖 **Máquina**\nSímbolo: ❌\nSua vez de jogar, {user_name}!"
    
    await message.reply_text(
        texto,
        reply_markup=gerar_teclado(tabuleiro),
        parse_mode="Markdown"
    )

async def resetar_velha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    chat_id = message.chat_id
    
    removido = False
    if chat_id in partidas:
        del partidas[chat_id]
        removido = True
        
    convites_removidos = [did for did, dados in list(convites.items()) if dados.get("chat_id") == chat_id]
    for did in convites_removidos:
        del convites[did]
        removido = True

    if removido:
        await message.reply_text("🧹 Todas as partidas pendentes e em andamento neste chat foram limpas com sucesso!")
    else:
        await message.reply_text("ℹ️ Não há partidas ativas ou convites pendentes neste chat para resetar.")

async def info_velha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    texto = (
        "📖 **Como jogar Jogo da Velha:**\n\n"
        "🤖 **Modo Solo (Contra a Máquina):**\n"
        "• Digite `/velha` sem marcar ninguém.\n"
        "• Você jogará com ❌ contra a inteligência artificial ⭕.\n\n"
        "👥 **Modo PvP (Contra outro Jogador):**\n"
        "• Responda a mensagem de um usuário com `/velha` ou digite `/velha @usuario`.\n"
        "• O desafiado deverá clicar no botão **Sim 👍** para aceitar a partida.\n\n"
        "🧹 **Limpar Partidas:**\n"
        "• Use `/resetvelha` para apagar qualquer jogo travado ou convite pendente no chat."
    )
    await message.reply_text(texto, parse_mode="Markdown")

async def callback_velha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    partes = data.split("_")
    acao = partes[1]

    if acao in ["aceitar", "recusar"]:
        desafiante_id = int(partes[2])

        if desafiante_id not in convites:
            await query.answer("Este convite expirou ou não é válido.", show_alert=True)
            return

        dados_convite = convites[desafiante_id]
        
        if user_id == desafiante_id:
            await query.answer("Você não pode aceitar o seu próprio desafio! Aguarde o outro jogador.", show_alert=True)
            return

        alvo_id = dados_convite.get("alvo_id")
        if alvo_id and alvo_id != 999999 and user_id != alvo_id:
            await query.answer("Este desafio não foi direcionado a você!", show_alert=True)
            return

        if acao == "recusar":
            del convites[desafiante_id]
            await query.message.edit_text("O usuário recusou o desafio de Jogo da Velha.")
            await query.answer()
            return

        chat_id = query.message.chat_id
        del convites[desafiante_id]

        tabuleiro = [["⬜", "⬜", "⬜"], 
                     ["⬜", "⬜", "⬜"], 
                     ["⬜", "⬜", "⬜"]]

        p1_nome = dados_convite["desafiante_nome"]
        p2_nome = query.from_user.first_name
        p2_id = query.from_user.id

        partidas[chat_id] = {
            "modo": "pvp",
            "tabuleiro": tabuleiro,
            "turno_id": desafiante_id,
            "p1_id": desafiante_id,
            "p1_nome": p1_nome,
            "p1_simbolo": "❌",
            "p2_id": p2_id,
            "p2_nome": p2_nome,
            "p2_simbolo": "⭕"
        }

        texto = f"🎮 **Modo PvP**\n{p1_nome} (❌) vs {p2_nome} (⭕)\nSua vez de jogar, {p1_nome}!"
        await query.message.edit_text(
            text=texto,
            reply_markup=gerar_teclado(tabuleiro),
            parse_mode="Markdown"
        )
        await query.answer()
        return

    if len(partes) >= 4 and partes[1] == "jogar":
        chat_id = query.message.chat_id
        linha, coluna = int(partes[2]), int(partes[3])

        if chat_id not in partidas:
            await query.answer("Essa partida já expirou. Digite /velha novamente.", show_alert=True)
            return

        jogo = partidas[chat_id]

        if jogo["modo"] == "solo":
            if user_id != jogo["jogador_id"]:
                await query.answer("Você não está participando deste jogo!", show_alert=True)
                return
            if jogo["turno"] != "jogador":
                await query.answer("Não é a sua vez!", show_alert=True)
                return

            if jogo["tabuleiro"][linha][coluna] != "⬜":
                await query.answer("Essa casa já está ocupada!", show_alert=True)
                return

            jogo["tabuleiro"][linha][coluna] = jogo["simbolo_jogador"]

            vencedor = verificar_vencedor(jogo["tabuleiro"])
            if vencedor:
                await finalizar_partida(query, jogo, vencedor, "solo")
                return

            jogo["turno"] = "maquina"
            jogada_maquina(jogo)

            vencedor = verificar_vencedor(jogo["tabuleiro"])
            if vencedor:
                await finalizar_partida(query, jogo, vencedor, "solo")
                return

            jogo["turno"] = "jogador"
            texto = f"🎮 **Modo Solo** vs 🤖 **Máquina**\nSímbolo: ❌\nSua vez de jogar, {jogo['jogador_nome']}!"

            await query.message.edit_text(
                text=texto,
                reply_markup=gerar_teclado(jogo["tabuleiro"]),
                parse_mode="Markdown"
            )
            await query.answer()

        elif jogo["modo"] == "pvp":
            if user_id != jogo["p1_id"] and user_id != jogo["p2_id"]:
                await query.answer("Você não faz parte desta partida!", show_alert=True)
                return

            if user_id != jogo["turno_id"]:
                await query.answer("Não é a sua vez!", show_alert=True)
                return

            if jogo["tabuleiro"][linha][coluna] != "⬜":
                await query.answer("Essa casa já está ocupada!", show_alert=True)
                return

            simbolo = jogo["p1_simbolo"] if user_id == jogo["p1_id"] else jogo["p2_simbolo"]
            jogo["tabuleiro"][linha][coluna] = simbolo

            vencedor = verificar_vencedor(jogo["tabuleiro"])
            if vencedor:
                await finalizar_partida(query, jogo, vencedor, "pvp")
                return

            proximo_id = jogo["p2_id"] if user_id == jogo["p1_id"] else jogo["p1_id"]
            proximo_nome = jogo["p2_nome"] if user_id == jogo["p1_id"] else jogo["p1_nome"]
            jogo["turno_id"] = proximo_id

            simbolo_proximo = jogo["p1_simbolo"] if proximo_id == jogo["p1_id"] else jogo["p2_simbolo"]
            texto = f"🎮 **Modo PvP**\nTurno de: {proximo_nome} ({simbolo_proximo})"

            await query.message.edit_text(
                text=texto,
                reply_markup=gerar_teclado(jogo["tabuleiro"]),
                parse_mode="Markdown"
            )
            await query.answer()

def gerar_teclado(tabuleiro):
    teclado = []
    for r in range(3):
        linha = []
        for c in range(3):
            simbolo = tabuleiro[r][c]
            linha.append(InlineKeyboardButton(simbolo, callback_data=f"velha_jogar_{r}_{c}"))
        teclado.append(linha)
    return InlineKeyboardMarkup(teclado)

def jogada_maquina(jogo):
    tab = jogo["tabuleiro"]
    vazias = [(r, c) for r in range(3) for c in range(3) if tab[r][c] == "⬜"]
    if vazias:
        r, c = random.choice(vazias)
        tab[r][c] = jogo["simbolo_maquina"]

def verificar_vencedor(tab):
    for i in range(3):
        if tab[i][0] == tab[i][1] == tab[i][2] != "⬜":
            return tab[i][0]
        if tab[0][i] == tab[1][i] == tab[2][i] != "⬜":
            return tab[0][i]
    
    if tab[0][0] == tab[1][1] == tab[2][2] != "⬜":
        return tab[0][0]
    if tab[0][2] == tab[1][1] == tab[2][0] != "⬜":
        return tab[0][2]

    if all(tab[r][c] != "⬜" for r in range(3) for c in range(3)):
        return "Empate"

    return None

async def finalizar_partida(query, jogo, resultado, modo):
    chat_id = query.message.chat_id
    
    if modo == "solo":
        if resultado == "Empate":
            texto = "🤝 **Fim de jogo! Deu Velha (Empate)!**"
        elif resultado == jogo["simbolo_jogador"]:
            texto = f"🎉 **Parabéns, {jogo['jogador_nome']}! Você venceu a máquina!**"
        else:
            texto = "🤖 **A Máquina venceu! Tente novamente.**"
    else:
        if resultado == "Empate":
            texto = "🤝 **Fim de jogo! Deu Velha (Empate)!**"
        else:
            vencedor_nome = jogo["p1_nome"] if resultado == jogo["p1_simbolo"] else jogo["p2_nome"]
            texto = f"🎉 **Fim de jogo! O vencedor foi {vencedor_nome} ({resultado})!**"

    if chat_id in partidas:
        del partidas[chat_id]

    await query.message.edit_text(
        text=texto,
        reply_markup=gerar_teclado(jogo["tabuleiro"]),
        parse_mode="Markdown"
    )
    await query.answer()
