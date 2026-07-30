import os
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from flask import Flask
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    TypeHandler, ContextTypes, filters, MessageHandler, ApplicationHandlerStop
)

from comandos.jogos.menujogos import menu_jogos_handler, processar_callback_jogos
from comandos.menus import menu_membros_handler, menu_adm_handler
from protecao.antiflod import executar_antiflod
from protecao.status import obter_punicao, obter_mencao_admins_str

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

async def listar_grupos_usuario(usuario_id: int):
    try:
        db = get_db()
        agora = time.time()
        grupos = list(db["grupos_autorizados"].find({
            "registrado_por": usuario_id,
            "ativo": True,
            "expira_em": {"$gt": agora}
        }))
        return grupos
    except Exception as e:
        logger.error(f"Erro lista grupos: {e}")
        return []

async def cmd_registrar_aluguel_dono(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        await update.message.reply_text("⚠️ Só funciona em grupos!")
        return
    if not DONO_ID or str(user.id) != str(DONO_ID):
        await update.message.reply_text("❌ Apenas o dono!")
        return
    db = get_db()
    agora = time.time()
    expira_em = agora + (10 * 365 * 24 * 60 * 60)
    db["grupos_autorizados"].update_one({"chat_id": chat.id}, {"$set":{"chat_id":chat.id,"chat_title":chat.title,"registrado_por":user.id,"expira_em":expira_em,"ativo":True}}, upsert=True)
    db["avisos_grupos_piratas"].delete_one({"chat_id": chat.id})
    await update.message.reply_text(f"✅ Grupo registrado com sucesso!", parse_mode="Markdown")

async def verificar_se_e_adm(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id_verificar=None) -> bool:
    uid = update.effective_user.id
    chat = update.effective_chat
    if DONO_ID and str(uid) == str(DONO_ID): return True
    chat_alvo_id = chat_id_verificar if chat_id_verificar else chat.id
    if chat_alvo_id < 0:
        try: return (await context.bot.get_chat_member(chat_alvo_id, uid)).status in ["administrator","creator"]
        except: pass
    return False

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

async def interceptador_grupos_nao_autorizados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        return
    if DONO_ID and str(user.id) == str(DONO_ID):
        return
    if not await grupo_autorizado(chat.id):
        raise ApplicationHandlerStop

async def interceptador_geral_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message or update.effective_message
    if not chat or not user or chat.type == "private" or not msg:
        return
    if DONO_ID and str(user.id) == str(DONO_ID):
        return
    if not await grupo_autorizado(chat.id):
        return
    if await executar_antiflod(update,context,chat,user,msg,get_db,verificar_se_e_adm,obter_punicao,obter_mencao_admins_str):
        raise ApplicationHandlerStop

async def interceptador_estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user or chat.type == "private": return
    if DONO_ID and str(user.id) == str(DONO_ID):
        return
    if not await grupo_autorizado(chat.id): return
    msg = update.message
    if not msg: return
    tipo = {"total_mensagens":1, "fotos":int(bool(msg.photo)), "videos":int(bool(msg.video)), "audios":int(bool(msg.voice or msg.audio)), "stickers":int(bool(msg.sticker))}
    try:
        db = get_db()
        db["mensagens_usuarios"].update_one({"chat_id":chat.id,"user_id":user.id}, {"$inc":tipo}, upsert=True)
    except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
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
        [InlineKeyboardButton("📜 Comandos & Membro", callback_data="menu_membros")],
        [InlineKeyboardButton("👑 Comandos & Adm", callback_data="menu_adm")],
        [InlineKeyboardButton("🤖 Alugar Bot", callback_data="menu_aluguel")],
        [InlineKeyboardButton("🤖 Adicionar ao seu Grupo", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ]

    if chat.type == "private" and await verificar_assinante(user.id):
        botoes.insert(2, [InlineKeyboardButton("⚙️ Configurar Grupos", callback_data="menu_config_grupos")])

    if DONO_ID and str(user.id) == str(DONO_ID):
        botoes.insert(3, [InlineKeyboardButton("🛠️ Painel do Dono", callback_data="menu_dono")])

    await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")

async def exibir_painel_config_grupo_privado(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id_grupo: int, nome_grupo: str):
    query = update.callback_query
    uid = update.effective_user.id

    if not await verificar_se_e_adm(update, context, chat_id_grupo):
        await query.answer("⚠️ Você não é administrador deste grupo!", show_alert=True)
        return

    texto = f"⚙️ **CONFIGURAÇÕES DO GRUPO**\n📌 {nome_grupo}\n🆔 `{chat_id_grupo}`"

    botoes = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ Proteções do Grupo", callback_data=f"prot_grupo_{chat_id_grupo}")],
        [InlineKeyboardButton("👋 Mensagem de Boas-Vindas", callback_data=f"bemvindo_grupo_{chat_id_grupo}")],
        [InlineKeyboardButton("⚖️ Configurar Punição", callback_data=f"punicao_grupo_{chat_id_grupo}")],
        [InlineKeyboardButton("🔙 Voltar aos Meus Grupos", callback_data="menu_config_grupos")]
    ])

    await query.message.edit_text(texto, reply_markup=botoes, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    uid = update.effective_user.id
    chat = query.message.chat
    dados = query.data
    logger.info(f"📥 CLIQUE: {dados} | Usuário: {uid}")

    # ✅ PRIMEIRO: VERIFICA VOLTAR — ANTES DE QUALQUER BLOQUEIO!
    if dados in ["voltar_menu_principal", "voltar_menu", "ver_comandos", "voltar_principal_grupo", "menu_voltar_inicio"]:
        await query.answer()
        await start(update, context)
        return

    if dados == "menu_config_grupos":
        if chat.type != "private":
            await query.answer("Acesse pelo privado!", show_alert=True)
            return
        grupos = await listar_grupos_usuario(uid)
        if not grupos:
            await query.answer("Sem grupos registrados!", show_alert=True)
            return
        await query.answer()
        botoes_grupos = []
        for g in grupos:
            titulo = g.get("chat_title", f"Grupo {g['chat_id']}")
            botoes_grupos.append([InlineKeyboardButton(f"📌 {titulo}", callback_data=f"config_grupo_{g['chat_id']}")])
        botoes_grupos.append([InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")])
        await query.message.edit_text(
            "⚙️ **SEUS GRUPOS**\nEscolha um grupo:",
            reply_markup=InlineKeyboardMarkup(botoes_grupos),
            parse_mode="Markdown"
        )
        return

    if dados.startswith("addgrupo_"):
        await processar_callback_addgrupo(update, context, get_db, FUSO_BR)
        return

    # ⚠️ BLOQUEIO SÓ VEM DEPOIS DO VOLTAR!
    if not (DONO_ID and str(uid) == str(DONO_ID)):
        if chat.type != "private" and not await grupo_autorizado(chat.id):
            await query.answer("❌ Grupo não autorizado!", show_alert=True)
            return

    if dados == "menu_membros":
        await query.answer()
        await menu_membros_handler(update, context)
        return
    elif dados == "menu_adm":
        await query.answer()
        await menu_adm_handler(update, context)
        return
    elif dados == "menu_dono":
        if str(uid) != str(DONO_ID):
            await query.answer("Negado!", show_alert=True)
            return
        await query.answer()
        await query.message.edit_text(
            "🛠️ **Painel do Dono**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Executar Deploy", callback_data="executar_deploy")],[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]]),
            parse_mode="Markdown"
        )
        return
    elif dados == "menu_aluguel":
        await query.answer()
        from comandos.aluguel import painel_aluguel
        await painel_aluguel(update, context)
        return
    elif dados == "executar_deploy":
        if str(uid) != str(DONO_ID):
            await query.answer("Negado!", show_alert=True)
            return
        from comandos.deploy import executar_clear_deploy
        await executar_clear_deploy(update, context)
        return

    elif dados == "menu_jogos_atalho":
        await query.answer()
        await menu_jogos_handler(update, context)
        return
    elif dados == "jogo_xadrez":
        await query.answer("Abrindo Xadrez...")
        from comandos.jogos.xadrez import menu_xadrez_handler
        await menu_xadrez_handler(update, context)
        return
    elif dados in ["jogo_velha","jogo_memoria","jogo_dama"]:
        await query.answer()
        await processar_callback_jogos(update, context)
        return

    elif dados == "botao_ping":
        await query.answer()
        from comandos.ping import ping_cmd
        await ping_cmd(update, context)
        return
    elif dados == "menu_perfil_atalho":
        await query.answer()
        if chat.type == "private":
            await query.message.reply_text("⚠️ Use em um grupo!", parse_mode="Markdown")
            return
        try:
            db = get_db()
            doc = db["mensagens_usuarios"].find_one({"chat_id":chat.id,"user_id":uid}) or {}
            total = doc.get("total_mensagens",1)
            fotos = doc.get("fotos",0)
            videos = doc.get("videos",0)
            audios = doc.get("audios",0)
            sticks = doc.get("stickers",0)
            soma = list(db["mensagens_usuarios"].aggregate([{"$match":{"chat_id":chat.id}},{"$group":{"_id":None,"s":{"$sum":"$total_mensagens"}}}]))
            total_geral = soma[0]["s"] if soma else 1
            pct = min((total/total_geral)*100,100)
        except: pct=0
        bio="Não configurada."
        try: bio=(await context.bot.get_chat(uid)).bio or bio
        except: pass
        await query.message.edit_text(
            f"👤 **PERFIL**\n🆔 `{uid}`\n💬 {bio}\n📊 Grupo: `{total}` msg | {fotos} fotos | {videos} vídeos | {audios} áudios | {sticks} figurinhas\n⚡ {pct:.1f}%",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_membros")]]),
            parse_mode="Markdown"
        )
        return
    elif dados == "menu_id_atalho":
        await query.answer()
        txt=f"🆔 Seu ID: `{uid}`"
        if chat.type!="private": txt+=f"\n🏢 ID Grupo: `{chat.id}`"
        await query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_membros")]]), parse_mode="Markdown")
        return

    elif dados == "config_bemvindo":
        if not await verificar_se_e_adm(update, context):
            await query.answer("Só ADM!", show_alert=True)
            return
        from comandos.bemvindo import enviar_painel_principal_bv
        await enviar_painel_principal_bv(context, chat.id, query=query)
        return
    elif dados == "menu_protecoes":
        if not await verificar_se_e_adm(update, context):
            await query.answer("Só ADM!", show_alert=True)
            return
        from protecao.status import enviar_painel_protecoes
        await enviar_painel_protecoes(update, context)
        return
    elif dados == "menu_config_punicao":
        if not await verificar_se_e_adm(update, context):
            await query.answer("Só ADM!", show_alert=True)
            return
        from protecao.status import enviar_painel_punicao
        await enviar_painel_punicao(update, context)
        return
    elif dados.startswith(("prot_grupo_","bemvindo_grupo_","punicao_grupo_")):
        if dados.startswith("prot_grupo_"):
            cid = int(dados.replace("prot_grupo_",""))
            if not await verificar_se_e_adm(update, context, cid):
                await query.answer("Sem permissão!", show_alert=True)
                return
            from protecao.status import enviar_painel_protecoes_privado
            await enviar_painel_protecoes_privado(update, context, cid)
        elif dados.startswith("bemvindo_grupo_"):
            cid = int(dados.replace("bemvindo_grupo_",""))
            if not await verificar_se_e_adm(update, context, cid):
                await query.answer("Sem permissão!", show_alert=True)
                return
            from comandos.bemvindo import enviar_painel_principal_bv
            await enviar_painel_principal_bv(context, cid, query=query)
        elif dados.startswith("punicao_grupo_"):
            cid = int(dados.replace("punicao_grupo_",""))
            if not await verificar_se_e_adm(update, context, cid):
                await query.answer("Sem permissão!", show_alert=True)
                return
            from protecao.status import enviar_painel_punicao_privado
            await enviar_painel_punicao_privado(update, context, cid)
        return
    elif dados.startswith(("prot_","pun_","menu_fechar","config_grupo_")):
        if dados.startswith("config_grupo_"):
            cid = int(dados.replace("config_grupo_",""))
            db = get_db()
            g = db["grupos_autorizados"].find_one({"chat_id":cid})
            nome = g.get("chat_title",f"Grupo {cid}") if g else f"Grupo {cid}"
            await exibir_painel_config_grupo_privado(update, context, cid, nome)
            return
        if not await verificar_se_e_adm(update, context):
            await query.answer("Negado!", show_alert=True)
            return
        from protecao.status import processar_callback_protecao
        await processar_callback_protecao(update, context)
        return

    logger.warning(f"⚠️ Botão não registrado: {dados}")
    await query.answer("❌ Função não encontrada!", show_alert=True)


