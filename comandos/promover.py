import os
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

DONO_ID = os.environ.get("DONO_ID", "").strip()

async def pode_gerenciar_adms(chat, user, bot):
    """Verifica se pode promover/rebaixar: 
    → Criador do grupo OU 
    → Admin com permissão de promover membros OU 
    → Dono do bot
    """
    if DONO_ID and str(user.id) == str(DONO_ID):
        return True
    try:
        member = await bot.get_chat_member(chat.id, user.id)
        # ✅ Agora ADMs com permissão TAMBÉM podem!
        if member.status == "creator":
            return True
        if member.status == "administrator" and getattr(member, "can_promote_members", False):
            return True
    except Exception:
        pass
    return False

async def promover_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    bot = context.bot
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só funciona em grupos!")
        return

    if not await pode_gerenciar_adms(chat, user, bot):
        await update.message.reply_text(
            "⚠️ Você precisa ser **criador** ou **administrador com permissão de promover membros**!",
            parse_mode="Markdown"
        )
        return

    # ✅ Verifica se o bot tem permissão
    try:
        bot_member = await bot.get_chat_member(chat.id, bot.id)
        if bot_member.status != "administrator" or not getattr(bot_member, "can_promote_members", False):
            await update.message.reply_text(
                "❌ Eu preciso ser administrador com permissão de **promover membros**!",
                parse_mode="Markdown"
            )
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao verificar permissões: {e}")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Responda à mensagem da pessoa que deseja promover.")
        return

    alvo = update.message.reply_to_message.from_user

    # ✅ Verificações de segurança
    if alvo.id == user.id:
        await update.message.reply_text("❌ Você já é administrador!")
        return
    if alvo.id == bot.id:
        await update.message.reply_text("🤖 Eu já sou administrador!")
        return

    try:
        alvo_member = await bot.get_chat_member(chat.id, alvo.id)
        if alvo_member.status in ["administrator", "creator"]:
            await update.message.reply_text("⚠️ Esse usuário já é administrador!")
            return

        await bot.promote_chat_member(
            chat.id, alvo.id,
            is_anonymous=False,
            can_manage_chat=True,
            can_delete_messages=True,
            can_restrict_members=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_promote_members=False,  # ❌ Não deixa o novo admin promover outros
            can_change_info=True
        )
        await update.message.reply_text(
            f"⭐ O usuário **{alvo.first_name}** foi promovido a Administrador!",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao promover: {e}")

async def rebaixar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    bot = context.bot
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só funciona em grupos!")
        return

    if not await pode_gerenciar_adms(chat, user, bot):
        await update.message.reply_text(
            "⚠️ Você precisa ser **criador** ou **administrador com permissão de promover membros**!",
            parse_mode="Markdown"
        )
        return

    try:
        bot_member = await bot.get_chat_member(chat.id, bot.id)
        if bot_member.status != "administrator" or not getattr(bot_member, "can_promote_members", False):
            await update.message.reply_text(
                "❌ Eu preciso ser administrador com permissão de **promover membros**!",
                parse_mode="Markdown"
            )
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao verificar minhas permissões: {e}")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Responda à mensagem do administrador que deseja rebaixar.")
        return

    alvo = update.message.reply_to_message.from_user

    try:
        alvo_member = await bot.get_chat_member(chat.id, alvo.id)
        if alvo_member.status == "creator":
            await update.message.reply_text("❌ Não é possível rebaixar o criador do grupo!")
            return
        if alvo_member.status == "member":
            await update.message.reply_text("⚠️ Esse usuário já é membro comum!")
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao verificar usuário: {e}")
        return

    try:
        await bot.promote_chat_member(
            chat.id, alvo.id,
            is_anonymous=False,
            can_manage_chat=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_change_info=False
        )
        await update.message.reply_text(
            f"📉 O usuário **{alvo.first_name}** foi rebaixado a membro comum.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao rebaixar: {e}")

def registrar_promover(app):
    app.add_handler(CommandHandler("promover", promover_cmd))
    app.add_handler(CommandHandler("rebaixar", rebaixar_cmd))
