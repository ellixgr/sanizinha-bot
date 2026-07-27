from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def citar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        return

    # Validação rigorosa de Administrador
    try:
        member = await chat.get_member(user.id)
        if member.status not in ["creator", "administrator"]:
            await message.reply_text("⚠️ Apenas administradores podem usar o comando /citar!")
            return
    except Exception:
        return

    if not message.reply_to_message:
        await message.reply_text("⚠️ Responda a uma mensagem para poder citá-la!")
        return

    alvo_msg = message.reply_to_message
    
    # Apaga a mensagem do comando /citar
    try:
        await message.delete()
    except Exception:
        pass

    legenda_original = alvo_msg.caption or alvo_msg.text or ""

    # Repubrica a mensagem original exatamente como ela é (foto, vídeo, áudio, figurinha ou texto)
    if alvo_msg.photo:
        await chat.send_photo(photo=alvo_msg.photo[-1].file_id, caption=legenda_original if legenda_original else None)
    elif alvo_msg.video:
        await chat.send_video(video=alvo_msg.video.file_id, caption=legenda_original if legenda_original else None)
    elif alvo_msg.audio:
        await chat.send_audio(audio=alvo_msg.audio.file_id, caption=legenda_original if legenda_original else None)
    elif alvo_msg.voice:
        await chat.send_voice(voice=alvo_msg.voice.file_id)
    elif alvo_msg.sticker:
        await chat.send_sticker(sticker=alvo_msg.sticker.file_id)
        if legenda_original:
            await chat.send_message(text=legenda_original)
    else:
        texto_enviar = legenda_original if legenda_original else "Mensagem citada."
        await chat.send_message(text=texto_enviar)

def registrar_citar(app):
    app.add_handler(CommandHandler("citar", citar_cmd))
