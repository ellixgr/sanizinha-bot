import os
import json
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

ARQUIVO_ESTADO_DEPLOY = "deploy_status.json"

async def checar_deploy_pendente_ao_iniciar(application):
    if not os.path.exists(ARQUIVO_ESTADO_DEPLOY):
        return
    await asyncio.sleep(3)
    try:
        with open(ARQUIVO_ESTADO_DEPLOY, "r", encoding="utf-8") as f:
            dados = json.load(f)
        chat_id = dados.get("chat_id")
        message_id = dados.get("message_id")
        deploy_id = dados.get("deploy_id")
        if chat_id and message_id:
            await application.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=f"✅ **Deploy Concluído!**\nID: `{deploy_id}`",
                parse_mode="Markdown"
            )
    except Exception:
        pass
    finally:
        if os.path.exists(ARQUIVO_ESTADO_DEPLOY):
            os.remove(ARQUIVO_ESTADO_DEPLOY)

async def executar_clear_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dono_id_env = os.environ.get("DONO_ID", "")
    
    # ✅ CORRIGIDO: comparação segura como STRING
    if str(user_id) != str(dono_id_env):
        if update.callback_query:
            await update.callback_query.answer("⚠️ Apenas o dono!", show_alert=True)
        else:
            await update.message.reply_text("⚠️ Apenas o dono!")
        return

    api_key = os.environ.get("RENDER_API_KEY")
    service_id = os.environ.get("RENDER_SERVICE_ID")
    if not api_key or not service_id:
        texto = "⚠️ Configure RENDER_API_KEY e RENDER_SERVICE_ID"
        if update.callback_query:
            await update.callback_query.answer(texto, show_alert=True)
        else:
            await update.message.reply_text(texto)
        return

    msg = None
    if update.callback_query:
        await update.callback_query.answer("🔄 Solicitando deploy...")
        msg = update.callback_query.message
    else:
        msg = await update.message.reply_text("🔄 Solicitando deploy...")

    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"clearCache": "clear"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    deploy_id = data.get("deploy", {}).get("id") or data.get("id", "Desconhecido")
                    with open(ARQUIVO_ESTADO_DEPLOY, "w") as f:
                        json.dump({"chat_id": msg.chat_id, "message_id": msg.message_id, "deploy_id": deploy_id}, f)
                    await msg.edit_text(f"🔄 **Deploy iniciado!**\nID: `{deploy_id}`", parse_mode="Markdown")
                else:
                    await msg.edit_text(f"❌ Erro: `{await resp.text()}`", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Erro: `{e}`", parse_mode="Markdown")

async def cmd_clear_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await executar_clear_deploy(update, context)

def registrar_deploy(app):
    app.add_handler(CommandHandler("cleardeploy", cmd_clear_deploy))
    if app.job_queue:
        app.job_queue.run_once(lambda ctx: asyncio.create_task(checar_deploy_pendente_ao_iniciar(app)), when=1)
