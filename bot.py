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
    MessageHandler, ContextTypes, filters, TypeHandler, ApplicationHandlerStop
)

from cmd import ler_comandos_membros, ler_comandos_adm
from comandos.jogos.menujogos import menu_jogos_handler, processar_callback_jogos
from protecao.status import (
    obter_punicao, obter_mencao_admins_str, verificar_todas_protecoes,
    coletar_dados_status, cmd_stts, tratar_botoes_config
)
from dono.addgrupo import cmd_addgrupo, processar_callback_addgrupo
from comandos.configp import tratar_botoes_configp

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

# ✅ FLASK EM PORTA SEPARADA — NÃO TRAVA O BOT
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "SanizinhaBot online!"
def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port, use_reloader=False)

_mongo_client = None
def get_db():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            maxPoolSize=100,
            tlsAllowInvalidCertificates=True
        )
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
        licenca = db["licencas_aluguel"].find_one({"user_id": usuario_id, "ativo": True, "expira_em": {"$gt": agora}})
        return bool(licenca)
    except Exception as e:
        logger.error(f"Erro verifica assinante: {e}")
        return False

# ✅ CORRIGIDA — VERIFICA ADMIN CORRETAMENTE
async def verificar_se_e_adm(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id_verificar=None) -> bool:
    uid = update.effective_user.id
    chat = update.effective_chat
    
    # Dono do bot sempre é admin
    if DONO_ID and str(uid) == str(DONO_ID):
        return True
    
    chat_alvo_id = chat_id_verificar if chat_id_verificar else chat.id
    
    # Apenas grupos/canais têm admins
    if chat_alvo_id > 0:
        return False
    
    try:
        membro = await context.bot.get_chat_member(chat_alvo_id, uid)
        return membro.status in ["administrator", "creator"]
    except Exception as e:
        logger.debug(f"Erro verificar admin: {e}")
        return False

# ✅ CORRIGIDO — SÓ RODA SE GRUPO FOR AUTORIZADO
async def interceptador_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat:
        return

    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Ignora comandos
    texto = update.message.text or update.message.caption or ""
    if texto.startswith("/"):
        return
    
    # Ignora dono
    if DONO_ID and str(uid) == str(DONO_ID):
        return
    
    # Ignora privado
    chat = update.effective_chat
    if chat.type == "private":
        return
    
    # ✅ SÓ RODA PROTEÇÕES SE GRUPO FOR AUTORIZADO
    if not await grupo_autorizado(chat.id):
        return
    
    # Ignora fluxo do bem-vindo
    try:
        from comandos.bemvindo import ESTADOS_FLUXO
        if (chat_id, uid) in ESTADOS_FLUXO:
            return
    except:
        pass

    user = update.effective_user
    message = update.message
    is_admin = await verificar_se_e_adm(update, context)
    
    bloqueado = await verificar_todas_protecoes(
        update, context, chat, user, message,
        get_db, is_admin
    )
    if bloqueado:
        raise ApplicationHandlerStop

# ✅ CORRIGIDO — TRATA USER NONE
async def bot_adicionado_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    bot_entrou = any(m.id == context.bot.id for m in update.message.new_chat_members)
    if not bot_entrou:
        return

    chat = update.effective_chat
    user = update.effective_user
    if not user:
        user = update.message.from_user
    
    if not chat or chat.type not in ["group", "supergroup"]:
        return

    logger.info(f"🔔 BOT ADICIONADO | Grupo: {chat.title} | ID: {chat.id} | Por: {user.id if user else 'DESCONHECIDO'}")

    db = get_db()
    eh_dono = bool(user and DONO_ID and str(user.id) == str(DONO_ID))
    eh_assinante = await verificar_assinante(user.id) if user else False
    agora = datetime.now(FUSO_BR)
    timestamp_atual = time.time()

    dados_grupo = {
        "chat_id": chat.id,
        "nome": chat.title,
        "tipo": chat.type,
        "dono_adicionou_id": user.id if user else 0,
        "dono_adicionou_nome": user.first_name if user else "Desconhecido",
        "adicionado_em": agora,
        "ativo": False,
        "expira_em": 0
    }

    if eh_dono:
        dados_grupo["ativo"] = True
        dados_grupo["expira_em"] = 9999999999
        logger.info("👑 DONO — ATIVADO PERMANENTE")
        db["grupos_autorizados"].update_one({"chat_id": chat.id}, {"$set": dados_grupo}, upsert=True)
        return

    elif eh_assinante and user:
        licenca = db["licencas_aluguel"].find_one(
            {"user_id": user.id, "ativo": True, "expira_em": {"$gt": timestamp_atual}}
        )
        if licenca:
            dados_grupo["ativo"] = True
            dados_grupo["expira_em"] = licenca["expira_em"]
            logger.info("💳 ASSINANTE — ATIVADO")
            db["grupos_autorizados"].update_one({"chat_id": chat.id}, {"$set": dados_grupo}, upsert=True)
            return

    logger.info("👤 USUÁRIO COMUM — SALVO E SAI")
    db["grupos_autorizados"].update_one({"chat_id": chat.id}, {"$set": dados_grupo}, upsert=True)

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

