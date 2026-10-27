"""
Controller de Movimentação de Estoque (RF09) - Camada de Controle (DVP, seção 2.1).

Mesmo papel dos outros controllers: abre/fecha a Session de cada operação,
devolve DTOs (nunca objetos ORM) e deixa as ErroDeNegocio subirem para a tela.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.persistencia.models import MovimentacaoEstoque, TipoMovimentacao
from src.servico.movimentacao_estoque_service import MovimentacaoEstoqueService
from src.servico.produto_service import ProdutoService

# Reexportadas de propósito: a tela importa tudo DAQUI, sem precisar
# conhecer as camadas de serviço e de persistência (regra do README).
from src.servico.excecoes import (  # noqa: F401
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)

__all__ = [
    "ErroDeNegocio",
    "MovimentacaoDTO",
    "MovimentacaoEstoqueController",
    "OperacaoNaoPermitidaError",
    "ProdutoOpcaoDTO",
    "RegistroNaoEncontradoError",
    "TipoMovimentacao",
    "ValidacaoError",
]


@dataclass(frozen=True)
class MovimentacaoDTO:
    """Cópia somente-leitura de uma movimentação, segura para a tela usar."""

    id_movimentacao_estoque: int
    id_produto: int
    nome_produto: str
    tipo: TipoMovimentacao
    quantidade: int  # COM SINAL: positiva aumenta o estoque, negativa diminui
    valor: Optional[Decimal]
    data_movimentacao: date
    fornecedor: Optional[str]
    observacao: Optional[str]

    @staticmethod
    def de_modelo(m: MovimentacaoEstoque) -> "MovimentacaoDTO":
        return MovimentacaoDTO(
            id_movimentacao_estoque=m.id_movimentacao_estoque,
            id_produto=m.id_produto,
            nome_produto=m.produto.nome,
            tipo=m.tipo,
            quantidade=m.quantidade,
            valor=m.valor,
            data_movimentacao=m.data_movimentacao,
            fornecedor=m.fornecedor,
            observacao=m.observacao,
        )


@dataclass(frozen=True)
class ProdutoOpcaoDTO:
    """Dados mínimos do produto para a lista de seleção (com o saldo atual)."""

    id_produto: int
    nome: str
    quantidade: int


class MovimentacaoEstoqueController:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def listar(
        self,
        termo: str = "",
        tipo: Optional[TipoMovimentacao] = None,
        data_inicio: Optional[date] = None,
        data_fim: Optional[date] = None,
    ) -> List[MovimentacaoDTO]:
        """Filtros opcionais: termo (produto, fornecedor ou observação), tipo e período."""
        with self._session_factory() as session:
            movimentacoes = MovimentacaoEstoqueService(session).listar(
                termo, tipo, data_inicio, data_fim
            )
            return [MovimentacaoDTO.de_modelo(m) for m in movimentacoes]

    def listar_produtos(self) -> List[ProdutoOpcaoDTO]:
        """Produtos em ordem alfabética, com o saldo atual, para o campo 'Produto'."""
        with self._session_factory() as session:
            return [
                ProdutoOpcaoDTO(p.id_produto, p.nome, p.quantidade)
                for p in ProdutoService(session).listar()
            ]

    def registrar(
        self,
        id_produto: Optional[int],
        tipo: TipoMovimentacao,
        quantidade: Optional[int],
        data_movimentacao: Optional[date] = None,
        valor: Optional[Decimal] = None,
        fornecedor: Optional[str] = None,
        observacao: Optional[str] = None,
    ) -> MovimentacaoDTO:
        with self._session_factory() as session:
            movimentacao = MovimentacaoEstoqueService(session).registrar(
                id_produto, tipo, quantidade, data_movimentacao, valor, fornecedor, observacao
            )
            return MovimentacaoDTO.de_modelo(movimentacao)

    def ajustar_para_contagem(
        self,
        id_produto: Optional[int],
        quantidade_contada: Optional[int],
        observacao: Optional[str],
        data_movimentacao: Optional[date] = None,
    ) -> MovimentacaoDTO:
        with self._session_factory() as session:
            movimentacao = MovimentacaoEstoqueService(session).ajustar_para_contagem(
                id_produto, quantidade_contada, observacao, data_movimentacao
            )
            return MovimentacaoDTO.de_modelo(movimentacao)
