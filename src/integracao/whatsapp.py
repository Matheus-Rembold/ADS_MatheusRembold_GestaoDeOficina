"""
Integração com o WhatsApp (RF07): link "clique para conversar" (wa.me).

Por que o link e não uma API (decidido em 15/11/2026):
- é gratuito e não exige cadastro na Meta (a API oficial do WhatsApp
  Business cobra por conversa e exige empresa verificada);
- a mensagem sai do WhatsApp da própria oficina, que o cliente já conhece;
- não automatiza o WhatsApp Web (isso viola os termos de uso e pode banir
  o número). Uma pessoa confere o texto e aperta "Enviar".

O resto do sistema só conhece a interface `ProvedorMensagens`. Para usar a
API oficial no futuro, basta escrever outro provedor com o mesmo método
`preparar` e trocá-lo em `provedor_padrao()`; serviços e telas não mudam.

Formato do link: https://wa.me/<55 + DDD + número>?text=<mensagem codificada>
"""
from __future__ import annotations

import re
from typing import Optional, Protocol
from urllib.parse import quote

CODIGO_BRASIL = "55"
URL_BASE = "https://wa.me/"


def normalizar_celular(contato: Optional[str]) -> Optional[str]:
    """
    Converte o contato do cliente para o formato internacional (55 + DDD + 9 dígitos).
    Devolve None se não for um celular brasileiro válido (fixo, incompleto, vazio).

    Aceita os jeitos comuns de digitar: "(54) 99999-1234", "54999991234",
    "054 99999 1234", "+55 54 99999-1234".
    """
    digitos = re.sub(r"\D", "", contato or "")
    if len(digitos) == 13 and digitos.startswith(CODIGO_BRASIL):
        digitos = digitos[2:]
    elif len(digitos) == 12 and digitos.startswith("0"):  # 0 + DDD (discagem nacional)
        digitos = digitos[1:]
    if len(digitos) != 11:
        return None
    ddd, primeiro = int(digitos[:2]), digitos[2]
    if not 11 <= ddd <= 99 or digitos[1] == "0" or primeiro != "9":
        return None  # DDD inexistente ou número fixo (celular começa com 9)
    return CODIGO_BRASIL + digitos


def formatar_celular(numero_internacional: str) -> str:
    """'5554999991234' -> '(54) 99999-1234', para mostrar na tela."""
    d = numero_internacional[2:]
    return f"({d[:2]}) {d[2:7]}-{d[7:]}"


class ProvedorMensagens(Protocol):
    """O que o sistema precisa de qualquer forma de envio."""

    nome: str

    def preparar(self, numero_internacional: str, mensagem: str) -> str:
        """Devolve o endereço que a tela abre para a pessoa enviar a mensagem."""
        ...


class ProvedorWaMe:
    """Envio semiautomático: abre o WhatsApp com o número e o texto prontos."""

    nome = "WhatsApp (link wa.me)"

    def preparar(self, numero_internacional: str, mensagem: str) -> str:
        # quote com safe="" codifica tudo (espaço, acento, quebra de linha, &, ?)
        return f"{URL_BASE}{numero_internacional}?text={quote(mensagem, safe='')}"


def provedor_padrao() -> ProvedorMensagens:
    return ProvedorWaMe()
