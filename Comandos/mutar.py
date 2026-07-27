from telegram import Update, ChatPermissions
from telegram.ext import CommandHandler, ContextTypes

async def mutar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado em grupos!")
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Você precisa ser administrador para mutar alguém!")
            return
    except Exception:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Responda à mensagem de quem deseja mutar.")
        return

    alvo = update.message.reply_to_message.from_user
    try:
        permissao_silenciar = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(chat.id, alvo.id, permissions=permissao_silenciar)
        await update.message.reply_text(f"🔇 Usuário **{alvo.first_name}** foi mutado!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao mutar usuário: {e}")

def registrar_mutar(app):
    app.add_handler(CommandHandler("mutar", mutar_cmd))
