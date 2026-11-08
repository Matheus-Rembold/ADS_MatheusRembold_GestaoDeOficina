"""
Precificação das peças (RF03, RF09 e RF04).

Este módulo é o ÚNICO lugar onde a conta do preço de venda existe. O estoque
(ao registrar uma compra), o cadastro de produto e a tela usam estas funções;
assim, mudar a margem é editar UMA constante (princípio DRY: cada regra num
lugar só).

Markup x margem (pergunta provável da banca)
--------------------------------------------
A regra da oficina é preço = custo × (1 + 20%). Isso é um MARKUP de 20%: o
percentual é aplicado SOBRE O CUSTO. A "margem de lucro" no sentido contábil
é calculada sobre o PREÇO DE VENDA e, neste caso, vale 20 ÷ 120 = 16,67%.
Por isso a constante se chama MARKUP_PADRAO e a tela diz "margem sobre o custo".

Exemplo: custo R$ 50,00 -> preço R$ 60,00. Lucro R$ 10,00 =
20% do custo (markup) = 16,67% do preço (margem).

Modo automático x manual
------------------------
- automático (preco_venda_manual = False): cada compra recalcula o preço a
  partir do novo custo;
- manual (preco_venda_manual = True): o usuário definiu o preço; uma compra
  NÃO o sobrescreve, só informa o valor sugerido pelo novo custo.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

# Percentual aplicado sobre o custo (0.20 = 20%). Altere aqui e todo o
# sistema passa a usar o novo valor nos próximos cálculos.
MARKUP_PADRAO = Decimal("0.20")

_CENTAVO = Decimal("0.01")
_QUATRO_CASAS = Decimal("0.0001")


def calcular_preco_venda(custo: Optional[Decimal]) -> Optional[Decimal]:
    """custo × (1 + MARKUP_PADRAO), em centavos (ROUND_HALF_UP). Sem custo -> None."""
    if custo is None:
        return None
    return (Decimal(custo) * (1 + MARKUP_PADRAO)).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def margem_sobre_custo(
    preco: Optional[Decimal], custo: Optional[Decimal]
) -> Optional[Decimal]:
    """
    Margem efetiva sobre o custo, como fração: (preço - custo) ÷ custo.
    0.20 = 20%; negativa = vendendo abaixo do custo.
    None quando falta preço ou custo, ou o custo é zero (divisão impossível).
    """
    if preco is None or custo is None or Decimal(custo) == 0:
        return None
    return ((Decimal(preco) - Decimal(custo)) / Decimal(custo)).quantize(
        _QUATRO_CASAS, rounding=ROUND_HALF_UP
    )


def recalcular_preco_automatico(produto) -> None:
    """Se o produto está no modo automático, alinha o preço ao custo atual."""
    if not produto.preco_venda_manual:
        produto.preco_venda = calcular_preco_venda(produto.valor_unitario)


def preco_sugerido_divergente(produto) -> Optional[Decimal]:
    """
    Para produto com preço MANUAL: devolve o preço que o custo atual sugere,
    se for diferente do preço definido. Serve para avisar o usuário depois de
    uma compra. Produto automático (ou sem diferença) -> None.
    """
    if not produto.preco_venda_manual:
        return None
    sugerido = calcular_preco_venda(produto.valor_unitario)
    if sugerido is None or sugerido == produto.preco_venda:
        return None
    return sugerido
