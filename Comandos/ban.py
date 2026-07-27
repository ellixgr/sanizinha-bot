from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado em grupos!")
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Você precisa ser administrador para banir alguém!")
            return
    except Exception:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Responda à mensagem de quem deseja banir.")
        return

    alvo = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(chat.id, alvo.id)
        await update.message.reply_text(f"🔨 Usuário **{alvo.first_name}** banido com sucesso!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Não foi possível banir o usuário: {e}")

def registrar_ban(app):
    app.add_handler(CommandHandler("ban", ban_cmd))