async def menu_adm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await verificar_se_e_adm(update, context):
        await query.answer("⚠️ Apenas Administradores!", show_alert=True)
        return

    texto = ler_comandos_adm()
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👋 Mensagem de Bem-Vindo", callback_data="menu_bemvindo")],
        [InlineKeyboardButton("🛡️ Configurar Proteções", callback_data="menu_config_grupo")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]
    ])
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def menu_membros_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = ler_comandos_membros()
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Ver Perfil", callback_data="executar_perfil")],
        [InlineKeyboardButton("🎮 Jogos", callback_data="menu_jogos_atalho")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]
    ])
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def tratar_botoes_adm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dados = query.data

    if not await verificar_se_e_adm(update, context):
        await query.answer("⚠️ Apenas ADMs!", show_alert=True)
        return

    if dados == "menu_bemvindo":
        try:
            from comandos.bemvindo import menu_bemvindo_handler
            await menu_bemvindo_handler(update, context)
        except Exception as e:
            logger.error(f"Erro abrir bemvindo: {e}")
            await query.message.edit_text(f"⚠️ Módulo bemvindo não encontrado: {e}")
        return

    if dados == "menu_config_grupo":
        chat = update.effective_chat
        cfg = get_db()["configuracoes_grupo"].find_one({"chat_id": chat.id}) or {}
        antilink_status = "✅ Ativo" if cfg.get("antilink", True) else "❌ Desativado"
        antifigu_status = "✅ Ativo" if cfg.get("antifigu", True) else "❌ Desativado"
        antiimagem_status = "✅ Ativo" if cfg.get("antiimagem", True) else "❌ Desativado"
        antienquete_status = "✅ Ativo" if cfg.get("antienquete", True) else "❌ Desativado"
        antiencaminhar_status = "✅ Ativo" if cfg.get("antiencaminhar", True) else "❌ Desativado"
        antimencao_status = "✅ Ativo" if cfg.get("antimencao", True) else "❌ Desativado"
        antiflod_status = "✅ Ativo" if cfg.get("antiflod", True) else "❌ Desativado"
        acao = cfg.get("acao_padrao", "aviso_ban")
        acao_texto = {"aviso_ban": "⚠️ Aviso → Banir","remover": "🚫 Banir Direto","silenciar": "🔇 Silenciar"}.get(acao, acao)
        tempo_mute = cfg.get("tempo_mute_padrao", 5)

        texto = (
            "🛡️ **CONFIGURAÇÕES DO GRUPO**\n\n"
            f"🔗 Anti-Link: {antilink_status}\n"
            f"🖼️ Anti-Figurinha: {antifigu_status}\n"
            f"📷 Anti-Imagem: {antiimagem_status}\n"
            f"📊 Anti-Enquete: {antienquete_status}\n"
            f"➡️ Anti-Encaminhar: {antiencaminhar_status}\n"
            f"👤 Anti-Menção: {antimencao_status}\n"
            f"🔊 Anti-Flood: {antiflod_status}\n\n"
            f"⚖️ Punição: {acao_texto}\n⏱️ Tempo Mute: {tempo_mute}min"
        )
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Link", callback_data="toggle_antilink"), InlineKeyboardButton("🖼️ Figurinha", callback_data="toggle_antifigu")],
            [InlineKeyboardButton("📷 Imagem", callback_data="toggle_antiimagem"), InlineKeyboardButton("📊 Enquete", callback_data="toggle_antienquete")],
            [InlineKeyboardButton("➡️ Encaminhar", callback_data="toggle_antiencaminhar"), InlineKeyboardButton("👤 Menção", callback_data="toggle_antimencao")],
            [InlineKeyboardButton("🔊 Flood", callback_data="toggle_antiflod")],
            [InlineKeyboardButton("⚙️ Escolher Punição", callback_data="menu_punicao")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="menu_adm")]
        ])
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        return

    if dados.startswith("toggle_") or dados in ["menu_punicao", "definir_punicao_aviso_ban", "definir_punicao_remover", "definir_punicao_silenciar"]:
        await tratar_botoes_config(update, context, get_db, verificar_se_e_adm)
        return

