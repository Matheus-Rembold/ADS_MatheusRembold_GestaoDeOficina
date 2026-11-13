"""
Consulta paginada reaproveitada por todos os repositories.

A mesma consulta (com os filtros já aplicados) é usada duas vezes:
1. COUNT(*) sobre ela, sem ordenação, para saber o total de registros;
2. a própria consulta com ORDER BY + LIMIT/OFFSET, para buscar só a página.

Por que LIMIT/OFFSET e não "carregar tudo e fatiar em Python": o banco
devolve 50 linhas em vez de milhares (RNF06). Com as tabelas desta
aplicação (milhares de linhas), o custo do OFFSET é desprezível.

As opções de carregamento (joinedload/selectinload) continuam valendo na
página: só as peças, clientes e veículos das 50 linhas são buscados.
"""
from __future__ import annotations

from typing import List, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def contar(session: Session, consulta: Select) -> int:
    """Quantos registros a consulta devolve (ignora ordenação e opções de carga)."""
    sub = consulta.order_by(None).subquery()
    return int(session.scalar(select(func.count()).select_from(sub)) or 0)


def buscar_pagina(
    session: Session,
    consulta: Select,
    ordem: Sequence,
    opcoes: Sequence = (),
    limite: int = 50,
    deslocamento: int = 0,
) -> List:
    """Uma página da consulta, na ordem pedida. A ordem precisa terminar num campo único (o id)."""
    stmt = consulta.options(*opcoes).order_by(*ordem).limit(limite).offset(deslocamento)
    return list(session.scalars(stmt).unique().all())
