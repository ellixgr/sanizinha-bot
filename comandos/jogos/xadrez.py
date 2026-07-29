from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from pymongo import MongoClient
import os
import random

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
xadrez_db = db["jogo_xadrez"]

# ==============================================
# 🎲 FUNÇÕES AUXILIARES E REGRAS DO XADREZ OFICIAL
# ==============================================
def criar_tabuleiro():
    return [
        ["♜","♞","♝","♛","♚","♝","♞","♜"],
        ["♟","♟","♟","♟","♟","♟","♟","♟"],
        [" "," "," "," "," "," "," "," "],
        [" "," "," "," "," "," "," "," "],
        [" "," "," "," "," "," "," "," "],
        [" "," "," "," "," "," "," "," "],
        ["♙","♙","♙","♙","♙","♙","♙","♙"],
        ["♖","♘","♗","♕","♔","♗","♘","♖"]
    ]

def eh_posicao_valida(l, c):
    return 0 <= l < 8 and 0 <= c < 8

def cor_peca(p):
    if p == " ": return None
    return "branca" if p.isupper() else "preta"

def movimento_valido(tab, l1, c1, l2, c2, roque_permitido=True, en_passant_alvo=None):
    p = tab[l1][c1]
    if p == " ": return False
    cor = cor_peca(p)
    alvo = tab[l2][c2]
    if alvo != " " and cor_peca(alvo) == cor: return False

    dl = l2 - l1
    dc = c2 - c1
    peca = p.lower()

    # PEÃO
    if peca == "p":
        dirc = -1 if cor == "branca" else 1
        if dc == 0 and tab[l2][c2] == " ":
            if dl == dirc: return True
            if (l1 in (1,6)) and dl == 2*dirc and tab[l1+dirc][c1] == " ": return True
        if abs(dc) == 1 and dl == dirc:
            if alvo != " " and cor_peca(alvo) != cor: return True
            if en_passant_alvo == (l2,c2): return True
        return False

    # TORRE
    if peca == "r":
        if dl !=0 and dc !=0: return False
        passo_l = 0 if dl==0 else (1 if dl>0 else -1)
        passo_c = 0 if dc==0 else (1 if dc>0 else -1)
        cl, cc = l1+passo_l, c1+passo_c
        while (cl,cc) != (l2,c2):
            if tab[cl][cc] != " ": return False
            cl += passo_l; cc += passo_c
        return True

    # CAVALO
    if peca == "n":
        return (abs(dl),abs(dc)) in [(1,2),(2,1)]

    # BISPO
    if peca == "b":
        if abs(dl) != abs(dc): return False
        passo_l = 1 if dl>0 else -1
        passo_c = 1 if dc>0 else -1
        cl, cc = l1+passo_l, c1+passo_c
        while (cl,cc) != (l2,c2):
            if tab[cl][cc] != " ": return False
            cl += passo_l; cc += passo_c
        return True

    # RAINHA
    if peca == "q":
        if dl !=0 and dc !=0 and abs(dl)!=abs(dc): return False
        if dl ==0: passo_l=0
        elif dl>0: passo_l=1
        else: passo_l=-1
        if dc ==0: passo_c=0
        elif dc>0: passo_c=1
        else: passo_c=-1
        cl, cc = l1+passo_l, c1+passo_c
        while (cl,cc) != (l2,c2):
            if tab[cl][cc] != " ": return False
            cl += passo_l; cc += passo_c
        return True

    # REI
    if peca == "k":
        if abs(dl) <=1 and abs(dc) <=1: return True
        if roque_permitido and dl==0 and abs(dc)==2:
            if esta_em_xeque(tab, cor): return False
            col_torre = 0 if dc<0 else 7
            if any(tab[l1][c]!=" " for c in range(min(c1,col_torre)+1, max(c1,col_torre))): return False
            if esta_em_xeque(tab, cor, l1,c1+dc//2): return False
            return True
        return False
    return False

def copiar_tabuleiro(tab):
    return [linha.copy() for linha in tab]

def encontrar_rei(tab, cor):
    rei = "♔" if cor=="branca" else "♚"
    for l in range(8):
        for c in range(8):
            if tab[l][c] == rei:
                return (l,c)
    return None

def esta_em_xeque(tab, cor, posicao_rei=None):
    rei = posicao_rei or encontrar_rei(tab, cor)
    if not rei: return False
    l_r, c_r = rei
    cor_op = "preta" if cor=="branca" else "branca"
    for l in range(8):
        for c in range(8):
            if cor_peca(tab[l][c]) == cor_op:
                if movimento_valido(tab, l,c, l_r,c_r, roque_permitido=False):
                    return True
    return False

def movimento_deixa_em_xeque(tab, l1,c1,l2,c2,cor):
    novo_tab = copiar_tabuleiro(tab)
    novo_tab[l2][c2] = novo_tab[l1][c1]
    novo_tab[l1][c1] = " "
    return esta_em_xeque(novo_tab, cor)

def listar_movimentos_validos(tab, cor, roque=True, en_passant=None):
    movs = []
    for l1 in range(8):
        for c1 in range(8):
            if cor_peca(tab[l1][c1]) != cor: continue
            for l2 in range(8):
                for c2 in range(8):
                    if movimento_valido(tab,l1,c1,l2,c2, roque, en_passant) and not movimento_deixa_em_xeque(tab,l1,c1,l2,c2,cor):
                        movs.append((l1,c1,l2,c2))
    return movs

def verificar_fim_jogo(tab, cor_turno, roque_branco, roque_preto, contador_50, historico_pos):
    movs = listar_movimentos_validos(tab, cor_turno)
    if esta_em_xeque(tab, cor_turno):
        if not movs: return "xeque_mate"
    else:
        if not movs: return "afogamento"
    if contador_50 >= 100: return "regra_50"
    from collections import Counter
    cont = Counter(historico_pos)
    if any(v>=3 for v in cont.values()): return "repeticao"
    return None

def tab_para_texto(tab):
    return "|".join("".join(l) for l in tab)

# ==============================================
# 🎮 SISTEMA DO JOGO (MESMA ESTRUTURA DO VELHA.PY)
# ==============================================
def setup_xadrez(app: Application):
    app.add_handler(CommandHandler("xadrez", cmd_xadrez))
    app.add_handler(CallbackQueryHandler(menu_xadrez_handler, pattern="^jogo_xadrez$"))
    app.add_handler(CallbackQueryHandler(tratar_botoes_xadrez, pattern="^x_"))
    app.add_handler(CallbackQueryHandler(jogada_xadrez, pattern="^xpos_"))

async def cmd_xadrez(update: Update, context):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando de desafio PvP deve ser usado dentro de grupos!")
        return

    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Para jogar PvP com amigos use /xadrez @usuario ou marque alguém respondendo a mensagem dele!", parse_mode="Markdown")
        return

    desafiado = reply.from_user
    if desafiado.id == user.id:
        await update.message.reply_text("❌ Você não pode desafiar a si mesmo!", parse_mode="Markdown")
        return
    
    # MODO CONTRA IA
    if desafiado.is_bot:
        tab = criar_tabuleiro()
        xadrez_db.update_one(
            {"chat_id": chat.id},
            {"$set": {
                "chat_id": chat.id,
                "tabuleiro": tab,
                "turno": user.id,
                "modo": "ia",
                "brancas": user.id,
                "pretas": "IA",
                "status": "ativo",
                "roque_branco": True,
                "roque_preto": True,
                "en_passant": None,
                "contador_50": 0,
                "historico": [tab_para_texto(tab)],
                "voto_revanche": []
            }}, upsert=True
        )
        botoes = gerar_botoes_tabuleiro(tab)
        await update.message.reply_text(
            f"♟️ Jogo contra a Máquina iniciado por {user.mention_markdown()}! Você joga com as **Brancas**, sua vez!\n*(Apenas você pode jogar nesta partida)*",
            reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown"
        )
        return

    # DESAFIO PvP
    xadrez_db.update_one(
        {"chat_id": chat.id},
        {"$set": {
            "chat_id": chat.id,
            "desafiante_id": user.id,
            "desafiante_nome": user.first_name,
            "desafiado_id": desafiado.id,
            "desafiado_nome": desafiado.first_name,
            "status": "pendente",
            "voto_revanche": []
        }}, upsert=True
    )
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ACEITAR", callback_data="x_aceitar"), InlineKeyboardButton("❌ RECUSAR", callback_data="x_recusar")],
        [InlineKeyboardButton("🚫 CANCELAR", callback_data="x_cancelar")]
    ])
    await update.message.reply_text(
        f"♟️ **DESAFIO DE XADREZ** ♟️\n\n"
        f"@{user.username or user.first_name} te desafiou para uma partida oficial, {desafiado.mention_markdown()}!\n\nVocê aceita?",
        reply_markup=teclado, parse_mode="Markdown"
    )

