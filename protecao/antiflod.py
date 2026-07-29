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

    # Limpa registros antigos com mais de 5 segundos
    REGISTRO_FLOOD_AVANCADO[chave_flood] = [t for t in REGISTRO_FLOOD_AVANCADO[chave_flood] if agora - t < 5]
    REGISTRO_FLOOD_AVANCADO[chave_flood].append(agora)

    # Dispara se ultrapassar 4 mensagens/mídias/comandos em menos de 5 segundos
    if len(REGISTRO_FLOOD_AVANCADO[chave_flood]) < 4:
        return False

    # Reseta o registro para evitar loop
    REGISTRO_FLOOD_AVANCADO[chave_flood] = []

    # Busca a punição configurada nas preferências do grupo
    punicao = obter_punicao(chat.id)
    tipo_acao = punicao.get("acao", "silenciar") # Padrão silenciar se não configurado
    tempo_mute = punicao.get("tempo_mute", 2)   # Minutos configurados no painel

    # Apaga a mensagem se configurado
    if punicao.get("apagar_msg", True):
        try:
            await message.delete()
        except Exception:
            pass

    mencoes_admins = await obter_mencao_admins(chat, context)

    try:
        if tipo_acao == "remover":
            await context.bot.ban_chat_member(chat.id, user.id)
            aviso = await chat.send_message(
                f"⚡ **ANTI-FLOOD ACIONADO**\n\n"
                f"👤 Usuário: {user.mention_html()}\n"
                f"🛑 Punição: **Banido(a)** por envio excessivo de mensagens/flood.\n\n"
                f"🔔 Admins: {mencoes_admins}",
                parse_mode="HTML"
            )
            asyncio.create_task(destruir_aviso_depois(context, aviso))

        elif tipo_acao == "silenciar":
            liberar_ate = timedelta(minutes=tempo_mute)
            await context.bot.restrict_chat_member(
                chat.id, user.id, permissions=False, until_date=liberar_ate
            )
            aviso = await chat.send_message(
                f"⚡ **ANTI-FLOOD ACIONADO**\n\n"
                f"👤 Usuário: {user.mention_html()}\n"
                f"🛑 Punição: Silenciado(a) por **{tempo_mute} minuto(s)** devido a flood.\n\n"
                f"🔔 Admins: {mencoes_admins}",
                parse_mode="HTML"
            )
            asyncio.create_task(destruir_aviso_depois(context, aviso))
            
        else: # Ação padrão de aviso/mutar rápido
            liberar_ate = timedelta(minutes=2)
            await context.bot.restrict_chat_member(
                chat.id, user.id, permissions=False, until_date=liberar_ate
            )
            aviso = await chat.send_message(
                f"⚡ **ANTI-FLOOD ACIONADO**\n\n"
                f"👤 Usuário: {user.mention_html()}\n"
                f"🛑 Punição: Silenciado(a) por **2 minutos** (Flood detectado).\n\n"
                f"🔔 Admins: {mencoes_admins}",
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
