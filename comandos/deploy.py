import os
import json
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

ARQUIVO_ESTADO_DEPLOY = "deploy_status.json"

async def checar_deploy_pendente_ao_iniciar(bot):
    """Função chamada logo após o bot ligar para avisar que o deploy terminou"""
    if not os.path.exists(ARQUIVO_ESTADO_DEPLOY):
        return

    # Aguarda 3 segundos para garantir que o bot está totalmente conectado
    await asyncio.sleep(3)

    try:
        with open(ARQUIVO_ESTADO_DEPLOY, "r", encoding="utf-8") as f:
            dados = json.load(f)
        
        chat_id = dados.get("chat_id")
        message_id = dados.get("message_id")
        deploy_id = dados.get("deploy_id")

        if chat_id and message_id:
            await bot.edit_message_text(
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

async def monitorar_status_deploy(bot, chat_id, message_id, api_key, service_id, deploy_id):
    url = f"https://api.render.com/v1/services/{service_id}/deploys/{deploy_id}"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    await asyncio.sleep(5)

    tentativas_max = 60
    tentativa = 0
    ja_avisou_building = False

    async with aiohttp.ClientSession() as session:
        while tentativa < tentativas_max:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        deploy_info = data.get("deploy", data)
                        status = deploy_info.get("status")

                        if status == "building" and not ja_avisou_building:
                            ja_avisou_building = True
                            try:
                                await bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=message_id,
                                    text=f"🚀 **Deploy Iniciado no Render!**\n\nID: `{deploy_id}`\nO código está sendo compilado...",
                                    parse_mode="Markdown"
                                )
                            except Exception:
                                pass

                        elif status == "live":
                            with open(ARQUIVO_ESTADO_DEPLOY, "w", encoding="utf-8") as f:
                                json.dump({"chat_id": chat_id, "message_id": message_id, "deploy_id": deploy_id}, f)
                            break

                        elif status in ["build_failed", "canceled", "update_failed"]:
                            try:
                                await bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=message_id,
                                    text=f"❌ **O Deploy Falhou!**\n\nID: `{deploy_id}`\nStatus no Render: `{status}`",
                                    parse_mode="Markdown"
                                )
                            except Exception:
                                pass
                            break
            except Exception:
                pass

            tentativa += 1
            await asyncio.sleep(10)

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
                    
                    texto_inicial = f"🔄 **Clear Build Cache & Deploy disparado!**\n\nID do Deploy: `{deploy_id}`\nAguardando o Render iniciar a compilação..."
                    
                    if update.callback_query:
                        await msg.edit_text(texto_inicial, parse_mode="Markdown")
                    else:
                        msg = await msg.edit_text(texto_inicial, parse_mode="Markdown")

                    context.application.create_task(
                        monitorar_status_deploy(
                            context.bot,
                            msg.chat_id,
                            msg.message_id,
                            api_key,
                            service_id,
                            deploy_id
                        )
                    )
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
    
    # Dispara a verificação logo que o bot inicializa de forma segura via create_task
    app.create_task(checar_deploy_pendente_ao_iniciar(app.bot))
