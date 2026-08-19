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

    # ✅ 1. VERIFICA SE A PROTEÇÃO ESTÁ ATIVA
    try:
        db = get_db()
        cfg = db["configuracoes_grupo"].find_one({"chat_id": chat.id}) or {}
        if not cfg.get("antiflod", True):  # Se desativado → ignora
            return False
    except Exception:
        return False

    # ✅ 2. IGNORA DONO E ADMINISTRADORES
    if await is_admin(update, context):
        return False

    agora = time.time()
    chave = (chat.id, user.id)

    # ✅ 3. VERIFICA SE O USUÁRIO JÁ ESTÁ BLOQUEADO
    if chave in BLOQUEADOS:
        if agora < BLOQUEADOS[chave]:
            try: 
                await message.delete()
            except: 
                pass
            return True
        else:
            del BLOQUEADOS[chave]
            if chave in REGISTRO_FLOOD:
                del REGISTRO_FLOOD[chave]

    # ✅ 4. PEGA CONFIGURAÇÃO DE PUNIÇÃO DO BANCO
    punicao = obter_punicao(chat.id, get_db)
    tempo_mute = punicao.get("tempo_mute", 1)  # Padrão 1 min

    # ✅ 5. CRIA O REGISTRO SE NÃO EXISTIR
    if chave not in REGISTRO_FLOOD:
        REGISTRO_FLOOD[chave] = []

    # ✅ 6. LIMPA REGISTROS MAIS ANTIGOS QUE 2 SEGUNDOS
    REGISTRO_FLOOD[chave] = [t for t in REGISTRO_FLOOD[chave] if agora - t < 2]
    REGISTRO_FLOOD[chave].append(agora)

    # ✅ 7. SE TIVER 2 OU MAIS MENSAGENS EM MENOS DE 2 SEGUNDOS → APLICA PUNIÇÃO
    if len(REGISTRO_FLOOD[chave]) >= 2:
        # Apaga a mensagem que causou o flood
        if punicao.get("apagar_msg", True):
            try: 
                await message.delete()
            except: 
                pass

        # ✅ Tempo de silêncio vindo do BANCO, não mais fixo!
        TEMPO_BLOQUEIO_MIN = tempo_mute
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

            # ✅ AVISO NO CHAT
            aviso = await context.bot.send_message(
                chat_id=chat.id,
                text=f"⚠️ {user.mention_html()} estava flodando o chat e foi silenciado por {TEMPO_BLOQUEIO_MIN} minuto(s)!",
                parse_mode="HTML"
            )
            # Apaga o aviso depois de 30s
            asyncio.create_task(_apagar_aviso(context, aviso))

        except Exception as e:
            print(f"[ERRO ANTIFLOD] Não foi possível aplicar punição: {e}")

        REGISTRO_FLOOD[chave] = []
        return True

    return False

async def _apagar_aviso(context, msg):
    await asyncio.sleep(30)
    try: 
        await msg.delete()
    except: 
        pass
