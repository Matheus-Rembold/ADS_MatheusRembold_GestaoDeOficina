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

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from src.persistencia.models import MovimentacaoEstoque, Produto, TipoMovimentacao


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
        stmt = (
            select(MovimentacaoEstoque)
            .join(MovimentacaoEstoque.produto)
            .options(joinedload(MovimentacaoEstoque.produto))
        )
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
        stmt = stmt.order_by(
            MovimentacaoEstoque.data_movimentacao.desc(),
            MovimentacaoEstoque.id_movimentacao_estoque.desc(),
        )
        return list(self._session.scalars(stmt).all())
