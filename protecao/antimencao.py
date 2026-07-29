import re
import asyncio
from datetime import timedelta

async def executar_antimencao(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
    if await is_admin(update, context, user.id, chat.id):
        return False

    texto = message.text or message.caption or ""
    chat_username = (chat.username or "").lower()
    
    bot_username = ""
    try:
        bot_username = (context.bot.username or "").lower()
    except Exception:
        pass

    # Verificação segura de encaminhamento
    veio_encaminhado = False
    try:
        if getattr(message, "forward_date", None) or getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None) or getattr(message, "forward_origin", None):
            veio_encaminhado = True
    except Exception:
        pass

    # Coleta menções via Entidades do Telegram (ex: menções diretas de usuários/bots na mensagem)
    tem_mencao_bot_externo = False
    entities = message.entities or message.caption_entities or []
    for ent in entities:
        if ent.type in ["mention", "text_link", "bot_command"]:
            mention_text = texto[ent.offset:ent.offset + ent.length].lower()
            
            # Se for menção ao próprio grupo ou ao nosso bot, ignora totalmente
            if chat_username and chat_username in mention_text:
                continue
            if bot_username and bot_username in mention_text:
                continue
            if ent.type == "bot_command" and bot_username and f"@{bot_username}" in mention_text:
                continue
                
            # Regra principal solicitada: Só pune se terminar com "bot" (indicando que é um bot externo/desconhecido)
            # Menções a pessoas reais como @joao não terminam em "bot", logo passam direto e livremente.
            limpo_mention = mention_text.replace("@", "").strip()
            if limpo_mention.endswith("bot"):
                tem_mencao_bot_externo = True
                break

    # Varredura por Regex de arrobas e links t.me no texto livre
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
            
            # Verifica se o arroba mencionado termina com "bot" (ex: @salalalbot)
            # Usuários normais (como @joao) não terminam com "bot", então não acionam punição.
            alvo_usuario = m_lower.split("/")[-1].replace("@", "")
            if alvo_usuario.endswith("bot"):
                mencao_externa_texto = True
                break

    if not (veio_encaminhado or tem_mencao_bot_externo or mencao_externa_texto):
        return False

    punicao = obter_punicao(chat.id)
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

    if tipo_acao == "remover":
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por mencionar bots externos que não estão no grupo ou encaminhar conteúdos.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    elif tipo_acao == "silenciar":
        try:
            liberar_ate = timedelta(minutes=punicao["tempo_mute"])
            await context.bot.restrict_chat_member(chat.id, user.id, permissions=False, until_date=liberar_ate)
            aviso = await chat.send_message(f"🔇 {user.mention_html()} foi silenciado(a) por menção a bot externo.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    else:
        avisos = reg.get("avisos", 0) + 1
        if avisos >= 2:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por insistir em mencionar bots externos.", parse_mode="HTML")
                col.delete_one(chave)
                asyncio.create_task(apagar_aviso_futuro(context, aviso))
            except Exception:
                pass
        else:
            col.update_one(chave, {"$set": {"avisos": avisos}}, upsert=True)
            aviso = await chat.send_message(f"⚠️ {user.mention_html()}, proibido menções a bots externos aqui! (1/2)", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
    return True
