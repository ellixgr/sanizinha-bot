from telegram import Update, ChatPermissions
from telegram.ext import CommandHandler, ContextTypes

async def mutar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Apenas administradores podem mutar!")
            return
    except Exception:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Responda à mensagem de quem deseja mutar.")
        return

    alvo = update.message.reply_to_message.from_user
    try:
        permissao = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(chat.id, alvo.id, permissions=permissao)
        await update.message.reply_text(f"🔇 O usuário **{alvo.first_name}** foi silenciado!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao mutar: {e}")

async def desmutar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Apenas administradores podem desmutar!")
            return
    except Exception:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Responda à mensagem de quem deseja desmutar.")
        return

    alvo = update.message.reply_to_message.from_user
    try:
        permissao = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        await context.bot.restrict_chat_member(chat.id, alvo.id, permissions=permissao)
        await update.message.reply_text(f"🔊 O usuário **{alvo.first_name}** foi desmutado!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao desmutar: {e}")

def registrar_mutar(app):
    app.add_handler(CommandHandler("mutar", mutar_cmd))
    app.add_handler(CommandHandler("desmutar", desmutar_cmd))
