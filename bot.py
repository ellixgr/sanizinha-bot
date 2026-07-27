import os
import re
import uuid
import time
import asyncio
import requests
import platform
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler, 
    TypeHandler, 
    ContextTypes,
    ApplicationHandlerStop,
    ChatMemberHandler,
    filters
)

from comandos.bemvindo import registrar_comandos_bv
registrar_comandos_bv(app)

from comandos.play import setup_play
setup_play(app)

from comandos.jogos.velha import setup_velha
from comandos.jogos.dama import setup_dama
from comandos.jogos.forca import setup_forca
from comandos.jogos.memoria import setup_memoria
from comandos.jogos.xadrez import setup_xadrez

setup_velha(app)
setup_dama(app)
setup_forca(app)
setup_memoria(app)
setup_xadrez(app)


try:
    import psutil
except ImportError:
    psutil = None

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = int(os.environ.get("DONO_ID", 7711945457))
CANAL_ALVO_ID = int(os.environ.get("CANAL_ALVO_ID", 0))
MONGO_URI = os.environ.get("MONGO_URI")

# Conexão segura com o MongoDB
try:
    mongo_client = MongoClient(
        MONGO_URI, 
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        tlsAllowInvalidCertificates=True
    )
    db = mongo_client["sanizinhabot_db"]
    collection_clientes = db["clientes"]
    collection_chats = db["chats_autorizados"]
    col_configs = db["config_grupos"]
    col_menu_adm = db["menu_adm"]
    print("✅ Conectado com sucesso ao MongoDB!")
except Exception as e:
    print(f"⚠️ Erro crítico ao conectar no MongoDB: {e}")

TEMPO_INICIAL = time.time()
FOTO_START = "https://files.catbox.moe/0pw3k8.jpg"

ultimo_envio = {}          
contador_spam = {}         
usuarios_bloqueados = {}     
bloqueio_temporario = {}     
pagamentos_notificados = set() 
FLOOD_CONTROL = defaultdict(list)
USER_MSG_CACHE = defaultdict(list)
PERMISSOES_SELECIONADAS = {}

OPCOES_PERMISSOES = {
    "can_manage_chat": "Gerenciar chat",
    "can_delete_messages": "Apagar mensagens",
    "can_manage_video_chats": "Gerenciar chamadas de voz",
    "can_restrict_members": "Banir/Restringir usuários",
    "can_promote_members": "Adicionar novos admins",
    "can_change_info": "Alterar dados do grupo",
    "can_invite_users": "Convidar via link",
    "can_pin_messages": "Fixar mensagens"
}

def get_config(chat_id: int):
    try:
        doc = col_configs.find_one({"chat_id": chat_id})
        if not doc:
            config_padrao = {
                "antilink": True,
                "antiflood": True,
                "antiimagem": False,
                "antifigurinha": False,
                "antitrava": True,
                "antienk_forward": True
            }
            col_configs.update_one({"chat_id": chat_id}, {"$set": config_padrao}, upsert=True)
            return config_padrao
        return doc
    except Exception:
        return {
            "antilink": True, "antiflood": True, "antiimagem": False,
            "antifigurinha": False, "antitrava": True, "antienk_forward": True
        }

def salvar_config_mongo(chat_id: int, cfg: dict):
    try:
        col_configs.update_one({"chat_id": chat_id}, {"$set": cfg}, upsert=True)
    except Exception:
        pass

async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False
    if chat.type == "private":
        return True
    if user.id == DONO_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ["creator", "administrator"]:
            return True
    except Exception:
        pass
    return False

