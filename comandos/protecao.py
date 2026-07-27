import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Armazenamento em memória para controle de Flood e Estados de Proteção por Grupo
FLOOD_CONTROL = {}
CONFIGS_PROTECAO = {} 

def registrar_protecoes(app):
    app.add_handler(CommandHandler("protecao", painel_protecao_cmd))
    app.add_handler(CallbackQueryHandler(callback_protecao_toggle, pattern=r"^prot_"))
    
    # Interceptador principal de segurança (roda com prioridade alta)
    app.add_handler(MessageHandler(~filters.COMMAND & ~filters.ChatType.PRIVATE, executor_protecoes), group=0)

async def painel_protecao_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Apenas administradores podem configurar as proteções.")
            return
    except Exception:
        return

    cfg = CONFIGS_PROTECAO.get(chat.id, {
        "antilink": False, "antiflood": False, "antiphoto": False, 
        "antisticker": False, "antitravas": True
    })

    txt = (
        f"🛡️ **PAINEL DE SEGURANÇA E PROTEÇÃO**\n\n"
        f"Configure as travas automáticas deste grupo abaixo:"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔗 Antilink: {'🟢 ON' if cfg['antilink'] else '🔴 OFF'}", callback_data="prot_antilink")],
        [InlineKeyboardButton(f"⚡ Antiflood: {'🟢 ON' if cfg['antiflood'] else '🔴 OFF'}", callback_data="prot_antiflood")],
        [InlineKeyboardButton(f"📸 Anti-Foto: {'🟢 ON' if cfg['antiphoto'] else '🔴 OFF'}", callback_data="prot_antiphoto")],
        [InlineKeyboardButton(f"🎭 Anti-Figurinha: {'🟢 ON' if cfg['antisticker'] else '🔴 OFF'}", callback_data="prot_antisticker")],
        [InlineKeyboardButton(f"💀 Anti-Travas: {'🟢 ON' if cfg['antitravas'] else '🔴 OFF'}", callback_data="prot_antitravas")],
    ])
    await update.message.reply_text(txt, reply_markup=teclado, parse_mode="Markdown")

async def callback_protecao_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = query.message.chat
    user = query.from_user

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"]:
            await query.answer("⚠️ Apenas administradores!", show_alert=True)
            return
    except Exception:
        return

    acao = query.data.replace("prot_", "")
    if chat.id not in CONFIGS_PROTECAO:
        CONFIGS_PROTECAO[chat.id] = {
            "antilink": False, "antiflood": False, "antiphoto": False, 
            "antisticker": False, "antitravas": True
        }

    CONFIGS_PROTECAO[chat.id][acao] = not CONFIGS_PROTECAO[chat.id][acao]
    cfg = CONFIGS_PROTECAO[chat.id]

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔗 Antilink: {'🟢 ON' if cfg['antilink'] else '🔴 OFF'}", callback_data="prot_antilink")],
        [InlineKeyboardButton(f"⚡ Antiflood: {'🟢 ON' if cfg['antiflood'] else '🔴 OFF'}", callback_data="prot_antiflood")],
        [InlineKeyboardButton(f"📸 Anti-Foto: {'🟢 ON' if cfg['antiphoto'] else '🔴 OFF'}", callback_data="prot_antiphoto")],
        [InlineKeyboardButton(f"🎭 Anti-Figurinha: {'🟢 ON' if cfg['antisticker'] else '🔴 OFF'}", callback_data="prot_antisticker")],
        [InlineKeyboardButton(f"💀 Anti-Travas: {'🟢 ON' if cfg['antitravas'] else '🔴 OFF'}", callback_data="prot_antitravas")],
    ])
    await query.message.edit_reply_markup(reply_markup=teclado)
    await query.answer(f"Proteção {acao} atualizada!")

async def executor_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    if not chat or not user or not message:
        return

    # Admins passam livre pelas proteções
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ["creator", "administrator"]:
            return
    except Exception:
        pass

    cfg = CONFIGS_PROTECAO.get(chat.id, {
        "antilink": False, "antiflood": False, "antiphoto": False, 
        "antisticker": False, "antitravas": True
    })

    texto_msg = message.text or message.caption or ""

    # 1. Anti-Travas (Mensagens com caracteres excessivos ou invisíveis / exploits)
    if cfg["antitravas"]:
        if len(texto_msg) > 1500 or texto_msg.count('\n') > 25:
            try:
                await message.delete()
                await chat.send_message(f"⚠️ {user.mention_markdown()} enviou uma trava e foi bloqueado!", parse_mode="Markdown")
                await context.bot.ban_chat_member(chat.id, user.id)
                return
            except Exception:
                pass

    # 2. Antilink
    if cfg["antilink"]:
        if "http://" in texto_msg or "https://" in texto_msg or "t.me/" in texto_msg or "www." in texto_msg:
            try:
                await message.delete()
                return
            except Exception:
                pass

    # 3. Anti-Foto
    if cfg["antiphoto"] and message.photo:
        try:
            await message.delete()
            return
        except Exception:
            pass

    # 4. Anti-Figurinha
    if cfg["antisticker"] and message.sticker:
        try:
            await message.delete()
            return
        except Exception:
            pass

    # 5. Antiflood (Mais de 5 msgs em 4 segundos)
    if cfg["antiflood"]:
        agora = time.time()
        chave = (chat.id, user.id)
        if chave not in FLOOD_CONTROL:
            FLOOD_CONTROL[chave] = []
        
        # Filtra histórico recente
        FLOOD_CONTROL[chave] = [t for t in FLOOD_CONTROL[chave] if agora - t < 4]
        FLOOD_CONTROL[chave].append(agora)

        if len(FLOOD_CONTROL[chave]) > 5:
            try:
                await message.delete()
                await context.bot.restrict_chat_member(chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
                await chat.send_message(f"⚠️ {user.mention_markdown()} foi mutado por flood!", parse_mode="Markdown")
            except Exception:
                pass
