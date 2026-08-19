import os
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

DONO_ID = os.environ.get("DONO_ID", "").strip()

async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Verifica se quem enviou o comando é admin do grupo OU dono do bot."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        return False
    
    # ✅ Dono do bot é sempre autorizado
    if DONO_ID and str(user.id) == str(DONO_ID):
        return True
        
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ["creator", "administrator"]:
            return True
    except Exception:
        pass
    return False

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado em grupos!")
        return

    # ✅ Verifica permissão
    if not await is_user_admin(update, context):
        await update.message.reply_text("⚠️ Você precisa ser administrador para banir alguém!")
        return

    alvo_id = None
    alvo_nome = "Usuário"

    # ✅ 1. Se respondeu a uma mensagem
    if update.message.reply_to_message:
        alvo = update.message.reply_to_message.from_user
        alvo_id = alvo.id
        alvo_nome = alvo.first_name or f"Usuário {alvo_id}"

    # ✅ 2. Se passou argumento (/ban @usuario ou /ban ID)
    elif context.args:
        arg = context.args[0].strip()
        
        if arg.startswith("@"):
            # Username não é possível buscar direto — orienta o usuário
            await update.message.reply_text(
                "⚠️ Para banir por username, **responda à mensagem** da pessoa ou use o **ID numérico**.\n"
                "Ex: `/ban 123456789`",
                parse_mode="Markdown"
            )
            return
        else:
            try:
                alvo_id = int(arg)
                alvo_nome = f"Usuário {alvo_id}"
            except ValueError:
                await update.message.reply_text("⚠️ ID inválido! Use apenas números.\nEx: `/ban 123456789`", parse_mode="Markdown")
                return
    else:
        await update.message.reply_text(
            "⚠️ Responda à mensagem de quem deseja banir ou informe o ID.\nEx: `/ban 123456789`",
            parse_mode="Markdown"
        )
        return

    # ✅ Verificações de segurança
    try:
        # Não pode banir a si mesmo
        if alvo_id == user.id:
            await update.message.reply_text("❌ Você não pode se banir!")
            return

        # Não pode banir o bot
        if alvo_id == context.bot.id:
            await update.message.reply_text("🤖 Eu não posso me auto-banir!")
            return

        # Verifica se é admin/creator
        membro_alvo = await context.bot.get_chat_member(chat.id, alvo_id)
        if membro_alvo.status == "creator":
            await update.message.reply_text("❌ Não é possível banir o criador do grupo!")
            return
        if membro_alvo.status in ["administrator"]:
            await update.message.reply_text("❌ Não é possível banir outro administrador!")
            return

        # ✅ Executa o banimento
        await context.bot.ban_chat_member(chat.id, alvo_id)
        await update.message.reply_text(f"🔨 **{alvo_nome}** foi banido com sucesso!", parse_mode="Markdown")

    except Exception as e:
        erro = str(e).lower()
        if "not enough rights" in erro or "administrator" in erro:
            await update.message.reply_text("❌ Eu não tenho permissão para banir! Verifique se sou administrador com direitos de banimento.")
        else:
            await update.message.reply_text(f"❌ Erro ao banir: {e}")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado em grupos!")
        return

    if not await is_user_admin(update, context):
        await update.message.reply_text("⚠️ Você precisa ser administrador para desbanir alguém!")
        return

    alvo_id = None

    if update.message.reply_to_message:
        alvo_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            alvo_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ ID inválido! Use apenas números.\nEx: `/desbanir 123456789`", parse_mode="Markdown")
            return
    else:
        await update.message.reply_text(
            "⚠️ Use `/desbanir [ID_DO_USUARIO]` ou responda a uma mensagem dele.",
            parse_mode="Markdown"
        )
        return

    try:
        # ✅ Remove only_if_banned que pode causar erro
        await context.bot.unban_chat_member(chat.id, alvo_id)
        await update.message.reply_text("🔓 Usuário desbanido com sucesso!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao desbanir: {e}")

def registrar_ban(app):
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("desbanir", unban_cmd))
