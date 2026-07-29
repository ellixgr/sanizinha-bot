import time
import asyncio
from datetime import timedelta

# Dicionário robusto para rastrear o histórico de eventos por usuário no chat
REGISTRO_FLOOD_AVANCADO = {}

async def executar_antiflod(update, context, chat, user, message, get_db, is_admin, obter_punicao, obter_menção_admins):
    # Admins passam livremente
    if await is_admin(update, context, user.id, chat.id):
        return False

    agora = time.time()
    chave_flood = (chat.id, user.id)
    
    if chave_flood not in REGISTRO_FLOOD_AVANCADO:
        REGISTRO_FLOOD_AVANCADO[chave_flood] = []

    # Limpa registros antigos com mais de 5 segundos
    REGISTRO_FLOOD_AVANCADO[chave_flood] = [t for t in REGISTRO_FLOOD_AVANCADO[chave_flood] if agora - t < 5]
    
    # Adiciona o timestamp atual da nova mensagem ou comando enviado
    REGISTRO_FLOOD_AVANCADO[chave_flood].append(agora)

    # Limite rígido: se ultrapassar 4 mensagens/comandos em um intervalo menor que 5 segundos, ativa o flood
    LIMITE_MENSAGENS = 4
    if len(REGISTRO_FLOOD_AVANCADO[chave_flood]) < LIMITE_MENSAGENS:
        return False

    # Reseta imediatamente o registro do usuário para evitar loop infinito de punições
    REGISTRO_FLOOD_AVANCADO[chave_flood] = []

    # Busca as regras de punição configuradas no grupo
    punicao = obter_punicao(chat.id)
    
    # Tenta apagar a última mensagem que estourou o limite
    if punicao.get("apagar_msg", True):
        try:
            await message.delete()
        except Exception:
            pass

    # Aplica a sanção por Flood (Silenciamento automático por 2 minutos)
    try:
        liberar_ate = timedelta(minutes=2)
        await context.bot.restrict_chat_member(
            chat.id, 
            user.id, 
            permissions=False,  # Bloqueia envio de mensagens
            until_date=liberar_ate
        )
        
        mencoes_admins = await obter_menção_admins(chat, context)
        aviso = await chat.send_message(
            f"⚡ **ANTI-FLOOD ACIONADO**\n\n"
            f"👤 Usuário: {user.mention_html()}\n"
            f"🛑 Punição: Silenciado(a) por **2 minutos** devido ao envio excessivo de mensagens ou comandos em sequência.\n\n"
            f"🔔 Administradores: {mencoes_admins}",
            parse_mode="HTML"
        )
        
        # Opcional: Auto-destruição do aviso do bot após 30 segundos para limpar o chat
        asyncio.create_task(destruir_aviso_depois(aviso))

    except Exception as e:
        print(f"Erro ao aplicar punição de anti-flood: {e}")
        pass

    return True

async def destruir_aviso_depois(mensagem):
    await asyncio.sleep(30)
    try:
        await mensagem.delete()
    except Exception:
        pass
