import os
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from flask import Flask
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, TypeHandler, ContextTypes, filters, MessageHandler, ApplicationHandlerStop

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

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
DONO_ID = os.environ.get("DONO_ID")

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

async def verificar_se_e_adm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    chat = update.effective_chat
    if DONO_ID and str(uid) == str(DONO_ID): return True
    if chat.type in ["group","supergroup"]:
        try: return (await chat.get_member(uid)).status in ["administrator","creator"]
        except: pass
    return False

async def bot_adicionado_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in ["group","supergroup"]:
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
    if not chat or chat.type == "private":
        return
    if not await grupo_autorizado(chat.id):
        raise ApplicationHandlerStop

async def interceptador_geral_protecoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message or update.effective_message
    if not chat or not user or chat.type == "private" or not msg:
        return
    if not await grupo_autorizado(chat.id):
        return
    if await executar_antiflod(update,context,chat,user,msg,get_db,verificar_se_e_adm,obter_punicao,obter_mencao_admins_str):
        raise ApplicationHandlerStop

async def interceptador_estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user or chat.type == "private": return
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
    if DONO_ID and str(user.id) == str(DONO_ID):
        botoes.insert(3, [InlineKeyboardButton("🛠️ Painel do Dono (Deploy)", callback_data="menu_dono")])
    await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    chat = query.message.chat

    if query.data.startswith("addgrupo_"):
        await processar_callback_addgrupo(update, context, get_db, FUSO_BR)
        return

    if chat.type != "private" and not await grupo_autorizado(chat.id):
        await query.answer("❌ Grupo não autorizado!", show_alert=True)
        return

    if query.data == "menu_membros":
        await menu_membros_handler(update, context)
    elif query.data == "menu_adm":
        await menu_adm_handler(update, context)
    elif query.data == "menu_dono":
        if str(uid) != str(DONO_ID):
            await query.answer("Negado!", show_alert=True)
            return
        await query.answer()
        await query.message.edit_text(
            "🛠️ **Painel do Dono**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Executar Deploy", callback_data="executar_deploy")],[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")]]),
            parse_mode="Markdown"
        )
    elif query.data == "executar_deploy":
        if str(uid) != str(DONO_ID):
            await query.answer("Negado!", show_alert=True)
            return
        from comandos.deploy import executar_clear_deploy
        await executar_clear_deploy(update, context)
    elif query.data == "config_bemvindo":
        if not await verificar_se_e_adm(update, context):
            await query.answer("Só ADM!", show_alert=True)
            return
        from comandos.bemvindo import enviar_painel_principal_bv
        await enviar_painel_principal_bv(context, chat.id, query=query)
    elif query.data == "menu_protecoes":
        if not await verificar_se_e_adm(update, context):
            await query.answer("Só ADM!", show_alert=True)
            return
        from protecao.status import enviar_painel_protecoes
        await enviar_painel_protecoes(update, context)
    elif query.data == "menu_config_punicao":
        if not await verificar_se_e_adm(update, context):
            await query.answer("Só ADM!", show_alert=True)
            return
        from protecao.status import enviar_painel_punicao
        await enviar_painel_punicao(update, context)
    elif query.data.startswith(("prot_","pun_","menu_fechar")):
        if not await verificar_se_e_adm(update, context):
            await query.answer("Negado!", show_alert=True)
            return
        from protecao.status import processar_callback_protecao
        await processar_callback_protecao(update, context)
    elif query.data == "botao_ping":
        from comandos.ping import ping_cmd
        await ping_cmd(update, context)
    elif query.data == "menu_perfil_atalho":
        await query.answer()
        if chat.type == "private":
            await query.message.reply_text("⚠️ Use este comando dentro de um grupo!", parse_mode="Markdown")
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
    elif query.data == "menu_id_atalho":
        txt=f"🆔 Seu ID: `{uid}`"
        if chat.type!="private": txt+=f"\n🏢 ID Grupo: `{chat.id}`"
        await query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="menu_membros")]]), parse_mode="Markdown")
    elif query.data == "menu_jogos_atalho":
        await menu_jogos_handler(update, context)
    elif query.data in ["jogo_velha","jogo_memoria","jogo_xadrez","jogo_dama"]:
        await processar_callback_jogos(update, context)
    elif query.data in ["voltar_menu","ver_comandos","voltar_principal_grupo"]:
        await start(update, context)

def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()

    app.add_handler(TypeHandler(Update, interceptador_grupos_nao_autorizados), group=-3)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_adicionado_grupo), group=-2)
    app.add_handler(MessageHandler((filters.ALL & ~filters.ChatType.PRIVATE), interceptador_geral_protecoes), group=-1)
    app.add_handler(TypeHandler(Update, interceptador_estatisticas), group=3)

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

    setup_velha(app); setup_memoria(app); setup_dama(app); setup_xadrez(app)
    registrar_figurinha(app); registrar_promover(app); registrar_rank(app); registrar_marcar(app)
    registrar_citar(app); registrar_protecoes(app); registrar_comandos_bv(app)
    registrar_ping(app); registrar_id(app); registrar_perfil(app); registrar_ban(app)
    setup_play(app); registrar_mutar(app); registrar_deploy(app); registrar_aluguel(app)

    app.add_handler(CommandHandler("lw", cmd_registrar_aluguel_dono))

    async def wrapper_addgrupo(update, context):
        await cmd_addgrupo(update, context, get_db, DONO_ID, FUSO_BR)
    app.add_handler(CommandHandler("addgrupo", wrapper_addgrupo))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, capturar_membros_handler), group=2)
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER & ~filters.ChatType.PRIVATE, remover_membro_saiu_handler), group=3)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("🤖 Sistema corrigido e funcionando!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
