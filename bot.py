import os
import logging
import threading
import time
import asyncio
from datetime import datetime, timezone, timedelta
from flask import Flask
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ChatMemberHandler, TypeHandler
)

from cmd import ler_comandos_membros, ler_comandos_adm
from comandos.jogos.menujogos import menu_jogos_handler, processar_callback_jogos
from protecao.antiflod import executar_antiflod
from protecao.status import obter_punicao, obter_mencao_admins_str, verificar_todas_protecoes
from dono.addgrupo import cmd_addgrupo, processar_callback_addgrupo

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
DONO_ID = os.environ.get("DONO_ID", "0").strip()

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN ESTÁ VAZIO!")
else:
    logger.info(f"✅ Token carregado! Tamanho: {len(TELEGRAM_TOKEN)}")

FUSO_BR = timezone(timedelta(hours=-3))

app_web = Flask(__name__)
@app_web.route('/')
def home(): return "SanizinhaBot online!"
def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

_mongo_client = None
def get_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000, connectTimeoutMS=1000, maxPoolSize=50, tlsAllowInvalidCertificates=True)
    return _mongo_client["sanizinhabot_db"]

async def grupo_autorizado(chat_id: int) -> bool:
    try:
        db = get_db()
        agora = time.time()
        grupo = db["grupos_autorizados"].find_one({"chat_id": chat_id, "ativo": True, "expira_em": {"$gt": agora}})
        return bool(grupo)
    except Exception as e:
        logger.error(f"Erro verifica grupo: {e}")
        return False

async def verificar_assinante(usuario_id: int) -> bool:
    try:
        db = get_db()
        agora = time.time()
        grupo = db["grupos_autorizados"].find_one({"registrado_por": usuario_id, "ativo": True, "expira_em": {"$gt": agora}})
        return bool(grupo)
    except Exception as e:
        logger.error(f"Erro verifica assinante: {e}")
        return False

async def verificar_se_e_adm(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id_verificar=None) -> bool:
    uid = update.effective_user.id
    chat = update.effective_chat
    if DONO_ID and str(uid) == str(DONO_ID): return True
    chat_alvo_id = chat_id_verificar if chat_id_verificar else chat.id
    if chat_alvo_id < 0:
        try: return (await context.bot.get_chat_member(chat_alvo_id, uid)).status in ["administrator","creator"]
        except: pass
    return False

# ✅ INTERCEPTADOR DE PROTEÇÕES — RODA ANTES DE TUDO
async def interceptador_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat:
        return

    user = update.effective_user
    chat = update.effective_chat
    message = update.message

    # ✅ DONO NÃO É BLOQUEADO
    if DONO_ID and str(user.id) == str(DONO_ID):
        return

    # ✅ EXECUTA TODAS AS PROTEÇÕES
    bloqueado = await verificar_todas_protecoes(
        update, context, chat, user, message,
        get_db, verificar_se_e_adm
    )
    if bloqueado:
        from telegram.ext import ApplicationHandlerStop
        raise ApplicationHandlerStop

async def bot_adicionado_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ["group","supergroup"]:
        return
    if DONO_ID and str(user.id) == str(DONO_ID):
        return
    if await grupo_autorizado(chat.id):
        return
    aviso = (
        "⚠️ **USO NÃO AUTORIZADO**\n\n"
        "Para usar este bot em seu grupo, é necessário contratar o plano de aluguel mensal.\n\n"
        "Clique no botão abaixo para contratar:"
    )
    botoes = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Contratar Plano", url=f"https://t.me/{context.bot.username}?start=aluguel")]
    ])
    await update.message.reply_text(aviso, reply_markup=botoes, parse_mode="Markdown")
    await context.bot.leave_chat(chat.id)

