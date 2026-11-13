"""
Repository de Movimentação de Estoque (RF09 - Gerenciar Estoque).

Mesmo padrão dos outros repositories: a Session vem de fora e nenhum método
faz commit (usam flush; o commit é do serviço).

Não há remover(): movimentações são só registradas e consultadas. Um erro
se corrige com uma nova movimentação do tipo ajuste.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from src.persistencia.models import MovimentacaoEstoque, Produto, TipoMovimentacao
from src.persistencia.repositories import paginacao


class MovimentacaoEstoqueRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def adicionar(self, movimentacao: MovimentacaoEstoque) -> MovimentacaoEstoque:
        """Insere a movimentação. Após o flush, o id já existe."""
        self._session.add(movimentacao)
        self._session.flush()
        return movimentacao

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def buscar_por_id(self, id_movimentacao: int) -> Optional[MovimentacaoEstoque]:
        return self._session.get(MovimentacaoEstoque, id_movimentacao)

    def ultima_compra(self, id_produto: int) -> Optional[MovimentacaoEstoque]:
        """Compra mais recente do produto (data e, em empate, a registrada por último)."""
        stmt = (
            select(MovimentacaoEstoque)
            .where(
                MovimentacaoEstoque.id_produto == id_produto,
                MovimentacaoEstoque.tipo == TipoMovimentacao.COMPRA,
            )
            .order_by(
                MovimentacaoEstoque.data_movimentacao.desc(),
                MovimentacaoEstoque.id_movimentacao_estoque.desc(),
            )
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def buscar_produto_com_trava(self, id_produto: int) -> Optional[Produto]:
        """
        Busca o produto TRAVANDO a linha (SELECT ... FOR UPDATE) até o fim da
        transação. Assim duas janelas movimentando o mesmo produto ao mesmo
        tempo não calculam o saldo em cima do mesmo valor antigo.
        populate_existing=True garante que o saldo lido é o do banco, e não
        um valor antigo guardado na sessão.
        """
        stmt = (
            select(Produto)
            .where(Produto.id_produto == id_produto)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self._session.scalars(stmt).first()

    def listar(
        self,
        termo: str = "",
        tipo: Optional[TipoMovimentacao] = None,
        data_inicio: Optional[date] = None,
        data_fim: Optional[date] = None,
    ) -> List[MovimentacaoEstoque]:
        """
        Consulta com filtros opcionais, da mais recente para a mais antiga.
        O produto vem junto (joinedload) para evitar o problema N+1.
        """
        stmt = self._consulta(termo, tipo, data_inicio, data_fim).options(
            joinedload(MovimentacaoEstoque.produto)
        )
        stmt = stmt.order_by(*self._ORDEM)
        return list(self._session.scalars(stmt).all())

    # --- paginação (09/11/2026) ---
    _ORDEM = (
        MovimentacaoEstoque.data_movimentacao.desc(),
        MovimentacaoEstoque.id_movimentacao_estoque.desc(),
    )

    def contar(self, termo="", tipo=None, data_inicio=None, data_fim=None) -> int:
        return paginacao.contar(self._session, self._consulta(termo, tipo, data_inicio, data_fim))

    def listar_pagina(self, termo, tipo, data_inicio, data_fim, limite: int, deslocamento: int):
        return paginacao.buscar_pagina(
            self._session, self._consulta(termo, tipo, data_inicio, data_fim),
            ordem=self._ORDEM, opcoes=(joinedload(MovimentacaoEstoque.produto),),
            limite=limite, deslocamento=deslocamento,
        )

    def somar_valores(self, termo="", tipo=None, data_inicio=None, data_fim=None) -> dict:
        """Soma do valor por tipo, sobre TODAS as movimentações do filtro (para o rodapé)."""
        stmt = (
            self._consulta(termo, tipo, data_inicio, data_fim)
            .with_only_columns(MovimentacaoEstoque.tipo, func.coalesce(func.sum(MovimentacaoEstoque.valor), 0))
            .group_by(MovimentacaoEstoque.tipo)
        )
        return {TipoMovimentacao(t): v for t, v in self._session.execute(stmt).all()}

    @staticmethod
    def _consulta(
        termo: str = "",
        tipo: Optional[TipoMovimentacao] = None,
        data_inicio: Optional[date] = None,
        data_fim: Optional[date] = None,
    ):
        stmt = select(MovimentacaoEstoque).join(MovimentacaoEstoque.produto)
        if termo:
            stmt = stmt.where(
                or_(
                    Produto.nome.icontains(termo, autoescape=True),
                    MovimentacaoEstoque.fornecedor.icontains(termo, autoescape=True),
                    MovimentacaoEstoque.observacao.icontains(termo, autoescape=True),
                )
            )
        if tipo is not None:
            stmt = stmt.where(MovimentacaoEstoque.tipo == tipo)
        if data_inicio is not None:
            stmt = stmt.where(MovimentacaoEstoque.data_movimentacao >= data_inicio)
        if data_fim is not None:
            stmt = stmt.where(MovimentacaoEstoque.data_movimentacao <= data_fim)
        return stmt
