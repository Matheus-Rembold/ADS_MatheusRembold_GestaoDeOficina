"""
Paginação das listagens (decidida em 09/11/2026).

As listas que só crescem (ordens de serviço, movimentações de estoque,
produtos, clientes e veículos) são buscadas no banco de 50 em 50 (LIMIT /
OFFSET), em vez de carregar tudo de uma vez. A busca e os filtros continuam
valendo para TODOS os registros: o banco filtra, conta o total e devolve só
a página pedida.

Este módulo guarda a parte de REGRA, igual para todas as telas:
- o tamanho da página (constante única);
- o ajuste de uma página fora do intervalo: pedir a página 30 de uma lista
  que agora só tem 2 páginas (por exemplo, depois de uma exclusão ou de uma
  busca) devolve a última página válida, e não uma tela vazia.

`Pagina` é imutável e não carrega objeto do banco quando sai do controller
(os itens viram DTOs), seguindo o padrão das outras camadas.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

POR_PAGINA = 50


def normalizar_pagina(pagina: Any, total: int, por_pagina: int = POR_PAGINA) -> int:
    """Página válida entre 1 e a última (lista vazia = página 1)."""
    if isinstance(pagina, bool) or not isinstance(pagina, int):
        pagina = 1
    ultima = max(1, -(-total // por_pagina))  # divisão arredondada para cima
    return min(max(1, pagina), ultima)


def montar_pagina(total: int, pagina: Any, buscar, por_pagina: int = POR_PAGINA, resumo=None) -> "Pagina":
    """
    Sequência comum a todos os services: com o total já contado, ajusta a
    página pedida e busca só ela. `buscar(limite, deslocamento)` é o método
    do repository.
    """
    if isinstance(por_pagina, bool) or not isinstance(por_pagina, int) or por_pagina < 1:
        por_pagina = POR_PAGINA
    atual = normalizar_pagina(pagina, total, por_pagina)
    itens = buscar(por_pagina, (atual - 1) * por_pagina) if total else []
    return Pagina(tuple(itens), total, atual, por_pagina, dict(resumo or {}))


@dataclass(frozen=True)
class Pagina:
    itens: tuple
    total: int  # quantidade de registros que passam no filtro (todas as páginas)
    pagina: int
    por_pagina: int = POR_PAGINA
    # Totais calculados sobre TODOS os registros filtrados, não só a página
    # (ex.: valor somado das OS, quantos produtos com estoque baixo).
    resumo: Mapping[str, Any] = field(default_factory=dict)

    @property
    def total_paginas(self) -> int:
        return max(1, -(-self.total // self.por_pagina))

    @property
    def primeiro(self) -> int:
        """Posição (1, 2, 3...) do primeiro item desta página; 0 se vazia."""
        return 0 if self.total == 0 else (self.pagina - 1) * self.por_pagina + 1

    @property
    def ultimo(self) -> int:
        return 0 if self.total == 0 else self.primeiro + len(self.itens) - 1

    @property
    def tem_anterior(self) -> bool:
        return self.pagina > 1

    @property
    def tem_proxima(self) -> bool:
        return self.pagina < self.total_paginas

    def com_itens(self, itens: Iterable) -> "Pagina":
        """Mesma página com outros itens (o controller troca objetos do banco por DTOs)."""
        return replace(self, itens=tuple(itens))
