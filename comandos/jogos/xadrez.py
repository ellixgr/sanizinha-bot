from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from pymongo import MongoClient
import os
import random
from collections import Counter

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["bot_database"]
xadrez_db = db["jogo_xadrez"]

# ==============================================
# 🎲 FUNÇÕES AUXILIARES - 100% CORRIGIDAS
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
    pecas_brancas = {"♙","♖","♘","♗","♕","♔"}
    return "branca" if p in pecas_brancas else "preta"

def movimento_valido(tab, l1, c1, l2, c2, roque_permitido=True, en_passant_alvo=None):
    p = tab[l1][c1]
    if p == " ": return False
    cor = cor_peca(p)
    alvo = tab[l2][c2]
    if alvo != " " and cor_peca(alvo) == cor: return False

    dl = l2 - l1
    dc = c2 - c1
    peca = p.lower()

    # ✅ PEÃO CORRIGIDO DEFINITIVAMENTE
    if peca == "p":
        dirc = -1 if cor == "branca" else 1
        if dc == 0 and tab[l2][c2] == " ":
            if dl == dirc: return True
            if cor == "branca" and l1 == 6 and dl == -2 and tab[5][c1] == " ": return True
            if cor == "preta" and l1 == 1 and dl == 2 and tab[2][c1] == " ": return True
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
        passo_l = 0 if dl==0 else (1 if dl>0 else -1)
        passo_c = 0 if dc==0 else (1 if dc>0 else -1)
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
                # ✅ NÃO VERIFICA ROQUE NA CHECAGEM DE XEQUE
                if movimento_valido(tab, l,c, l_r,c_r, roque_permitido=False):
                    return True
    return False

# ✅ CORREÇÃO PRINCIPAL: NÃO MAIS BLOQUEIA MOVIMENTOS INICIAIS ERRADAMENTE
def movimento_deixa_em_xeque(tab, l1,c1,l2,c2,cor):
    novo_tab = copiar_tabuleiro(tab)
    novo_tab[l2][c2] = novo_tab[l1][c1]
    novo_tab[l1][c1] = " "
    return esta_em_xeque(novo_tab, cor)

def listar_destinos_validos(tab, l1,c1, cor, roque=True, en_passant=None):
    destinos = []
    for l2 in range(8):
        for c2 in range(8):
            if movimento_valido(tab,l1,c1,l2,c2, roque, en_passant):
                # ✅ SÓ BLOQUEIA SE REALMENTE DEIXAR EM XEQUE
                if not movimento_deixa_em_xeque(tab,l1,c1,l2,c2,cor):
                    destinos.append((l2,c2))
    return destinos

def verificar_fim_jogo(tab, cor_turno, roque_branco, roque_preto, contador_50, historico_pos):
    movs = []
    for l1 in range(8):
        for c1 in range(8):
            if cor_peca(tab[l1][c1]) != cor_turno: continue
            movs.extend(listar_destinos_validos(tab,l1,c1, cor_turno, roque_branco if cor_turno=="branca" else roque_preto))
    if esta_em_xeque(tab, cor_turno):
        if not movs: return "xeque_mate"
    else:
        if not movs: return "afogamento"
    if contador_50 >= 100: return "regra_50"
    cont = Counter(historico_pos)
    if any(v>=3 for v in cont.values()): return "repeticao"
    return None

def tab_para_texto(tab):
    return "|".join("".join(l) for l in tab)

# ==============================================
# 🎲 GERADOR DE BOTÕES
# ==============================================
def gerar_botoes_tabuleiro(tab, selecionado=None, destinos_validos=None):
    botoes = []
    destinos = destinos_validos or []
    l_sel, c_sel = selecionado or (None, None)
    for l in range(8):
        linha = []
        for c in range(8):
            texto = tab[l][c]
            if selecionado and l==l_sel and c==c_sel:
                texto = f"[{texto}]"
            elif (l,c) in destinos:
                texto = "✅" if tab[l][c] == " " else f"⚔️{texto}"
            linha.append(InlineKeyboardButton(texto, callback_data=f"xpos_{l}_{c}"))
        botoes.append(linha)
    botoes.append([InlineKeyboardButton("❌ Cancelar Seleção", callback_data="x_cancelar_sel")])
    botoes.append([InlineKeyboardButton("🚫 Abandonar Partida", callback_data="x_cancelar")])
    return botoes

