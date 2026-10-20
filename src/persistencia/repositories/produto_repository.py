"""
Repository de Produto (RF03 - Gerenciar Produtos).

Mesmo padrão dos outros repositories: a Session vem de fora e nenhum
método faz commit (usam flush; o commit é do serviço).
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from src.persistencia.models import EntradaEstoque, OsProduto, Produto


class ProdutoRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def adicionar(self, produto: Produto) -> Produto:
        """Insere um novo produto. Após o flush, produto.id_produto já existe."""
        self._session.add(produto)
        self._session.flush()
        return produto

    def remover(self, produto: Produto) -> None:
        self._session.delete(produto)
        self._session.flush()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def buscar_por_id(self, id_produto: int) -> Optional[Produto]:
        return self._session.get(Produto, id_produto)

    def buscar_por_nome_exato(self, nome: str) -> Optional[Produto]:
        """
        Comparação sem diferenciar maiúsculas, igual ao índice uq_produto_nome.

        LOWER é aplicado nos DOIS lados pelo próprio banco (e não com
        nome.lower() do Python), para a consulta e o índice usarem sempre a
        mesma regra de minúsculas, inclusive com acentos ("Óleo" = "óleo").
        """
        stmt = select(Produto).where(func.lower(Produto.nome) == func.lower(nome))
        return self._session.scalars(stmt).first()

    def buscar(self, termo: str) -> List[Produto]:
        """Busca parcial por nome, categoria ou prateleira."""
        stmt = (
            select(Produto)
            .where(
                or_(
                    Produto.nome.icontains(termo, autoescape=True),
                    Produto.categoria.icontains(termo, autoescape=True),
                    Produto.prateleira.icontains(termo, autoescape=True),
                )
            )
            .order_by(Produto.nome)
        )
        return list(self._session.scalars(stmt).all())

    def listar_todos(self) -> List[Produto]:
        stmt = select(Produto).order_by(Produto.nome)
        return list(self._session.scalars(stmt).all())

    # ------------------------------------------------------------------
    # Consultas de apoio às regras de negócio (a decisão fica no serviço)
    # ------------------------------------------------------------------
    def possui_os(self, id_produto: int) -> bool:
        """True se o produto já foi usado em alguma ordem de serviço."""
        stmt = select(exists().where(OsProduto.id_produto == id_produto))
        return bool(self._session.scalar(stmt))

    def possui_entradas(self, id_produto: int) -> bool:
        """True se o produto tem alguma entrada de estoque (RF09) registrada."""
        stmt = select(exists().where(EntradaEstoque.id_produto == id_produto))
        return bool(self._session.scalar(stmt))
