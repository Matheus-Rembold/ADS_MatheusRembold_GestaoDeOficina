"""
Funções puras de validação reutilizáveis (sem acesso a banco).

Por serem puras (entrada -> saída, sem efeitos colaterais), são as mais
fáceis de testar de todo o sistema.
"""
from __future__ import annotations

import re


def somente_digitos(texto: str | None) -> str:
    """Remove tudo que não é número: '529.982.247-25' -> '52998224725'."""
    return re.sub(r"\D", "", texto or "")


def cpf_valido(digitos: str) -> bool:
    """
    Valida um CPF (11 dígitos, já sem pontuação) pelo algoritmo oficial.

    Os dois últimos dígitos são verificadores, calculados a partir dos
    anteriores com pesos decrescentes (10..2 para o 1º, 11..2 para o 2º).
    """
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False  # tamanho errado ou todos os dígitos iguais (ex.: 111...)

    for tamanho in (9, 10):
        pesos = range(tamanho + 1, 1, -1)
        soma = sum(int(d) * p for d, p in zip(digitos[:tamanho], pesos))
        verificador = (soma * 10) % 11 % 10
        if verificador != int(digitos[tamanho]):
            return False
    return True


def formatar_cpf(digitos: str) -> str:
    """'52998224725' -> '529.982.247-25' (formato usado no banco, VARCHAR(14))."""
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
