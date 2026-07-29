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

    # IGNORA DONO E ADMINISTRADORES
    if await is_admin(update, context):
        return False

    agora = time.time()
    chave = (chat.id, user.id)

    # VERIFICA SE O USUÁRIO JÁ ESTÁ BLOQUEADO
    if chave in BLOQUEADOS:
        if agora < BLOQUEADOS[chave]:
            try: await message.delete()
            except: pass
            return True
        else:
            del BLOQUEADOS[chave]
            if chave in REGISTRO_FLOOD:
                del REGISTRO_FLOOD[chave]

    # Cria o registro se não existir
    if chave not in REGISTRO_FLOOD:
        REGISTRO_FLOOD[chave] = []

    # Limpa registros mais antigos que 2 segundos
    REGISTRO_FLOOD[chave] = [t for t in REGISTRO_FLOOD[chave] if agora - t < 2]
    REGISTRO_FLOOD[chave].append(agora)

    # SE TIVER 2 OU MAIS COMANDOS EM MENOS DE 2 SEGUNDOS → APLICA PUNIÇÃO
    if len(REGISTRO_FLOOD[chave]) >= 2:
        try: await message.delete()
        except: pass

        # Define bloqueio por 1 minuto
        TEMPO_BLOQUEIO_MIN = 1
        BLOQUEIO_ATE = agora + (TEMPO_BLOQUEIO_MIN * 60)
        BLOQUEADOS[chave] = BLOQUEIO_ATE

        try:
            data_liberacao = datetime.now(timezone.utc) + timedelta(minutes=TEMPO_BLOQUEIO_MIN)
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                permissions=ChatPermissions(),
                until_date=data_liberacao
            )

            # ✅ NOVO AVISO NO CHAT COMO VOCÊ PEDIU
            aviso = await context.bot.send_message(
                chat_id=chat.id,
                text=f"⚠️ {user.mention_html()} estava flodando o chat e foi silenciado por {TEMPO_BLOQUEIO_MIN} minuto(s)!",
                parse_mode="HTML"
            )
            # Apaga o aviso depois de 30s para não sujar o chat
            asyncio.create_task(_apagar_aviso(context, aviso))

        except Exception as e:
            print(f"[ERRO ANTIFLOD] Não foi possível aplicar punição: {e}")

        REGISTRO_FLOOD[chave] = []
        return True

    return False

async def _apagar_aviso(context, msg):
    await asyncio.sleep(30)
    try: await msg.delete()
    except: pass
