import os
import json
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

ARQUIVO_ESTADO_DEPLOY = "deploy_status.json"

async def checar_deploy_pendente_ao_iniciar(application):
    """Função chamada logo após o bot ligar para verificar se há um deploy pendente"""
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
                chat_id=chat_id,
                message_id=message_id,
                text=f"✅ **Deploy Concluído com Sucesso!**\n\nID: `{deploy_id}`\nO bot foi reiniciado e já está online.",
                parse_mode="Markdown"
            )
    except Exception:
        pass
    finally:
        if os.path.exists(ARQUIVO_ESTADO_DEPLOY):
            os.remove(ARQUIVO_ESTADO_DEPLOY)

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
    
    payload = {
        "clearCache": "clear"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status in [200, 201]:
                    data = await response.json()
                    deploy_data = data.get("deploy", data)
                    deploy_id = deploy_data.get("id") or data.get("id", "Desconhecido")
                    
                    with open(ARQUIVO_ESTADO_DEPLOY, "w", encoding="utf-8") as f:
                        json.dump({
                            "chat_id": msg.chat_id, 
                            "message_id": msg.message_id, 
                            "deploy_id": deploy_id
                        }, f)

                    texto_inicial = f"🔄 **Clear Build Cache & Deploy disparado!**\n\nID: `{deploy_id}`\nO Render está compilando. O bot vai se atualizar assim que religar..."
                    
                    await msg.edit_text(texto_inicial, parse_mode="Markdown")
                else:
                    erro_texto = await response.text()
                    texto_falha = f"❌ Erro ao comunicar com a API do Render:\n`{erro_texto}`"
                    await msg.edit_text(texto_falha, parse_mode="Markdown")
    except Exception as e:
        texto_ex = f"❌ Erro interno ao executar o comando: {e}"
        await msg.edit_text(texto_ex)

async def cmd_clear_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await executar_clear_deploy(update, context)

def registrar_deploy(app):
    app.add_handler(CommandHandler("cleardeploy", cmd_clear_deploy))
    
    # Maneira segura e nativa do PTB v20+ de rodar funções assíncronas logo na inicialização sem erro de event loop
    if app.job_queue:
        app.job_queue.run_once(lambda ctx: asyncio.create_task(checar_deploy_pendente_ao_iniciar(app)), when=1)
