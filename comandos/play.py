import os
import yt_dlp
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

def setup_play(app: Application):
    app.add_handler(CommandHandler(["baixar", "dl", "play"], play_pesquisa, filters=~filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(baixar_callback, pattern=r"^dl_(video|audio)\|"))

async def play_pesquisa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if not context.args:
        await message.reply_text("⚠️ Envie o comando junto com o nome ou link.\nExemplo: `/play travis scott`")
        return

    query = " ".join(context.args)
    status_msg = await message.reply_text("🔍 Procurando...")

    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
        'default_search': 'ytsearch1',
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            
            titulo = info.get('title', 'Desconhecido')
            url = info.get('webpage_url')
            duracao = info.get('duration_string', 'N/A')
            thumbnail = info.get('thumbnail')
            
            views = info.get('view_count')
            views_str = f"{views:,}".replace(",", ".") if views else "Não disponível"
            
            likes = info.get('like_count')
            likes_str = f"{likes:,}".replace(",", ".") if likes else "Não disponível"
            
            comentarios = info.get('comment_count')
            comentarios_str = f"{comentarios:,}".replace(",", ".") if comentarios else "Não disponível"

    except Exception as e:
        await status_msg.edit_text(f"❌ Erro na busca: `{e}`", parse_mode="Markdown")
        return

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Baixar Vídeo", callback_data=f"dl_video|{url}"),
            InlineKeyboardButton("🎵 Baixar Áudio", callback_data=f"dl_audio|{url}")
        ]
    ])

    legenda = (
        f"🎵 **Informações da Mídia:**\n\n"
        f"📌 **Título:** {titulo}\n"
        f"⏱️ **Duração:** {duracao}\n"
        f"👀 **Visualizações:** {views_str}\n"
        f"❤️ **Curtidas:** {likes_str}\n"
        f"💬 **Comentários:** {comentarios_str}\n\n"
        f"👇 Escolha o formato desejado abaixo:"
    )

    await status_msg.delete()
    if thumbnail:
        await message.reply_photo(
            photo=thumbnail,
            caption=legenda,
            reply_markup=teclado,
            parse_mode="Markdown"
        )
    else:
        await message.reply_text(legenda, reply_markup=teclado, parse_mode="Markdown")

async def baixar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data
    tipo, url = dados.split("|")
    
    await query.answer("⏳ Baixando, aguarde...")
    
    texto_processando = "⏳ Processando o download, por favor aguarde..."
    try:
        if query.message.caption is not None:
            await query.message.edit_caption(caption=texto_processando)
        else:
            await query.message.edit_text(text=texto_processando)
    except Exception:
        pass

    if tipo == "dl_video":
        ydl_opts = {
            'format': 'best',
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'noplaylist': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }
    else:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'noplaylist': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

    caminho_arquivo = None
    try:
        os.makedirs("downloads", exist_ok=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            caminho_arquivo = ydl.prepare_filename(info)
            if tipo == "dl_audio":
                caminho_arquivo = os.path.splitext(caminho_arquivo)[0] + ".mp3"

        try:
            if query.message.caption is not None:
                await query.message.edit_caption(caption="📤 Enviando para o chat...")
            else:
                await query.message.edit_text(text="📤 Enviando para o chat...")
        except Exception:
            pass

        mention = query.from_user.mention_html()

        if tipo == "dl_audio":
            with open(caminho_arquivo, 'rb') as audio_file:
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=audio_file,
                    caption=f"Prontinho🙂 {mention}",
                    parse_mode="HTML"
                )
        else:
            with open(caminho_arquivo, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=video_file,
                    caption=f"Prontinho🙂 {mention}",
                    parse_mode="HTML"
                )

        await query.message.delete()

    except Exception as e:
        erro_msg = f"❌ Erro ao baixar: `{e}`"
        try:
            if query.message.caption is not None:
                await query.message.edit_caption(caption=erro_msg, parse_mode="Markdown")
            else:
                await query.message.edit_text(text=erro_msg, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(query.message.chat_id, erro_msg)
    
    finally:
        if caminho_arquivo and os.path.exists(caminho_arquivo):
            try:
                os.remove(caminho_arquivo)
            except Exception:
                pass
