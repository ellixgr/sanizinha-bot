import os
import aiohttp
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

async def executar_clear_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dono_id_env = os.environ.get("DONO_ID")
    
    if not dono_id_env or user_id != int(dono_id_env):
        if update.callback_query:
            await update.callback_query.answer("⚠️ Apenas o dono do bot pode executar esta ação!", show_alert=True)
        else:
            await update.message.reply_text("⚠️ Você não tem permissão para usar este comando.")
        return

    api_key = os.environ.get("RENDER_API_KEY")
    service_id = os.environ.get("RENDER_SERVICE_ID")

    if not api_key or not service_id:
        texto_erro = "⚠️ As variáveis RENDER_API_KEY ou RENDER_SERVICE_ID não foram configuradas no Render!"
        if update.callback_query:
            await update.callback_query.answer(texto_erro, show_alert=True)
        else:
            await update.message.reply_text(texto_erro)
        return

    if update.callback_query:
        query = update.callback_query
        await query.answer("🔄 Solicitando Clear Build Cache & Deploy...")
        msg = query.message
    else:
        msg = await update.message.reply_text("🔄 Solicitando Clear Build Cache & Deploy no Render...")

    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # CORRIGIDO: A API do Render exige a string "clear" em vez de true
    payload = {
        "clearCache": "clear"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status in [200, 201]:
                    data = await response.json()
                    deploy_id = data.get("deploy", {}).get("id", "Desconhecido")
                    texto_sucesso = f"✅ **Clear Build Cache & Deploy disparado com sucesso!**\n\nID do Deploy: `{deploy_id}`\nO Render já está compilando do zero."
                    if update.callback_query:
                        await msg.edit_text(texto_sucesso, parse_mode="Markdown")
                    else:
                        await msg.edit_text(texto_sucesso, parse_mode="Markdown")
                else:
                    erro_texto = await response.text()
                    texto_falha = f"❌ Erro ao comunicar com a API do Render:\n`{erro_texto}`"
                    if update.callback_query:
                        await msg.edit_text(texto_falha, parse_mode="Markdown")
                    else:
                        await msg.edit_text(texto_falha, parse_mode="Markdown")
    except Exception as e:
        texto_ex = f"❌ Erro interno ao executar o comando: {e}"
        if update.callback_query:
            await msg.edit_text(texto_ex)
        else:
            await msg.edit_text(texto_ex)

async def cmd_clear_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await executar_clear_deploy(update, context)

def registrar_deploy(app):
    app.add_handler(CommandHandler("cleardeploy", cmd_clear_deploy))
