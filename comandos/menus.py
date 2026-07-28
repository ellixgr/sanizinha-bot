from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def menu_membros_handler(update, context):
    query = update.callback_query
    await query.answer()
    
    texto_membros = (
        "📜 **Comandos para Membros:**\n\n"
        "🏓 `/ping` - Status de hardware, RAM e latência\n"
        "👤 `/perfil` - Suas estatísticas completas, bio e mídias\n"
        "🆔 `/id` - Mostra seu ID e do chat\n"
        "📥 `/play` ou `/dl` - Baixa vídeos e músicas do YouTube"
    )
    
    teclado_membros = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏓 Ping", callback_data="botao_ping"), InlineKeyboardButton("👤 Perfil", callback_data="menu_perfil_atalho")],
        [InlineKeyboardButton("🆔 ID", callback_data="menu_id_atalho"), InlineKeyboardButton("🎮 Jogos", callback_data="menu_jogos_atalho")],
        [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]
    ])
    
    await query.message.edit_text(texto_membros, reply_markup=teclado_membros, parse_mode="Markdown")

async def menu_adm_handler(update, context):
    query = update.callback_query
    await query.answer()
    
    texto_adm = (
        "🛡️ **Comandos para Administradores:**\n\n"
        "🔨 `/ban` - Bane o usuário respondido\n"
        "🔇 `/mutar` / `/desmutar` - Silencia ou libera o usuário\n"
        "⭐ `/promover` - Promove a administrador\n"
        "📉 `/rebaixar` - Rebaixa administrador\n"
        "📢 `/marcar` - Marca todos do grupo\n"
        "📌 `/citar` - Cita mídias/textos marcando todos\n"
        "⚙️ `/protecao` - Configura as travas de segurança\n"
        "👋 Configurar Bem-Vindo abaixo:"
    )
    
    teclado_adm = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ Proteções do Grupo", callback_data="menu_protecoes")],
        [InlineKeyboardButton("👋 Configurar Bem-Vindo", callback_data="config_bemvindo")],
        [InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu")]
    ])
    
    await query.message.edit_text(texto_adm, reply_markup=teclado_adm, parse_mode="Markdown")