# ✅ CORRIGIDO — VERIFICA GRUPO AUTORIZADO
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    query = update.callback_query

    if chat.type in ["group", "supergroup"]:
        if not await grupo_autorizado(chat.id):
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
        texto = "👋 Olá! Bem-vindo ao Bot!\n\nEscolha uma opção abaixo:"
        botoes = [
            [InlineKeyboardButton("🤖 Alugar Bot", callback_data="menu_aluguel")],
            [InlineKeyboardButton("📜 Ver Comandos", callback_data="ver_comandos")]
        ]
        eh_dono = (DONO_ID and str(user.id) == str(DONO_ID))
        if eh_dono or await verificar_assinante(user.id):
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

# ✅ CORRIGIDO — VERIFICA GRUPO ANTES DE TUDO
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    dados = query.data
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    logger.info(f"📥 CLIQUE: {dados}")

    # Verifica grupo autorizado antes de processar
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        if not await grupo_autorizado(chat.id):
            await query.answer("⚠️ Grupo não autorizado!", show_alert=True)
            return

    if dados.startswith("v_") or dados.startswith("vpos_") or \
       dados.startswith("xadrez_") or dados.startswith("mem_") or \
       dados.startswith("min_"):
        return

    if dados.startswith("bv_"):
        from comandos.bemvindo import tratar_botoes_bemvindo
        await tratar_botoes_bemvindo(update, context)
        return

    if dados == "menu_config_grupos":
        eh_dono = (DONO_ID and str(user_id) == str(DONO_ID))
        tem_licenca = await verificar_assinante(user_id)
        if eh_dono:
            await query.answer("Opa! Como você é o DONO, tem acesso total! ✅", show_alert=True)
        elif not tem_licenca:
            await query.answer("⚠️ Você precisa alugar o bot para usar essa função!", show_alert=True)
            return
        await tratar_botoes_configp(update, context)
        return

    if dados.startswith("config_grupo_") or dados.startswith("config_bemvindo_") or dados.startswith("config_protecao_") or dados.startswith("toggle_priv_") or dados.startswith("menu_punicao_priv_") or dados.startswith("def_pun_"):
        await tratar_botoes_configp(update, context)
        return

    if dados == "menu_adm":
        await menu_adm_handler(update, context)
        return

    if dados in ["menu_bemvindo", "menu_config_grupo", "menu_punicao", "definir_punicao_aviso_ban", "definir_punicao_remover", "definir_punicao_silenciar"] or dados.startswith("toggle_"):
        await tratar_botoes_adm(update, context)
        return

    if dados in ["voltar_menu_principal", "voltar_menu"]:
        await query.answer()
        await start(update, context)
        return

    if dados == "menu_membros":
        await query.answer()
        await menu_membros_handler(update, context)
        return

    if dados == "executar_perfil":
        await query.answer("Abrindo seu perfil...")
        from comandos.perfil import perfil_cmd
        await perfil_cmd(update, context)
        return

    if dados == "ver_comandos":
        await query.answer()
        texto = ler_comandos_membros() + "\n" + ler_comandos_adm()
        teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]])
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        return

    if dados == "menu_aluguel":
        await query.answer()
        from comandos.aluguel import painel_aluguel
        await painel_aluguel(update, context)
        return

    if dados.startswith("aluguel_") or dados.startswith("checar_pagamento_") or dados == "voltar_ao_painel":
        await query.answer()
        from comandos.aluguel import tratar_todos_botoes_aluguel
        await tratar_todos_botoes_aluguel(update, context)
        return

    if dados.startswith("addgrupo_"):
        await processar_callback_addgrupo(update, context, get_db, FUSO_BR)
        return

    if dados == "menu_jogos_atalho":
        await query.answer()
        await menu_jogos_handler(update, context)
        return

    if dados == "jogo_velha":
        await query.answer("Abrindo Jogo da Velha...")
        from comandos.jogos.velha import menu_velha_handler
        await menu_velha_handler(update, context)
        return

    if dados == "jogo_xadrez":
        await query.answer("Abrindo Xadrez...")
        from comandos.jogos.xadrez import menu_xadrez_handler
        await menu_xadrez_handler(update, context)
        return

    if dados == "jogo_memoria":
        await query.answer("Abrindo Memória...")
        from comandos.jogos.memoria import iniciar_memoria
        await iniciar_memoria(update, context)
        return

    if dados == "jogo_minado":
        await query.answer("Abrindo Campo Minado...")
        from comandos.jogos.minado import iniciar_minado
        await iniciar_minado(update, context)
        return

    if dados == "jogo_dama":
        await query.answer("🔴 Damas em breve!", show_alert=True)
        return

    logger.warning(f"⚠️ Botão não registrado: {dados}")
    await query.answer("❌ Função não encontrada!", show_alert=True)

