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
        await update.message.reply_text(f"🔨 Usuário **{alvo.first_name}** foi banido com sucesso!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao banir: {e}")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"]:
            return
    except Exception:
        return

    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Use `/desbanir [ID_DO_USUARIO]` ou responda a ele.")
        return

    alvo_id = None
    if update.message.reply_to_message:
        alvo_id = update.message.reply_to_message.from_user.id
    else:
        try:
            alvo_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ ID inválido.")
            return

    try:
        await context.bot.unban_chat_member(chat.id, alvo_id, only_if_banned=True)
        await update.message.reply_text("🔓 Usuário desbanido com sucesso!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao desbanir: {e}")

def registrar_ban(app):
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("desbanir", unban_cmd))
