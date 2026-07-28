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

            # Processamento de Imagem com Pillow para criar um quadrado perfeito 512x512
            img = Image.open(input_path).convert("RGBA")
            
            # Redimensiona mantendo a proporção para caber dentro de 512x512
            img.thumbnail((512, 512), Image.Resampling.LANCZOS)
            
            # Cria uma base transparente 512x512
            novo_fundo = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            
            # Calcula a posição centralizada para colar a foto no fundo quadrado
            x = (512 - img.width) // 2
            y = (512 - img.height) // 2
            novo_fundo.paste(img, (x, y), img)

            # Salva no formato webp otimizado para sticker
            novo_fundo.save(output_path, "WEBP", quality=95, method=6)

            # Envia a figurinha estática
            with open(output_path, "rb") as f:
                await chat.send_sticker(sticker=f)

        elif video:
            # Baixa o vídeo/animação
            arquivo = await video.get_file()
            input_path += ".mp4"
            output_path += ".webm"
            await arquivo.download_to_drive(input_path)

            # Processamento de Vídeo com FFmpeg forçando tamanho quadrado 512x512 (preenchendo com transparência se necessário)
            comando_ffmpeg = [
                "ffmpeg", "-y", "-i", input_path,
                "-t", "3",  # Limita a 3 segundos para figurinha animada
                "-vf", "scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=black@0,format=yuva420p,fps=30",
                "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "256k",
                "-an",  # Sem som
                output_path
            ]
            
            processo = subprocess.run(comando_ffmpeg, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if processo.returncode != 0:
                await status_msg.edit_text("❌ Erro ao converter o vídeo em figurinha animada.")
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
