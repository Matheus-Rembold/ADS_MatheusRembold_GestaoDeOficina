"""
Repository de Relatórios (RF06) — SOMENTE LEITURA.

Não existe "model de relatório": relatório não é tabela, é CONSULTA sobre as
tabelas que já existem. Por isso este repository só faz SELECT agregado
(SUM/COUNT agrupado por período) e nunca grava nem faz flush.

As somas são feitas NO BANCO, não em Python: o banco devolve uma linha por
dia/mês em vez de todas as OS, o que mantém a tela rápida mesmo com milhares
de registros (RNF06, consultas em até 3 s).

`date_trunc` e `mode() WITHIN GROUP` são do PostgreSQL (mesma escolha
consciente do pg_advisory_xact_lock do RF05).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Tuple

from sqlalchemy import DateTime, and_, cast, func, select
from sqlalchemy.orm import Session

from src.persistencia.models import (
    MovimentacaoEstoque,
    OrdemServico,
    OsProduto,
    StatusOrdemServico,
    TipoMovimentacao,
)

# Unidades aceitas pelo date_trunc do PostgreSQL.
UNIDADES = ("day", "month")


class RelatorioRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    def _pecas_por_os(self, filtro_os):
        """
        Subconsulta: por OS, soma das peças cobradas, custo das peças (CMV) e
        peças sem custo — SÓ das OS que passam no mesmo filtro da consulta
        principal. Sem esse filtro aqui dentro, o banco somaria as peças de
        TODAS as OS da história antes de filtrar o período (medido com 50 mil
        OS: era o gargalo e escondia o ganho do índice idx_os_entregue_em).
        """
        return (
            select(
                OsProduto.id_ordem_servico.label("id_os"),
                func.sum(OsProduto.quantidade_utilizada * OsProduto.preco_unitario).label("pecas"),
                func.sum(
                    OsProduto.quantidade_utilizada * func.coalesce(OsProduto.custo_unitario, 0)
                ).label("custo"),
                func.count().filter(OsProduto.custo_unitario.is_(None)).label("sem_custo"),
            )
            .join(OrdemServico, OrdemServico.id_ordem_servico == OsProduto.id_ordem_servico)
            .where(filtro_os)
            .group_by(OsProduto.id_ordem_servico)
            .subquery()
        )

    @staticmethod
    def _filtro_entregue(inicio: datetime, fim_exclusivo: datetime):
        return and_(
            OrdemServico.status == StatusOrdemServico.ENTREGUE,
            OrdemServico.entregue_em >= inicio,
            OrdemServico.entregue_em < fim_exclusivo,
        )

    # ------------------------------------------------------------------
    def receita_os_por_periodo(
        self, inicio: datetime, fim_exclusivo: datetime, unidade: str
    ) -> List[Tuple]:
        """
        Uma linha por dia/mês com OS entregues:
        (período, qtd_os, valor_pecas, mao_de_obra, custo_pecas, pecas_sem_custo).
        """
        assert unidade in UNIDADES
        filtro = self._filtro_entregue(inicio, fim_exclusivo)
        pecas = self._pecas_por_os(filtro)
        periodo = func.date_trunc(unidade, OrdemServico.entregue_em).label("periodo")
        stmt = (
            select(
                periodo,
                func.count(OrdemServico.id_ordem_servico),
                func.coalesce(func.sum(pecas.c.pecas), 0),
                func.coalesce(func.sum(OrdemServico.valor_mao_de_obra), 0),
                func.coalesce(func.sum(pecas.c.custo), 0),
                func.coalesce(func.sum(pecas.c.sem_custo), 0),
            )
            .select_from(OrdemServico)
            .outerjoin(pecas, pecas.c.id_os == OrdemServico.id_ordem_servico)
            .where(filtro)
            .group_by(periodo)
            .order_by(periodo)
        )
        return [tuple(linha) for linha in self._session.execute(stmt).all()]

    def movimentacoes_por_periodo(
        self, inicio: date, fim_exclusivo: date, unidade: str
    ) -> List[Tuple]:
        """
        Uma linha por (dia/mês, tipo) para os tipos que mexem com dinheiro:
        compra (saída), venda por fora (entrada) e devolução (ressarcimento).
        (período, tipo, qtd_registros, soma_valor)
        """
        assert unidade in UNIDADES
        tipos = [
            TipoMovimentacao.COMPRA,
            TipoMovimentacao.VENDA_AVULSA,
            TipoMovimentacao.DEVOLUCAO_FORNECEDOR,
        ]
        # DATE -> TIMESTAMP antes do date_trunc: sem o cast o PostgreSQL devolve
        # um valor COM fuso horário, e a virada do mês poderia escorregar.
        dia = cast(MovimentacaoEstoque.data_movimentacao, DateTime)
        periodo = func.date_trunc(unidade, dia).label("periodo")
        stmt = (
            select(
                periodo,
                MovimentacaoEstoque.tipo,
                func.count(),
                func.coalesce(func.sum(MovimentacaoEstoque.valor), 0),
            )
            .where(
                MovimentacaoEstoque.tipo.in_(tipos),
                MovimentacaoEstoque.data_movimentacao >= inicio,
                MovimentacaoEstoque.data_movimentacao < fim_exclusivo,
            )
            .group_by(periodo, MovimentacaoEstoque.tipo)
            .order_by(periodo)
        )
        return [tuple(linha) for linha in self._session.execute(stmt).all()]

    def ranking_servicos(self, inicio: datetime, fim_exclusivo: datetime) -> List[Tuple]:
        """
        Serviços das OS entregues no período, agrupados sem diferenciar
        maiúsculas/espaços nas pontas. A grafia exibida é a mais usada (mode).
        (grafia, qtd_os, faturamento) — ordenado por qtd desc, faturamento desc, nome.
        """
        filtro = self._filtro_entregue(inicio, fim_exclusivo)
        pecas = self._pecas_por_os(filtro)
        tipo_limpo = func.nullif(func.trim(OrdemServico.tipo_servico), "")
        chave = func.lower(tipo_limpo).label("chave")
        faturamento = func.coalesce(
            func.sum(func.coalesce(pecas.c.pecas, 0) + OrdemServico.valor_mao_de_obra), 0
        )
        quantidade = func.count(OrdemServico.id_ordem_servico)
        stmt = (
            select(
                func.mode().within_group(tipo_limpo),
                quantidade,
                faturamento,
            )
            .select_from(OrdemServico)
            .outerjoin(pecas, pecas.c.id_os == OrdemServico.id_ordem_servico)
            .where(filtro)
            .group_by(chave)
            .order_by(quantidade.desc(), faturamento.desc(), chave)
        )
        return [tuple(linha) for linha in self._session.execute(stmt).all()]

    def a_receber(self) -> Tuple[int, object]:
        """OS em 'aguardando pagamento' (sem filtro de data): (quantidade, total)."""
        filtro = OrdemServico.status == StatusOrdemServico.AGUARDANDO_PAGAMENTO
        pecas = self._pecas_por_os(filtro)
        stmt = (
            select(
                func.count(OrdemServico.id_ordem_servico),
                func.coalesce(
                    func.sum(func.coalesce(pecas.c.pecas, 0) + OrdemServico.valor_mao_de_obra), 0
                ),
            )
            .select_from(OrdemServico)
            .outerjoin(pecas, pecas.c.id_os == OrdemServico.id_ordem_servico)
            .where(filtro)
        )
        qtd, total = self._session.execute(stmt).one()
        return qtd, total
