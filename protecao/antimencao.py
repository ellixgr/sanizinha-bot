import re
import asyncio
from datetime import timedelta

async def executar_antimencao(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
    if await is_admin(update, context, user.id, chat.id):
        return False

    texto = message.text or message.caption or ""
    chat_username = (chat.username or "").lower()

    veio_encaminhado = bool(
        message.forward_date or 
        message.forward_from or 
        message.forward_from_chat or 
        message.forward_origin
    )

    padrao_mencao = r"(@[A-Za-z0-9_]{5,}|t\.me/[A-Za-z0-9_]+)"
    mencoes = re.findall(padrao_mencao, texto, re.IGNORECASE)
    
    mencao_externa = False
    if mencoes:
        for m in mencoes:
            if chat_username and chat_username in m.lower():
                continue
            mencao_externa = True
            break

    if not (veio_encaminhado or mencao_externa):
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
            aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por menção/encaminhamento externo.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    elif tipo_acao == "silenciar":
        try:
            liberar_ate = timedelta(minutes=punicao["tempo_mute"])
            await context.bot.restrict_chat_member(chat.id, user.id, permissions=False, until_date=liberar_ate)
            aviso = await chat.send_message(f"🔇 {user.mention_html()} foi silenciado(a) por menção externa.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    else:
        avisos = reg.get("avisos", 0) + 1
        if avisos >= 2:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por insistir em enviar menções/encaminhados.", parse_mode="HTML")
                col.delete_one(chave)
                asyncio.create_task(apagar_aviso_futuro(context, aviso))
            except Exception:
                pass
        else:
            col.update_one(chave, {"$set": {"avisos": avisos}}, upsert=True)
            aviso = await chat.send_message(f"⚠️ {user.mention_html()}, proibido menções ou mensagens encaminhadas aqui! (1/2)", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
    return True
