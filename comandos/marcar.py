from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def marcar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado em grupos.")
        return

    # Validação rigorosa de Administrador
    try:
        member = await chat.get_member(user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Apenas administradores podem usar este comando!")
            return
    except Exception:
        await update.message.reply_text("⚠️ Erro ao verificar suas permissões de administrador.")
        return

    texto_chamada = " ".join(context.args) if context.args else "Atenção todos!"
    
    # Apaga a mensagem do comando digitado
    try:
        await update.message.delete()
    except Exception:
        pass

    # Envia a chamada geral formatada
    msg_final = (
        f"📢 **{texto_chamada}**\n\n"
        f"👥 *Chamada geral disparada por* {user.mention_markdown()}"
    )
    
    await chat.send_message(msg_final, parse_mode="Markdown")

def registrar_marcar(app):
    app.add_handler(CommandHandler(["marcar", "todos", "tagall"], marcar_cmd))
