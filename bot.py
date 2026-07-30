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

async def verificar_assinante(usuario_id: int) -> bool:
    """Verifica se o usuário é assinante ativo de algum grupo"""
    try:
        db = get_db()
        agora = time.time()
        grupo = db["grupos_autorizados"].find_one({"registrado_por": usuario_id, "ativo": True, "expira_em": {"$gt": agora}})
        return bool(grupo)
    except Exception as e:
        logger.error(f"Erro verifica assinante: {e}")
        return False

async def listar_grupos_usuario(usuario_id: int):
    """Retorna lista de grupos do usuário onde o bot está autorizado"""
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
    
    # ✅ Mostra "Configurar Grupos" apenas no privado e se for assinante
    if chat.type == "private" and await verificar_assinante(user.id):
        botoes.insert(2, [InlineKeyboardButton("⚙️ Configurar Grupos", callback_data="menu_config_grupos")])
    
    if DONO_ID and str(user.id) == str(DONO_ID):
        botoes.insert(3, [InlineKeyboardButton("🛠️ Painel do Dono (Deploy)", callback_data="menu_dono")])
    
    await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")

async def exibir_painel_config_grupo_privado(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id_grupo: int, nome_grupo: str):
    """Exibe painel de configurações de um grupo pelo privado"""
    query = update.callback_query
    uid = update.effective_user.id
    
    # Verifica se é dono/adm do grupo
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
    uid = update.effective_user.id
    chat = query.message.chat

    if query.data.startswith("addgrupo_"):
        await processar_callback_addgrupo(update, context, get_db, FUSO_BR)
        return

    # ✅ MENU CONFIGURAR GRUPOS (listar grupos do assinante)
    if query.data == "menu_config_grupos":
        if chat.type != "private":
            await query.answer("Acesse pelo privado do bot!", show_alert=True)
            return
        grupos = await listar_grupos_usuario(uid)
        if not grupos:
            await query.answer("Você não tem grupos registrados!", show_alert=True)
            return
        await query.answer()
        botoes_grupos = []
        for g in grupos:
            titulo = g.get("chat_title", f"Grupo {g['chat_id']}")
            botoes_grupos.append([InlineKeyboardButton(f"📌 {titulo}", callback_data=f"config_grupo_{g['chat_id']}")])
        botoes_grupos.append([InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu_principal")])
        await query.message.edit_text(
            "⚙️ **SEUS GRUPOS REGISTRADOS**\n\nEscolha um grupo para configurar:",
            reply_markup=InlineKeyboardMarkup(botoes_grupos),
            parse_mode="Markdown"
        )
        return

    # ✅ ABRIR CONFIGURAÇÃO DE UM GRUPO ESPECÍFICO
    if query.data.startswith("config_grupo_"):
        chat_id_grupo = int(query.data.replace("config_grupo_", ""))
        db = get_db()
        grupo = db["grupos_autorizados"].find_one({"chat_id": chat_id_grupo})
        nome_grupo = grupo.get("chat_title", f"Grupo {chat_id_grupo}") if grupo else f"Grupo {chat_id_grupo}"
        await exibir_painel_config_grupo_privado(update, context, chat_id_grupo, nome_grupo)
        return

    # ✅ PROTEÇÕES DE UM GRUPO PELO PRIVADO
    if query.data.startswith("prot_grupo_"):
        chat_id_grupo = int(query.data.replace("prot_grupo_", ""))
        if not await verificar_se_e_adm(update, context, chat_id_grupo):
            await query.answer("⚠️ Você não é administrador!", show_alert=True)
            return
        from protecao.status import enviar_painel_protecoes_privado
        await enviar_painel_protecoes_privado(update, context, chat_id_grupo)
        return

    # ✅ BOAS-VINDAS DE UM GRUPO PELO PRIVADO
    if query.data.startswith("bemvindo_grupo_"):
        chat_id_grupo = int(query.data.replace("bemvindo_grupo_", ""))
        if not await verificar_se_e_adm(update, context, chat_id_grupo):
            await query.answer("⚠️ Você não é administrador!", show_alert=True)
            return
        from comandos.bemvindo import enviar_painel_principal_bv
        await enviar_painel_principal_bv(context, chat_id_grupo, query=query)
        return

    # ✅ PUNIÇÃO DE UM GRUPO PELO PRIVADO
    if query.data.startswith("punicao_grupo_"):
        chat_id_grupo = int(query.data.replace("punicao_grupo_", ""))
        if not await verificar_se_e_adm(update, context, chat_id_grupo):
            await query.answer("⚠️ Você não é administrador!", show_alert=True)
            return
        from protecao.status import enviar_painel_punicao_privado
        await enviar_painel_punicao_privado(update, context, chat_id_grupo)
        return

    if not (DONO_ID and str(uid) == str(DONO_ID)):
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Executar Deploy", callback_data="executar_deploy")],[InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu_principal")]]),
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
    elif query.data == "jogo_xadrez":
        await query.answer("Abrindo menu do Xadrez...")
        from comandos.jogos.xadrez import menu_xadrez_handler
        await menu_xadrez_handler(update, context)
    elif query.data in ["jogo_velha","jogo_memoria","jogo_dama"]:
        await processar_callback_jogos(update, context)
    # ✅ CORRIGIDO: Botões de voltar — TODOS voltam ao menu principal (função start)
    elif query.data in ["voltar_menu_principal", "voltar_menu","ver_comandos","voltar_principal_grupo","menu_voltar_inicio"]:
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

    logger.info("🤖 Dono sempre liberado em qualquer lugar!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