# ================= INTERCEPTADOR UNIVERSAL E PROTEÇÕES =================
async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return  
    user_id = user.id
    agora = time.time()
    
    if user_id == DONO_ID:
        return

    # Se for em grupo, aplicar proteções de chat
    if chat and chat.type in ["group", "supergroup"]:
        message = update.message
        if message and message.text and not message.text.startswith('/'):
            if not await is_user_admin(update, context):
                cfg = get_config(chat.id)
                texto = message.text or message.caption or ""

                if cfg.get("antilink", True):
                    padrao_link = r"(https?://\S+|t\.me/\S+|www\.\S+|@[a-zA-Z0-9_]{5,})"
                    if re.search(padrao_link, texto):
                        try:
                            await message.delete()
                            await message.reply_text(f"⚠️ **{user.first_name}**, links não são permitidos aqui!")
                        except Exception:
                            pass
                        raise ApplicationHandlerStop

                if cfg.get("antienk_forward", True) and message.forward_date:
                    try:
                        await message.delete()
                        await message.reply_text(f"⚠️ **{user.first_name}**, mensagens encaminhadas são proibidas!")
                    except Exception:
                        pass
                    raise ApplicationHandlerStop

                if cfg.get("antitrava", True) and len(texto) > 1500:
                    try:
                        await message.delete()
                        await context.bot.ban_chat_member(chat.id, user_id)
                        await message.reply_text(f"🛡️ **{user.first_name}** banido por texto malicioso/trava.")
                    except Exception:
                        pass
                    raise ApplicationHandlerStop

    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].split('@')[0].lower()
        allowed_public = ['/start', '/suporte', '/suport', '/ping', '/id', '/perfil', '/jogos', '/figu', '/sticker']
        if cmd not in allowed_public and not await is_user_admin(update, context):
            # Deixar passar para verificação interna se necessário
            pass

    if user_id in bloqueio_temporario:
        if bloqueio_temporario[user_id] - agora > 0:
            raise ApplicationHandlerStop  
        else:
            del bloqueio_temporario[user_id]
            contador_spam.pop(user_id, None)
                
    if user_id in usuarios_bloqueados:
        raise ApplicationHandlerStop        

    if user_id in ultimo_envio:
        if agora - ultimo_envio[user_id] < 1.2:
            contador_spam[user_id] = contador_spam.get(user_id, 0) + 1
            ultimo_envio[user_id] = agora
            if contador_spam[user_id] >= 8:
                bloqueio_temporario[user_id] = agora + 300  
                contador_spam[user_id] = 0
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="⚠️ **Muitas mensagens enviadas rapidamente. Aguarde alguns instantes.**",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
                raise ApplicationHandlerStop           
            raise ApplicationHandlerStop
            
    ultimo_envio[user_id] = agora

async def verificar_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return        
    chat = result.chat
    new_status = result.new_chat_member.status
    if chat.type in ["group", "supergroup", "channel"]:
        try:
            if new_status in ["member", "administrator"]:
                collection_chats.update_one(
                    {"chat_id": chat.id},
                    {"$set": {"chat_id": chat.id, "title": chat.title, "type": chat.type}},
                    upsert=True
                )
            elif new_status in ["left", "kicked"]:
                collection_chats.delete_one({"chat_id": chat.id})
        except Exception:
            pass

# ================= COMANDOS ORIGINAIS E PORTADOS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await start_group_handler(update, context)
        return
        
    texto_boas_vindas = (
        "🔥 **SEJA BEM-VINDO AO CANAL EXCLUSIVO** 🇧🇷\n\n"
        "✨ Tenha acesso completo a todo o nosso conteúdo diário atualizado em um só lugar:\n\n"
        "📁 +130 mil mídias disponíveis (vídeos e fotos)\n"
        "🚀 Atualizações diárias sem censura\n"
        "💎 Material organizado e exclusivo\n\n"
        "👇 Escolha o seu plano abaixo para liberar o seu acesso:\n\n"
        "💡 *Precisa de ajuda? Fale com o suporte:* @Lyhhxv"
    )
    keyboard = [
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐎𝐑 1 𝐃𝐈𝐀 → R$ 2,00 🔥", callback_data="comprar_2.00")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐎𝐑 1 𝐒𝐄𝐌𝐀𝐍𝐀 → R$ 7,00", callback_data="comprar_7.00")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐎𝐑 1 𝐌𝐄𝐒 → R$ 20,00", callback_data="comprar_20.00")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 𝐏𝐄𝐑𝐌𝐀ℕ𝐄ℕ𝐓𝐄 → R$ 60,00", callback_data="comprar_60.00")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await update.message.reply_photo(
            photo=FOTO_START,
            caption=texto_boas_vindas,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text(texto_boas_vindas, reply_markup=reply_markup, parse_mode="Markdown")

async def start_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    mention = user.mention_markdown() if user else "Usuário"
    teclado_grupo = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Comandos de Membros", callback_data="cmd_membros")],
        [InlineKeyboardButton("🛡️ Comandos de Administradores", callback_data="cmd_adm")],
        [InlineKeyboardButton("⚙️ Central de Proteções", callback_data=f"painel_prot_{chat.id}")]
    ])
    texto_grupo = (
        f"🛡️ **Painel de Controle Oficial** — {mention}\n"
        f"📌 Grupo: `{chat.title}`\n\n"
        "✨ Gerencie a segurança e os comandos do grupo através dos botões abaixo:"
    )
    await update.message.reply_text(texto_grupo, reply_markup=teclado_grupo, parse_mode="Markdown")

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    resposta = (
        f"📊 **INFORMAÇÕES DE ID:**\n\n"
        f"💬 **Nome do Chat:** {chat.title if chat.title else 'Privado'}\n"
        f"🆔 **ID deste Chat/Grupo:** `{chat.id}`\n"
        f"👤 **Seu ID de Usuário:** `{user.id}`"
    )
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        alvo = update.message.reply_to_message.from_user
        resposta += f"\n👤 **Alvo Respondido:** {alvo.first_name}\n🆔 **ID do Alvo:** `{alvo.id}`"
    await update.message.reply_text(resposta, parse_mode="Markdown")