async def menu_xadrez_handler(update: Update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()
    if xadrez_db.find_one({"chat_id": chat_id, "status": "ativo"}):
        await query.answer("⚠️ Já existe uma partida ativa neste grupo!", show_alert=True)
        return
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Jogar PvP", callback_data="x_infopvp")],
        [InlineKeyboardButton("🤖 Jogar Contra a Máquina", callback_data="x_modoia")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text("♟️ **Xadrez Oficial**\nEscolha o modo de jogo:", reply_markup=teclado, parse_mode="Markdown")

def gerar_botoes_tabuleiro(tab):
    botoes = []
    for l in range(8):
        linha = []
        for c in range(8):
            linha.append(InlineKeyboardButton(tab[l][c], callback_data=f"xpos_{l}_{c}"))
        botoes.append(linha)
    botoes.append([InlineKeyboardButton("🚫 Cancelar Partida", callback_data="x_cancelar")])
    return botoes

async def tratar_botoes_xadrez(update: Update, context):
    query = update.callback_query
    d = query.data
    chat_id = query.message.chat_id
    uid = update.effective_user.id
    estado = xadrez_db.find_one({"chat_id": chat_id})

    if d == "x_infopvp":
        await query.answer("Para jogar PvP use /xadrez @usuario ou marque alguém com o comando!", show_alert=True)
        return

    if d == "x_modoia":
        if estado and estado.get("status") == "ativo":
            await query.answer("⚠️ Já existe partida em andamento!", show_alert=True)
            return
        tab = criar_tabuleiro()
        xadrez_db.update_one({"chat_id": chat_id}, {"$set": {
            "tabuleiro": tab, "turno": uid, "modo": "ia", "brancas": uid, "pretas": "IA", "status": "ativo",
            "roque_branco": True, "roque_preto": True, "en_passant": None, "contador_50":0, "historico":[tab_para_texto(tab)], "voto_revanche":[]
        }}, upsert=True)
        await query.answer()
        await query.message.edit_text("♟️ **Contra IA iniciado!** Você é as Brancas, sua vez!", reply_markup=InlineKeyboardMarkup(gerar_botoes_tabuleiro(tab)), parse_mode="Markdown")
        return

    if d == "x_aceitar":
        if not estado or estado["status"]!="pendente" or uid!=estado["desafiado_id"]:
            await query.answer("Convite inválido ou expirado!", show_alert=True)
            return
        tab = criar_tabuleiro()
        xadrez_db.update_one({"chat_id": chat_id}, {"$set": {
            "tabuleiro": tab, "turno": estado["desafiante_id"], "modo": "pvp",
            "brancas": estado["desafiante_id"], "pretas": estado["desafiado_id"], "status": "ativo",
            "roque_branco": True, "roque_preto": True, "en_passant": None, "contador_50":0, "historico":[tab_para_texto(tab)], "voto_revanche":[]
        }})
        await query.answer()
        await atualizar_tabuleiro_xadrez(query, tab, f"Partida iniciada! Vez de {estado['desafiante_nome']} (Brancas)")
        return

    if d == "x_recusar":
        if not estado or uid!=estado["desafiado_id"]:
            await query.answer("Sem permissão!", show_alert=True)
            return
        xadrez_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("❌ Desafio recusado!", parse_mode="Markdown")
        return

    if d == "x_cancelar":
        if not estado:
            await query.answer("Nenhuma partida ativa!", show_alert=True)
            return
        dono = int(os.environ.get("DONO_ID",0))
        jogadores = [estado.get("brancas"), estado.get("pretas"), estado.get("desafiante_id"), estado.get("desafiado_id")]
        if uid not in jogadores and uid != dono:
            await query.answer("Apenas participantes ou dono podem cancelar!", show_alert=True)
            return
        xadrez_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("🚫 Partida cancelada!", parse_mode="Markdown")
        return

    if d == "x_reiniciar":
        if not estado: return await query.answer("Jogo não encontrado!", show_alert=True)
        modo = estado["modo"]
        if modo == "ia":
            if uid != estado["brancas"]: return await query.answer("Você não joga essa partida!", show_alert=True)
            tab = criar_tabuleiro()
            xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"tabuleiro":tab,"turno":uid,"status":"ativo","contador_50":0,"historico":[tab_para_texto(tab)],"voto_revanche":[]}})
            await atualizar_tabuleiro_xadrez(query, tab, "Novo jogo contra IA! Sua vez (Brancas)")
            return
        if modo == "pvp":
            if uid not in [estado["brancas"], estado["pretas"]]: return await query.answer("Apenas jogadores podem pedir revanche!", show_alert=True)
            votos = estado.get("voto_revanche",[])
            if uid in votos: return await query.answer("Você já votou!", show_alert=True)
            votos.append(uid)
            if len(votos)>=2:
                tab = criar_tabuleiro()
                novo_turno = estado["pretas"]
                xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"tabuleiro":tab,"turno":novo_turno,"brancas":estado["pretas"],"pretas":estado["brancas"],"status":"ativo","contador_50":0,"historico":[tab_para_texto(tab)],"voto_revanche":[]}})
                await atualizar_tabuleiro_xadrez(query, tab, "Revanche iniciada! Agora você trocou de cor, vez do adversário!")
            else:
                xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"voto_revanche":votos}})
                await query.answer("Voto registrado! Aguardando o outro jogador...")
                await query.message.edit_text("⏳ Aguardando o adversário aceitar a revanche...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 ACEITAR REVANCHE", callback_data="x_reiniciar")],[InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]]), parse_mode="Markdown")
        return

