import time
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# ❌ REMOVA ESSA LINHA: from bot import get_db, DONO_ID, FUSO_BR

# ✅ RECEBE OS VALORES POR PARÂMETRO, NÃO IMPORTA
async def cmd_addgrupo(update: Update, context: ContextTypes.DEFAULT_TYPE, get_db, DONO_ID, FUSO_BR):
    chat = update.effective_chat
    user = update.effective_user

    if not DONO_ID or str(user.id) != str(DONO_ID):
        await update.message.reply_text("❌ Apenas o dono do bot pode usar este comando!")
        return

    if not chat or chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ Use este comando DENTRO do grupo que deseja registrar!")
        return

    context.user_data["meses_aluguel"] = 1
    context.user_data["grupo_add_id"] = chat.id
    context.user_data["grupo_add_nome"] = chat.title

    await exibir_painel_adicionar(update, context)

async def exibir_painel_adicionar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meses = context.user_data.get("meses_aluguel", 1)
    nome_grupo = context.user_data.get("grupo_add_nome", "Sem nome")

    texto = (
        "🛠️ **ADICIONAR GRUPO NO SISTEMA**\n\n"
        f"📌 Grupo: `{nome_grupo}`\n"
        f"🆔 ID: `{context.user_data.get('grupo_add_id')}`\n\n"
        f"⏳ Tempo de permissão: **{meses} mês{'es' if meses > 1 else ''}**\n\n"
        "Ajuste o tempo e confirme para liberar o bot neste grupo!"
    )

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖ Diminuir", callback_data="addgrupo_diminuir"),
            InlineKeyboardButton("➕ Aumentar", callback_data="addgrupo_aumentar")
        ],
        [
            InlineKeyboardButton("✅ CONFIRMAR", callback_data="addgrupo_ok"),
            InlineKeyboardButton("❌ CANCELAR", callback_data="addgrupo_cancelar")
        ]
    ])

    if update.callback_query:
        await update.callback_query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def processar_callback_addgrupo(update: Update, context: ContextTypes.DEFAULT_TYPE, get_db, FUSO_BR):
    query = update.callback_query
    await query.answer()
    dados = query.data

    if dados == "addgrupo_aumentar":
        atual = context.user_data.get("meses_aluguel", 1)
        if atual < 24:
            context.user_data["meses_aluguel"] = atual + 1
        await exibir_painel_adicionar(update, context)

    elif dados == "addgrupo_diminuir":
        atual = context.user_data.get("meses_aluguel", 1)
        if atual > 1:
            context.user_data["meses_aluguel"] = atual - 1
        await exibir_painel_adicionar(update, context)

    elif dados == "addgrupo_cancelar":
        await query.message.edit_text("❌ Operação cancelada!")
        context.user_data.clear()

    elif dados == "addgrupo_ok":
        meses = context.user_data.get("meses_aluguel", 1)
        chat_id = context.user_data.get("grupo_add_id")
        chat_nome = context.user_data.get("grupo_add_nome")

        db = get_db()
        agora = time.time()
        expira_em = agora + (meses * 30 * 24 * 60 * 60)

        db["grupos_autorizados"].update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "chat_title": chat_nome,
                    "registrado_por": update.effective_user.id,
                    "expira_em": expira_em,
                    "ativo": True
                }
            },
            upsert=True
        )
        db["avisos_grupos_piratas"].delete_one({"chat_id": chat_id})

        data_expira = datetime.fromtimestamp(expira_em, FUSO_BR).strftime("%d/%m/%Y")

        await query.message.edit_text(
            f"✅ **GRUPO REGISTRADO COM SUCESSO!**\n\n"
            f"📌 Grupo: `{chat_nome}`\n"
            f"⏳ Válido por: {meses} mês{'es' if meses > 1 else ''}\n"
            f"📅 Expira em: {data_expira}\n\n"
            "O bot já está liberado e funcionando normalmente aqui!",
            parse_mode="Markdown"
        )
        context.user_data.clear()
