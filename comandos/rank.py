import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from pymongo import MongoClient
import re

MONGO_URI = os.environ.get("MONGO_URI")
DONO_ID = os.environ.get("DONO_ID", "").strip()

# ✅ Reutiliza a conexão (se já existir) — NÃO abre toda hora
_mongo_client = None
def get_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=2000,
            tlsAllowInvalidCertificates=True
        )
    return _mongo_client["sanizinhabot_db"]

def limpar_nome(nome: str) -> str:
    """Remove caracteres problemáticos do nome"""
    if not nome:
        return "Membro"
    return re.sub(r'[_*`\[\]()]', '', nome)

async def gerar_texto_rank(chat, context):
    db = get_db()
    colecao = db["mensagens_usuarios"]

    # ✅ Limita ANTES de ordenar — mais rápido!
    top_usuarios = list(
        colecao.find({"chat_id": chat.id})
        .sort("total_mensagens", -1)
        .limit(10)  # ✅ Garantido!
    )

    if not top_usuarios:
        return None
    
    texto_rank = "🏆 RANK ATIVOS DO CHAT\n               ┑(￣▽￣)┍\n\n"

    for i, doc in enumerate(top_usuarios, start=1):
        user_id = doc.get("user_id")
        total_msgs = doc.get("total_mensagens", 0)
        # ✅ Garante que é número
        if not isinstance(total_msgs, (int, float)):
            total_msgs = 0
        total_msgs = int(total_msgs)

        mencao_usuario = f"Usuário {user_id}"
        try:
            membro_info = await context.bot.get_chat_member(chat.id, user_id)
            tg_user = membro_info.user
            
            if tg_user.username:
                mencao_usuario = f"@{tg_user.username}"
            elif tg_user.first_name:
                nome_limpo = limpar_nome(tg_user.first_name)
                mencao_usuario = nome_limpo if nome_limpo else f"Usuário {user_id}"
            else:
                mencao_usuario = f"Usuário {user_id}"
        except Exception:
            # Se não conseguir pegar info, mantém o ID
            pass

        # ✅ Ícones de posição simplificados
        pos_icon = f"{i}️⃣ {i}º LUGAR"
        if i == 1:
            pos_icon = "🥇 1º LUGAR"
        elif i == 2:
            pos_icon = "🥈 2º LUGAR"
        elif i == 3:
            pos_icon = "🥉 3º LUGAR"

        texto_rank += (
            f"{pos_icon}\n"
            f"├ 👤 Usuario: {mencao_usuario}\n"
            f"├ 💬 Msg: {total_msgs}\n"
            f"╰━━━━━━━━━━━━━━━\n\n"
        )

    return texto_rank

# ✅ FUNÇÃO ÚNICA DE VERIFICAÇÃO DE ADMIN — sem duplicata!
async def is_admin_do_grupo(chat, user):
    if not user or not chat:
        return False
    # Dono do bot é sempre admin
    if DONO_ID and str(user.id) == str(DONO_ID):
        return True
    # Verifica no grupo
    try:
        membro = await chat.get_member(user.id)
        return membro.status in ["administrator", "creator"]
    except Exception:
        return False

async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando só pode ser usado dentro de grupos!")
        return

    if not await is_admin_do_grupo(chat, user):
        await update.message.reply_text("⚠️ Apenas administradores do grupo podem usar o comando /rank!")
        return

    try:
        texto_rank = await gerar_texto_rank(chat, context)
        if not texto_rank:
            await update.message.reply_text("📊 Ainda não há dados de mensagens registrados neste grupo.")
            return

        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Atualizar Ranking", callback_data="atualizar_rank")]
        ])

        await update.message.reply_text(texto_rank, reply_markup=teclado)

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao gerar o ranking: {e}")

async def callback_atualizar_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user

    if not await is_admin_do_grupo(chat, user):
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

        try:
            await query.message.edit_text(texto_rank, reply_markup=teclado)
            await query.answer("✅ Ranking atualizado com sucesso!")
        except Exception as telegram_error:
            if "Message is not modified" in str(telegram_error):
                await query.answer("✨ O ranking já está atualizado!", show_alert=False)
            else:
                raise telegram_error

    except Exception as e:
        await query.answer(f"❌ Erro ao atualizar: {e}", show_alert=True)

def registrar_rank(app):
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CallbackQueryHandler(callback_atualizar_rank, pattern="^atualizar_rank$"))