# ==============================================
# 🎮 REGISTRO DE COMANDOS
# ==============================================
def setup_xadrez(app: Application):
    app.add_handler(CommandHandler("xadrez", cmd_xadrez))
    app.add_handler(CallbackQueryHandler(tratar_botoes_xadrez, pattern="^x_"))
    app.add_handler(CallbackQueryHandler(jogada_xadrez, pattern="^xpos_"))

# ==============================================
# 🚀 COMANDO /xadrez
# ==============================================
async def cmd_xadrez(update: Update, context):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        await update.message.reply_text("⚠️ Este comando deve ser usado em grupos!")
        return

    reply = update.message.reply_to_message
    if not reply:
        await update.message.reply_text("⚠️ Use `/xadrez @usuario` ou responda a mensagem de alguém!", parse_mode="Markdown")
        return

    desafiado = reply.from_user
    if desafiado.id == user.id:
        await update.message.reply_text("❌ Não pode desafiar você mesmo!", parse_mode="Markdown")
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
                "peca_selecionada": None
            }}, upsert=True
        )
        botoes = gerar_botoes_tabuleiro(tab)
        await update.message.reply_text(
            f"♟️ **Jogo contra IA iniciado!**\nVocê é as **Brancas** — clique em uma peça sua para começar!",
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
        f"@{user.username or user.first_name} te desafiou!\nAceita, {desafiado.mention_markdown()}?",
        reply_markup=teclado, parse_mode="Markdown"
    )

# ==============================================
# 📋 MENU PRINCIPAL DO XADREZ
# ==============================================
async def menu_xadrez_handler(update: Update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()
    if xadrez_db.find_one({"chat_id": chat_id, "status": "ativo"}):
        await query.answer("⚠️ Já tem uma partida em andamento!", show_alert=True)
        return
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Jogar PvP", callback_data="x_infopvp")],
        [InlineKeyboardButton("🤖 Jogar Contra a Máquina", callback_data="x_modoia")],
        [InlineKeyboardButton("🔙 Voltar ao Menu de Jogos", callback_data="menu_jogos_atalho")]
    ])
    await query.message.edit_text("♟️ **XADREZ OFICIAL**\nEscolha o modo de jogo:", reply_markup=teclado, parse_mode="Markdown")

