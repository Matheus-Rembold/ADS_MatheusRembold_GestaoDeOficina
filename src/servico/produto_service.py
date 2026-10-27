"""
Serviço de Produto (RF03 - Gerenciar Produtos).

Regras deste módulo:
- o nome do produto é único, sem diferenciar maiúsculas/minúsculas;
- a QUANTIDADE EM ESTOQUE não é digitada aqui: um produto novo nasce com 0
  e só o RF09 (movimentações de estoque) a altera. Por isso cadastrar/atualizar
  não recebem "quantidade" e o atualizar nunca a modifica;
- quantidade_minima é editável e alimenta o alerta de estoque baixo (HU09);
- produto já usado em OS ou com movimentações de estoque não pode ser excluído
  (mesma política de preservar o histórico dos outros módulos).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.persistencia.models import Produto
from src.persistencia.repositories.produto_repository import ProdutoRepository
from src.servico.excecoes import (
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)

QUANTIDADE_MINIMA_MAXIMA = 1_000_000


class ProdutoService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = ProdutoRepository(session)

    # ------------------------------------------------------------------
    # Cadastrar produto
    # ------------------------------------------------------------------
    def cadastrar(
        self,
        nome: str,
        categoria: Optional[str] = None,
        prateleira: Optional[str] = None,
        quantidade_minima: Optional[int] = 0,
    ) -> Produto:
        dados = self._validar_dados(nome, categoria, prateleira, quantidade_minima)

        if self._repo.buscar_por_nome_exato(dados["nome"]) is not None:
            raise RegistroDuplicadoError("Já existe um produto cadastrado com este nome.")

        # quantidade começa em 0: o estoque entra pelo RF09.
        produto = self._repo.adicionar(Produto(quantidade=0, **dados))
        self._confirmar()
        return produto

    # ------------------------------------------------------------------
    # Atualizar produto
    # ------------------------------------------------------------------
    def atualizar(
        self,
        id_produto: int,
        nome: str,
        categoria: Optional[str] = None,
        prateleira: Optional[str] = None,
        quantidade_minima: Optional[int] = 0,
    ) -> Produto:
        produto = self.obter(id_produto)  # regra: só edita quem já existe
        dados = self._validar_dados(nome, categoria, prateleira, quantidade_minima)

        # O nome pode repetir apenas se pertencer ao PRÓPRIO produto editado.
        outro = self._repo.buscar_por_nome_exato(dados["nome"])
        if outro is not None and outro.id_produto != produto.id_produto:
            raise RegistroDuplicadoError("Já existe outro produto com este nome.")

        for campo, valor in dados.items():
            setattr(produto, campo, valor)  # "quantidade" não está em dados: não muda
        self._confirmar()
        return produto

    # ------------------------------------------------------------------
    # Excluir produto
    # ------------------------------------------------------------------
    def excluir(self, id_produto: int) -> None:
        produto = self.obter(id_produto)

        if self._repo.possui_os(id_produto):
            raise OperacaoNaoPermitidaError(
                "Não é possível excluir: o produto já foi utilizado em ordens de serviço."
            )
        if self._repo.possui_movimentacoes(id_produto):
            raise OperacaoNaoPermitidaError(
                "Não é possível excluir: o produto possui movimentações de estoque registradas, "
                "que fazem parte do histórico da oficina."
            )

        self._repo.remover(produto)
        self._confirmar()

    # ------------------------------------------------------------------
    # Consultas (não precisam de commit)
    # ------------------------------------------------------------------
    def obter(self, id_produto: int) -> Produto:
        produto = self._repo.buscar_por_id(id_produto)
        if produto is None:
            raise RegistroNaoEncontradoError(f"Produto {id_produto} não encontrado.")
        return produto

    def buscar_por_nome(self, nome: str) -> Optional[Produto]:
        return self._repo.buscar_por_nome_exato(self._normalizar_nome(nome))

    def buscar(self, termo: str) -> List[Produto]:
        return self._repo.buscar(termo.strip())

    def listar(self) -> List[Produto]:
        return self._repo.listar_todos()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    @staticmethod
    def _normalizar_nome(nome: Optional[str]) -> str:
        """Tira espaços das pontas e repetidos no meio: ' Filtro   de  Ar ' -> 'Filtro de Ar'."""
        return " ".join((nome or "").split())

    def _validar_dados(
        self,
        nome: Optional[str],
        categoria: Optional[str],
        prateleira: Optional[str],
        quantidade_minima: Optional[int],
    ) -> Dict[str, Any]:
        """
        Valida e normaliza os dados. Acumula TODOS os erros e levanta uma
        única ValidacaoError, para a tela mostrar tudo de uma vez.
        """
        erros: List[str] = []

        nome = self._normalizar_nome(nome)
        if not nome:
            erros.append("O nome é obrigatório.")
        elif len(nome) > 150:
            erros.append("O nome deve ter no máximo 150 caracteres.")

        categoria = (categoria or "").strip() or None
        if categoria is not None and len(categoria) > 100:
            erros.append("A categoria deve ter no máximo 100 caracteres.")

        prateleira = (prateleira or "").strip() or None
        if prateleira is not None and len(prateleira) > 50:
            erros.append("A prateleira deve ter no máximo 50 caracteres.")

        if quantidade_minima is None:
            quantidade_minima = 0
        if not (
            isinstance(quantidade_minima, int)
            and not isinstance(quantidade_minima, bool)
            and 0 <= quantidade_minima <= QUANTIDADE_MINIMA_MAXIMA
        ):
            erros.append(
                f"A quantidade mínima deve ser um número inteiro entre 0 e {QUANTIDADE_MINIMA_MAXIMA}."
            )

        if erros:
            raise ValidacaoError(erros)

        return {
            "nome": nome,
            "categoria": categoria,
            "prateleira": prateleira,
            "quantidade_minima": quantidade_minima,
        }

    def _confirmar(self) -> None:
        """
        Faz o commit. Se o banco recusar, desfaz tudo (rollback).

        O IntegrityError é a "última linha de defesa": a checagem de nome
        duplicado acima pode falhar numa corrida entre duas janelas, mas o
        índice único uq_produto_nome do banco nunca falha.
        """
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise RegistroDuplicadoError(
                "O banco de dados recusou a operação por violar uma restrição "
                "de unicidade ou de vínculo."
            ) from exc
        except Exception:
            self._session.rollback()
            raise