# ✅ CORRIGIDO — EVENT LOOP FUNCIONA NO RENDER!
def main():
    # Inicia Flask em thread separada
    threading.Thread(target=run_web, daemon=True).start()
    logger.info("🌐 Servidor Web iniciado")

    # ✅ CRIA E DEFINE O EVENT LOOP ANTES DE TUDO!
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # ✅ HANDLER DE ADIÇÃO DO BOT — PRIORIDADE MÁXIMA
    application.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_adicionado_grupo),
        group=0
    )
    application.add_handler(
        MessageHandler(filters.StatusUpdate.CHAT_CREATED, bot_adicionado_grupo),
        group=0
    )

    # ✅ INTERCEPTADOR DE PROTEÇÕES
    application.add_handler(TypeHandler(Update, interceptador_protecoes), group=1)

    # ✅ HANDLERS DOS JOGOS (com tratamento de erro)
    try:
        from comandos.jogos.velha import setup_velha
        from comandos.jogos.xadrez import setup_xadrez
        from comandos.jogos.memoria import setup_memoria
        from comandos.jogos.minado import setup_minado
        from comandos.jogos.dama import setup_dama
        setup_velha(application)
        setup_xadrez(application)
        setup_memoria(application)
        setup_minado(application)
        setup_dama(application)
        logger.info("🎮 Módulos de jogos carregados")
    except Exception as e:
        logger.error(f"❌ Erro ao carregar jogos: {e}")

    # ✅ HANDLERS GERAIS
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stts", lambda u,c: cmd_stts(u, c, get_db, verificar_se_e_adm)))
    application.add_handler(CommandHandler("addgrupo", lambda u,c: cmd_addgrupo(u,c,get_db,FUSO_BR)))
    application.add_handler(CallbackQueryHandler(button_handler))

    # ✅ Registro de comandos com tratamento de erro
    try:
        from comandos.ping import registrar_ping
        from comandos.id import registrar_id
        from comandos.perfil import registrar_perfil
        from comandos.ban import registrar_ban
        from comandos.mutar import registrar_mutar
        from comandos.bemvindo import registrar_comandos_bv
        from comandos.promover import registrar_promover
        from comandos.marcar import registrar_marcar
        from comandos.citar import registrar_citar
        from comandos.play import setup_play
        from comandos.deploy import registrar_deploy
        from comandos.rank import registrar_rank
        from comandos.figurinha import registrar_figurinha
        from comandos.aluguel import registrar_aluguel

        registrar_figurinha(application); registrar_promover(application); registrar_rank(application); registrar_marcar(application)
        registrar_citar(application); registrar_comandos_bv(application)
        registrar_ping(application); registrar_id(application); registrar_perfil(application); registrar_ban(application)
        setup_play(application); registrar_mutar(application); registrar_deploy(application); registrar_aluguel(application)
        logger.info("📦 Todos os comandos carregados")
    except Exception as e:
        logger.error(f"❌ Erro ao carregar comandos: {e}")

    logger.info("🤖 Bot iniciado com sucesso! ✅")

    try:
        # ✅ RODA O POLLING CORRETAMENTE NO LOOP
        loop.run_until_complete(application.run_polling(drop_pending_updates=True))
    except Exception as e:
        logger.error(f"❌ Falha no polling: {e}")
    finally:
        try:
            loop.run_until_complete(application.shutdown())
        except:
            pass
        loop.close()

if __name__ == "__main__":
    main()
