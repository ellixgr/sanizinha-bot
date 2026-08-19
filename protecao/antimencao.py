import re
import asyncio
from datetime import timedelta, datetime
from telegram import ChatPermissions

async def executar_antimencao(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
    # ✅ 1. VERIFICA SE A PROTEÇÃO ESTÁ ATIVA
    try:
        db = get_db()
        cfg = db["configuracoes_grupo"].find_one({"chat_id": chat.id}) or {}
        if not cfg.get("antimencao", True):
            return False
    except Exception:
        return False

    # ✅ 2. VERIFICA SE É ADMIN (argumentos CORRETOS)
    if await is_admin(update, context):
        return False

    texto = message.text or message.caption or ""
    chat_username = (chat.username or "").lower()
    
    bot_username = ""
    try:
        bot_username = (context.bot.username or "").lower()
    except Exception:
        pass

    # ✅ 3. VERIFICA ENCAMINHAMENTO
    veio_encaminhado = False
    try:
        if (getattr(message, "forward_date", None) or getattr(message, "forward_from", None) or 
            getattr(message, "forward_from_chat", None) or getattr(message, "forward_origin", None)):
            veio_encaminhado = True
    except Exception:
        pass

    # ✅ 4. DETECTA MENÇÕES VIA ENTIDADES
    tem_mencao_bot_externo = False
    entities = message.entities or message.caption_entities or []
    for ent in entities:
        if ent.type in ["mention", "text_link", "bot_command"]:
            mention_text = texto[ent.offset:ent.offset + ent.length].lower()
            
            # Ignora menção ao próprio grupo e ao nosso bot
            if chat_username and chat_username in mention_text:
                continue
            if bot_username and bot_username in mention_text:
                continue
            if ent.type == "bot_command" and bot_username and f"@{bot_username}" in mention_text:
                continue
                
            # Pune só se terminar com "bot"
            limpo_mention = mention_text.replace("@", "").strip()
            if limpo_mention.endswith("bot"):
                tem_mencao_bot_externo = True
                break

    # ✅ 5. DETECTA MENÇÕES VIA REGEX
    padrao_mencao = r"(@[A-Za-z0-9_]{5,}|t\.me/[A-Za-z0-9_]+)"
    mencoes_texto = re.findall(padrao_mencao, texto, re.IGNORECASE)
    
    mencao_externa_texto = False
    if mencoes_texto:
        for m in mencoes_texto:
            m_lower = m.lower()
            if chat_username and chat_username in m_lower:
                continue
            if bot_username and bot_username in m_lower:
                continue
            
            alvo_usuario = m_lower.split("/")[-1].replace("@", "")
            if alvo_usuario.endswith("bot"):
                mencao_externa_texto = True
                break

    if not (veio_encaminhado or tem_mencao_bot_externo or mencao_externa_texto):
        return False

    # ✅ 6. PEGA PUNIÇÃO DO BANCO (com get_db!)
    punicao = obter_punicao(chat.id, get_db)

    # ✅ 7. APAGA A MENSAGEM
    if punicao.get("apagar_msg", True):
        try:
            await message.delete()
        except Exception:
            pass

    db = get_db()
    col = db["avisos_usuarios"]
    chave = {"chat_id": chat.id, "user_id": user.id}
    reg = col.find_one(chave) or {"avisos": 0}
    
    tipo_acao = punicao.get("acao", "aviso_ban")
    tempo_mute = punicao.get("tempo_mute", 5)

    # ✅ 8. EXECUTA PUNIÇÃO CORRIGIDA
    if tipo_acao == "remover":
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            aviso = await chat.send_message(
                f"🚨 {user.mention_html()} foi BANIDO por mencionar bots externos ou encaminhar conteúdo!",
                parse_mode="HTML"
            )
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass

    elif tipo_acao == "silenciar":
        try:
            # ✅ CORRIGIDO: Usa ChatPermissions corretamente
            sem_permissoes = ChatPermissions()
            ate = datetime.now() + timedelta(minutes=tempo_mute)
            await context.bot.restrict_chat_member(
                chat.id, 
                user.id, 
                permissions=sem_permissoes, 
                until_date=ate
            )
            aviso = await chat.send_message(
                f"🔇 {user.mention_html()} SILENCIADO por {tempo_mute} min por menção a bot externo!",
                parse_mode="HTML"
            )
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass

    else:  # aviso_ban
        avisos = reg.get("avisos", 0) + 1
        if avisos >= 2:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                aviso = await chat.send_message(
                    f"🚨 {user.mention_html()} BANIDO por insistir em mencionar bots externos!",
                    parse_mode="HTML"
                )
                col.delete_one(chave)
                asyncio.create_task(apagar_aviso_futuro(context, aviso))
            except Exception:
                pass
        else:
            col.update_one(chave, {"$set": {"avisos": avisos}}, upsert=True)
            aviso = await chat.send_message(
                f"⚠️ {user.mention_html()} PROIBIDO menções a bots externos aqui! ({avisos}/2)",
                parse_mode="HTML"
            )
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
    return True
