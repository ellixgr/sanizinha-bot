import os
import time
import threading
import asyncio
from flask import Flask
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ChatMemberHandler, TypeHandler, ContextTypes

token = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DONO_ID = int(os.environ.get("DONO_ID", 7711945457))
MONGO_URI = os.environ.get("MONGO_URI")
FOTO_START = "https://files.catbox.moe/0pw3k8.jpg"

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, tlsAllowInvalidCertificates=True)
    db = mongo_client["sanizinhabot_db"]
    collection_chats = db["chats_autorizados"]
    print("✅ Conectado com sucesso ao MongoDB!")
except Exception as e:
    print(f"⚠️ Erro crítico ao conectar no MongoDB: {e}")

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        chat = update.effective_chat
        user = update.effective_user
        mention = user.mention_markdown() if user else "Usuário"
        teclado_grupo = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Comandos de Membros", callback_data="cmd_membros")],
            [InlineKeyboardButton("🛡️ Comandos de Administradores", callback_data="cmd_adm")],
            [InlineKeyboardButton("⚙️ Central de Proteções", callback_data=f"painel_prot_{chat.id}")]
        ])
        texto_grupo = f"🛡️ **Painel Oficial** — {mention}\n📌 Grupo: `{chat.title}`"
        await update.message.reply_text(texto_grupo, reply_markup=teclado_grupo, parse_mode="Markdown")
        return
        
    texto_boas_vindas = "🔥 **SEJA BEM-VINDO AO BOT** 🇧🇷\n\nEscolha uma opção abaixo:"
    keyboard = [
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 1 𝐃𝐈𝐀 → R$ 2,00", callback_data="comprar_2.00")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 1 𝐒𝐄𝐌𝐀𝐍𝐀 → R$ 7,00", callback_data="comprar_7.00")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 1 𝐌𝐄𝐒 → R$ 20,00", callback_data="comprar_20.00")]
    ]
    try:
        await update.message.reply_photo(photo=FOTO_START, caption=texto_boas_vindas, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(texto_boas_vindas, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def verificar_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return        
    chat = result.chat
    new_status = result.new_chat_member.status
    if chat.type in ["group", "supergroup", "channel"]:
        try:
            if new_status in ["member", "administrator"]:
                collection_chats.update_one({"chat_id": chat.id}, {"$set": {"chat_id": chat.id, "title": chat.title, "type": chat.type}}, upsert=True)
            elif new_status in ["left", "kicked"]:
                collection_chats.delete_one({"chat_id": chat.id})
        except Exception:
            pass

def main():
    threading.Thread(target=run_web, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Importando e registrando os módulos de comandos separados
    from Comandos.ping import registrar_ping
    from Comandos.ban import registrar_ban
    from Comandos.mutar import registrar_mutar
    from Comandos.perfil import registrar_perfil
    from Comandos.id import registrar_id
    from Comandos.bemvindo import registrar_comandos_bv
    from Comandos.play import setup_play

    registrar_ping(app)
    registrar_ban(app)
    registrar_mutar(app)
    registrar_perfil(app)
    registrar_id(app)
    registrar_comandos_bv(app)
    setup_play(app)

    app.add_handler(ChatMemberHandler(verificar_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("start", start))
    
    print("🤖 Bot rodando com módulos separados!")
    app.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    main()
