import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI")
DONO_ID = os.environ.get("DONO_ID")

def escapar_markdown(texto: str) -> str:
    """Escapa caracteres que quebram o Markdown padrão do Telegram"""
    caracteres = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for c in caracteres:
        texto = texto.replace(c, f"\\{c}")
    return texto

async def gerar_texto_rank(chat, context):
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
    db = client["sanizinhabot_db"]
    colecao = db["mensagens_usuarios"]

    # Busca os 10 usuários com mais mensagens neste chat
    top_usuarios = list(
        colecao.find({"chat_id": chat.id})
        .sort("total_mensagens", -1)
        .limit(10)
    )

    if not top_usuarios:
        return None

    nome_grupo = escapar_markdown(chat.title)
    
    texto_rank = f"🏆 𝐑𝐀𝐍𝐊 𝐀𝐓𝐈𝐕𝐎𝐒 𝐃𝐎 𝐂𝐇𝐀𝐓\n               ┑(￣▽￣)┍\n\n"

    for i, doc in enumerate(top_usuarios, start=1):
        user_id = doc.get("user_id")
        total_msgs = doc.get("total_mensagens", 0)

        # Tenta buscar os dados do usuário para pegar o @username ou formatar o nome
        mencao_usuario = f"Usuário `{user_id}`"
        try:
            membro_info = await context.bot.get_chat_member(chat.id, user_id)
            tg_user = membro_info.user
            
            if tg_user.username:
                mencao_usuario = f"@{tg_user.username}"
            elif tg_user.first_name:
                nome_seguro = escapar_markdown(tg_user.first_name)
                mencao_usuario = f"[{nome_seguro}](tg://user?id={user_id})"
        except Exception:
            pass

        # Define os emojis e o layout das caixas conforme solicitado
        if i == 1:
            pos_icon = "🥇 1º LUGAR"
        elif i == 2:
            pos_icon = "🥈 2º LUGAR"
        elif i == 3:
            pos_icon = "🥉 3º LUGAR"
        elif i == 4:
            pos_icon = "4️⃣ 4º LUGAR"
        elif i == 5:
            pos_icon = "5️⃣ 5º LUGAR"
        elif i == 6:
            pos_icon = "6️⃣ 6º LUGAR"
        elif i == 7:
            pos_icon = "7️⃣ 7º LUGAR"
        elif i == 8:
            pos_icon = "8️⃣ 8º LUGAR"
        elif i == 9:
            pos_icon = "9️⃣ 9º LUGAR"
        else:
            pos_icon = "🔟 10º LUGAR"

        # Bloco estilizado igual ao seu modelo
        texto_rank += (
            f"{pos_icon}\n"
            f"├ 👤 Usuario: {mencao_usuario}\n"
            f"├ 💬 Msg: `{total_msgs}`\n"
            f"╰━━━━━━━━━━━━━━━\n\n"
        )

    return texto_rank

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
        texto_rank = await gerar_texto_rank(chat, context)
        if not texto_rank:
            await update.message.reply_text("📊 Ainda não há dados de mensagens registrados neste grupo.")
            return

        # Botão de atualizar rank
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Atualizar Ranking", callback_data="atualizar_rank")]
        ])

        await update.message.reply_text(texto_rank, reply_markup=teclado, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao gerar o ranking: {e}")

async def callback_atualizar_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user

    # Verifica se quem clicou no botão também é admin ou dono
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
        await query.answer("⚠️ Apenas administradores podem atualizar o ranking!", show_alert=True)
        return

    try:
        texto_rank = await gerar_texto_rank(chat, context)
        if not texto_rank:
            await query.answer("📊 Não há dados suficientes.", show_alert=True)
            return

        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Atualizar Ranking", callback_data="atualizar_rank")]
        ])

        await query.message.edit_text(texto_rank, reply_markup=teclado, parse_mode="Markdown")
        await query.answer("✅ Ranking atualizado com sucesso!")
    except Exception as e:
        await query.answer(f"❌ Erro ao atualizar: {e}", show_alert=True)

def registrar_rank(app):
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CallbackQueryHandler(callback_atualizar_rank, pattern="^atualizar_rank$"))
