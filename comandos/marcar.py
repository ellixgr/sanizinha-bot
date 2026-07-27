from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, ContextTypes, filters
from pymongo import MongoClient
import os

# Configuração do MongoDB (usando a mesma base do seu projeto)
MONGO_URI = os.getenv("MONGO_URI", "sua_uri_do_mongodb_aqui")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["sanizinhabot_db"]  # Nome da db unificado com o bot.py
col_membros = db["membros_grupo"]

# 1. Salva automaticamente cada usuário que mandar mensagem no grupo
async def capturar_membros_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if not chat or not user or chat.type == "private":
        return
        
    if user.is_bot:
        return

    col_membros.update_one(
        {"chat_id": chat.id, "user_id": user.id},
        {
            "$set": {
                "username": user.username,
                "first_name": user.first_name
            }
        },
        upsert=True
    )

# 2. Remove do MongoDB quando o usuário sai do grupo (Economiza espaço!)
async def remover_membro_saiu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    left_member = update.message.left_chat_member
    
    if not chat or not left_member:
        return
        
    # Deleta o usuário específico deste grupo no banco
    col_membros.delete_one({
        "chat_id": chat.id,
        "user_id": left_member.id
    })

# 3. Comando /marcar que busca os usuários salvos no banco e lista numerados
async def marcar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Apenas em grupos.")
        return

    # Validação rigorosa de Administrador
    try:
        member = await chat.get_member(user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Apenas administradores podem usar este comando!")
            return
    except Exception:
        return

    # Pega o texto personalizado (ex: /marcar oiiii -> texto_chamada = "oiiii")
    # Se não mandar nada, usa "CHAMANDO TODOS OS MEMBROS 🗣️"
    texto_chamada = " ".join(context.args) if context.args else "CHAMANDO TODOS OS MEMBROS 🗣️"
    
    # Apaga a mensagem do comando enviada pelo admin
    try:
        await update.message.delete()
    except Exception:
        pass

    # Busca todos os usuários salvos deste grupo no banco de dados
    membros_salvos = list(col_membros.find({"chat_id": chat.id}))

    if not membros_salvos:
        await chat.send_message(f"📢 **{texto_chamada}**\n\nNenhum membro registrado ainda no banco.")
        return
    
    # Monta a lista numerada (1 @usuario, 2 @usuario...)
    linhas_mencoes = []
    for index, m in enumerate(membros_salvos, start=1):
        username = m.get("username")
        uid = m["user_id"]
        nome = m.get("first_name", "Membro")
        
        if username:
            linhas_mencoes.append(f"{index} @{username}")
        else:
            linhas_mencoes.append(f"{index} [{nome}](tg://user?id={uid})")

    # Como o Telegram tem limite de caracteres por mensagem, dividimos em blocos se necessário ou enviamos direto
    bloco_texto = f"📢 **{texto_chamada}**\n\n" + "\n".join(linhas_mencoes)

    try:
        await chat.send_message(bloco_texto, parse_mode="Markdown")
    except Exception:
        # Se ultrapassar o limite do telegram por ter gente demais, envia fatiado ou avisa
        await chat.send_message(f"📢 **{texto_chamada}**\n\n*(Muitos membros para marcar de uma vez só, lista excedeu o limite do Telegram)*", parse_mode="Markdown")

def registrar_marcar(app):
    app.add_handler(CommandHandler(["marcar", "todos", "tagall"], marcar_cmd))
    # Salva o membro quando ele manda mensagem
    app.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, capturar_membros_handler), group=2)
    # Remove do banco automaticamente se o membro sair do grupo
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER & ~filters.ChatType.PRIVATE, remover_membro_saiu_handler), group=3)
