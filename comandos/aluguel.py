import os
import time
import uuid
import requests
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters

MONGO_URI = os.environ.get("MONGO_URI")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = os.environ.get("DONO_ID")

def get_db():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)["sanizinhabot_db"]

async def painel_aluguel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat = update.effective_chat
    user_id = update.effective_user.id

    if chat and chat.type != "private":
        await query.answer("🔒 Use no privado!", show_alert=True)
        link = f"https://t.me/{context.bot.username}?start=aluguel"
        await query.message.reply_text(
            "🔒 **Acesse o painel de aluguel no privado:**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Ir ao Privado", url=link)]])
        )
        return

    context.user_data[f"aluguel_meses_{user_id}"] = 1
    context.user_data[f"aluguel_valor_{user_id}"] = 10.00

    texto = (
        "🤖 **Sistema de Aluguel**\n\n"
        "• 1 Mês = R$ 10,00\n"
        "• Máximo: 12 meses\n\n"
        "Escolha o período abaixo:"
    )
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("➖", callback_data="aluguel_menos"),
         InlineKeyboardButton("📅 1 Mês — R$ 10,00", callback_data="aluguel_info_mes"),
         InlineKeyboardButton("➕", callback_data="aluguel_mais")],
        [InlineKeyboardButton("⚡ Gerar Pix", callback_data="aluguel_gerar_pix")],
        [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu_principal")]
    ])
    await query.answer()
    try:
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    except Exception:
        await query.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")


async def callback_aluguel_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    dados = query.data

    meses = context.user_data.get(f"aluguel_meses_{user_id}", 1)

    if dados == "aluguel_mais":
        meses = min(12, meses + 1)
    elif dados == "aluguel_menos":
        meses = max(1, meses - 1)
    elif dados == "aluguel_info_mes":
        await query.answer("Use os botões ➕ e ➖", show_alert=False)
        return

    valor = meses * 10.00
    context.user_data[f"aluguel_meses_{user_id}"] = meses
    context.user_data[f"aluguel_valor_{user_id}"] = valor

    texto = f"🤖 **Aluguel**\n• {meses} Mês(es) — R$ {valor:.2f}".replace('.', ',')
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("➖", callback_data="aluguel_menos"),
         InlineKeyboardButton(f"📅 {meses} Mês — R$ {valor:.2f}".replace('.', ','), callback_data="aluguel_info_mes"),
         InlineKeyboardButton("➕", callback_data="aluguel_mais")],
        [InlineKeyboardButton("⚡ Gerar Pix", callback_data="aluguel_gerar_pix")],
        [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu_principal")]
    ])
    await query.answer()
    try:
        await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
    except Exception:
        await query.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")


async def gerar_pix_aluguel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user = update.effective_user
    meses = context.user_data.get(f"aluguel_meses_{user_id}", 1)
    valor = meses * 10.00

    # ✅ SE FOR O DONO, ATIVA DIRETO SEM PAGAMENTO
    if str(user_id) == str(DONO_ID):
        db = get_db()
        expira = time.time() + meses * 30 * 86400
        db["licencas_aluguel"].update_one(
            {"user_id": user_id},
            {"$set": {"expira_em": expira, "meses": meses, "ativo": True}},
            upsert=True
        )
        link = f"https://t.me/{context.bot.username}?startgroup=true"
        texto = "👑 **Licença ativada com sucesso!**\n\nAdicione o bot ao seu grupo:"
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Adicionar ao Grupo", url=link)],
            [InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="voltar_ao_painel")]
        ])
        try:
            await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
        except Exception:
            await query.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")
        return

    # ✅ VERIFICA SE TEM TOKEN DO MERCADO PAGO
    if not MP_ACCESS_TOKEN or len(MP_ACCESS_TOKEN) < 10:
        await query.answer("⚠️ Token do Mercado Pago não configurado!", show_alert=True)
        await query.message.edit_text(
            "⚠️ **Token do Mercado Pago não encontrado!**\n\n"
            "Configure a variável de ambiente MP_ACCESS_TOKEN no Render.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Voltar", callback_data="voltar_ao_painel")
            ]])
        )
        return

    await query.answer("⚡ Gerando pagamento...")

    # ✅ GERA ID ÚNICO OBRIGATÓRIO
    idempotency_key = str(uuid.uuid4())

    try:
        # ✅ DADOS CORRIGIDOS E VALIDADOS
        email_pagador = f"pagamento+{user_id}@gmail.com"  # ✅ EMAIL VÁLIDO
        nome_pagador = user.first_name or "Usuario"

        cabecalhos = {
            "Authorization": f"Bearer {MP_ACCESS_TOKEN.strip()}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": idempotency_key
        }

        dados_pagamento = {
            "transaction_amount": round(valor, 2),
            "description": f"Aluguel Bot - {meses} meses",
            "payment_method_id": "pix",
            "payer": {
                "email": email_pagador,
                "first_name": nome_pagador
            }
        }

        print(f"🔹 Enviando para Mercado Pago: {dados_pagamento}")

        resp = requests.post(
            "https://api.mercadopago.com/v1/payments",
            headers=cabecalhos,
            json=dados_pagamento,
            timeout=30
        )

        print(f"🔹 Status: {resp.status_code}")
        print(f"🔹 Resposta: {resp.text[:500]}")

        res = resp.json()

        if resp.status_code in (200, 201):
            pid = res.get("id")
            qr_code = res.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")

            if not pid or not qr_code:
                raise Exception("Resposta não tem ID ou QR Code")

            # ✅ SALVA NO BANCO
            db = get_db()
            db["alugueis_pendentes"].update_one(
                {"payment_id": pid},
                {"$set": {
                    "user_id": user_id,
                    "meses": meses,
                    "valor": valor,
                    "status": "pendente",
                    "qr_code": qr_code,
                    "criado_em": time.time()
                }},
                upsert=True
            )

            msg = (
                f"⚡ **PIX GERADO COM SUCESSO!**\n\n"
                f"💸 Valor: R$ {valor:.2f}\n"
                f"📅 {meses} mês(es)\n\n"
                f"📋 **Código Pix Copia e Cola:**\n\n"
                f"`{qr_code}`\n\n"
                f"👉 Toque e segure o código acima para copiar!"
            )

            botoes = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Verificar Pagamento", callback_data=f"checar_pagamento_{pid}")],
                [InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="voltar_ao_painel")]
            ])

            try:
                await query.message.edit_text(msg, reply_markup=botoes, parse_mode="Markdown")
            except Exception:
                await query.message.reply_text(msg, reply_markup=botoes, parse_mode="Markdown")

        else:
            erro_msg = res.get("message", f"Erro {resp.status_code}")
            await query.message.edit_text(
                f"❌ **ERRO AO GERAR PIX:**\n\n{erro_msg}\n\n"
                f"Verifique se o token MP_ACCESS_TOKEN está correto.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Voltar", callback_data="voltar_ao_painel")
                ]])
            )

    except Exception as e:
        print(f"🔹 ERRO EXCEÇÃO: {str(e)}")
        await query.message.edit_text(
            f"❌ **ERRO DE CONEXÃO:**\n\n{str(e)}\n\n"
            f"Verifique o token do Mercado Pago nas variáveis do Render!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Voltar", callback_data="voltar_ao_painel")
            ]])
        )


