import os
import subprocess
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image

async def fazer_figurinhas_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    
    msg_alvo = message.reply_to_message if message.reply_to_message else message
    
    if not msg_alvo:
        await message.reply_text("⚠️ Responda a uma foto ou vídeo com `/s` ou envie a mídia junto com o comando.")
        return

    foto = msg_alvo.photo[-1] if msg_alvo.photo else None
    video = msg_alvo.video if msg_alvo.video else (msg_alvo.animation if msg_alvo.animation else None)

    if not foto and not video:
        await message.reply_text("⚠️ O arquivo enviado precisa ser uma **foto** ou um **vídeo/GIF** válido!")
        return

    if video:
        duracao = getattr(video, 'duration', 0)
        if duracao > 9:
            await message.reply_text(f"⚠️ O vídeo é muito longo ({duracao}s). O limite máximo permitido é de **9 segundos**!")
            return

    status_msg = await message.reply_text("🔄 Processando figurinha quadrada...")

    input_path = f"temp_input_{message.from_user.id}"
    output_path = f"temp_output_{message.from_user.id}"

    try:
        if foto:
            arquivo = await foto.get_file()
            input_path += ".jpg"
            output_path += ".webp"
            await arquivo.download_to_drive(input_path)

            # Abre a imagem e força o formato quadrado exato 512x512
            img = Image.open(input_path).convert("RGBA")
            
            largura, altura = img.size
            
            # Corta as bordas excedentes para transformar em quadrado perfeito (Centralizado)
            if largura > altura:
                diferenca = largura - altura
                esquerda = diferenca // 2
                direita = largura - (diferenca // 2)
                img = img.crop((esquerda, 0, direita, altura))
            elif altura > largura:
                diferenca = altura - largura
                topo = diferenca // 2
                baixo = altura - (diferenca // 2)
                img = img.crop((0, topo, largura, baixo))

            # Redimensiona rigorosamente para 512x512 pixels exatos
            img = img.resize((512, 512), Image.Resampling.LANCZOS)

            # Salva como webp fixo quadrado
            img.save(output_path, "WEBP", quality=95, method=6)

            with open(output_path, "rb") as f:
                await chat.send_sticker(sticker=f)

        elif video:
            arquivo = await video.get_file()
            input_path += ".mp4"
            output_path += ".webm"
            await arquivo.download_to_drive(input_path)

            # Força o FFmpeg a cortar e preencher perfeitamente num quadrado de 512x512 exato
            comando_ffmpeg = [
                "ffmpeg", "-y", "-i", input_path,
                "-t", "3",
                "-vf", "crop=min(iw\,ih):min(iw\,ih),scale=512:512,format=yuva420p,fps=30",
                "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "256k",
                "-an",
                output_path
            ]
            
            processo = subprocess.run(comando_ffmpeg, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if processo.returncode != 0:
                await status_msg.edit_text("❌ Erro ao converter o vídeo em figurinha animada.")
                return

            with open(output_path, "rb") as f:
                await chat.send_sticker(sticker=f)

        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Ocorreu um erro: {e}")

    finally:
        for caminho in [input_path, output_path, f"{input_path}.jpg", f"{input_path}.mp4", f"{output_path}.webp", f"{output_path}.webm"]:
            if os.path.exists(caminho):
                try:
                    os.remove(caminho)
                except Exception:
                    pass

def registrar_figurinha(app):
    app.add_handler(CommandHandler(["s", "f", "sticker"], fazer_figurinhas_cmd))
