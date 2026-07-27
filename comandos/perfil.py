import os
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from pymongo import MongoClient

async def perfil_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Use este comando dentro de um grupo para ver suas estatísticas completas!")
        return

    # Coleta de dados no MongoDB
    total_msgs = 1
    fotos = 0
    videos = 0
    audios = 0
    stickers = 0
    
    try:
        client = MongoClient(os.environ.get("MONGO_URI"), serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
        db = client["sanizinhabot_db"]
        
        # Dados do usuário no chat
        doc = db["mensagens_usuarios"].find_one({"chat_id": chat.id, "user_id": user.id})
        if doc:
            total_msgs = doc.get("total_mensagens", 1)
            fotos = doc.get("fotos", 0)
            videos = doc.get("videos", 0)
            audios = doc.get("audios", 0)
            stickers = doc.get("stickers", 0)

        # Total geral de mensagens no grupo para calcular a porcentagem de atividade
        total_grupo = db["mensagens_usuarios"].aggregate([
            {"$match": {"chat_id": chat.id}},
            {"$group": {"_id": None, "soma": {"$sum": "$total_mensagens"}}}
        ])
        soma_doc = list(total_grupo)
        total_geral_grupo = soma_doc[0]["soma"] if soma_doc else 1
        
        atividade_pct = (total_msgs / total_geral_grupo) * 100
        if atividade_pct > 100: 
            atividade_pct = 100.0
    except Exception:
        atividade_pct = 0.0

    # Puxar Bio e Foto de Perfil do Telegram
    bio = "Não configurada ou oculta."
    try:
        chat_info = await context.bot.get_chat(user.id)
        if chat_info.bio:
            bio = chat_info.bio
    except Exception:
        pass

    # Envio da foto de perfil se houver
    enviou_foto = False
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            texto_legenda = (
                f"👤 **PERFIL DE {user.first_name.upper()}**\n\n"
                f"🆔 **ID:** `{user.id}`\n"
                f"💬 **Bio:** _{bio}_\n\n"
                f"📊 **ESTATÍSTICAS NO GRUPO:**\n"
                f"💬 Mensagens Totais: `{total_msgs}`\n"
                f"📸 Fotos Enviadas: `{fotos}`\n"
                f"🎥 Vídeos Enviados: `{videos}`\n"
                f"🎙️ Áudios/Voz: `{audios}`\n"
                f"🎭 Figurinhas: `{stickers}`\n"
                f"⚡ Índice de Atividade: `{atividade_pct:.1f}%`"
            )
            await update.message.reply_photo(photo=file_id, caption=texto_legenda, parse_mode="Markdown")
            enviou_foto = True
    except Exception:
        pass

    if not enviou_foto:
        texto_perfil = (
            f"👤 **PERFIL DE {user.first_name.upper()}**\n\n"
            f"🆔 **ID:** `{user.id}`\n"
            f"💬 **Bio:** _{bio}_\n\n"
            f"📊 **ESTATÍSTICAS NO GRUPO:**\n"
            f"💬 Mensagens Totais: `{total_msgs}`\n"
            f"📸 Fotos Enviadas: `{fotos}`\n"
            f"🎥 Vídeos Enviados: `{videos}`\n"
            f"🎙️ Áudios/Voz: `{audios}`\n"
            f"🎭 Figurinhas: `{stickers}`\n"
            f"⚡ Índice de Atividade: `{atividade_pct:.1f}%`"
        )
        await update.message.reply_text(texto_perfil, parse_mode="Markdown")

def registrar_perfil(app):
    app.add_handler(CommandHandler("perfil", perfil_cmd))
