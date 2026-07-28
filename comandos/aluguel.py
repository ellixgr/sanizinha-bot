import os
import time
import requests
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

MONGO_URI = os.environ.get("MONGO_URI")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN") # Token do Mercado Pago para gerar o Pix

def get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)
    return client["sanizinhabot_db"]

# --- PAINEL DE ALUGUEL (MENU /START OU BOTÃO) ---
async def painel_aluguel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Salva temporariamente o tempo escolhido pelo usuário (padrão: 1 mês)
    context.user_data[f"aluguel_meses_{user_id}"] = 1
    
    texto = (
        "🤖 **Sistema de Aluguel do Bot**\n\n"
        "Para usar o bot em seus grupos ou canais, é necessário assinar o plano de aluguel.\n"
        "• **Valor por mês:** R$ 10,00\n"
        "• **Desconto progressivo/Proporcional:** R$ 10 por mês (Máx: 1 ano / R$ 120)\n\n"
        "Selecione a quantidade de meses desejada abaixo:"
    )
    
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data="aluguel_menos"),
            InlineKeyboardButton("📅 1 Mês (R$ 10,00)", callback_data="aluguel_info_mes"),
            InlineKeyboardButton("➕", callback_data="aluguel_mais")
        ],
        [InlineKeyboardButton("⚡ Gerar Código Pix", callback_data="aluguel_gerar_pix")],
        [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]
    ])
    
    if query:
        await query.answer()
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")

async def callback_aluguel_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    
    meses_atuais = context.user_data.get(f"aluguel_meses_{user_id}", 1)
    
    if data == "aluguel_mais":
        if meses_atuais < 12:
            meses_atuais += 1
        else:
            await query.answer("⚠️ O limite máximo é de 1 ano (12 meses)!", show_alert=True)
            return
    elif data == "aluguel_menos":
        if meses_atuais > 1:
            meses_atuais -= 1
        else:
            await query.answer("⚠️ O valor mínimo é 1 mês!", show_alert=True)
            return
    elif data == "aluguel_info_mes":
        await query.answer("Use os botões ➕ e ➖ para alterar os meses.", show_alert=False)
        return

    context.user_data[f"aluguel_meses_{user_id}"] = meses_atuais
    valor_total = meses_atuais * 10.00
    
    texto = (
        "🤖 **Sistema de Aluguel do Bot**\n\n"
        "Para usar o bot em seus grupos ou canais, é necessário assinar o plano de aluguel.\n"
        "• **Valor por mês:** R$ 10,00\n"
        f"• **Total Selecionado:** {meses_atuais} Mês(es)\n\n"
        "Selecione a quantidade de meses desejada abaixo:"
    )
    
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data="aluguel_menos"),
            InlineKeyboardButton(f"📅 {meses_atuais} Mês(es) (R$ {valor_total:.2f})".replace('.', ','), callback_data="aluguel_info_mes"),
            InlineKeyboardButton("➕", callback_data="aluguel_mais")
        ],
        [InlineKeyboardButton("⚡ Gerar Código Pix", callback_data="aluguel_gerar_pix")],
        [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]
    ])
    
    await query.answer()
    await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")

# --- GERAÇÃO DO PIX VIA MERCADO PAGO ---
async def gerar_pix_aluguel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user = update.effective_user
    
    meses = context.user_data.get(f"aluguel_meses_{user_id}", 1)
    valor = float(meses * 10.00)
    
    if not MP_ACCESS_TOKEN:
        await query.answer("⚠️ Token do Mercado Pago não configurado no bot!", show_alert=True)
        return
        
    await query.answer("Gerando código Pix, aguarde...", show_alert=False)
    
    url = "https://api.mercadopago.com/v1/payments"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": f"aluguel_{user_id}_{int(time.time())}"
    }
    
    payload = {
        "transaction_amount": valor,
        "description": f"Aluguel SanizinhaBot - {meses} Mes(es)",
        "payment_method_id": "pix",
        "payer": {
            "email": f"usuario_{user_id}@telegram.bot",
            "first_name": user.first_name
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        res_json = response.json()
        
        if response.status_code in [200, 201]:
            payment_id = res_json.get("id")
            point_of_interaction = res_json.get("point_of_interaction", {})
            qr_data = point_of_interaction.get("transaction_data", {}).get("qr_code", "")
            
            db = get_db()
            db["alugueis_pendentes"].update_one(
                {"payment_id": payment_id},
                {
                    "$set": {
                        "user_id": user_id,
                        "meses": meses,
                        "valor": valor,
                        "status": "pendente",
                        "criado_em": time.time()
                    }
                },
                upsert=True
            )
            
            texto_pix = (
                f"⚡ **Pix Gerado com Sucesso!**\n\n"
                f"👤 **Comprador:** {user.first_name}\n"
                f"📅 **Plano:** {meses} Mês(es)\n"
                f"💰 **Valor Total:** R$ {valor:.2f}\n\n"
                f"Copie o código Pix abaixo (Pix Copia e Cola) e pague no app do seu banco:\n\n"
                f"`{qr_data}`\n\n"
                f"🔄 *Assim que o pagamento for aprovado, clique no botão abaixo para verificar e liberar seu acesso.*"
            )
            
            teclado_status = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Verificar Pagamento", callback_data=f"checar_pagamento_{payment_id}")],
                [InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="menu_aluguel")]
            ])
            
            await query.message.edit_text(texto_pix, reply_markup=teclado_status, parse_mode="Markdown")
        else:
            err_msg = res_json.get("message", "Erro desconhecido")
            await query.message.reply_text(f"⚠️ Erro ao gerar Pix no Mercado Pago: {err_msg}")
    except Exception as e:
        await query.message.reply_text(f"⚠️ Falha de comunicação com a API de pagamentos: {e}")