async def verificar_status_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    pid = query.data.replace("checar_pagamento_", "")

    if not MP_ACCESS_TOKEN:
        await query.answer("⚠️ Token não configurado!", show_alert=True)
        return

    try:
        resp = requests.get(
            f"https://api.mercadopago.com/v1/payments/{pid}",
            headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN.strip()}"},
            timeout=10
        )
        res = resp.json()
        status = res.get("status")

        if status == "approved":
            db = get_db()
            pendente = db["alugueis_pendentes"].find_one({"payment_id": int(pid)})
            if pendente and pendente.get("status") != "pago":
                expira = time.time() + pendente["meses"] * 30 * 86400
                db["licencas_aluguel"].update_one(
                    {"user_id": user_id},
                    {"$set": {"expira_em": expira, "meses": pendente["meses"], "ativo": True}},
                    upsert=True
                )
                db["alugueis_pendentes"].update_one(
                    {"payment_id": int(pid)},
                    {"$set": {"status": "pago"}}
                )
            link = f"https://t.me/{context.bot.username}?startgroup=true"
            texto = "✅ **PAGAMENTO CONFIRMADO!** 🎉\n\nAdicione o bot ao seu grupo:"
            teclado = InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Adicionar ao Grupo", url=link)],
                [InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="voltar_ao_painel")]
            ])
            try:
                await query.message.edit_text(texto, reply_markup=teclado, parse_mode="Markdown")
            except Exception:
                await query.message.reply_text(texto, reply_markup=teclado, parse_mode="Markdown")

        elif status in ["pending", "in_process"]:
            await query.answer("⏳ Aguardando pagamento...", show_alert=True)
        else:
            await query.answer(f"❌ Status: {status}", show_alert=True)

    except Exception as e:
        await query.answer(f"Erro: {str(e)}", show_alert=True)


async def voltar_ao_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await painel_aluguel(update, context)


async def verificar_entrada_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ["group", "supergroup"] or not user:
        return
    db = get_db()
    agora = time.time()
    if str(user.id) == str(DONO_ID):
        db["licencas_aluguel"].update_one({"user_id": user.id}, {"$setOnInsert": {"expira_em": agora + 30*86400, "meses": 1, "ativo": True}}, upsert=True)
    autorizado = db["grupos_autorizados"].find_one({"chat_id": chat.id, "expira_em": {"$gt": agora}})
    licenca = db["licencas_aluguel"].find_one({"user_id": user.id})
    valido = autorizado or (licenca and licenca.get("ativo") and licenca.get("expira_em", 0) > agora)
    if valido:
        restante = "permanente" if autorizado else f"{int((licenca['expira_em']-agora)/86400)} dias"
        mention = f"@{user.username}" if user.username else user.first_name
        try:
            await chat.send_message(f"Olá! Vou ficar por {restante} aqui. O ADM {mention} pagou! 😼")
        except Exception:
            pass


def registrar_aluguel(app):
    app.add_handler(CallbackQueryHandler(painel_aluguel, pattern="^menu_aluguel$"))
    app.add_handler(CallbackQueryHandler(callback_aluguel_painel, pattern="^aluguel_(mais|menos|info_mes)$"))
    app.add_handler(CallbackQueryHandler(gerar_pix_aluguel, pattern="^aluguel_gerar_pix$"))
    app.add_handler(CallbackQueryHandler(verificar_status_pagamento, pattern="^checar_pagamento_"))
    app.add_handler(CallbackQueryHandler(voltar_ao_painel, pattern="^voltar_ao_painel$"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, verificar_entrada_grupo))
