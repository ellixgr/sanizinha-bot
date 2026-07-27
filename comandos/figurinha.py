import os
import subprocess
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image

async def fazer_figurinhas_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    
    # Verifica se é uma resposta a uma mensagem com mídia ou se a própria mensagem tem mídia
    msg_alvo = message.reply_to_message if message.reply_to_message else message
    
    if not msg_alvo:
        await message.reply_text("⚠️ Responda a uma foto ou vídeo de até 9 segundos com `/s` ou envie a mídia junto com o comando.")
        return

    # Identifica se é foto ou vídeo
    foto = msg_alvo.photo[-1] if msg_alvo.photo else None
    video = msg_alvo.video if msg_alvo.video else (msg_alvo.animation if msg_alvo.animation else None)

    if not foto and not video:
        await message.reply_text("⚠️ O arquivo enviado precisa ser uma **foto** ou um **vídeo/GIF** válido!")
        return

    # Validação rigorosa de tempo para vídeos (máximo 9 segundos)
    if video:
        duracao = getattr(video, 'duration', 0)
        if duracao > 9:
            await message.reply_text(f"⚠️ O vídeo é muito longo ({duracao}s). O limite máximo permitido é de **9 segundos**!")
            return

    # Mensagem de status avisando que está processando
    status_msg = await message.reply_text("🔄 Processando sua figurinha...")

    input_path = f"temp_input_{message.from_user.id}"
    output_path = f"temp_output_{message.from_user.id}"

    try:
        if foto:
            # Baixa a foto
            arquivo = await foto.get_file()
            input_path += ".jpg"
            output_path += ".webp"
            await arquivo.download_to_drive(input_path)

            # Processamento de Imagem com Pillow (Redimensiona para 512x512 mantendo proporção)
            img = Image.open(input_path)
            img.thumbnail((512, 512))
            
            # Converte para RGBA se necessário
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            img.save(output_path, "WEBP", quality=90, method=6)

            # Envia a figurinha estática
            with open(output_path, "rb") as f:
                await chat.send_sticker(sticker=f)

        elif video:
            # Baixa o vídeo/animação
            arquivo = await video.get_file()
            input_path += ".mp4"
            output_path += ".webm"
            await arquivo.download_to_drive(input_path)

            # Processamento de Vídeo com FFmpeg (Obrigatório para figurinha animada no Telegram)
            # Converte para WebM VP9, max 512x512, max 30fps, cortado para máx 3 segundos ou o tamanho real se menor
            comando_ffmpeg = [
                "ffmpeg", "-y", "-i", input_path,
                "-t", "3",  # Limita por segurança a 3 segundos (ou ajusta pro formato aceito)
                "-vf", "scale='if(gt(iw,ih),512,-2)':'if(gt(iw,ih),-2,512)',format=yuva420p,fps=30",
                "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "256k",
                "-an",  # Sem som (Telegram não aceita som em figurinhas)
                output_path
            ]
            
            processo = subprocess.run(comando_ffmpeg, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if processo.returncode != 0:
                await status_msg.edit_text("❌ Erro ao converter o vídeo em figurinha animada. Certifique-se de que o FFmpeg está instalado no ambiente.")
                return

            # Envia a figurinha animada
            with open(output_path, "rb") as f:
                await chat.send_sticker(sticker=f)

        # Apaga a mensagem de "Processando..."
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Ocorreu um erro ao criar a figurinha: {e}")

    finally:
        # Limpeza de arquivos temporários do servidor
        for caminho in [input_path, output_path, f"{input_path}.jpg", f"{input_path}.mp4", f"{output_path}.webp", f"{output_path}.webm"]:
            if os.path.exists(caminho):
                try:
                    os.remove(caminho)
                except Exception:
                    pass

def registrar_figurinha(app):
    # Registra comandos /s, /f e /sticker
    app.add_handler(CommandHandler(["s", "f", "sticker"], fazer_figurinhas_cmd))
