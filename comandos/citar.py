from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def citar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat

    if chat.type == "private":
        return

    if not message.reply_to_message:
        await message.reply_text("⚠️ Responda a uma mensagem (foto, vídeo, áudio, figurinha ou texto) para citar!")
        return

    alvo_msg = message.reply_to_message
    
    try:
        await message.delete()
    except Exception:
        pass

    legenda_base = alvo_msg.caption or alvo_msg.text or "Mídia citada"
    nova_legenda = f"📌 **Citação Geral:**\n{legenda_base}"

    if alvo_msg.photo:
        await chat.send_photo(photo=alvo_msg.photo[-1].file_id, caption=nova_legenda, parse_mode="Markdown")
    elif alvo_msg.video:
        await chat.send_video(video=alvo_msg.video.file_id, caption=nova_legenda, parse_mode="Markdown")
    elif alvo_msg.audio:
        await chat.send_audio(audio=alvo_msg.audio.file_id, caption=nova_legenda, parse_mode="Markdown")
    elif alvo_msg.voice:
        await chat.send_voice(voice=alvo_msg.voice.file_id, caption=nova_legenda, parse_mode="Markdown")
    elif alvo_msg.sticker:
        await chat.send_sticker(sticker=alvo_msg.sticker.file_id)
        await chat.send_message(text=nova_legenda, parse_mode="Markdown")
    else:
        await chat.send_message(text=nova_legenda, parse_mode="Markdown")

def registrar_citar(app):
    app.add_handler(CommandHandler("citar", citar_cmd))
