import os
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI")
DONO_ID = os.environ.get("DONO_ID")

async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    # O ranking só faz sentido em grupos/supergrupos
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado dentro de grupos!")
        return

    # Verificação se o usuário é Administrador ou o Dono do bot
    is_admin = False
    if DONO_ID and str(user.id) == str(DONO_ID):
        is_admin = True
    else:
        try:
            membro = await chat.get_member(user.id)
            if membro.status in ["administrator", "creator"]:
                is_admin = True
        except Exception:
            pass

    if not is_admin:
        await update.message.reply_text("⚠️ Apenas administradores do grupo podem usar o comando `/rank`!", parse_mode="Markdown")
        return

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
        db = client["sanizinhabot_db"]
        
        # Busca os 10 usuários com mais mensagens neste chat específico, ordenando do maior para o menor
        top_usuarios = list(
            db["mensagens_usuarios"]
            .find({"chat_id": chat.id})
            .sort("total_mensagens", -1)
            .limit(10)
        )

        if not top_usuarios:
            await update.message.reply_text("📊 Ainda não há dados de mensagens registrados neste grupo.")
            return

        texto_rank = f"🏆 **Top 10 Membros Mais Ativos**\n👥 *Grupo:* {chat.title}\n\n"

        for i, doc in enumerate(top_usuarios, start=1):
            user_id = doc.get("user_id")
            total_msgs = doc.get("total_mensagens", 0)

            # Tenta buscar o nome atualizado do usuário no Telegram
            nome_usuario = f"Usuário `{user_id}`"
            try:
                membro_info = await context.bot.get_chat_member(chat.id, user_id)
                nome_usuario = membro_info.user.first_name
            except Exception:
                pass

            # Ícones especiais para o pódio (1º, 2º e 3º lugar)
            if i == 1:
                pos = "🥇"
            elif i == 2:
                pos = "🥈"
            elif i == 3:
                pos = "🥉"
            else:
                pos = f"#{i}"

            texto_rank += f"{pos} **{nome_usuario}** — `{total_msgs}` mensagens\n"

        await update.message.reply_text(texto_rank, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao gerar o ranking: {e}")

def registrar_rank(app):
    app.add_handler(CommandHandler("rank", cmd_rank))
