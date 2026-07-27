import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, TypeHandler, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

# Servidor Flask simples para manter o bot acordado no Render/Koyeb
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot online e operacional!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

# Interceptador universal para computar mensagens e mídias das estatísticas
async def interceptador_estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user or chat.type == "private":
        return

    message = update.message
    if not message:
        return

    tipo_incremento = {"total_mensagens": 1}
    if message.photo:
        tipo_incremento["fotos"] = 1
    elif message.video:
        tipo_incremento["videos"] = 1
    elif message.voice or message.audio:
        tipo_incremento["audios"] = 1
    elif message.sticker:
        tipo_incremento["stickers"] = 1

    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
        db = client["sanizinhabot_db"]
        db["mensagens_usuarios"].update_one(
            {"chat_id": chat.id, "user_id": user.id},
            {"$inc": tipo_incremento},
            upsert=True
        )
    except Exception:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(f"🛡️ Olá {user.mention_markdown()}! Estou ativo neste grupo.", parse_mode="Markdown")
        return

    teclado_privado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Lista de Comandos", callback_data="ver_comandos")],
        [InlineKeyboardButton("🤖 Adicionar ao seu Grupo", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ])
    
    await update.message.reply_text(
        f"🔥 **Eae, {user.first_name}!** Escolha o que deseja fazer abaixo:",
        reply_markup=teclado_privado,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "ver_comandos":
        await query.answer()
        texto_ajuda = (
            "🤖 **Lista de Comandos Disponíveis:**\n\n"
            "🏓 `/ping` - Status de hardware, RAM e latência\n"
            "👤 `/perfil` - Suas estatísticas completas, bio e mídias\n"
            "🆔 `/id` - Mostra seu ID e do chat\n\n"
            "🛡️ *Em Grupos (Admin):*\n"
            "🔨 `/ban` - Bane o usuário respondido\n"
            "🔇 `/mutar` - Muta o usuário respondido"
        )
        await query.message.edit_text(texto_ajuda, parse_mode="Markdown")

def main():
    # Inicia o servidor Flask em segundo plano
    threading.Thread(target=run_web, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Registra o interceptador de estatísticas nas mensagens de grupo
    app.add_handler(TypeHandler(Update, interceptador_estatisticas), group=-1)

    # Importa e registra os comandos organizados na pasta comandos/
    from comandos.ping import registrar_ping
    from comandos.id import registrar_id
    from comandos.perfil import registrar_perfil
    from comandos.ban import registrar_ban
    from comandos.mutar import registrar_mutar
    from comandos.bemvindo import registrar_comandos_bv
    from comandos.promover import registrar_promover
    from comandos.marcar import registrar_marcar
    from comandos.citar import registrar_citar
    from comandos.protecao import registrar_protecoes

    registrar_promover(app)
    registrar_marcar(app)
    registrar_citar(app)
    registrar_protecoes(app)
    registrar_comandos_bv(app)
    registrar_ping(app)
    registrar_id(app)
    registrar_perfil(app)
    registrar_ban(app)
    setup_play(app)
    registrar_mutar(app)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot rodando com sucesso e módulos separados!")
    app.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    main()
    