import re
import asyncio
from datetime import timedelta, datetime

async def executar_antilink(update, context, chat, user, message, get_db, is_admin, obter_punicao, salvar_punicao, apagar_aviso_futuro):
    # ✅ 1. VERIFICA SE A PROTEÇÃO ESTÁ ATIVA NO BANCO
    try:
        db = get_db()
        cfg = db["configuracoes_grupo"].find_one({"chat_id": chat.id}) or {}
        if not cfg.get("antilink", True):  # Se desativado → ignora
            return False
    except Exception as e:
        return False

    # ✅ 2. VERIFICA SE É ADMIN (argumentos CORRETOS)
    if await is_admin(update, context):
        return False

    texto = message.text or message.caption or ""
    chat_username = (chat.username or "").lower()

    # ✅ 3. DETECTA LINKS — MELHORADO
    padrao_link = r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+|chat\.whatsapp\.com/\S+|[a-zA-Z0-9][-a-zA-Z0-9]*\.(com|net|org|br|io|gov|edu|me|xyz|ru|tk|ml|ga|cf|gq|gg|to|cc|co)\b\S*)"
    links_encontrados = re.findall(padrao_link, texto, re.IGNORECASE)
    
    tem_link = False

    # ✅ 4. VERIFICA ENTIDADES (links embutidos / botões)
    if message.entities:
        for entidade in message.entities:
            if entidade.type in ["url", "text_link"]:
                # Permite link do próprio grupo/canal
                if entidade.type == "text_link" and entidade.url and chat_username in entidade.url.lower():
                    continue
                tem_link = True
                break

    # ✅ 5. VERIFICA LINKS NO TEXTO — CORRIGIDO (sem tupla quebrada)
    if links_encontrados and not tem_link:
        for l in links_encontrados:
            # Regex pode retornar tupla com grupos → pega o primeiro match
            url_str = l[0] if isinstance(l, tuple) else l
            if chat_username and chat_username in url_str.lower():
                continue
            tem_link = True
            break

    if not tem_link:
        return False

    # ✅ 6. PEGA PUNIÇÃO DO BANCO (com get_db!)
    punicao = obter_punicao(chat.id, get_db)

    # ✅ 7. APAGA A MENSAGEM
    if punicao.get("apagar_msg", True):
        try:
            await message.delete()
        except Exception:
            pass

    # ✅ 8. PEGA OU CRIA REGISTRO DE AVISOS
    col = db["avisos_usuarios"]
    chave = {"chat_id": chat.id, "user_id": user.id}
    reg = col.find_one(chave) or {"avisos": 0}
    
    tipo_acao = punicao.get("acao", "aviso_ban")
    tempo_mute = punicao.get("tempo_mute", 5)

    # ✅ 9. EXECUTA PUNIÇÃO
    if tipo_acao == "remover":
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            aviso = await chat.send_message(
                f"🚨 {user.mention_html()} foi BANIDO por enviar link proibido!",
                parse_mode="HTML"
            )
            asyncio.create_task(apagar_aviso_futuro(context, aviso))
        except Exception:
            pass

    elif tipo_acao == "silenciar":
        try:
            # ✅ CORRIGIDO: Permissões corretas para silenciar
            from telegram import ChatPermissions
            sem_permissoes = ChatPermissions()  # Nada permitido
            ate = datetime.now() + timedelta(minutes=tempo_mute)
            await context.bot.restrict_chat_member(
                chat.id, 
                user.id, 
                permissions=sem_permissoes, 
                until_date=ate
            )
            aviso = await chat.send_message(
                f"🔇 {user.mention_html()} SILENCIADO por {tempo_mute} min por enviar link!",
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
                    f"🚨 {user.mention_html()} BANIDO por insistir em enviar links!",
                    parse_mode="HTML"
                )
                col.delete_one(chave)
                asyncio.create_task(apagar_aviso_futuro(context, aviso))
            except Exception:
                pass
        else:
            col.update_one(chave, {"$set": {"avisos": avisos}}, upsert=True)
            aviso = await chat.send_message(
                f"⚠️ {user.mention_html()} PROIBIDO enviar links! ({avisos}/2)",
                parse_mode="HTML"
            )
            asyncio.create_task(apagar_aviso_futuro(context, aviso))

    return True
