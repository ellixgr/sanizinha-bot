import os
import aiohttp
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def cmd_clear_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    MEU_USER_ID = 7711945457  
    if user_id != MEU_USER_ID:
        await update.message.reply_text("⚠️ Você não tem permissão para usar este comando.")
        return

    api_key = os.environ.get("RENDER_API_KEY")
    service_id = os.environ.get("RENDER_SERVICE_ID")

    if not api_key or not service_id:
        await update.message.reply_text("⚠️ As variáveis RENDER_API_KEY ou RENDER_SERVICE_ID não foram configuradas no Render!")
        return

    msg = await update.message.reply_text("🔄 Solicitando Clear Build Cache & Deploy no Render...")

    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "clearCache": "true"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status in [200, 201]:
                    data = await response.json()
                    deploy_id = data.get("deploy", {}).get("id", "Desconhecido")
                    await msg.edit_text(f"✅ **Clear Build Cache & Deploy disparado com sucesso!**\n\nID do Deploy: `{deploy_id}`\nO Render já está compilando do zero.", parse_mode="Markdown")
                else:
                    erro_texto = await response.text()
                    await msg.edit_text(f"❌ Erro ao comunicar com a API do Render:\n`{erro_texto}`", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Erro interno ao executar o comando: {e}")

def registrar_deploy(app):
    app.add_handler(CommandHandler("cleardeploy", cmd_clear_deploy))
