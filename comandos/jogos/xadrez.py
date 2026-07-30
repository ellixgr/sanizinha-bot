import chess  # ✅ TODA A LÓGICA PRONTA

# Cria tabuleiro oficial
tabuleiro = chess.Board()

# Pegar todos os movimentos permitidos de uma casa
movimentos_permitidos = tabuleiro.legal_moves

# Verificar se o clique do usuário é válido
if movimento in tabuleiro.legal_moves:
    tabuleiro.push(movimento)
