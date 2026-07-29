import os
import tempfile
import pathlib
import logging
import yt_dlp
from pymongo import MongoClient
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, filters, ContextTypes

logger = logging.getLogger(__name__)

# Configuração do MongoDB (puxa da variável de ambiente MONGO_URI ou usa uma padrão local)
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["bot_database"] # Nome do banco de dados
cookie_collection = db["config_cookies"] # Coleção para guardar o cookie

def setup_play(app: Application):
    app.add_handler(CommandHandler(["baixar", "dl", "play"], play_pesquisa, filters=~filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("addcookie", cmd_adicionar_cookie))
    app.add_handler(CommandHandler("limpacookie", cmd_limpar_cookie))
    app.add_handler(CallbackQueryHandler(baixar_callback, pattern=r"^dl_(video|audio)\|"))

async def verificar_permissao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    
    # Pega o ID do dono via variável de ambiente
    dono_id = os.environ.get("DONO_ID")
    if dono_id and str(user.id) == str(dono_id):
        return True

    # Se for em grupo, verifica se é Administrador
    if chat.type in ["group", "supergroup"]:
        try:
            member = await chat.get_member(user.id)
            if member.status in ["creator", "administrator"]:
                return True
        except Exception:
            pass

    return False

def obter_cookie_temporario():
    """Busca o cookie no MongoDB e cria um arquivo temporário físico para o yt-dlp ler."""
    registro = cookie_collection.find_one({"_id": "youtube_cookie"})
    if not registro or not registro.get("conteudo"):
        return None, None

    # Cria um arquivo temporário seguro no disco apenas durante a execução do download
    temp_cookie = tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8", suffix=".txt")
    temp_cookie.write(registro["conteudo"])
    temp_cookie.close()
    return temp_cookie.name, temp_cookie

async def cmd_adicionar_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    # Valida se é Dono ou ADM
    if not await verificar_permissao(update, context):
        await message.reply_text("❌ Apenas o dono ou administradores podem atualizar os cookies.")
        return

    if not context.args:
        await message.reply_text(
            "⚠️ **Como usar o comando:**\n\n"
            "Envie o comando seguido do conteúdo do seu arquivo `cookies.txt`.\n"
            "Exemplo: `/addcookie # Netscape HTTP Cookie File...`",
            parse_mode="Markdown"
        )
        return

    conteudo_cookie = " ".join(context.args)

    try:
        # Salva ou atualiza no MongoDB
        cookie_collection.update_one(
            {"_id": "youtube_cookie"},
            {"$set": {"conteudo": conteudo_cookie}},
            upsert=True
        )
        await message.reply_text("✅ **Cookie salvo no MongoDB com sucesso!**\nO bot já está utilizando essa sessão para os downloads.")
    except Exception as e:
        await message.reply_text(f"❌ Erro ao salvar o cookie no banco: `{e}`", parse_mode="Markdown")

async def cmd_limpar_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    # Valida se é Dono ou ADM
    if not await verificar_permissao(update, context):
        await message.reply_text("❌ Apenas o dono ou administradores podem limpar os cookies.")
        return

    try:
        resultado = cookie_collection.delete_one({"_id": "youtube_cookie"})
        if resultado.deleted_count > 0:
            await message.reply_text("🗑️ **Cookie removido do MongoDB com sucesso!** O bot agora funcionará sem cookies.")
        else:
            await message.reply_text("⚠️ Não há nenhum cookie salvo no momento.")
    except Exception as e:
        await message.reply_text(f"❌ Erro ao limpar o cookie: `{e}`", parse_mode="Markdown")

async def play_pesquisa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if not context.args:
        await message.reply_text("⚠️ Envie o comando junto com o nome ou link.\nExemplo: `/play travis scott`", parse_mode="Markdown")
        return

    query = " ".join(context.args)
    status_msg = await message.reply_text("🔍 Procurando...")

    cookie_path, temp_file_obj = obter_cookie_temporario()

    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
        'default_search': 'ytsearch1',
        'cookiefile': cookie_path,
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb', 'android', 'web'],
            }
        },
        'socket_timeout': 30,
        'quiet': True,
        'no_warnings': True,
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
    finally:
        if cookie_path and os.path.exists(cookie_path):
            try:
                os.unlink(cookie_path)
            except Exception:
                pass

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

    cookie_path, temp_file_obj = obter_cookie_temporario()

    if tipo == "dl_video":
        ydl_opts = {
            'format': 'best/bestvideo+bestaudio',
            'noplaylist': True,
            'cookiefile': cookie_path,
            'extractor_args': {
                'youtube': {
                    'player_client': ['mweb', 'android', 'web'],
                }
            },
            'outtmpl': os.path.join(tempfile.gettempdir(), f'video_{os.getpid()}_%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
    else:
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'cookiefile': cookie_path,
            'extractor_args': {
                'youtube': {
                    'player_client': ['mweb', 'android', 'web'],
                }
            },
            'extract_audio': True,
            'audioformat': 'mp3',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(tempfile.gettempdir(), f'audio_{os.getpid()}_%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }

    output_path = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            output_path = pathlib.Path(ydl.prepare_filename(info))
            if tipo == "dl_audio":
                output_path = output_path.with_suffix('.mp3')

            ydl.download([url])

        try:
            if query.message.caption is not None:
                await query.message.edit_caption(caption="📤 Enviando para o chat...")
            else:
                await query.message.edit_text(text="📤 Enviando para o chat...")
        except Exception:
            pass

        mention = query.from_user.mention_html()

        if tipo == "dl_audio":
            with open(output_path, 'rb') as audio_file:
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=audio_file,
                    caption=f"Prontinho🙂 {mention}",
                    parse_mode="HTML"
                )
        else:
            with open(output_path, 'rb') as video_file:
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
        # Limpa o arquivo de cookie temporário criado para a requisição
        if cookie_path and os.path.exists(cookie_path):
            try:
                os.unlink(cookie_path)
            except Exception:
                pass
        
        # Limpa o arquivo de mídia baixado
        if output_path and os.path.exists(output_path):
            try:
                os.unlink(output_path)
            except Exception:
                pass
