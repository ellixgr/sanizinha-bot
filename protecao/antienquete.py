import re
import asyncio
from datetime import timedelta

async def executar_antienquete(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
    if await is_admin(update, context, user.id, chat.id):
        return False

    if not message.poll:
        return False

    poll = message.poll
    # Extrai a pergunta e todas as opções da enquete para varredura de links
    texto_analise = poll.question or ""
    if poll.options:
        for opt in poll.options:
            texto_analise += " " + (opt.text or "")

    # Regex para detectar links web, t.me ou tentativas de ocultar URLs
    padrao_link = r"(https?://|www\.|t\.me/|[a-zA-Z0-9-]+\.(com|br|net|org|gg|me|xyz|site|online))"
    tem_link_oculto = bool(re.search(padrao_link, texto_analise, re.IGNORECASE))

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
    motivo_txt = "enviar enquetes com links" if tem_link_oculto else "enviar enquetes"

    if tipo_acao == "remover":
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por {motivo_txt}.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    elif tipo_acao == "silenciar":
        try:
            liberar_ate = timedelta(minutes=punicao["tempo_mute"])
            await context.bot.restrict_chat_member(chat.id, user.id, permissions=False, until_date=liberar_ate)
            aviso = await chat.send_message(f"🔇 {user.mention_html()} foi silenciado(a) por {motivo_txt}.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    else:
        avisos = reg.get("avisos", 0) + 1
        if avisos >= 2:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por insistir em {motivo_txt}.", parse_mode="HTML")
                col.delete_one(chave)
                asyncio.create_task(apagar_aviso_futuro(context, aviso))
            except Exception:
                pass
        else:
            col.update_one(chave, {"$set": {"avisos": avisos}}, upsert=True)
            aviso = await chat.send_message(f"⚠️ {user.mention_html()}, o envio de enquetes não é permitido neste grupo! (1/2)", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
    return True
