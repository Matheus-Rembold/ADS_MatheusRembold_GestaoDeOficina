"""
Senhas (RF10 / RNF05): política mínima e hash bcrypt.

Senha NÃO se criptografa (criptografia é reversível com a chave): guarda-se
um HASH com sal, que não pode ser desfeito. No login, calcula-se o hash da
senha digitada com o mesmo sal (embutido no próprio hash) e compara-se.
Se o banco vazar, as senhas não aparecem.

Decisões:
- bcrypt com custo 12: medido em 251 ms por verificação nesta máquina.
  Imperceptível para quem digita; caro para quem tenta milhões de senhas
  (cada +1 no custo dobra o tempo).
- Política (NIST SP 800-63B): mínimo 8 caracteres, SEM regras de
  composição ("maiúscula + símbolo"), que levam a senhas previsíveis;
  máximo 64 caracteres e 72 BYTES em UTF-8, porque o bcrypt 5 recusa
  senhas maiores (acento conta 2 bytes). Também não pode ser igual ao login.
- HASH_FALSO: quando o login não existe, a senha é conferida mesmo assim
  contra um hash qualquer. Sem isso, "login inexistente" responderia em
  1 ms e "senha errada" em 250 ms, e o tempo revelaria quem existe.
"""
from __future__ import annotations

from typing import List, Optional

import bcrypt

CUSTO_BCRYPT = 12
SENHA_MINIMA = 8
SENHA_MAXIMA = 64
LIMITE_BYTES_BCRYPT = 72

# Calculado uma vez, ao importar (custo igual ao real, para o tempo bater).
HASH_FALSO = bcrypt.hashpw(b"camaro-usuario-inexistente", bcrypt.gensalt(CUSTO_BCRYPT))


def problemas_da_senha(senha: Optional[str], login: Optional[str] = None) -> List[str]:
    """Lista de problemas (vazia = senha aceita). Não altera nem guarda a senha."""
    if not isinstance(senha, str) or senha == "":
        return ["Informe a senha."]
    erros = []
    if len(senha) < SENHA_MINIMA:
        erros.append(f"A senha deve ter pelo menos {SENHA_MINIMA} caracteres.")
    if len(senha) > SENHA_MAXIMA or len(senha.encode("utf-8")) > LIMITE_BYTES_BCRYPT:
        erros.append(f"A senha deve ter no máximo {SENHA_MAXIMA} caracteres (letras com acento contam em dobro).")
    if senha.strip() == "":
        erros.append("A senha não pode ser só de espaços.")
    if login and senha.strip().lower() == login.strip().lower():
        erros.append("A senha não pode ser igual ao nome de usuário.")
    return erros


def gerar_hash(senha: str) -> str:
    """Hash bcrypt (60 caracteres, com sal aleatório). Senhas iguais geram hashes diferentes."""
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(CUSTO_BCRYPT)).decode("ascii")


def senha_confere(senha: Optional[str], senha_hash: Optional[str]) -> bool:
    """
    Compara a senha digitada com o hash. Sem hash (login inexistente), confere
    contra o HASH_FALSO e devolve False: o tempo de resposta é o mesmo.
    """
    alvo = senha_hash.encode("ascii") if senha_hash else HASH_FALSO
    candidata = (senha or "").encode("utf-8")
    if len(candidata) > LIMITE_BYTES_BCRYPT:  # nunca seria cadastrada; não deixa o bcrypt estourar
        bcrypt.checkpw(b"x", alvo)
        return False
    return bcrypt.checkpw(candidata, alvo) and senha_hash is not None