async def teste_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != DONO_ID:
        return
    msg_teste = f"🧪 **DADOS CAPTURADOS (COMANDO /TESTE)!**\n👤 **Nome:** {user.first_name}\n🆔 **ID:** `{user.id}`"
    await update.message.reply_text("✅ Teste executado!")
    try:
        await context.bot.send_message(chat_id=DONO_ID, text=msg_teste, parse_mode="Markdown")
    except Exception:
        pass

async def comandos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    texto = (
        "📜 **LISTA DE COMANDOS DO BOT**\n\n"
        "• `/start` - Inicia o bot\n• `/id` - Mostra IDs\n• `/protecao` - Painel de segurança\n"
        "• `/ban` - Bane usuário\n• `/mutar` / `/desmutar` - Moderação\n• `/marcar` / `/totag` - Menções em massa\n"
        "• `/figu` - Cria figurinhas\n• `/ping` - Latência\n• `/jogos` - Central de Jogos"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    await comandos_cmd(update, context)

async def config_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    chats = list(collection_chats.find({}))
    if not chats:
        await update.message.reply_text("⚙️ Nenhum grupo catalogado ainda.", parse_mode="Markdown")
        return
    keyboard = [[InlineKeyboardButton(f"👥 {c.get('title', 'Grupo')}", callback_data=f"cfg_chat_{c['chat_id']}")] for c in chats]
    await update.message.reply_text("⚙️ **Painel de Configuração de Grupos**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def clientes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    lista = list(collection_clientes.find({}))
    if not lista:
        await update.message.reply_text("📁 Nenhum cliente ativo.", parse_mode="Markdown")
        return
    resposta = f"📋 **CLIENTES ATIVOS ({len(lista)})**:\n\n"
    for c in lista:
        resposta += f"🔹 `{c.get('user_id')}` - Expira em: {time.strftime('%d/%m/%Y', time.localtime(c.get('expira_em', 0)))}\n"
    await update.message.reply_text(resposta, parse_mode="Markdown")

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inicio = time.time()
    msg = await update.message.reply_text("pong 🏓...")
    latencia = int((time.time() - inicio) * 1000)
    uptime = int(time.time() - TEMPO_INICIAL)
    resposta = f"🏓 **PONG!**\n⚡ Latência: `{latencia}ms`\n⏳ Uptime: `{uptime // 3600}h {(uptime % 3600) // 60}m`"
    await msg.edit_text(resposta, parse_mode="Markdown")

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛠 **Suporte:** @Lyhhxv", parse_mode="Markdown")

async def addusuario_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ Use: `/addusuario <id> <dias>`", parse_mode="Markdown")
        return
    try:
        user_id = int(args[0])
        dias = int(args[1])
        exp = time.time() + (dias * 86400)
        collection_clientes.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "expira_em": exp}}, upsert=True)
        await update.message.reply_text(f"✅ Usuário `{user_id}` adicionado por `{dias}` dias!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

# ================= COMANDOS DE MODERAÇÃO E UTILITÁRIOS =================
async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        await update.message.reply_text("⚠️ Apenas administradores!")
        return
    chat = update.effective_chat
    alvo_id = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        alvo_id = update.message.reply_to_message.from_user.id
    elif context.args:
        termo = context.args[0].replace("@", "")
        if termo.isdigit():
            alvo_id = int(termo)
    
    if not alvo_id:
        await update.message.reply_text("⚠️ Responda a alguém ou informe o ID para banir.")
        return
    try:
        await context.bot.ban_chat_member(chat.id, alvo_id)
        await update.message.reply_text(f"🔨 Usuário `{alvo_id}` banido com sucesso!")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao banir: {e}")

async def mutar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Responda a mensagem do usuário que deseja mutar.")
        return
    alvo = update.message.reply_to_message.from_user
    try:
        await context.bot.restrict_chat_member(
            chat.id if 'chat' in locals() else update.effective_chat.id,
            alvo.id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text(f"🔇 {alvo.first_name} foi mutado!")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def desmutar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        return
    if not update.message.reply_to_message:
        return
    alvo = update.message.reply_to_message.from_user
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            alvo.id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True
            )
        )
        await update.message.reply_text(f"🔊 {alvo.first_name} foi desmutado!")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def figu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    alvo = msg.reply_to_message if msg.reply_to_message else msg
    if not alvo.photo:
        await msg.reply_text("⚠️ Responda a uma foto com `/figu` para criar uma figurinha!")
        return
    m = await msg.reply_text("🎨 Criando figurinha...")
    try:
        photo_file = await context.bot.get_file(alvo.photo[-1].file_id)
        caminho = f"downloads/{uuid.uuid4()}.jpg"
        os.makedirs("downloads", exist_ok=True)
        await photo_file.download_to_drive(caminho)
        
        caminho_webp = caminho.rsplit(".", 1)[0] + ".webp"
        cmd_ffmpeg = ["ffmpeg", "-y", "-i", caminho, "-vf", "scale='if(gt(iw,ih),512,-1)':'if(gt(iw,ih),-1,512)'", "-vcodec", "libwebp", caminho_webp]
        processo = await asyncio.create_subprocess_exec(*cmd_ffmpeg, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await processo.communicate()

        if os.path.exists(caminho_webp):
            await update.effective_chat.send_sticker(sticker=open(caminho_webp, "rb"))
        else:
            await update.effective_chat.send_sticker(sticker=open(caminho, "rb"))
        await m.delete()
    except Exception as e:
        await m.edit_text(f"❌ Erro ao gerar figurinha: {e}")

async def perfil_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"╭━×🗿 **PERFIL** 🌹×━━╮\n"
        f"┃ 👤 **Nome:** {user.first_name}\n"
        f"┃ 🆔 **ID:** `{user.id}`\n"
        f"╰━━━━━━━━━━━━━╯",
        parse_mode="Markdown"
    )

