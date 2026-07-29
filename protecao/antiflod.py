import time
import asyncio
from datetime import timedelta

REGISTRO_FLOOD = {}

async def executar_antiflod(update, context, chat, user, message, get_db, is_admin, obter_punicao, obter_menção_admins):
    if await is_admin(update, context, user.id, chat.id):
        return False

    agora = time.time()
    chave_flood = (chat.id, user.id)
    
    if chave_flood not in REGISTRO_FLOOD:
        REGISTRO_FLOOD[chave_flood] = []
    
    # Mantém apenas as mensagens enviadas nos últimos 5 segundos
    REGISTRO_FLOOD[chave_flood] = [t for t in REGISTRO_FLOOD[chave_flood] if agora - t < 5]
    REGISTRO_FLOOD[chave_flood].append(agora)

    # Dispara o flood se enviar mais de 3 mensagens em menos de 5 segundos
    if len(REGISTRO_FLOOD[chave_flood]) < 3:
        return False

    # Limpa o registro para evitar loops de avisos contínuos
    REGISTRO_FLOOD[chave_flood] = []

    punicao = obter_punicao(chat.id)
    if punicao.get("apagar_msg", True):
        try:
            await message.delete()
        except Exception:
            pass

    try:
        liberar_ate = timedelta(minutes=2)
        await context.bot.restrict_chat_member(chat.id, user.id, permissions=False, until_date=liberar_ate)
        mencoes_admins = await obter_menção_admins(chat, context)
        await chat.send_message(
            f"⚡ {user.mention_html()} foi silenciado(a) por **2 minutos** por flood!\n\n"
            f"Notificação para os administradores:\n{mencoes_admins}",
            parse_mode="HTML"
        )
    except Exception:
        pass
    return True
