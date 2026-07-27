from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def marcar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Apenas em grupos.")
        return

    # Validação rigorosa de Administrador
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Apenas administradores podem marcar todos!")
            return
    except Exception as e:
        print(f"Erro ao verificar ADM: {e}")
        return

    texto_chamada = " ".join(context.args) if context.args else "Atenção todos!"
    
    # Tenta apagar a mensagem do comando com segurança
    try:
        await update.message.delete()
    except Exception as e:
        print(f"Não foi possível apagar a mensagem: {e}")

    # Envia a chamada geral diretamente no chat para garantir que nunca falhe
    try:
        msg_final = (
            f"📢 **{texto_chamada}**\n\n"
            f"👥 *Chamada geral convocada por* {user.mention_markdown()}"
        )
        await chat.send_message(msg_final, parse_mode="Markdown")
    except Exception as e:
        print(f"Erro ao enviar chamada: {e}")

def registrar_marcar(app):
    app.add_handler(CommandHandler(["marcar", "todos", "tagall"], marcar_cmd))
