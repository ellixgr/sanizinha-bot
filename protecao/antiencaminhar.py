import asyncio
from datetime import timedelta

async def executar_antiencaminhar(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
    if await is_admin(update, context, user.id, chat.id):
        return False

    # Verificação totalmente segura de encaminhamento
    veio_encaminhado = False
    try:
        if getattr(message, "forward_date", None) or getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None) or getattr(message, "forward_origin", None):
            veio_encaminhado = True
    except Exception:
        pass

    if not veio_encaminhado:
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
            aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por encaminhar conteúdos de outros chats.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    elif tipo_acao == "silenciar":
        try:
            liberar_ate = timedelta(minutes=punicao["tempo_mute"])
            await context.bot.restrict_chat_member(chat.id, user.id, permissions=False, until_date=liberar_ate)
            aviso = await chat.send_message(f"🔇 {user.mention_html()} foi silenciado(a) por encaminhar conteúdos.", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass
    else:
        avisos_atual = reg.get("avisos", 0) + 1
        if avisos_atual >= 2:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                aviso = await chat.send_message(f"🚨 {user.mention_html()} foi banido(a) por insistir em encaminhar mensagens.", parse_mode="HTML")
                col.delete_one(chave)
                asyncio.create_task(apagar_aviso_futuro(context, aviso))
            except Exception:
                pass
        else:
            col.update_one(chave, {"$set": {"avisos": avisos_atual}}, upsert=True)
            aviso = await chat.send_message(f"⚠️ {user.mention_html()}, proibido encaminhar conteúdos de outros grupos ou canais aqui! (1/2)", parse_mode="HTML")
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
    return True
