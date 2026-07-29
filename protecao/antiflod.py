import time
import asyncio
from datetime import datetime, timezone, timedelta
from telegram import ChatPermissions

# Armazena os horários dos comandos e o tempo de bloqueio por usuário
REGISTRO_FLOOD = {}
BLOQUEADOS = {}

async def executar_antiflod(update, context, chat, user, message, get_db, is_admin, obter_punicao, obter_mencao_admins):
    global REGISTRO_FLOOD, BLOQUEADOS

    if not chat or not user or chat.type == "private":
        return False

    # IGNORA DONO E ADMINISTRADORES (como combinado)
    if await is_admin(update, context):
        return False

    agora = time.time()
    chave = (chat.id, user.id)

    # VERIFICA SE O USUÁRIO ESTÁ BLOQUEADO NO MOMENTO
    if chave in BLOQUEADOS:
        if agora < BLOQUEADOS[chave]:
            # Apaga a mensagem do usuário e não deixa o comando rodar
            try: await message.delete()
            except: pass
            return True
        else:
            # Libera o usuário depois do tempo
            del BLOQUEADOS[chave]
            if chave in REGISTRO_FLOOD:
                del REGISTRO_FLOOD[chave]

    # Cria o registro se não existir
    if chave not in REGISTRO_FLOOD:
        REGISTRO_FLOOD[chave] = []

    # Limpa registros mais antigos que 2 segundos
    REGISTRO_FLOOD[chave] = [t for t in REGISTRO_FLOOD[chave] if agora - t < 2]
    # Adiciona o horário atual
    REGISTRO_FLOOD[chave].append(agora)

    # SE TIVER 2 OU MAIS COMANDOS EM MENOS DE 2 SEGUNDOS → APLICA PUNIÇÃO
    if len(REGISTRO_FLOOD[chave]) >= 2:
        # Apaga as mensagens rápidas
        try: await message.delete()
        except: pass

        # Define o bloqueio por 1 minuto
        BLOQUEIO_ATE = agora + 60
        BLOQUEADOS[chave] = BLOQUEIO_ATE

        try:
            # Revoga todas as permissões de envio por 1 minuto
            data_liberacao = datetime.now(timezone.utc) + timedelta(minutes=1)
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                permissions=ChatPermissions(),
                until_date=data_liberacao
            )

            # Envia aviso
            aviso = await message.reply_text(
                f"⚠️ {user.mention_html()}, você está bloqueado de usar os comandos por 1 minuto por floodar o bot.",
                parse_mode="HTML"
            )
            # Apaga o aviso depois de 30s
            asyncio.create_task(_apagar_aviso(context, aviso))

        except Exception as e:
            print(f"[ERRO ANTIFLOD] Não foi possível silenciar: {e}")

        # Limpa o registro e BLOQUEIA o processamento do comando
        REGISTRO_FLOOD[chave] = []
        return True

    return False

async def _apagar_aviso(context, msg):
    await asyncio.sleep(30)
    try: await msg.delete()
    except: pass