async def menu_membros_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = ler_comandos_membros()
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]])
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def menu_adm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = ler_comandos_adm()
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]])
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    query = update.callback_query

    if chat.type in ["group", "supergroup"]:
        if DONO_ID and str(user.id) == str(DONO_ID):
            pass
        elif not await grupo_autorizado(chat.id):
            aviso = (
                "⚠️ **USO NÃO AUTORIZADO**\n\n"
                "Este grupo não está cadastrado.\n"
                "Contrate o bot para poder usá-lo."
            )
            botoes = InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Alugar Bot", url=f"https://t.me/{context.bot.username}?start=aluguel")]
            ])
            if query:
                await query.message.edit_text(aviso, reply_markup=botoes, parse_mode="Markdown")
            else:
                await update.message.reply_text(aviso, reply_markup=botoes, parse_mode="Markdown")
            return

    if chat.type == "private":
        texto = (
            "👋 Olá! Bem-vindo ao Bot!\n\n"
            "Escolha uma opção abaixo:"
        )
        botoes = [
            [InlineKeyboardButton("🤖 Alugar Bot", callback_data="menu_aluguel")],
            [InlineKeyboardButton("📜 Ver Comandos", callback_data="ver_comandos")]
        ]
        if await verificar_assinante(user.id):
            botoes.insert(2, [InlineKeyboardButton("⚙️ Configurar Grupos", callback_data="menu_config_grupos")])
        botoes = InlineKeyboardMarkup(botoes)
    else:
        agora = datetime.now(FUSO_BR)
        hora = agora.strftime("%H:%M:%S")
        data = agora.strftime("%d/%m/%Y")
        texto = (
            "✪\\▁▁▁▁▁▁▁▁▁▁▁▁\\\n"
            f"✰┃👤 : {user.first_name}\n"
            f"✰┃🆔 : `{user.id}`\n"
            f"✰┃🕘 : {hora}\n"
            f"✰┃☀️ : {data}\n"
            "✰┃ 🤖 **BOT**\n✪/ 🌬️ **Sanizinha** ®\n\n┌──────────┐\n   ≡  **M E N U S**  ≡\n└──────────┘"
        )
        botoes = [
            [InlineKeyboardButton("📜 Comandos Membro", callback_data="menu_membros")],
            [InlineKeyboardButton("🛡️ Comandos ADM", callback_data="menu_adm")],
            [InlineKeyboardButton("🎮 Jogos", callback_data="menu_jogos_atalho")],
            [InlineKeyboardButton("🤖 Alugar Bot", callback_data="menu_aluguel")],
            [InlineKeyboardButton("➕ Adicionar ao seu Grupo", url=f"https://t.me/{context.bot.username}?startgroup=true")]
        ]
        if DONO_ID and str(user.id) == str(DONO_ID):
            botoes.insert(3, [InlineKeyboardButton("🛠️ Painel do Dono", callback_data="menu_dono")])
        botoes = InlineKeyboardMarkup(botoes)

    if query:
        await query.message.edit_text(texto, reply_markup=botoes, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=botoes, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    dados = query.data
    logger.info(f"📥 CLIQUE: {dados}")

    if dados in ["voltar_menu_principal", "voltar_menu"]:
        await query.answer()
        await start(update, context)
        return

    if dados == "menu_membros":
        await query.answer()
        await menu_membros_handler(update, context)
        return

    if dados == "menu_adm":
        await query.answer()
        await menu_adm_handler(update, context)
        return

    if dados == "ver_comandos":
        await query.answer()
        texto = ler_comandos_membros() + "\n" + ler_comandos_adm()
        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]])
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        return

    # ✅ ABRE PAINEL DE ALUGUEL
    if dados == "menu_aluguel":
        await query.answer()
        from comandos.aluguel import painel_aluguel
        await painel_aluguel(update, context)
        return

    # ✅ TRATA OS BOTÕES ➕ ➖ DO ALUGUEL
    if dados.startswith("aluguel_"):
        await query.answer()
        from comandos.aluguel import callback_aluguel_painel, gerar_pix_aluguel
        if dados == "aluguel_gerar_pix":
            await gerar_pix_aluguel(update, context)
        else:
            await callback_aluguel_painel(update, context)
        return

    # ✅ TRATA VERIFICAÇÃO DE PAGAMENTO
    if dados.startswith("checar_pagamento_"):
        await query.answer()
        from comandos.aluguel import verificar_status_pagamento
        await verificar_status_pagamento(update, context)
        return

    if dados.startswith("addgrupo_"):
        await processar_callback_addgrupo(update, context, get_db, FUSO_BR)
        return

    if dados == "menu_jogos_atalho":
        await query.answer()
        await menu_jogos_handler(update, context)
        return
    if dados == "jogo_xadrez":
        await query.answer("Abrindo Xadrez...")
        from comandos.jogos.xadrez import menu_xadrez_handler
        await menu_xadrez_handler(update, context)
        return
    if dados in ["jogo_velha","jogo_memoria","jogo_dama"]:
        await query.answer()
        await processar_callback_jogos(update, context)
        return

    logger.warning(f"⚠️ Botão não registrado: {dados}")
    await query.answer("❌ Função não encontrada!", show_alert=True)

def main():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    threading.Thread(target=run_web, daemon=True).start()

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # ✅ INTERCEPTADOR DE PROTEÇÕES — RODA PRIMEIRO
    application.add_handler(TypeHandler(Update, interceptador_protecoes), group=-1)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    from comandos.ping import registrar_ping
    from comandos.id import registrar_id
    from comandos.perfil import registrar_perfil
    from comandos.ban import registrar_ban
    from comandos.mutar import registrar_mutar
    from comandos.bemvindo import registrar_comandos_bv
    from comandos.promover import registrar_promover
    from comandos.marcar import registrar_marcar, capturar_membros_handler, remover_membro_saiu_handler
    from comandos.citar import registrar_citar
    from comandos.play import setup_play
    from comandos.deploy import registrar_deploy
    from comandos.rank import registrar_rank
    from comandos.figurinha import registrar_figurinha
    from comandos.aluguel import registrar_aluguel
    from comandos.jogos.velha import setup_velha
    from comandos.jogos.memoria import setup_memoria
    from comandos.jogos.dama import setup_dama
    from comandos.jogos.xadrez import setup_xadrez

    setup_velha(application); setup_memoria(application); setup_dama(application); setup_xadrez(application)
    registrar_figurinha(application); registrar_promover(application); registrar_rank(application); registrar_marcar(application)
    registrar_citar(application); registrar_comandos_bv(application)
    registrar_ping(application); registrar_id(application); registrar_perfil(application); registrar_ban(application)
    setup_play(application); registrar_mutar(application); registrar_deploy(application); registrar_aluguel(application)

    async def wrapper_addgrupo(update, context):
        await cmd_addgrupo(update, context, get_db, DONO_ID, FUSO_BR)
    application.add_handler(CommandHandler("addgrupo", wrapper_addgrupo))

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_adicionado_grupo), group=-2)

    logger.info("🤖 Bot iniciado com sucesso! ✅")

    import sys
    try:
        loop.run_until_complete(application.run_polling(drop_pending_updates=True))
    except Exception as e:
        logger.warning(f"⚠️ Falha: {e}")
        try:
            loop.run_until_complete(application.run_polling())
        except Exception as e2:
            logger.error(f"❌ Falha total: {e2}")
            sys.exit(1)

if __name__ == "__main__":
    main()
