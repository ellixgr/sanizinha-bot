import os
import threading
from flask import Flask
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Configurações básicas
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

# Conexão MongoDB (Opcional, caso queira salvar coisas globais)
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, tlsAllowInvalidCertificates=True)
    db = mongo_client["sanizinhabot_db"]
    print("✅ Conectado ao MongoDB no bot.py!")
except Exception as e:
    print(f"⚠️ Erro no Mongo: {e}")

# Servidor Flask para manter o bot acordado (Render, Koyeb, etc.)
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot online com sucesso!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

# ==================== O COMANDO START ====================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    # Se o start foi chamado em um GRUPO
    if chat.type in ["group", "supergroup"]:
        teclado_grupo = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Ver Comandos", callback_data="cmd_membros")],
            [InlineKeyboardButton("⚙️ Painel do Grupo", callback_data=f"painel_prot_{chat.id}")]
        ])
        await update.message.reply_text(
            f"👋 Olá {user.mention_markdown()}! Estou ativo neste grupo.",
            reply_markup=teclado_grupo,
            parse_mode="Markdown"
        )
        return

    # Se o start foi chamado no PRIVADO
    teclado_privado = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Lista de Comandos", callback_data="cmd_membros")],
        [InlineKeyboardButton("💎 Comprar VIP / Acesso", callback_data="comprar_menu")],
        [InlineKeyboardButton("🤖 Adicionar ao seu Grupo", url="https://t.me/SEU_BOT?startgroup=true")]
    ])
    
    texto_pv = (
        "🔥 **Bem-vindo ao Painel Principal do Bot!**\n\n"
        "Escolha uma das opções abaixo para navegar:"
    )
    await update.message.reply_text(texto_pv, reply_markup=teclado_privado, parse_mode="Markdown")

# ==================== FUNÇÃO MAIN ====================
def main():
    # Inicia o servidor web em uma thread separada
    threading.Thread(target=run_web, daemon=True).start()
    
    # Inicia a aplicação do Telegram
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # REGISTRO DE COMANDOS (Puxando dos seus arquivos em /Comandos/)
    from Comandos.ping import registrar_ping
    from Comandos.ban import registrar_ban
    from Comandos.mutar import registrar_mutar
    from Comandos.perfil import registrar_perfil
    from Comandos.id import registrar_id

    registrar_ping(app)
    registrar_ban(app)
    registrar_mutar(app)
    registrar_perfil(app)
    registrar_id(app)

    # Registra o start principal
    app.add_handler(CommandHandler("start", start_cmd))

    print("🤖 Robô iniciado com sucesso e escutando comandos!")
    app.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    main()