async def jogos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Jogo da Velha", callback_data="jogar_velha"), InlineKeyboardButton("🎯 Forca", callback_data="jogar_forca")]
    ])
    await update.message.reply_text("🕹️ **Central de Jogos**\nEscolha uma opção:", reply_markup=teclado)

async def protecao_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        await update.message.reply_text("⚠️ Apenas administradores!")
        return
    chat_id = update.effective_chat.id
    cfg = get_config(chat_id)
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🛡️ Antilink: {'✅' if cfg.get('antilink') else '❌'}", callback_data=f"toggle_{chat_id}_antilink")],
        [InlineKeyboardButton(f"⚡ Anti-Flood: {'✅' if cfg.get('antiflood') else '❌'}", callback_data=f"toggle_{chat_id}_antiflood")]
    ])
    await update.message.reply_text("⚙️ **Central de Proteções Avançadas**", reply_markup=teclado)

# ================= CALLBACK QUERY HANDLER UNIFICADO =================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    chat_id_atual = query.message.chat.id

    if data.startswith("toggle_"):
        _, chat_id_str, recurso = data.split("_", 2)
        chat_id = int(chat_id_str)
        cfg = get_config(chat_id)
        if recurso in cfg:
            cfg[recurso] = not cfg[recurso]
            salvar_config_mongo(chat_id, cfg)
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🛡️ Antilink: {'✅' if cfg.get('antilink') else '❌'}", callback_data=f"toggle_{chat_id}_antilink")],
            [InlineKeyboardButton(f"⚡ Anti-Flood: {'✅' if cfg.get('antiflood') else '❌'}", callback_data=f"toggle_{chat_id}_antiflood")]
        ])
        await query.edit_message_text("⚙️ **Central de Proteções atualizada!**", reply_markup=teclado)
        await query.answer("Configuração alterada!")
        return

    if data == "cmd_membros":
        await query.message.edit_text("📜 **Comandos disponíveis para membros:**\n• `/ping`\n• `/perfil`\n• `/figu`\n• `/jogos`", parse_mode="Markdown")
        await query.answer()
        return

    if data == "cmd_adm":
        await query.message.edit_text("🛡️ **Comandos de Administradores:**\n• `/ban`\n• `/mutar`\n• `/protecao`", parse_mode="Markdown")
        await query.answer()
        return

    if data.startswith("comprar_"):
        try:
            await query.answer()
        except Exception:
            pass
        valor = float(data.split("_")[1])
        try:
            await query.edit_message_caption(caption="⏳ Gerando seu PIX, aguarde...", reply_markup=None)
        except Exception:
            try:
                await query.edit_message_text("⏳ Gerando seu PIX, aguarde...")
            except Exception:
                pass
        
        user = update.effective_user
        url = "https://api.mercadopago.com/v1/payments"
        headers = {
            "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": str(uuid.uuid4())
        }
        payload = {
            "transaction_amount": valor,
            "description": f"Acesso VIP - R$ {valor:.2f}",
            "payment_method_id": "pix",
            "payer": {"email": f"user_{user.id}@telegrambot.com", "first_name": user.first_name or "Cliente"}
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
        except Exception:
            await query.message.reply_text("❌ Erro de conexão com o gateway de pagamento.", parse_mode="Markdown")
            return

        if response.status_code == 201:
            resp_data = response.json()
            payment_id = resp_data["id"]
            qr_data = resp_data.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")
            
            keyboard_final = [
                [InlineKeyboardButton("📋 Copiar Código Pix", copy_text=dict(text=qr_data))],
                [InlineKeyboardButton("🔄 Verificar Pagamento", callback_data=f"check_{payment_id}")]
            ]
            await query.message.reply_text(
                f"✅ **PIX Gerado com Sucesso!**\n\n💰 **Valor:** R$ {valor:.2f}\n\n`{qr_data}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard_final)
            )
        else:
            await query.message.reply_text(f"❌ Erro ao gerar o Pix.", parse_mode="Markdown")

    elif data.startswith("check_"):
        payment_id = data.split("_")[1]       
        url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
        headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}      
        try:
            response = requests.get(url, headers=headers, timeout=10)
        except Exception:
            return
            
        if response.status_code == 200 and response.json().get("status") == "approved":
            try:
                await query.answer("🎉 Pagamento Aprovado!", show_alert=True)
            except Exception:
                pass              
            
            valor_pago = float(response.json().get("transaction_amount", 0.0))
            dias = 7 if valor_pago == 7.0 else 30 if valor_pago == 20.0 else 365 if valor_pago == 60.0 else 1
            user_id = update.effective_user.id
            exp = time.time() + (dias * 86400)
            
            collection_clientes.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "expira_em": exp}},
                upsert=True
            )
            await query.message.reply_text("🎉 **Pagamento Aprovado com Sucesso!** Seu acesso foi liberado.")
        else:
            try:
                await query.answer("❌ Pagamento ainda não identificado!", show_alert=True)
            except Exception:
                pass

