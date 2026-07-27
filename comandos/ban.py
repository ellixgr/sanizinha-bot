from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Verifica se quem enviou o comando é admin do grupo."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        return False
        
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ["creator", "administrator"]:
            return True
    except Exception:
        pass
    return False

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado em grupos!")
        return

    # Validação rigorosa de administrador
    if not await is_user_admin(update, context):
        await update.message.reply_text("⚠️ Você precisa ser administrador para banir alguém!")
        return

    alvo_id = None
    alvo_nome = "Usuário"

    # 1. Se respondeu a uma mensagem
    if update.message.reply_to_message:
        alvo = update.message.reply_to_message.from_user
        alvo_id = alvo.id
        alvo_nome = alvo.first_name

    # 2. Se passou argumento (/ban @usuario ou /ban ID)
    elif context.args:
        arg = context.args[0].strip()
        
        # Se passou por username (ex: @fulano)
        if arg.startswith("@"):
            username_limpo = arg.replace("@", "")
            # Como a API do Telegram não busca username direto no chat, tentamos extrair se estiver no histórico recente 
            # ou resolvemos via menção/texto se o bot o conhecer, mas a forma mais garantida por ID/Reply é padrão.
            # Alternativa segura para user_id digitado ou ID numérico:
            try:
                # Tenta converter para ID numérico direto caso tenham mandado o ID
                alvo_id = int(arg)
            except ValueError:
                # Se for username real, tentamos buscar se o bot tiver interagir, senão orientamos
                await update.message.reply_text(
                    "⚠️ Para banir por nome de usuário, por favor **responda à mensagem** da pessoa ou use o **ID numérico**.",
                    parse_mode="Markdown"
                )
                return
        else:
            try:
                alvo_id = int(arg)
            except ValueError:
                await update.message.reply_text("⚠️ Formato inválido. Responda à mensagem ou informe o ID/Username correto.")
                return
    else:
        await update.message.reply_text("⚠️ Responda à mensagem de quem deseja banir ou informe o ID/usuário. Ex: `/ban @usuario`", parse_mode="Markdown")
        return

    # Tenta executar o banimento
    try:
        # Evita que o bot tente banir a si mesmo ou um admin do grupo
        membro_alvo = await context.bot.get_chat_member(chat.id, alvo_id)
        if membro_alvo.status in ["creator", "administrator"]:
            await update.message.reply_text("❌ Não é possível banir outro administrador do grupo!")
            return
        if membro_alvo.user.id == context.bot.id:
            await update.message.reply_text("🤖 Eu não posso me auto-banir!")
            return

        await context.bot.ban_chat_member(chat.id, alvo_id)
        await update.message.reply_text(f"🔨 Usuário banido com sucesso!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao banir (verifique se sou administrador e tenho permissão): {e}")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == "private":
        return

    # Validação de administrador
    if not await is_user_admin(update, context):
        await update.message.reply_text("⚠️ Você precisa ser administrador para desbanir alguém!")
        return

    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Use `/desbanir [ID_DO_USUARIO]` ou responda a uma mensagem dele.", parse_mode="Markdown")
        return

    alvo_id = None
    if update.message.reply_to_message:
        alvo_id = update.message.reply_to_message.from_user.id
    else:
        try:
            alvo_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ ID inválido. Certifique-se de enviar apenas números no ID.")
            return

    try:
        await context.bot.unban_chat_member(chat.id, alvo_id, only_if_banned=True)
        await update.message.reply_text("🔓 Usuário desbanido com sucesso!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao desbanir: {e}")

def registrar_ban(app):
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("desbanir", unban_cmd))
