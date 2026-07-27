from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def perfil_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    total_msgs = "Desconhecido"
    try:
        from pymongo import MongoClient
        import os
        client = MongoClient(os.environ.get("MONGO_URI"), serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
        db = client["sanizinhabot_db"]
        doc = db["mensagens_usuarios"].find_one({"chat_id": chat.id, "user_id": user.id})
        if doc:
            total_msgs = doc.get("total_mensagens", 0)
    except Exception:
        pass

    texto = (
        f"👤 **Perfil de {user.first_name}**\n\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"💬 **Mensagens no grupo:** `{total_msgs}`"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

def registrar_perfil(app):
    app.add_handler(CommandHandler("perfil", perfil_cmd))
