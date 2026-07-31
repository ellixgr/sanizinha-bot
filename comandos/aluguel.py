import os
import time
import uuid
import traceback
import requests
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

MONGO_URI = os.environ.get("MONGO_URI")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = os.environ.get("DONO_ID")

def get_db():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, tlsAllowInvalidCertificates=True)["sanizinhabot_db"]


# ==============================================
# 🛡️ FUNÇÃO AUXILIAR — MOSTRA ERRO NO CHAT
# ==============================================
async def enviar_erro_chat(update: Update, mensagem_erro: str):
    """Envia qualquer erro no chat pra facilitar verificar"""
    texto = f"⚠️ **ERRO:**\n{mensagem_erro}"
    try:
        if update.callback_query:
            await update.callback_query.message.reply_text(texto, parse_mode="Markdown")
        else:
            await update.message.reply_text(texto, parse_mode="Markdown")
    except:
        print(f"ERRO: {mensagem_erro}")


# ==============================================
# 🎉 PAINEL PRINCIPAL DE ALUGUEL
# ==============================================
async def painel_aluguel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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

    except Exception as e:
        erro_completo = traceback.format_exc()
        await enviar_erro_chat(update, f"Erro no painel principal:\n`{str(e)}`\n\nDetalhes:\n{erro_completo[:1500]}")


# ==============================================
# ➕ / ➖ ALTERAR MESES
# ==============================================
async def callback_aluguel_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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

    except Exception as e:
        erro_completo = traceback.format_exc()
        await enviar_erro_chat(update, f"Erro ao alterar meses:\n`{str(e)}`\n\nDetalhes:\n{erro_completo[:1500]}")


# ==============================================
# ⚡ GERAR PIX — CORRIGIDO SEM copy_text
# ==============================================
async def gerar_pix_aluguel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        user_id = update.effective_user.id
        user = update.effective_user
        meses = context.user_data.get(f"aluguel_meses_{user_id}", 1)
        valor = meses * 10.00

        # 👑 DONO ATIVA DIRETO
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

        # ⚠️ VERIFICA TOKEN
        if not MP_ACCESS_TOKEN:
            await query.answer("⚠️ Token do Mercado Pago não configurado!", show_alert=True)
            await enviar_erro_chat(update, "MP_ACCESS_TOKEN não está definido nas variáveis de ambiente!")
            return

        await query.answer("⚡ Gerando pagamento...")

        # 🔁 CHAMA MERCADO PAGO
        url = "https://api.mercadopago.com/v1/payments"
        idempotency_key = str(uuid.uuid4())

        headers = {
            "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": idempotency_key
        }

        payload = {
            "transaction_amount": valor,
            "description": f"Aluguel SanizinhaBot - {meses} meses",
            "payment_method_id": "pix",
            "payer": {
                "email": f"user_{user.id}@telegrambot.com",
                "first_name": user.first_name or "Cliente",
                "last_name": user.last_name or "Telegram"
            }
        }

        response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code == 201:
            resp_data = response.json()
            payment_id = resp_data["id"]
            qr_code = resp_data.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")

            if not qr_code:
                await enviar_erro_chat(update, f"Pix gerado mas sem código QR!\nResposta: {str(resp_data)[:500]}")
                return

            # 💾 SALVA NO BANCO
            db = get_db()
            db["alugueis_pendentes"].update_one(
                {"payment_id": payment_id},
                {"$set": {
                    "user_id": user_id,
                    "meses": meses,
                    "valor": valor,
                    "status": "pendente",
                    "qr_code": qr_code
                }},
                upsert=True
            )

            # ✅ SEM BOTÃO copy_text — USUÁRIO COPIA DO TEXTO
            msg_completa = (
                f"✅ **PIX GERADO COM SUCESSO!**\n\n"
                f"💰 **Valor:** R$ {valor:.2f}\n"
                f"📅 {meses} mês(es)\n\n"
                f"📋 **Código Pix Copia e Cola:**\n"
                f"`{qr_code}`\n\n"
                f"👉 Toque e segure o código acima para copiar!"
            )

            teclado = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Verificar Pagamento", callback_data=f"checar_pagamento_{payment_id}")],
                [InlineKeyboardButton("🔙 Voltar ao Painel", callback_data="voltar_ao_painel")]
            ])

            await query.message.reply_text(msg_completa, parse_mode="Markdown", reply_markup=teclado)

        else:
            erro_msg = f"Erro Mercado Pago: Status {response.status_code}\n{response.text[:800]}"
            await enviar_erro_chat(update, erro_msg)

    except Exception as e:
        erro_completo = traceback.format_exc()
        await enviar_erro_chat(update, f"Erro ao gerar Pix:\n`{str(e)}`\n\n{erro_completo[:1500]}")


# ==============================================
# 🔄 VERIFICAR PAGAMENTO
# ==============================================
async def verificar_status_pagamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        user_id = update.effective_user.id
        payment_id = query.data.replace("checar_pagamento_", "")

        if not MP_ACCESS_TOKEN:
            await query.answer("⚠️ Token não configurado!", show_alert=True)
            return

        url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
        headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            resp_data = response.json()
            status = resp_data.get("status")

            if status == "approved":
                await query.answer("🎉 Pagamento Aprovado!", show_alert=True)

                db = get_db()
                pendente = db["alugueis_pendentes"].find_one({"payment_id": int(payment_id)})
                if pendente and pendente.get("status") != "pago":
                    expira = time.time() + pendente["meses"] * 30 * 86400
                    db["licencas_aluguel"].update_one(
                        {"user_id": user_id},
                        {"$set": {"expira_em": expira, "meses": pendente["meses"], "ativo": True}},
                        upsert=True
                    )
                    db["alugueis_pendentes"].update_one(
                        {"payment_id": int(payment_id)},
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
        else:
            await enviar_erro_chat(update, f"Erro ao consultar pagamento: {response.status_code}\n{response.text[:500]}")

    except Exception as e:
        erro_completo = traceback.format_exc()
        await enviar_erro_chat(update, f"Erro ao verificar pagamento:\n`{str(e)}`\n\n{erro_completo[:1500]}")


# ==============================================
# 🔙 VOLTAR
# ==============================================
async def voltar_ao_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        await painel_aluguel(update, context)
    except Exception as e:
        await enviar_erro_chat(update, f"Erro ao voltar:\n{str(e)}")


async def voltar_ao_menu_principal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from bot import start
        await start(update, context)
    except Exception as e:
        await enviar_erro_chat(update, f"Erro ao voltar ao menu:\n{str(e)}")


# ==============================================
# 🎯 CENTRAL DE BOTÕES
# ==============================================
async def tratar_todos_botoes_aluguel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dados = update.callback_query.data

        if dados in ["aluguel_mais", "aluguel_menos", "aluguel_info_mes"]:
            await callback_aluguel_painel(update, context)
            return

        if dados == "aluguel_gerar_pix":
            await gerar_pix_aluguel(update, context)
            return

        if dados.startswith("checar_pagamento_"):
            await verificar_status_pagamento(update, context)
            return

        if dados == "voltar_ao_painel":
            await voltar_ao_painel(update, context)
            return

        if dados == "voltar_menu_principal":
            await voltar_ao_menu_principal(update, context)
            return

    except Exception as e:
        await enviar_erro_chat(update, f"Erro desconhecido no botão:\n{str(e)}")


def registrar_aluguel(app):
    app.add_handler(CallbackQueryHandler(painel_aluguel, pattern="^menu_aluguel$"))
    app.add_handler(CallbackQueryHandler(tratar_todos_botoes_aluguel, pattern="^(aluguel_|checar_pagamento_)"))