def main():
    threading.Thread(target=run_web, daemon=True).start()

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

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
    from protecao.status import registrar_protecoes
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
    registrar_citar(application); registrar_protecoes(application); registrar_comandos_bv(application)
    registrar_ping(application); registrar_id(application); registrar_perfil(application); registrar_ban(application)
    setup_play(application); registrar_mutar(application); registrar_deploy(application); registrar_aluguel(application)

    application.add_handler(CommandHandler("lw", cmd_registrar_aluguel_dono))

    async def wrapper_addgrupo(update, context):
        await cmd_addgrupo(update, context, get_db, DONO_ID, FUSO_BR)
    application.add_handler(CommandHandler("addgrupo", wrapper_addgrupo))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, capturar_membros_handler), group=2)
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER & ~filters.ChatType.PRIVATE, remover_membro_saiu_handler), group=3)

    application.add_handler(CommandHandler("start", start))

    application.add_handler(TypeHandler(Update, interceptador_grupos_nao_autorizados), group=-3)
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_adicionado_grupo), group=-2)
    application.add_handler(MessageHandler((filters.ALL & ~filters.ChatType.PRIVATE), interceptador_geral_protecoes), group=-1)
    application.add_handler(TypeHandler(Update, interceptador_estatisticas), group=3)

    logger.info("🤖 Bot iniciado! Botões prontos.")

    import sys
    try:
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"⚠️ Com parâmetro falhou: {e}")
        try:
            application.run_polling()
        except Exception as e2:
            logger.error(f"❌ Falha total: {e2}")
            sys.exit(1)

if __name__ == "__main__":
    main()
