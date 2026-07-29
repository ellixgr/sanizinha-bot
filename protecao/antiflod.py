import time
import asyncio
from datetime import timedelta

REGISTRO_FLOOD_AVANCADO = {}

async def executar_antiflod(update, context, chat, user, message, get_db, is_admin, obter_punicao, obter_mencao_admins):
    if not chat or not user or chat.type == "private":
        return False

    # Admins passam livremente
    if await is_admin(update, context, user.id, chat.id):
        return False

    agora = time.time()
    chave_flood = (chat.id, user.id)
    
    if chave_flood not in REGISTRO_FLOOD_AVANCADO:
        REGISTRO_FLOOD_AVANCADO[chave_flood] = []

    # Limpa registros antigos com mais de 3 segundos
    REGISTRO_FLOOD_AVANCADO[chave_flood] = [t for t in REGISTRO_FLOOD_AVANCADO[chave_flood] if agora - t < 3]
    REGISTRO_FLOOD_AVANCADO[chave_flood].append(agora)

    # Dispara se mandar 2 mensagens/comandos em sequência rápida (ex: segundo 1 e segundo 2)
    if len(REGISTRO_FLOOD_AVANCADO[chave_flood]) < 2:
        return False

    # Reseta o registro para evitar loop
    REGISTRO_FLOOD_AVANCADO[chave_flood] = []

    # Apaga a mensagem atual se possível
    try:
        await message.delete()
    except Exception:
        pass

    try:
        # Silencia por 1 minuto (60 segundos)
        liberar_ate = timedelta(minutes=1)
        await context.bot.restrict_chat_member(
            chat.id, user.id, permissions=False, until_date=liberar_ate
        )
        
        # Responde marcando a mensagem do infeliz com o texto exato pedido
        aviso = await message.reply_text(
            f"⚠️ {user.mention_html()}, você está bloqueado de usar os comandos por 1 minuto por flodar o bot.",
            parse_mode="HTML"
        )
        asyncio.create_task(destruir_aviso_depois(context, aviso))

    except Exception as e:
        print(f"Erro ao aplicar punição de anti-flood: {e}")

    return True

async def destruir_aviso_depois(context, mensagem):
    await asyncio.sleep(30)
    try:
        await mensagem.delete()
    except Exception:
        pass
