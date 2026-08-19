import asyncio
from datetime import timedelta, datetime
from telegram import ChatPermissions

async def executar_antiencaminhar(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
    # ✅ 1. VERIFICA SE A PROTEÇÃO ESTÁ ATIVA
    try:
        db = get_db()
        cfg = db["configuracoes_grupo"].find_one({"chat_id": chat.id}) or {}
        if not cfg.get("antiencaminhar", True):
            return False
    except Exception:
        return False

    # ✅ 2. VERIFICA SE É ADMIN (argumentos CORRETOS)
    if await is_admin(update, context):
        return False

    # ✅ 3. DETECTA ENCAMINHAMENTO
    veio_encaminhado = False
    try:
        if (getattr(message, "forward_date", None) or getattr(message, "forward_from", None) or 
            getattr(message, "forward_from_chat", None) or getattr(message, "forward_origin", None)):
            veio_encaminhado = True
    except Exception:
        pass

    if not veio_encaminhado:
        return False

    # ✅ 4. PEGA PUNIÇÃO DO BANCO (com get_db!)
    punicao = obter_punicao(chat.id, get_db)

    # ✅ 5. APAGA A MENSAGEM
    if punicao.get("apagar_msg", True):
        try:
            await message.delete()
        except Exception:
            pass

    col = db["avisos_usuarios"]
    chave = {"chat_id": chat.id, "user_id": user.id}
    reg = col.find_one(chave) or {"avisos": 0}
    
    tipo_acao = punicao.get("acao", "aviso_ban")
    tempo_mute = punicao.get("tempo_mute", 5)

    # ✅ 6. EXECUTA PUNIÇÃO CORRIGIDA
    if tipo_acao == "remover":
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            aviso = await chat.send_message(
                f"🚨 {user.mention_html()} foi BANIDO por encaminhar conteúdos de outros chats!",
                parse_mode="HTML"
            )
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass

    elif tipo_acao == "silenciar":
        try:
            # ✅ CORRIGIDO: ChatPermissions + datetime válido
            sem_permissoes = ChatPermissions()
            ate = datetime.now() + timedelta(minutes=tempo_mute)
            await context.bot.restrict_chat_member(
                chat.id, 
                user.id, 
                permissions=sem_permissoes, 
                until_date=ate
            )
            aviso = await chat.send_message(
                f"🔇 {user.mention_html()} SILENCIADO por {tempo_mute} min por encaminhar conteúdo!",
                parse_mode="HTML"
            )
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass

    else:  # aviso_ban
        avisos_atual = reg.get("avisos", 0) + 1
        if avisos_atual >= 2:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                aviso = await chat.send_message(
                    f"🚨 {user.mention_html()} BANIDO por insistir em encaminhar mensagens!",
                    parse_mode="HTML"
                )
                col.delete_one(chave)
                asyncio.create_task(apagar_aviso_futuro(context, aviso))
            except Exception:
                pass
        else:
            col.update_one(chave, {"$set": {"avisos": avisos_atual}}, upsert=True)
            aviso = await chat.send_message(
                f"⚠️ {user.mention_html()} PROIBIDO encaminhar conteúdos de outros grupos ou canais aqui! ({avisos_atual}/2)",
                parse_mode="HTML"
            )
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
    return True