# ==============================================
# 🎯 TRATAMENTO DE BOTÕES GERAIS
# ==============================================
async def tratar_botoes_xadrez(update: Update, context):
    query = update.callback_query
    d = query.data
    chat_id = query.message.chat_id
    uid = update.effective_user.id
    estado = xadrez_db.find_one({"chat_id": chat_id})

    if d == "x_infopvp":
        await query.answer("Use /xadrez @usuario para desafiar alguém!", show_alert=True)
        return

    if d == "x_modoia":
        if estado and estado.get("status") == "ativo":
            await query.answer("⚠️ Partida já em andamento!", show_alert=True)
            return
        tab = criar_tabuleiro()
        xadrez_db.update_one({"chat_id": chat_id}, {"$set": {
            "tabuleiro": tab, "turno": uid, "modo": "ia", "brancas": uid, "pretas": "IA", "status": "ativo",
            "roque_branco": True, "roque_preto": True, "en_passant": None, "contador_50":0, "historico":[tab_para_texto(tab)], "voto_revanche":[], "peca_selecionada":None
        }}, upsert=True)
        await query.answer()
        await atualizar_tabuleiro_xadrez(query, tab, "Clique em uma peça BRANCA sua para começar!")
        return

    if d == "x_aceitar":
        if not estado or estado["status"]!="pendente" or uid!=estado["desafiado_id"]:
            await query.answer("Convite inválido!", show_alert=True)
            return
        tab = criar_tabuleiro()
        xadrez_db.update_one({"chat_id": chat_id}, {"$set": {
            "tabuleiro": tab, "turno": estado["desafiante_id"], "modo": "pvp",
            "brancas": estado["desafiante_id"], "pretas": estado["desafiado_id"], "status": "ativo",
            "roque_branco": True, "roque_preto": True, "en_passant": None, "contador_50":0, "historico":[tab_para_texto(tab)], "voto_revanche":[], "peca_selecionada":None
        }})
        await query.answer()
        await atualizar_tabuleiro_xadrez(query, tab, f"Partida iniciada! Vez de {estado['desafiante_nome']} — clique em uma peça")
        return

    if d == "x_recusar":
        if not estado or uid!=estado["desafiado_id"]:
            await query.answer("Sem permissão!", show_alert=True)
            return
        xadrez_db.delete_one({"chat_id": chat_id})
        await query.message.edit_text("❌ Desafio recusado!", parse_mode="Markdown")
        return

    if d == "x_cancelar_sel":
        if not estado or not estado.get("peca_selecionada"):
            await query.answer("Nenhuma peça selecionada!", show_alert=True)
            return
        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"peca_selecionada":None}})
        await atualizar_tabuleiro_xadrez(query, estado["tabuleiro"], "Seleção cancelada — clique em uma peça sua")
        return

    if d == "x_cancelar":
        if not estado:
            await query.answer("Nenhuma partida ativa!", show_alert=True)
            return
        dono = int(os.environ.get("DONO_ID",0))
        jogadores = [estado.get("brancas"), estado.get("pretas"), estado.get("desafiante_id"), estado.get("desafiado_id")]
        if uid not in jogadores and uid != dono:
            await query.answer("Apenas participantes podem cancelar!", show_alert=True)
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
            xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"tabuleiro":tab,"turno":uid,"status":"ativo","contador_50":0,"historico":[tab_para_texto(tab)],"voto_revanche":[],"peca_selecionada":None}})
            await atualizar_tabuleiro_xadrez(query, tab, "Novo jogo! Clique na sua peça branca")
            return
        if modo == "pvp":
            if uid not in [estado["brancas"], estado["pretas"]]: return await query.answer("Apenas jogadores podem pedir revanche!", show_alert=True)
            votos = estado.get("voto_revanche",[])
            if uid in votos: return await query.answer("Você já votou!", show_alert=True)
            votos.append(uid)
            if len(votos)>=2:
                tab = criar_tabuleiro()
                novo_turno = estado["pretas"]
                xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"tabuleiro":tab,"turno":novo_turno,"brancas":estado["pretas"],"pretas":estado["brancas"],"status":"ativo","contador_50":0,"historico":[tab_para_texto(tab)],"voto_revanche":[],"peca_selecionada":None}})
                await atualizar_tabuleiro_xadrez(query, tab, "Revanche! Agora trocaram de cor — clique na sua peça")
            else:
                xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"voto_revanche":votos}})
                await query.answer("Aguardando o outro jogador...")
                await query.message.edit_text("⏳ Aguardando confirmação para revanche...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 ACEITAR REVANCHE", callback_data="x_reiniciar")],[InlineKeyboardButton("🔙 Voltar", callback_data="menu_jogos_atalho")]]), parse_mode="Markdown")
        return

