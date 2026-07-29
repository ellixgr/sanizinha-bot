from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
from pymongo import MongoClient
import os, random

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
jogos_db = db["jogo_memoria"]

def setup_memoria(app: Application):
    app.add_handler(CallbackQueryHandler(iniciar_memoria, pattern="^jogo_memoria$"))
    app.add_handler(CallbackQueryHandler(jogada_memoria, pattern="^mem_"))

async def iniciar_memoria(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Jogar Contra a Máquina", callback_data="mem_modo_ia")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text("🧠 **Jogo da Memória (Encontre os pares)**\n\nEscolha o modo:", reply_markup=teclado, parse_mode="Markdown")

async def jogada_memoria(update: Update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id

    if data == "mem_modo_ia":
        # 6 cartas (3 pares: 🍎, 🍌, 🍇)
        icones = ["🍎", "🍎", "🍌", "🍌", "🍇", "🍇"]
        random.shuffle(icones)
        cartas_estado = ["❓" for _ in range(6)]
        
        jogos_db.update_one(
            {"chat_id": chat_id},
            {"$set": {"icones": icones, "cartas": cartas_estado, "selecionada": None, "pontos_player": 0, "pontos_ia": 0}},
            upsert=True
        )
        await mostrar_painel_memoria(query, cartas_estado, "Sua vez! Escolha uma carta.")
        return

    if data.startswith("mem_pos_"):
        pos = int(data.split("_")[2])
        estado = jogos_db.find_one({"chat_id": chat_id})
        if not estado:
            await query.answer("⚠️ Inicie um novo jogo!", show_alert=True)
            return

        cartas = estado["cartas"]
        icones = estado["icones"]
        
        if cartas[pos] != "❓":
            await query.answer("⚠️ Carta já aberta!", show_alert=True)
            return

        primeira = estado.get("selecionada")
        cartas[pos] = icones[pos]

        if primeira is None:
            jogos_db.update_one({"chat_id": chat_id}, {"$set": {"cartas": cartas, "selecionada": pos}})
            await mostrar_painel_memoria(query, cartas, "Escolha a segunda carta...")
        else:
            # Conferir par
            if icones[primeira] == icones[pos]:
                pontos = estado["pontos_player"] + 1
                jogos_db.update_one({"chat_id": chat_id}, {"$set": {"cartas": cartas, "selecionada": None, "pontos_player": pontos}})
                if pontos == 3:
                    await query.message.edit_text("🎉 **Você Venceu o Jogo da Memória!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]]))
                    jogos_db.delete_one({"chat_id": chat_id})
                    return
                await mostrar_painel_memoria(query, cartas, "ACERTOU UM PAR! Jogue de novo.")
            else:
                # Errou, fecha de novo após mostrar
                await mostrar_painel_memoria(query, cartas, "ERROU! Vez da Máquina...")
                # Simula IA jogando
                import asyncio
                await asyncio.sleep(1)
                cartas[primeira] = "❓"
                cartas[pos] = "❓"
                jogos_db.update_one({"chat_id": chat_id}, {"$set": {"cartas": cartas, "selecionada": None}})
                await mostrar_painel_memoria(query, cartas, "A máquina jogou. Sua vez!")

async def mostrar_painel_memoria(query, cartas, texto):
    botoes = [
        [InlineKeyboardButton(cartas[0], callback_data="mem_pos_0"), InlineKeyboardButton(cartas[1], callback_data="mem_pos_1"), InlineKeyboardButton(cartas[2], callback_data="mem_pos_2")],
        [InlineKeyboardButton(cartas[3], callback_data="mem_pos_3"), InlineKeyboardButton(cartas[4], callback_data="mem_pos_4"), InlineKeyboardButton(cartas[5], callback_data="mem_pos_5")],
        [InlineKeyboardButton("❌ Sair", callback_data="menu_jogos_atalho")]
    ]
    await query.message.edit_text(f"🧠 **Memória**\n{texto}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
