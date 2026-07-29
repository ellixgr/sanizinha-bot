import re
import asyncio
from datetime import timedelta

async def executar_antilink(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
    if await is_admin(update, context, user.id, chat.id):
        return False

    texto = message.text or message.caption or ""
    chat_username = (chat.username or "").lower()

    padrao_link = r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+|chat\.whatsapp\.com/\S+|[a-zA-Z0-9][-a-zA-Z0-9]*\.(com|net|org|br|io|gov|edu|me|xyz|ru|tk|ml|ga|cf|gq|gg|to|cc|co)\b\S*)"
    links_encontrados = re.findall(padrao_link, texto, re.IGNORECASE)
    
    tem_link = False
    if message.entities:
        for entidade in message.entities:
            if entidade.type in ["url", "text_link"]:
                if entidade.type == "text_link" and entidade.url and chat_username in entidade.url.lower():
                    continue
                tem_link = True
                break

    if links_encontrados:
        for l in links_encontrados:
            url_str = "".join(l) if isinstance(l, tuple) else l
            if chat_username and chat_username in url_str.lower():
                continue
            tem_link = True
            break

    if not tem_link:
        return False

    # Ação punitiva e avisos
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
            aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por enviar link proibido.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    elif tipo_acao == "silenciar":
        try:
            liberar_ate = timedelta(minutes=punicao["tempo_mute"])
            await context.bot.restrict_chat_member(chat.id, user.id, permissions=False, until_date=liberar_ate)
            aviso = await chat.send_message(f"🔇 {user.mention_html()} foi silenciado(a) por {punicao['tempo_mute']} min por enviar link.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    else:
        avisos = reg.get("avisos", 0) + 1
        if avisos >= 2:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por insistir em enviar links.", parse_mode="HTML")
                col.delete_one(chave)
                asyncio.create_task(apagar_aviso_futuro(context, aviso))
            except Exception:
                pass
        else:
            col.update_one(chave, {"$set": {"avisos": avisos}}, upsert=True)
            aviso = await chat.send_message(f"⚠️ {user.mention_html()}, proibido enviar links aqui! (1/2)", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
    return True