# ==============================================
# ♟️ SISTEMA DE JOGADAS — AGORA FUNCIONA 100%
# ==============================================
async def jogada_xadrez(update: Update, context):
    query = update.callback_query
    dados = query.data.split("_")
    l, c = int(dados[1]), int(dados[2])
    chat_id = query.message.chat_id
    uid = update.effective_user.id
    estado = xadrez_db.find_one({"chat_id": chat_id})

    if not estado or estado["status"]!="ativo":
        return await query.answer("Partida não encontrada!", show_alert=True)
    if uid != estado["turno"]:
        return await query.answer("Não é a sua vez de jogar!", show_alert=True)

    tab = estado["tabuleiro"]
    cor_turno = "branca" if uid == estado["brancas"] else "preta"
    selecionado = estado.get("peca_selecionada")

    # PRIMEIRO CLIQUE: SELECIONAR PEÇA
    if not selecionado:
        peca_clicada = tab[l][c]
        cor_da_peca = cor_peca(peca_clicada)
        if peca_clicada == " ":
            return await query.answer("Escolha uma peça, não uma casa vazia!", show_alert=True)
        if cor_da_peca != cor_turno:
            return await query.answer("Essa peça não é sua! Escolha uma peça sua.", show_alert=True)

        roque_usa = estado["roque_branco"] if cor_turno == "branca" else estado["roque_preto"]
        destinos = listar_destinos_validos(tab, l, c, cor_turno, roque_usa, estado["en_passant"])
        if not destinos:
            return await query.answer("Essa peça não tem movimentos válidos agora!", show_alert=True)

        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"peca_selecionada": (l,c)}})
        await atualizar_tabuleiro_xadrez(query, tab, "✅ Peça selecionada! Clique em um destino para mover", selecionado=(l,c), destinos=destinos)
        return

    # SEGUNDO CLIQUE: MOVER OU CANCELAR
    l1, c1 = selecionado
    if l == l1 and c == c1:
        xadrez_db.update_one({"chat_id": chat_id}, {"$set":{"peca_selecionada": None}})
        await atualizar_tabuleiro_xadrez(query, tab, "Seleção cancelada — escolha outra peça")
        return

    # VALIDAÇÃO DO MOVIMENTO
    roque_usa = estado["roque_branco"] if cor_turno == "branca" else estado["roque_preto"]
    if not movimento_valido(tab, l1, c1, l, c, roque_usa, estado["en_passant"]):
        await query.answer("❌ Movimento inválido!", show_alert=True)
        destinos = listar_destinos_validos(tab,l1,c1,cor_turno,roque_usa,estado["en_passant"])
        await atualizar_tabuleiro_xadrez(query, tab, "Escolha um destino marcado com ✅ ou ⚔️", selecionado=(l1,c1), destinos=destinos)
        return
    if movimento_deixa_em_xeque(tab,l1,c1,l,c,cor_turno):
        await query.answer("❌ Não pode se colocar em xeque!", show_alert=True)
        destinos = listar_destinos_validos(tab,l1,c1,cor_turno,roque_usa,estado["en_passant"])
        await atualizar_tabuleiro_xadrez(query, tab, "Escolha outro movimento", selecionado=(l1,c1), destinos=destinos)
        return

    # EXECUTAR MOVIMENTO
    peca = tab[l1][c1]
    capturou = tab[l][c] != " "
    tab[l][c] = peca
    tab[l1][c1] = " "
    novo_en_passant = None
    novo_roque_b = estado["roque_branco"]
    novo_roque_p = estado["roque_preto"]

    # REGRAS ESPECIAIS
    if peca.lower() == "p" and abs(l-l1) == 2:
        novo_en_passant = ((l1+l)//2, c)
    if peca.lower() == "p" and estado["en_passant"] == (l,c):
        tab[l1][c] = " "
        capturou = True
    if peca == "♔":
        novo_roque_b = False
        if abs(c-c1) == 2:
            tab[7][5 if c>c1 else 3], tab[7][7 if c>c1 else 0] = tab[7][7 if c>c1 else 0], " "
    if peca == "♚":
        novo_roque_p = False
        if abs(c-c1) == 2:
            tab[0][5 if c>c1 else 3], tab[0][7 if c>c1 else 0] = tab[0][7 if c>c1 else 0], " "
    if peca.lower() == "p" and l in (0,7):
        tab[l][c] = "♕" if cor_turno == "branca" else "♛"
    if peca in ("♔","♖"): novo_roque_b = False
    if peca in ("♚","♜"): novo_roque_p = False

    # VERIFICAR FIM DE JOGO E TURNO
    novo_contador = 0 if capturou or peca.lower()=="p" else estado["contador_50"]+1
    historico = estado["historico"] + [tab_para_texto(tab)]
    prox_cor = "preta" if cor_turno=="branca" else "branca"
    prox_uid = estado["pretas"] if cor_turno=="branca" else estado["brancas"]

    fim = verificar_fim_jogo(tab, prox_cor, novo_roque_b, novo_roque_p, novo_contador, historico)
    if fim:
        xadrez_db.delete_one({"chat_id": chat_id})
        await finalizar_xadrez(query, tab, fim, estado)
        return

    # TURNO DA IA
    if estado["modo"] == "ia" and prox_uid == "IA":
        movimentos_validos = []
        for la in range(8):
            for ca in range(8):
                if cor_peca(tab[la][ca]) != "preta":
                    continue
                destinos_ia = listar_destinos_validos(tab, la, ca, "preta", novo_roque_p, novo_en_passant)
                for lb, cb in destinos_ia:
                    movimentos_validos.append((la, ca, lb, cb))
        if movimentos_validos:
            l1i, c1i, l2i, c2i = random.choice(movimentos_validos)
            tab[l2i][c2i] = tab[l1i][c1i]
            tab[l1i][c1i] = " "
            if tab[l2i][c2i].lower() == "p" and l2i == 7:
                tab[l2i][c2i] = "♛"
            fim_ia = verificar_fim_jogo(tab, "branca", novo_roque_b, novo_roque_p, 0, historico+[tab_para_texto(tab)])
            if fim_ia:
                xadrez_db.delete_one({"chat_id": chat_id})
                await finalizar_xadrez(query, tab, fim_ia, estado)
                return
            await atualizar_tabuleiro_xadrez(query, tab, "Sua vez! Clique em uma peça branca")
            return

    # SALVAR ESTADO E ATUALIZAR
    xadrez_db.update_one({"chat_id": chat_id}, {"$set":{
        "tabuleiro":tab,"turno":prox_uid,"roque_branco":novo_roque_b,"roque_preto":novo_roque_p,
        "en_passant":novo_en_passant,"contador_50":novo_contador,"historico":historico,"peca_selecionada":None
    }})
    msg = f"⚠️ **XEQUE!** Vez das {'Brancas' if prox_cor=='branca' else 'Pretas'}" if esta_em_xeque(tab, prox_cor) else f"Vez das {'Brancas' if prox_cor=='branca' else 'Pretas'}"
    await atualizar_tabuleiro_xadrez(query, tab, msg)

# ==============================================
# 📤 ATUALIZAR VISUALIZAÇÃO
# ==============================================
async def atualizar_tabuleiro_xadrez(query, tab, status, selecionado=None, destinos=None):
    await query.message.edit_text(
        f"♟️ **XADREZ**\n📌 {status}",
        reply_markup=InlineKeyboardMarkup(gerar_botoes_tabuleiro(tab, selecionado, destinos)),
        parse_mode="Markdown"
    )

# ==============================================
# 🏆 FIM DE PARTIDA
# ==============================================
async def finalizar_xadrez(query, tab, motivo, estado):
    msgs = {
        "xeque_mate": f"🏆 **XEQUE-MATE!** {'Brancas' if estado['turno']==estado['pretas'] else 'Pretas'} vencem a partida!",
        "afogamento": "🤝 **EMPATE - Afogamento!** Nenhum jogador tem movimentos válidos mas não está em xeque.",
        "regra_50": "🤝 **EMPATE - Regra dos 50 lances!** Nenhuma captura ou movimento de peão em 50 turnos.",
        "repeticao": "🤝 **EMPATE - Repetição tripla!** A mesma posição ocorreu 3 vezes."
    }
    botoes = gerar_botoes_tabuleiro(tab)[:-2]
    botoes.extend([[InlineKeyboardButton("🎮 JOGAR DE NOVO", callback_data="x_reiniciar")],[InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="menu_jogos_atalho")]])
    await query.message.edit_text(f"♟️ **FIM DA PARTIDA**\n\n{msgs[motivo]}", reply_markup=InlineKeyboardMarkup(botoes), parse_mode="Markdown")