# ================= BACKGROUND GERENCIADOR DE ASSINATURAS =================
async def gerenciador_assinaturas(application):
    await asyncio.sleep(10)  
    while True:
        try:
            agora = time.time()
            clientes = collection_clientes.find({})
            for cliente in clientes:
                user_id = cliente["user_id"]
                expira_em = cliente["expira_em"]
                if expira_em - agora <= 0 and CANAL_ALVO_ID != 0:
                    try:
                        await application.bot.ban_chat_member(chat_id=CANAL_ALVO_ID, user_id=user_id)
                        await application.bot.unban_chat_member(chat_id=CANAL_ALVO_ID, user_id=user_id)
                    except Exception:
                        pass
                    collection_clientes.delete_one({"user_id": user_id})
        except Exception:
            pass
        await asyncio.sleep(60)

def run_background_loop(application):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(gerenciador_assinaturas(application))

# ================= MAIN =================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    threading.Thread(target=run_background_loop, args=(app,), daemon=True).start()

    # Handlers unificados
    app.add_handler(TypeHandler(Update, interceptador_universal), group=-1)
    app.add_handler(ChatMemberHandler(verificar_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("teste", teste_cmd))
    app.add_handler(CommandHandler("comandos", comandos_cmd))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("clientes", clientes_cmd))
    app.add_handler(CommandHandler("config", config_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler(["suport", "suporte"], suporte_cmd))
    app.add_handler(CommandHandler("addusuario", addusuario_cmd))
    
    # Comandos de moderação e utilitários trazidos do segundo bot
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("mutar", mutar_cmd))
    app.add_handler(CommandHandler("desmutar", desmutar_cmd))
    app.add_handler(CommandHandler("figu", figu_cmd))
    app.add_handler(CommandHandler("sticker", figu_cmd))
    app.add_handler(CommandHandler("perfil", perfil_cmd))
    app.add_handler(CommandHandler("jogos", jogos_cmd))
    app.add_handler(CommandHandler("protecao", protecao_cmd))
    
    app.add_handler(CallbackQueryHandler(button_handler))    
    
    print("🤖 Bot unificado rodando perfeitamente!")
    app.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    main()