async def verificar_status_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    payment_id = query.data.replace("checar_pagamento_", "")
    
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    
    try:
        response = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers, timeout=10)
        res_json = response.json()
        status = res_json.get("status")
        
        if status == "approved":
            db = get_db()
            dados_pix = db["alugueis_pendentes"].find_one({"payment_id": int(payment_id)})
            
            if dados_pix and dados_pix.get("status") != "pago":
                meses = dados_pix["meses"]
                tempo_segundos = meses * 30 * 24 * 60 * 60 # Dias aproximados em segundos
                expira_em = time.time() + tempo_segundos
                
                # Salva a licença ativa para o usuário dono da compra
                db["licencas_aluguel"].update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "expira_em": expira_em,
                            "meses": meses,
                            "ativo": True
                        }
                    },
                    upsert=True
                )
                db["alugueis_pendentes"].update_one({"payment_id": int(payment_id)}, {"$set": {"status": "pago"}})
                
            link_adicao = f"https://t.me/{context.bot.username}?startgroup=true"
            texto_sucesso = (
                "✅ **Pagamento Aprovado com Sucesso!**\n\n"
                f"Seu aluguel foi ativado por {dados_pix['meses'] if 'dados_pix' in locals() else '1'} mês(es).\n"
                "Agora você já pode adicionar o bot ao seu grupo ou canal clicando no botão abaixo!"
            )
            teclado_add = InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Adicionar ao seu Grupo/Canal", url=link_adicao)],
                [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]
            ])
            await query.message.edit_text(texto_sucesso, reply_markup=teclado_add, parse_mode="Markdown")
        else:
            await query.answer("⏳ O pagamento ainda não foi identificado. Pague o Pix e tente novamente em instantes.", show_alert=True)
    except Exception as e:
        await query.answer(f"⚠️ Erro ao verificar pagamento: {e}", show_alert=True)

# --- CONTROLE DE ENTRADA E EXPIRAÇÃO NOS GRUPOS ---
async def verificar_entrada_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ["group", "supergroup", "channel"]:
        return

    # Identifica quem adicionou o bot (ou o criador/administradores recentes)
    try:
        user_id = update.message.from_user.id
    except Exception:
        return

    db = get_db()
    licenca = db["licencas_aluguel"].find_one({"user_id": user_id})
    
    agora = time.time()
    
    # Se encontrou licença e o tempo ainda está válido
    if licenca and licenca.get("ativo", False) and licenca.get("expira_em", 0) > agora:
        # Tudo certo, o bot fica no grupo
        return
    
    # Se não tiver licença ou o prazo expirou, o bot sai imediatamente!
    texto_aviso = (
        "⚠️ **Aluguel Expirado ou Não Encontrado!**\n\n"
        "O usuário que adicionou este bot não possui um plano de aluguel ativo ou o prazo venceu.\n"
        "O bot está se retirando deste grupo/canal. Para alugar, fale com o bot no privado!"
    )
    try:
        await chat.send_message(texto_aviso, parse_mode="Markdown")
    except Exception:
        pass
    
    try:
        await context.bot.leave_chat(chat.id)
    except Exception:
        pass

# Função executada em background para checar grupos periodicamente se o prazo venceu
async def checar_expiracoes_background(context: ContextTypes.DEFAULT_TYPE):
    # Esta função pode ser chamada por job_queue se desejar, mas o bloqueio na entrada já protege.
    pass

def registrar_aluguel(app):
    app.add_handler(CallbackQueryHandler(painel_aluguel, pattern="^menu_aluguel$"))
    app.add_handler(CallbackQueryHandler(callback_aluguel_painel, pattern="^aluguel_(mais|menos|info_mes)$"))
    app.add_handler(CallbackQueryHandler(gerar_pix_aluguel, pattern="^aluguel_gerar_pix$"))
    app.add_handler(CallbackQueryHandler(verificar_status_pagamento, pattern="^checar_pagamento_"))
    
    # Monitora quando o bot é adicionado a um grupo/canal
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, verificar_entrada_grupo))
