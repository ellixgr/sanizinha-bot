from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def citar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    DONO_ID = os.environ.get("DONO_ID", "")
    
    if chat.type == "private":
        await message.reply_text("⚠️ Este comando só funciona dentro de grupos!")
        return

    # ✅ Verifica se grupo é autorizado
    from bot import grupo_autorizado
    if not (str(user.id) == str(DONO_ID)):
        if not await grupo_autorizado(chat.id):
            await message.reply_text("❌ Grupo não autorizado!")
            return

    # Validação de Administrador
    try:
        member = await chat.get_member(user.id)
        if member.status not in ["creator", "administrator"] and str(user.id) != str(DONO_ID):
            await message.reply_text("⚠️ Apenas administradores podem usar o comando /citar!")
            return
    except Exception:
        return

    if not message.reply_to_message:
        await message.reply_text("⚠️ Responda a uma mensagem para poder citá-la!")
        return

    alvo_msg = message.reply_to_message
    
    # Apaga a mensagem do comando
    try:
        await message.delete()
    except Exception:
        pass

    legenda_original = alvo_msg.caption or alvo_msg.text or ""

    # Republica a mensagem
    if alvo_msg.photo:
        await chat.send_photo(photo=alvo_msg.photo[-1].file_id, caption=legenda_original or None)
    elif alvo_msg.video:
        await chat.send_video(video=alvo_msg.video.file_id, caption=legenda_original or None)
    elif alvo_msg.audio:
        await chat.send_audio(audio=alvo_msg.audio.file_id, caption=legenda_original or None)
    elif alvo_msg.voice:
        await chat.send_voice(voice=alvo_msg.voice.file_id)
    elif alvo_msg.sticker:
        await chat.send_sticker(sticker=alvo_msg.sticker.file_id)
        if legenda_original:
            await chat.send_message(text=legenda_original)
    else:
        texto_enviar = legenda_original or "Mensagem citada."
        await chat.send_message(text=texto_enviar)

def registrar_citar(app):
    from bot import verificar_se_e_adm, grupo_autorizado
    app.add_handler(CommandHandler("citar", citar_cmd))
