import time
import re
import asyncio
from datetime import timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes, ChatMemberHandler

REGISTRO_FLOOD = {}
REGISTRO_AVISADOS = {}

def get_db():
    from pymongo import MongoClient
    import os
    mongo_uri = os.environ.get("MONGO_URI")
    client = MongoClient(
        mongo_uri, 
        serverSelectionTimeoutMS=1000, 
        connectTimeoutMS=1000,
        tlsAllowInvalidCertificates=True
    )
    return client["sanizinhabot_db"]

def obter_configs(chat_id: int):
    padrao = {
        "antilink": True,
        "antimencao": True,
        "antifoto": False,
        "antifigu": False,
        "antitravas": True,
        "antiflood": True
    }
    try:
        db = get_db()
        doc = db["configs_protecao"].find_one({"chat_id": chat_id})
        if doc and "configs" in doc:
            cfg = doc["configs"]
            for k, v in padrao.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception:
        pass
    return padrao

def salvar_configs(chat_id: int, cfg: dict):
    try:
        db = get_db()
        db["configs_protecao"].update_one(
            {"chat_id": chat_id},
            {"$set": {"configs": cfg}},
            upsert=True
        )
    except Exception:
        pass

def obter_punicao(chat_id: int):
    padrao = {
        "acao": "aviso_ban",
        "apagar_msg": True,
        "tempo_mute": 1
    }
    try:
        db = get_db()
        doc = db["configs_protecao"].find_one({"chat_id": chat_id})
        if doc and "punicao" in doc:
            p = doc["punicao"]
            for k, v in padrao.items():
                if k not in p:
                    p[k] = v
            return p
    except Exception:
        pass
    return padrao

def salvar_punicao(chat_id: int, punicao: dict):
    try:
        db = get_db()
        db["configs_protecao"].update_one(
            {"chat_id": chat_id},
            {"$set": {"punicao": punicao}},
            upsert=True
        )
    except Exception:
        pass

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int) -> bool:
    if chat_id > 0:  
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ["creator", "administrator"]:
            return True
    except Exception:
        pass
    return False

async def obter_menção_admins(chat, context: ContextTypes.DEFAULT_TYPE) -> str:
    try:
        admins = await chat.get_administrators()
        mencoes = []
        for adm in admins:
            if not adm.user.is_bot:
                mencoes.append(adm.user.mention_html("adm"))
        if mencoes:
            return " ".join(mencoes)
    except Exception:
        pass
    return "@adm"

def gerar_teclado_protecoes(cfg):
    s_link = "🟢 Ligado" if cfg.get("antilink", True) else "🔴 Desligado"
    s_mencao = "🟢 Ligado" if cfg.get("antimencao", True) else "🔴 Desligado"
    s_foto = "🟢 Ligado" if cfg.get("antifoto", False) else "🔴 Desligado"
    s_figu = "🟢 Ligado" if cfg.get("antifigu", False) else "🔴 Desligado"
    s_trav = "🟢 Ligado" if cfg.get("antitravas", True) else "🔴 Desligado"
    s_flood = "🟢 Ligado" if cfg.get("antiflood", True) else "🔴 Desligado"

    texto = "🛡️ **PAINEL DE PROTEÇÕES DO GRUPO**"

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔗 Anti-Link: {s_link}", callback_data="prot_toggle_antilink")],
        [InlineKeyboardButton(f"📢 Anti-Menção: {s_mencao}", callback_data="prot_toggle_antimencao")],
        [InlineKeyboardButton(f"📸 Anti-Foto: {s_foto}", callback_data="prot_toggle_antifoto")],
        [InlineKeyboardButton(f"🖼️ Anti-Figurinha: {s_figu}", callback_data="prot_toggle_antifigu")],
        [InlineKeyboardButton(f"⚠️ Anti-Travas: {s_trav}", callback_data="prot_toggle_antitravas")],
        [InlineKeyboardButton(f"⚡ Anti-Flood: {s_flood}", callback_data="prot_toggle_antiflood")],
        [InlineKeyboardButton("⚙️ Configurar Punição", callback_data="menu_config_punicao")],
        [InlineKeyboardButton("🔙 Voltar ao Menu ADM", callback_data="menu_adm")]
    ])
    return texto, teclado

