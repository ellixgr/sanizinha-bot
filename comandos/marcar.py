from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def marcar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Apenas em grupos.")
        return

    # Restrito apenas a administradores
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Apenas administradores podem marcar todos!")
            return
    except Exception:
        return

    texto_chamada = " ".join(context.args) if context.args else "Atenção todos!"
    
    # Apaga a mensagem do comando para manter o chat limpo
    try:
        await update.message.delete()
    except Exception:
        pass

    await update.message.reply_text(f"📢 **{texto_chamada}**\n\n_(Chamada geral disparada por {user.mention_markdown()})_", parse_mode="Markdown")

def registrar_marcar(app):
    app.add_handler(CommandHandler(["marcar", "todos", "tagall"], marcar_cmd))
