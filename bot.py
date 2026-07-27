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

token = os.environ.get("TELEGRAM_TOKEN")
app = ApplicationBuilder().token(token).build()

from Comandos.bemvindo import registrar_comandos_bv
registrar_comandos_bv(app)

from Comandos.play import setup_play
setup_play(app)

from Comandos.jogos.velha import setup_velha
from Comandos.jogos.dama import setup_dama
from Comandos.jogos.forca import setup_forca
from Comandos.jogos.memoria import setup_memoria
from Comandos.jogos.xadrez import setup_xadrez

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
    col_mensagens_usuarios = db["mensagens_usuarios"]
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
ADVERTENCIAS_LINK = defaultdict(dict)  

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

async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return  
    user_id = user.id
    agora = time.time()
    
    if chat and chat.type in ["group", "supergroup"] and update.message:
        try:
            col_mensagens_usuarios.update_one(
                {"chat_id": chat.id, "user_id": user_id},
                {"$inc": {"total_mensagens": 1}},
                upsert=True
            )
        except Exception:
            pass

    if user_id == DONO_ID:
        return

    if update.message and update.message.text and update.message.text.startswith('/'):
        if user_id in ultimo_envio:
            tempo_decorrido = agora - ultimo_envio[user_id]
            if tempo_decorrido < 2.0:
                try:
                    await update.message.reply_text(f"⚠️ **Aguarde {2.0 - tempo_decorrido:.1f}s**.", parse_mode="Markdown")
                except Exception:
                    pass
                raise ApplicationHandlerStop

    if chat and chat.type in ["group", "supergroup"]:
        message = update.message
        if message:
            if not await is_user_admin(update, context):
                cfg = get_config(chat.id)
                texto = message.text or message.caption or ""
                is_forward_proibido = cfg.get("antienk_forward", True) and (message.forward_date or message.forward_origin)
                padrao_link = r"(https?://\S+|t\.me/\S+|www\.\S+|@[a-zA-Z0-9_]{5,})"
                tem_link_ou_mencao = bool(re.search(padrao_link, texto)) or message.entities and any(e.type in ["text_link", "mention"] for e in message.entities)
                
                if cfg.get("antilink", True) and (tem_link_ou_mencao or is_forward_proibido):
                    try:
                        await message.delete()
                        if chat.id not in ADVERTENCIAS_LINK:
                            ADVERTENCIAS_LINK[chat.id] = {}
                        avisos_usuario = ADVERTENCIAS_LINK[chat.id].get(user_id, 0) + 1
                        ADVERTENCIAS_LINK[chat.id][user_id] = avisos_usuario
                        if avisos_usuario == 1:
                            await message.reply_text(f"⚠️ **{user.first_name}**, links não permitidos! 1º aviso.")
                        else:
                            await context.bot.ban_chat_member(chat.id, user_id)
                            await message.reply_text(f"🛡️ **{user.first_name}** banido por reincidência de links.")
                            ADVERTENCIAS_LINK[chat.id][user_id] = 0
                    except Exception:
                        pass
                    raise ApplicationHandlerStop

                if cfg.get("antitrava", True) and len(texto) > 1500:
                    try:
                        await message.delete()
                        await context.bot.ban_chat_member(chat.id, user_id)
                    except Exception:
                        pass
                    raise ApplicationHandlerStop

                if cfg.get("antiimagem", False) and message.photo:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    raise ApplicationHandlerStop

                if cfg.get("antifigurinha", False) and message.sticker:
                    try:
                        await message.delete()
                    except Exception:
                        pass
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await start_group_handler(update, context)
        return
        
    texto_boas_vindas = "🔥 **SEJA BEM-VINDO AO BOT** 🇧🇷\n\nEscolha uma opção abaixo:"
    keyboard = [
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 1 𝐃𝐈𝐀 → R$ 2,00", callback_data="comprar_2.00")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 1 𝐒𝐄𝐌𝐀𝐍𝐀 → R$ 7,00", callback_data="comprar_7.00")],
        [InlineKeyboardButton("𝐀𝐂𝐄𝐒𝐒𝐎 1 𝐌𝐄𝐒 → R$ 20,00", callback_data="comprar_20.00")]
    ]
    try:
        await update.message.reply_photo(photo=FOTO_START, caption=texto_boas_vindas, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(texto_boas_vindas, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def start_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    mention = user.mention_markdown() if user else "Usuário"
    teclado_grupo = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Comandos de Membros", callback_data="cmd_membros")],
        [InlineKeyboardButton("🛡️ Comandos de Administradores", callback_data="cmd_adm")],
        [InlineKeyboardButton("⚙️ Central de Proteções", callback_data=f"painel_prot_{chat.id}")]
    ])
    texto_grupo = f"🛡️ **Painel Oficial** — {mention}\n📌 Grupo: `{chat.title}`"
    await update.message.reply_text(texto_grupo, reply_markup=teclado_grupo, parse_mode="Markdown")

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inicio = time.time()
    msg = await update.message.reply_text("pong 🏓...")
    latencia = int((time.time() - inicio) * 1000)
    uptime = int(time.time() - TEMPO_INICIAL)
    await msg.edit_text(f"🏓 **Latência:** `{latencia}ms` | **Online:** `{uptime//3600}h`", parse_mode="Markdown")

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
            [InlineKeyboardButton(f"🛡️ Antilink: {'✅' if cfg.get('antilink') else '❌'}", callback_data=f"toggle_{chat_id}_antilink"),
             InlineKeyboardButton(f"⚡ Anti-Flood: {'✅' if cfg.get('antiflood') else '❌'}", callback_data=f"toggle_{chat_id}_antiflood")],
            [InlineKeyboardButton(f"🖼️ Anti-Imagem: {'✅' if cfg.get('antiimagem') else '❌'}", callback_data=f"toggle_{chat_id}_antiimagem"),
             InlineKeyboardButton(f"🎭 Anti-Figurinha: {'✅' if cfg.get('antifigurinha') else '❌'}", callback_data=f"toggle_{chat_id}_antifigurinha")],
            [InlineKeyboardButton(f"🚨 Anti-Trava: {'✅' if cfg.get('antitrava') else '❌'}", callback_data=f"toggle_{chat_id}_antitrava"),
             InlineKeyboardButton(f"🔄 Anti-Forward: {'✅' if cfg.get('antienk_forward') else '❌'}", callback_data=f"toggle_{chat_id}_antienk_forward")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data=f"voltar_principal_grupo_{chat_id}")]
        ])
        await query.edit_message_text("⚙️ **Central de Proteções atualizada!**", reply_markup=teclado)
        await query.answer("Atualizado!")
        return

    if data.startswith("painel_prot_"):
        chat_id = int(data.split("_")[2])
        cfg = get_config(chat_id)
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🛡️ Antilink: {'✅' if cfg.get('antilink') else '❌'}", callback_data=f"toggle_{chat_id}_antilink"),
             InlineKeyboardButton(f"⚡ Anti-Flood: {'✅' if cfg.get('antiflood') else '❌'}", callback_data=f"toggle_{chat_id}_antiflood")],
            [InlineKeyboardButton(f"🖼️ Anti-Imagem: {'✅' if cfg.get('antiimagem') else '❌'}", callback_data=f"toggle_{chat_id}_antiimagem"),
             InlineKeyboardButton(f"🎭 Anti-Figurinha: {'✅' if cfg.get('antifigurinha') else '❌'}", callback_data=f"toggle_{chat_id}_antifigurinha")],
            [InlineKeyboardButton(f"🚨 Anti-Trava: {'✅' if cfg.get('antitrava') else '❌'}", callback_data=f"toggle_{chat_id}_antitrava"),
             InlineKeyboardButton(f"🔄 Anti-Forward: {'✅' if cfg.get('antienk_forward') else '❌'}", callback_data=f"toggle_{chat_id}_antienk_forward")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data=f"voltar_principal_grupo_{chat_id}")]
        ])
        await query.message.edit_text("⚙️ **Central de Proteções do Grupo**", reply_markup=teclado)
        await query.answer()
        return

    if data.startswith("voltar_principal_grupo_") or data == "cmd_adm":
        chat_id = chat_id_atual
        if "_" in data and data.split("_")[-1].isdigit():
            chat_id = int(data.split("_")[-1])
        from Comandos.bemvindo import enviar_painel_principal_bv
        await enviar_painel_principal_bv(context, chat_id, query=query)
        await query.answer()
        return

    if data == "cmd_membros":
        teclado_membros = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏓 Ping", callback_data="menu_ping"), InlineKeyboardButton("🆔 ID", callback_data="menu_id")],
            [InlineKeyboardButton("🎮 Jogos", callback_data="menu_jogos"), InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_principal")]
        ])
        await query.message.edit_text("📜 **Menu de Membros**", reply_markup=teclado_membros, parse_mode="Markdown")
        await query.answer()
        return

    if data == "voltar_principal":
        chat = query.message.chat
        mention = query.from_user.mention_markdown() if query.from_user else "Usuário"
        teclado_grupo = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Comandos de Membros", callback_data="cmd_membros")],
            [InlineKeyboardButton("🛡️ Administradores", callback_data="cmd_adm")],
            [InlineKeyboardButton("⚙️ Proteções", callback_data=f"painel_prot_{chat.id}")]
        ])
        await query.message.edit_text(f"🛡️ **Painel de Controle** — {mention}", reply_markup=teclado_grupo, parse_mode="Markdown")
        await query.answer()
        return

    if data == "menu_ping":
        await query.answer()
        inicio = time.time()
        latencia = int((time.time() - inicio) * 1000)
        await query.message.reply_text(f"🏓 **Latência:** `{latencia}ms`", parse_mode="Markdown")
        return

    if data == "menu_id":
        await query.answer()
        user = query.from_user
        chat = query.message.chat
        await query.message.reply_text(f"🆔 **ID:** `{user.id}` | **Chat ID:** `{chat.id}`", parse_mode="Markdown")
        return

    if data == "menu_jogos":
        await query.answer()
        teclado_jogos = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 Velha", callback_data="jogar_velha"), InlineKeyboardButton("🎯 Forca", callback_data="jogar_forca")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="cmd_membros")]
        ])
        await query.message.edit_text("🕹️ **Central de Jogos**", reply_markup=teclado_jogos, parse_mode="Markdown")
        return

    if data.startswith("comprar_"):
        try:
            await query.answer()
        except Exception:
            pass
        valor = float(data.split("_")[1])
        try:
            await query.edit_message_caption(caption="⏳ Gerando PIX...", reply_markup=None)
        except Exception:
            try:
                await query.edit_message_text("⏳ Gerando PIX...")
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
            "description": f"VIP - R$ {valor:.2f}",
            "payment_method_id": "pix",
            "payer": {"email": f"user_{user.id}@telegrambot.com", "first_name": user.first_name or "Cliente"}
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
        except Exception:
            await query.message.reply_text("❌ Erro de conexão com Mercado Pago.")
            return

        if response.status_code == 201:
            resp_data = response.json()
            payment_id = resp_data["id"]
            qr_data = resp_data.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")
            keyboard_final = [
                [InlineKeyboardButton("📋 Copiar Pix", copy_text=dict(text=qr_data))],
                [InlineKeyboardButton("🔄 Verificar", callback_data=f"check_{payment_id}")]
            ]
            await query.message.reply_text(f"✅ **PIX Gerado!**\n\n`{qr_data}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard_final))
        else:
            await query.message.reply_text("❌ Erro ao gerar Pix no MP.")

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
                await query.answer("🎉 Aprovado!", show_alert=True)
            except Exception:
                pass              
            await query.message.reply_text("🎉 **Pagamento Aprovado!** Acesso liberado.")
        else:
            try:
                await query.answer("❌ Não identificado!", show_alert=True)
            except Exception:
                pass

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

def main():
    threading.Thread(target=run_web, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    threading.Thread(target=run_background_loop, args=(app,), daemon=True).start()

    app.add_handler(TypeHandler(Update, interceptador_universal), group=-1)
    app.add_handler(ChatMemberHandler(verificar_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping_cmd))
    
    app.add_handler(CallbackQueryHandler(button_handler))    
    
    print("🤖 Bot rodando com todas as correções de botões!")
    app.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    main()
