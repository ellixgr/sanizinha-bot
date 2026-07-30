import os
import tempfile
import pathlib
import logging
import yt_dlp
from pymongo import MongoClient
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, filters, ContextTypes

logger = logging.getLogger(__name__)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["sanizinhabot_db"]
cookie_collection = db["config_cookies"]
DONO_ID = os.environ.get("DONO_ID", "")

async def verificar_permissao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    
    # ✅ Dono SEMPRE tem permissão
    if str(user.id) == str(DONO_ID):
        return True
    
    # ✅ Verifica grupo autorizado
    from bot import grupo_autorizado
    if chat.type in ["group", "supergroup"]:
        if not await grupo_autorizado(chat.id):
            return False
        try:
            member = await chat.get_member(user.id)
            if member.status in ["creator", "administrator"]:
                return True
        except Exception:
            pass
    return False

def obter_cookie_temporario():
    registro = cookie_collection.find_one({"_id": "youtube_cookie"})
    if not registro or not registro.get("conteudo"):
        return None, None
    temp_cookie = tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8", suffix=".txt")
    temp_cookie.write(registro["conteudo"])
    temp_cookie.close()
    return temp_cookie.name, temp_cookie

async def cmd_adicionar_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not await verificar_permissao(update, context):
        await message.reply_text("❌ Apenas o dono ou administradores podem atualizar os cookies.")
        return
    if not context.args:
        await message.reply_text(
            "⚠️ **Como usar:**\n\n`/addcookie # Netscape HTTP Cookie File...`",
            parse_mode="Markdown"
        )
        return
    conteudo_cookie = " ".join(context.args)
    try:
        cookie_collection.update_one(
            {"_id": "youtube_cookie"},
            {"$set": {"conteudo": conteudo_cookie}},
            upsert=True
        )
        await message.reply_text("✅ **Cookie salvo com sucesso!**")
    except Exception as e:
        await message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")

async def cmd_limpar_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not await verificar_permissao(update, context):
        await message.reply_text("❌ Sem permissão!")
        return
    try:
        res = cookie_collection.delete_one({"_id": "youtube_cookie"})
        await message.reply_text("✅ Cookie removido!" if res.deleted_count else "⚠️ Sem cookie salvo.")
    except Exception as e:
        await message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")

async def play_pesquisa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    
    if not message or not context.args:
        await message.reply_text("⚠️ Use: `/play nome ou link`", parse_mode="Markdown")
        return

    # ✅ Verifica permissão
    if str(user.id) != str(DONO_ID):
        if chat.type == "private":
            from bot import verificar_assinante
            if not await verificar_assinante(user.id):
                await message.reply_text("⚠️ Comando disponível apenas para assinantes no privado!")
                return
        else:
            from bot import grupo_autorizado
            if not await grupo_autorizado(chat.id):
                await message.reply_text("❌ Grupo não autorizado!")
                return

    query = " ".join(context.args)
    status_msg = await message.reply_text("🔍 Procurando...")
    cookie_path, _ = obter_cookie_temporario()

    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
        'default_search': 'ytsearch1',
        'cookiefile': cookie_path,
        'extractor_args': {'youtube': {'player_client': ['mweb', 'android', 'web']}},
        'socket_timeout': 30,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info: info = info['entries'][0]
            
            titulo = info.get('title', 'Desconhecido')
            url = info.get('webpage_url')
            duracao = info.get('duration_string', 'N/A')
            thumbnail = info.get('thumbnail')
            views = f"{info.get('view_count', 0):,}".replace(",", ".")
            likes = f"{info.get('like_count', 0):,}".replace(",", ".")
    except Exception as e:
        await status_msg.edit_text(f"❌ Erro: `{e}`", parse_mode="Markdown")
        return
    finally:
        if cookie_path and os.path.exists(cookie_path): os.unlink(cookie_path)

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Vídeo", callback_data=f"dl_video|{url}"),
         InlineKeyboardButton("🎵 Áudio", callback_data=f"dl_audio|{url}")]
    ])

    legenda = (
        f"🎵 **Mídia encontrada:**\n📌 {titulo}\n⏱️ {duracao}\n👀 {views} | ❤️ {likes}"
    )
    await status_msg.delete()
    if thumbnail:
        await message.reply_photo(thumbnail, caption=legenda, reply_markup=teclado, parse_mode="Markdown")
    else:
        await message.reply_text(legenda, reply_markup=teclado, parse_mode="Markdown")

async def baixar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data
    tipo, url = dados.split("|")
    chat = query.message.chat
    user = query.from_user

    # ✅ Verifica permissão
    if str(user.id) != str(DONO_ID):
        if chat.type == "private":
            from bot import verificar_assinante
            if not await verificar_assinante(user.id):
                await query.answer("⚠️ Apenas assinantes!", show_alert=True)
                return
        else:
            from bot import grupo_autorizado
            if not await grupo_autorizado(chat.id):
                await query.answer("❌ Grupo não autorizado!", show_alert=True)
                return

    await query.answer("⏳ Baixando...")
    cookie_path, _ = obter_cookie_temporario()

    ydl_opts = {
        'format': 'best/bestvideo+bestaudio' if tipo == "dl_video" else 'bestaudio/best',
        'noplaylist': True,
        'cookiefile': cookie_path,
        'extractor_args': {'youtube': {'player_client': ['mweb', 'android', 'web']}},
        'outtmpl': os.path.join(tempfile.gettempdir(), f'{tipo}_{os.getpid()}_%(id)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
    }
    if tipo == "dl_audio":
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]

    output_path = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            output_path = pathlib.Path(ydl.prepare_filename(info))
            if tipo == "dl_audio": output_path = output_path.with_suffix('.mp3')
            ydl.download([url])

        await query.message.edit_text("📤 Enviando...")
        mention = query.from_user.mention_html()
        with open(output_path, 'rb') as f:
            if tipo == "dl_audio":
                await context.bot.send_audio(chat.id, f, caption=f"✅ Pronto! {mention}", parse_mode="HTML")
            else:
                await context.bot.send_video(chat.id, f, caption=f"✅ Pronto! {mention}", parse_mode="HTML")
        await query.message.delete()
    except Exception as e:
        await query.message.edit_text(f"❌ Erro: `{e}`", parse_mode="Markdown")
    finally:
        if cookie_path and os.path.exists(cookie_path): os.unlink(cookie_path)
        if output_path and os.path.exists(output_path): os.unlink(output_path)

def setup_play(app: Application):
    app.add_handler(CommandHandler(["baixar", "dl", "play"], play_pesquisa))
    app.add_handler(CommandHandler("addcookie", cmd_adicionar_cookie))
    app.add_handler(CommandHandler("limpacookie", cmd_limpar_cookie))
    app.add_handler(CallbackQueryHandler(baixar_callback, pattern=r"^dl_(video|audio)\|"))