async def jogada_xadrez(update: Update, context):
    query = update.callback_query
    dados = query.data.split("_")
    l1, c1, l2, c2 = map(int, dados[1:]) if len(dados)==5 else None
    chat_id = query.message.chat_id
    uid = update.effective_user.id
    estado = xadrez_db.find_one({"chat_id": chat_id})
    if not estado or estado["status"]!="ativo":
        return await query.answer("Partida não encontrada!", show_alert=True)

    tab = estado["tabuleiro"]
    cor_turno = "branca" if uid == estado["brancas"] else "preta"
    if uid != estado["turno"]:
        return await query.answer("Não é a sua vez!", show_alert=True)
    if cor_peca(tab[l1][c1]) != cor_turno:
        return await query.answer("Escolha uma peça sua!", show_alert=True)
    if not movimento_valido(tab,l1,c1,l2,c2, estado["roque_branco"] if cor_turno=="branca" else estado["roque_preto"], estado["en_passant"]):
        return await query.answer("Movimento inválido!", show_alert=True)
    if movimento_deixa_em_xeque(tab,l1,c1,l2,c2,cor_turno):
        return await query.answer("Você não pode se colocar em xeque!", show_alert=True)

    # EXECUTA MOVIMENTO
    peca = tab[l1][c1]
    capturou = tab[l2][c2] != " "
    tab[l2][c2] = peca
    tab[l1][c1] = " "
    novo_en_passant = None
    novo_roque_b = estado["roque_branco"]
    novo_roque_p = estado["roque_preto"]

    # REGRAS ESPECIAIS
    if peca.lower() == "p" and abs(l2-l1)==2:
        novo_en_passant = ((l1+l2)//2, c1)
    if peca.lower() == "p" and estado["en_passant"] == (l2,c2):
        tab[l1][c2] = " "
        capturou = True
    if peca == "♔":
        novo_roque_b = False
        if abs(c2-c1)==2: tab[7][5 if c2>c1 else 3], tab[7][7 if c2>c1 else 0] = tab[7][7 if c2>c1 else 0], " "
    if peca == "♚":
        novo_roque_p = False
        if abs(c2-c1)==2: tab[0][5 if c2>c1 else 3], tab[0][7 if c2>c1 else 0] = tab[0][7 if c2>c1 else 0], " "
    if peca.lower() == "p" and l2 in (0,7):
        tab[l2][c2] = "♕" if cor_turno=="branca" else "♛"
    if peca in ("♔","♖"): novo_roque_b=False
    if peca in ("♚","♜"): novo_roque_p=False

    # CONTADOR E HISTÓRICO
    novo_contador = 0 if capturou or peca.lower()=="p" else estado["contador_50"]+1
    historico = estado["historico"] + [tab_para_texto(tab)]
    prox_cor = "preta" if cor_turno=="branca" else "branca"
    prox_uid = estado["pretas"] if cor_turno=="branca" else estado["brancas"]

    # FIM DE JOGO
    fim = verificar_fim_jogo(tab, prox_cor, novo_roque_b, novo_roque_p, novo_contador, historico)
    if fim:
        xadrez_db.delete_one({"chat_id": chat_id})
        await finalizar_xadrez(query, tab, fim, estado)
        return

    # CONTRA IA - JOGADA AUTOMÁTICA
    if estado["modo"] == "ia" and prox_uid == "IA":
        movs_ia = listar_movimentos_validos(tab, "preta", novo_roque_p, novo_en_passant)
        if movs_ia:
            l1i,c1i,l2i,c2i = random.choice(movs_ia)
            tab[l2i][c2i] = tab[l1i][c1i]
            tab[l1i][c1i] = " "
            if tab[l2i][c2i].lower()=="p" and l2i==7: tab[l2i][c2i] = "♛"
            fim_ia = verificar_fim_jogo(tab, "branca", novo_roque_b, novo_roque_p, 0, historico+[tab_para_texto(tab)])
            if fim_ia:
                xadrez_db.delete_one({"chat_id": chat_id})
                await finalizar_xadrez(query, tab, fim_ia, estado)
                return
            await atualizar_tabuleiro_xadrez(query, tab, "Sua vez (Brancas)")
            return

    # SALVA E ATUALIZA
    xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"tabuleiro":tab,"turno":prox_uid,"roque_branco":novo_roque_b,"roque_preto":novo_roque_p,"en_passant":novo_en_passant,"contador_50":novo_contador,"historico":historico}})
    txt = f"Xeque! Vez das {'Brancas' if prox_cor=='branca' else 'Pretas'}" if esta_em_xeque(tab, prox_cor) else f"Vez das {'Brancas' if prox_cor=='branca' else 'Pretas'}"
    await atualizar_tabuleiro_xadrez(query, tab, txt)

async def atualizar_tabuleiro_xadrez(query, tab, status):
    await query.message.edit_text(f"♟️ **Xadrez**\n📌 {status}", reply_markup=InlineKeyboardMarkup(gerar_botoes_tabuleiro(tab)), parse_mode="Markdown")

async def finalizar_xadrez(query, tab, motivo, estado):
    msgs = {
        "xeque_mate": f"🏆 **XEQUE-MATE!** {'Brancas' if estado['turno']==estado['pretas'] else 'Pretas'} vencem!",
        "afogamento": "🤝 **EMPATE - Afogamento!** O rei não está em xeque mas não tem movimentos válidos.",
        "regra_50": "🤝 **EMPATE - Regra dos 50 lances!** Nenhuma captura ou movimento de peão em 50 lances.",
        "repeticao": "🤝 **EMPATE - Repetição tripla!** A mesma posição ocorreu 3 vezes."
    }
    botoes = gerar_botoes_tabuleiro(tab)[:-1]
    botoes.extend([[InlineKeyboardButton("🎮 JOGAR DE NOVO", callback_data="x_reiniciar")],[InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]])
    await query.message.edit_text(f"♟️ **FIM DA PARTIDA**\n\n{msgs[motivo]}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
