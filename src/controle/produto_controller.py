"""
Controller de Produto (RF03) - Camada de Controle (DVP, seção 2.1).

Mesmo papel dos outros controllers: abre/fecha a Session de cada operação,
devolve DTOs (nunca objetos ORM) e deixa as ErroDeNegocio subirem para a tela.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.persistencia.models import Produto
from src.servico.produto_service import ProdutoService

# Reexportadas de propósito: a tela importa as exceções DAQUI.
from src.servico.excecoes import (  # noqa: F401
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)


@dataclass(frozen=True)
class ProdutoDTO:
    """Cópia somente-leitura dos dados do produto, segura para a tela usar."""

    id_produto: int
    nome: str
    categoria: Optional[str]
    prateleira: Optional[str]
    quantidade: int
    quantidade_minima: int
    estoque_baixo: bool  # regra do HU09, calculada no model

    @staticmethod
    def de_modelo(produto: Produto) -> "ProdutoDTO":
        return ProdutoDTO(
            id_produto=produto.id_produto,
            nome=produto.nome,
            categoria=produto.categoria,
            prateleira=produto.prateleira,
            quantidade=produto.quantidade,
            quantidade_minima=produto.quantidade_minima,
            estoque_baixo=produto.estoque_baixo,
        )


class ProdutoController:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def listar(self, termo: str = "") -> List[ProdutoDTO]:
        """Sem termo lista todos; com termo busca por nome, categoria ou prateleira."""
        termo = (termo or "").strip()
        with self._session_factory() as session:
            servico = ProdutoService(session)
            produtos = servico.buscar(termo) if termo else servico.listar()
            return [ProdutoDTO.de_modelo(p) for p in produtos]

    def obter(self, id_produto: int) -> ProdutoDTO:
        """Leitura fresca (levanta RegistroNaoEncontradoError se sumiu)."""
        with self._session_factory() as session:
            return ProdutoDTO.de_modelo(ProdutoService(session).obter(id_produto))

    def cadastrar(
        self,
        nome: str,
        categoria: Optional[str] = None,
        prateleira: Optional[str] = None,
        quantidade_minima: Optional[int] = 0,
    ) -> ProdutoDTO:
        with self._session_factory() as session:
            produto = ProdutoService(session).cadastrar(
                nome, categoria, prateleira, quantidade_minima
            )
            return ProdutoDTO.de_modelo(produto)

    def atualizar(
        self,
        id_produto: int,
        nome: str,
        categoria: Optional[str] = None,
        prateleira: Optional[str] = None,
        quantidade_minima: Optional[int] = 0,
    ) -> ProdutoDTO:
        with self._session_factory() as session:
            produto = ProdutoService(session).atualizar(
                id_produto, nome, categoria, prateleira, quantidade_minima
            )
            return ProdutoDTO.de_modelo(produto)

    def excluir(self, id_produto: int) -> None:
        with self._session_factory() as session:
            ProdutoService(session).excluir(id_produto)