async def enviar_painel_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    query = update.callback_query

    if not await is_admin(update, context, user_id, chat_id):
        if query:
            await query.answer("⚠️ Apenas administradores podem mexer nas proteções!", show_alert=True)
        return

    cfg = obter_configs(chat_id)
    texto, teclado = gerar_teclado_protecoes(cfg)

    if query:
        await query.answer()
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    else:
        if update.message:
            await update.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def enviar_painel_punicao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(update, context, user_id, chat_id):
        if query:
            await query.answer("⚠️ Apenas administradores podem configurar punições!", show_alert=True)
        return

    punicao = obter_punicao(chat_id)

    acoes_nomes = {
        "aviso_ban": "⚠️ 1º Aviso, 2º Banimento",
        "remover": "🔨 Remover / Banir Direto",
        "silenciar": "🔇 Silenciar (Mute)"
    }
    nome_acao_atual = acoes_nomes.get(punicao["acao"], "⚠️ 1º Aviso, 2º Banimento")
    status_apagar = "🟢 Sim" if punicao["apagar_msg"] else "🔴 Não"
    tempo_str = f"{punicao['tempo_mute']} minuto(s)"

    texto = (
        f"⚙️ **CONFIGURAR PUNIÇÃO DAS PROTEÇÕES**\n\n"
        f"📌 **Tipo de Punição:** `{nome_acao_atual}`\n"
        f"🗑️ **Apagar Mensagem Infratora:** `{status_apagar}`\n"
        f"⏱️ **Tempo de Silenciamento:** `{tempo_str}`"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📌 Tipo: {nome_acao_atual}", callback_data="pun_trocar_acao")],
        [InlineKeyboardButton(f"🗑️ Apagar Msg: {status_apagar}", callback_data="pun_toggle_apagar")],
        [
            InlineKeyboardButton("➖ Menos", callback_data="pun_tempo_menos"),
            InlineKeyboardButton(f"⏱️ {punicao['tempo_mute']} min", callback_data="pun_ignorar"),
            InlineKeyboardButton("➕ Mais", callback_data="pun_tempo_mais")
        ],
        [InlineKeyboardButton("🔙 Voltar às Proteções", callback_data="menu_protecoes")]
    ])

    if query:
        await query.answer()
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def processar_callback_protecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(update, context, user_id, chat_id):
        await query.answer("⚠️ Apenas administradores podem alterar as configurações!", show_alert=True)
        return

    data = query.data

    if data.startswith("prot_toggle_"):
        acao = data.replace("prot_toggle_", "")
        cfg = obter_configs(chat_id)
        if acao in cfg:
            cfg[acao] = not cfg[acao]
            salvar_configs(chat_id, cfg)
            await query.answer("Status alterado com sucesso!")
            texto, teclado = gerar_teclado_protecoes(cfg)
            await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

    elif data == "menu_config_punicao":
        await enviar_painel_punicao(update, context)

    elif data == "menu_protecoes":
        await enviar_painel_protecoes(update, context)

    elif data == "pun_toggle_apagar":
        p = obter_punicao(chat_id)
        p["apagar_msg"] = not p["apagar_msg"]
        salvar_punicao(chat_id, p)
        await query.answer("Configuração alterada!")
        await enviar_painel_punicao(update, context)

    elif data == "pun_trocar_acao":
        p = obter_punicao(chat_id)
        ciclo = {"aviso_ban": "remover", "remover": "silenciar", "silenciar": "aviso_ban"}
        p["acao"] = ciclo.get(p["acao"], "aviso_ban")
        salvar_punicao(chat_id, p)
        await query.answer("Modo de punição alterado!")
        await enviar_painel_punicao(update, context)

    elif data == "pun_tempo_menos":
        p = obter_punicao(chat_id)
        if p["tempo_mute"] > 1:
            p["tempo_mute"] -= 1
            salvar_punicao(chat_id, p)
            await query.answer(f"Tempo reduzido para {p['tempo_mute']} min")
        else:
            await query.answer("O tempo mínimo é 1 minuto!", show_alert=False)
        await enviar_painel_punicao(update, context)

    elif data == "pun_tempo_mais":
        p = obter_punicao(chat_id)
        if p["tempo_mute"] < 1440:
            p["tempo_mute"] += 1
            salvar_punicao(chat_id, p)
            await query.answer(f"Tempo aumentado para {p['tempo_mute']} min")
        else:
            await query.answer("O tempo máximo é 1440 minutos!", show_alert=False)
        await enviar_painel_punicao(update, context)

    elif data == "pun_ignorar":
        await query.answer("Use os botões ➕ e ➖ para ajustar.", show_alert=False)

