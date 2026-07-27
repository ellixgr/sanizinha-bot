import os
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI")
DONO_ID = os.environ.get("DONO_ID")

def escapar_markdown(texto: str) -> str:
    """Escapa caracteres que quebram o Markdown padrão do Telegram"""
    caracteres = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for c in caracteres:
        texto = texto.replace(c, f"\\{c}")
    return texto

async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado dentro de grupos!")
        return

    # Verificação de Administrador ou Dono
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
        
        colecao = db["mensagens_usuarios"]

        # Calcula o total geral de mensagens enviadas no grupo inteiro
        pipeline_total = [
            {"$match": {"chat_id": chat.id}},
            {"$group": {"_id": None, "soma_total": {"$sum": "$total_mensagens"}}}
        ]
        resultado_total = list(colecao.aggregate(pipeline_total))
        total_geral_grupo = resultado_total[0]["soma_total"] if resultado_total else 0

        # Busca os 10 usuários com mais mensagens neste chat
        top_usuarios = list(
            colecao.find({"chat_id": chat.id})
            .sort("total_mensagens", -1)
            .limit(10)
        )

        if not top_usuarios or total_geral_grupo == 0:
            await update.message.reply_text("📊 Ainda não há dados de mensagens registrados neste grupo.")
            return

        # Nome do grupo seguro contra caracteres especiais
        nome_grupo = escapar_markdown(chat.title)
        texto_rank = f"🏆 *Top 10 Membros Mais Ativos*\n👥 *Grupo:* {nome_grupo}\n📊 *Total de Msgs:* `{total_geral_grupo}`\n\n"

        for i, doc in enumerate(top_usuarios, start=1):
            user_id = doc.get("user_id")
            total_msgs = doc.get("total_mensagens", 0)

            # Calcula a porcentagem de participação (evitando divisão por zero)
            porcentagem = (total_msgs / total_geral_grupo) * 100 if total_geral_grupo > 0 else 0

            nome_usuario = f"Usuário {user_id}"
            try:
                membro_info = await context.bot.get_chat_member(chat.id, user_id)
                if membro_info.user.first_name:
                    nome_usuario = escapar_markdown(membro_info.user.first_name)
            except Exception:
                pass

            # Apenas 1º, 2º e 3º lugar ganham emoji de medalha
            if i == 1:
                pos = "🥇"
            elif i == 2:
                pos = "🥈"
            elif i == 3:
                pos = "🥉"
            else:
                pos = f"#{i}"

            texto_rank += f"{pos} *{nome_usuario}* — `{total_msgs}` msgs (*{porcentagem:.1f}%*)\n"

        await update.message.reply_text(texto_rank, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao gerar o ranking: {e}")

def registrar_rank(app):
    app.add_handler(CommandHandler("rank", cmd_rank))
