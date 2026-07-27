from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def promover_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status != "creator":
            await update.message.reply_text("⚠️ Apenas o **criador** do grupo pode promover novos administradores!", parse_mode="Markdown")
            return
    except Exception:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Responda à mensagem da pessoa que deseja promover.")
        return

    alvo = update.message.reply_to_message.from_user
    try:
        await context.bot.promote_chat_member(
            chat.id, alvo.id,
            is_anonymous=False,
            can_manage_chat=True,
            can_delete_messages=True,
            can_restrict_members=True,
            can_invite_users=True,
            can_pin_messages=True
        )
        await update.message.reply_text(f"⭐ O usuário **{alvo.first_name}** foi promovido a Administrador!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao promover: {e}")

async def rebaixar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status != "creator":
            await update.message.reply_text("⚠️ Apenas o **criador** do grupo pode rebaixar administradores!", parse_mode="Markdown")
            return
    except Exception:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Responda à mensagem do administrador que deseja rebaixar.")
        return

    alvo = update.message.reply_to_message.from_user
    try:
        await context.bot.promote_chat_member(
            chat.id, alvo.id,
            is_anonymous=False,
            can_manage_chat=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        await update.message.reply_text(f"📉 O usuário **{alvo.first_name}** foi rebaixado a membro comum.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao rebaixar: {e}")

def registrar_promover(app):
    app.add_handler(CommandHandler("promover", promover_cmd))
    app.add_handler(CommandHandler("rebaixar", rebaixar_cmd))