async def cmd_protecao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if chat_id > 0:
        await update.message.reply_text("⚠️ Este comando só pode ser usado em grupos.")
        return
    if not await is_admin(update, context, user_id, chat_id):
        await update.message.reply_text("⚠️ Apenas administradores podem usar este comando.")
        return
    await enviar_painel_protecoes(update, context)

async def monitorar_seguranca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    message = update.message

    if not chat or not user or chat.type == "private" or not message:
        return

    if await is_admin(update, context, user.id, chat.id):
        return

    cfg = obter_configs(chat.id)
    punicao = obter_punicao(chat.id)
    
    texto_conteudo = message.text or message.caption or ""
    violacao_detectada = None
    motivo_violacao = ""
    eh_flood = False

    # 1. Anti-Flood Otimizado (mensagens, comandos, figurinhas ou qualquer tipo de msg em curto espaço de tempo)
    if cfg.get("antiflood", True):
        agora = time.time()
        chave = (chat.id, user.id)
        if chave not in REGISTRO_FLOOD:
            REGISTRO_FLOOD[chave] = []
        
        # Janela de 4 segundos para contagem de flood
        REGISTRO_FLOOD[chave] = [t for t in REGISTRO_FLOOD[chave] if agora - t < 4]
        REGISTRO_FLOOD[chave].append(agora)

        # Se enviar mais de 4 mensagens/comandos/figurinhas em menos de 4 segundos
        if len(REGISTRO_FLOOD[chave]) > 4:
            eh_flood = True
            violacao_detectada = True
            motivo_violacao = "flood de mensagens/comandos"

    if not eh_flood:
        chat_username = (chat.username or "").lower()

        # 2. Anti-Link
        if cfg.get("antilink", True):
            padrao_link = r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+|chat\.whatsapp\.com/\S+|[a-zA-Z0-9][-a-zA-Z0-9]*\.(com|net|org|br|io|gov|edu|me|xyz|ru|tk|ml|ga|cf|gq|gg|to|cc|co)\b\S*)"
            links_encontrados = re.findall(padrao_link, texto_conteudo, re.IGNORECASE)
            
            tem_link_entidade = False
            if message.entities:
                for entidade in message.entities:
                    if entidade.type in ["url", "text_link"]:
                        tem_link_entidade = True
                        break

            if links_encontrados or tem_link_entidade:
                link_proprio = False
                for l in links_encontrados:
                    url_str = "".join(l) if isinstance(l, tuple) else l
                    if chat_username and chat_username in url_str.lower():
                        link_proprio = True
                        break
                
                if not link_proprio:
                    violacao_detectada = True
                    motivo_violacao = "link proibido"

        # 3. Anti-Menção / Mensagens Encaminhadas
        if not violacao_detectada and cfg.get("antimencao", True):
            veio_encaminhado = bool(
                message.forward_date or 
                message.forward_from or 
                message.forward_from_chat or 
                message.forward_origin
            )

            padrao_mencao = r"(@[A-Za-z0-9_]{5,}|t\.me/[A-Za-z0-9_]+)"
            mencoes = re.findall(padrao_mencao, texto_conteudo, re.IGNORECASE)
            
            mencao_externa = False
            if mencoes:
                for m in mencoes:
                    if chat_username and chat_username in m.lower():
                        continue
                    mencao_externa = True
                    break

            if veio_encaminhado or mencao_externa:
                violacao_detectada = True
                motivo_violacao = "mensagem encaminhada / menção externa"

        # 4. Anti-Foto
        if not violacao_detectada and cfg.get("antifoto", False) and message.photo:
            violacao_detectada = True
            motivo_violacao = "foto"

        # 5. Anti-Figurinha
        if not violacao_detectada and cfg.get("antifigu", False) and message.sticker:
            violacao_detectada = True
            motivo_violacao = "figurinha"

        # 6. Anti-Travas
        if not violacao_detectada and cfg.get("antitravas", True) and len(texto_conteudo) > 600:
            violacao_detectada = True
            motivo_violacao = "trava de caracteres"

    if violacao_detectada:
        # Apaga a mensagem infratora APENAS se a opção estiver ativa no painel de punição
        if punicao.get("apagar_msg", True):
            try:
                await message.delete()
            except Exception:
                pass

        chave_aviso = (chat.id, user.id)
        tipo_acao = punicao.get("acao", "aviso_ban")

        # Se for flood detectado, silencia obrigatoriamente por 2 minutos e marca todos os ADMs
        if eh_flood:
            try:
                liberar_ate = timedelta(minutes=2)
                await context.bot.restrict_chat_member(chat.id, user.id, permissions=False, until_date=liberar_ate)
                
                mencoes_admins = await obter_menção_admins(chat, context)
                
                aviso = await chat.send_message(
                    f"⚡ {user.mention_html()} foi silenciado(a) por **2 minutos** por flood de mensagens/comandos/figurinhas!\n\n"
                    f"Ativação de segurança para os administradores:\n{mencoes_admins}",
                    parse_mode="HTML"
                )
                # O aviso do bot NUNCA é apagado automaticamente para manter o registro visível
            except Exception:
                pass
            return

        if tipo_acao == "remover":
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                aviso = await chat.send_message(
                    f"🚨 {user.mention_html()} foi removido(a)/banido(a) por enviar {motivo_violacao}.",
                    parse_mode="HTML"
                )
                asyncio.create_task(apagar_aviso_futuro_async(context, aviso))
            except Exception:
                pass

        elif tipo_acao == "silenciar":
            try:
                liberar_ate = timedelta(minutes=punicao["tempo_mute"])
                await context.bot.restrict_chat_member(chat.id, user.id, permissions=False, until_date=liberar_ate)
                aviso = await chat.send_message(
                    f"🔇 {user.mention_html()} foi silenciado(a) por **{punicao['tempo_mute']} minuto(s)** por enviar {motivo_violacao}.",
                    parse_mode="HTML"
                )
                asyncio.create_task(apagar_aviso_futuro_async(context, aviso))
            except Exception:
                pass

        else:
            if chave_aviso not in REGISTRO_AVISADOS:
                REGISTRO_AVISADOS[chave_aviso] = True
                aviso = await chat.send_message(
                    f"⚠️ {user.mention_html()}, proibido enviar {motivo_violacao} aqui!",
                    parse_mode="HTML"
                )
                asyncio.create_task(apagar_aviso_futuro_async(context, aviso))
            else:
                try:
                    await context.bot.ban_chat_member(chat.id, user.id)
                    aviso = await chat.send_message(
                        f"🚨 {user.mention_html()} foi removido(a)/banido(a) por insistir em enviar {motivo_violacao}.",
                        parse_mode="HTML"
                    )
                    asyncio.create_task(apagar_aviso_futuro_async(context, aviso))
                except Exception:
                    pass

async def apagar_aviso_futuro_async(context, mensagem):
    await asyncio.sleep(8)
    try:
        await mensagem.delete()
    except Exception:
        pass

async def limpar_dados_grupo_removido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    
    chat = update.effective_chat
    novo_status = result.new_chat_member.status
    
    if novo_status in ["left", "kicked"]:
        try:
            db = get_db()
            db["configs_protecao"].delete_one({"chat_id": chat.id})
            db["mensagens_usuarios"].delete_many({"chat_id": chat.id})
            db["grupos_autorizados"].delete_one({"chat_id": chat.id})
            db["avisos_grupos_piratas"].delete_one({"chat_id": chat.id})
        except Exception:
            pass

def registrar_protecoes(app):
    app.add_handler(CommandHandler("protecao", cmd_protecao))
    app.add_handler(MessageHandler(~filters.StatusUpdate.ALL, monitorar_seguranca), group=1)
    app.add_handler(ChatMemberHandler(limpar_dados_grupo_removido, ChatMemberHandler.MY_CHAT_MEMBER))
