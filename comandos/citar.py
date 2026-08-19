import os
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

DONO_ID = os.environ.get("DONO_ID", "").strip()

async def citar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await message.reply_text("⚠️ Este comando só funciona dentro de grupos!")
        return

    # ✅ Verifica se grupo é autorizado
    from bot import grupo_autorizado
    if str(user.id) != str(DONO_ID):
        if not await grupo_autorizado(chat.id):
            await message.reply_text("❌ Grupo não autorizado!")
            return

    # ✅ Verifica permissão (dono ou admin)
    try:
        e_dono = str(user.id) == str(DONO_ID)
        membro = await chat.get_member(user.id)
        e_admin = membro.status in ["creator", "administrator"]
        
        if not e_dono and not e_admin:
            await message.reply_text("⚠️ Apenas administradores podem usar o comando /citar!")
            return
    except Exception as e:
        await message.reply_text("❌ Não foi possível verificar suas permissões.")
        return

    # ✅ Verifica se respondeu a mensagem
    if not message.reply_to_message:
        await message.reply_text("⚠️ Responda a uma mensagem para poder citá-la!")
        return

    # ✅ SÓ AGORA apaga o comando (depois de TODAS as verificações)
    try:
        await message.delete()
    except Exception:
        pass

    alvo_msg = message.reply_to_message
    legenda = alvo_msg.caption or alvo_msg.text or ""

    # ✅ Reproduz a mensagem corretamente
    try:
        if alvo_msg.photo:
            await chat.send_photo(
                photo=alvo_msg.photo[-1].file_id,
                caption=legenda if legenda else None
            )
        elif alvo_msg.video:
            await chat.send_video(
                video=alvo_msg.video.file_id,
                caption=legenda if legenda else None
            )
        elif alvo_msg.document:
            await chat.send_document(
                document=alvo_msg.document.file_id,
                caption=legenda if legenda else None
            )
        elif alvo_msg.audio:
            await chat.send_audio(
                audio=alvo_msg.audio.file_id,
                caption=legenda if legenda else None
            )
        elif alvo_msg.voice:
            await chat.send_voice(voice=alvo_msg.voice.file_id)
            if legenda:
                await chat.send_message(text=legenda)
        elif alvo_msg.sticker:
            await chat.send_sticker(sticker=alvo_msg.sticker.file_id)
            if legenda:
                await chat.send_message(text=legenda)
        else:
            texto = legenda or "Mensagem citada."
            await chat.send_message(text=texto)
    except Exception as e:
        await chat.send_message(f"❌ Não foi possível citar a mensagem: {e}")

def registrar_citar(app):
    app.add_handler(CommandHandler("citar", citar_cmd))
