"""
Controller de Cliente (RF01) - Camada de Controle (DVP, seção 2.1).

Faz a ponte entre a tela e o serviço:
- abre e fecha a Session de cada operação (a tela nunca vê SQLAlchemy);
- devolve DTOs (dados simples), não objetos ORM, porque um objeto ORM só
  pode ser lido enquanto a sessão está aberta;
- deixa as ErroDeNegocio subirem para a tela, que as exibe ao usuário.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.persistencia.models import Cliente
from src.servico.cliente_service import ClienteService
from src.servico.validadores import somente_digitos

# Reexportadas de propósito: a tela importa as exceções DAQUI, sem precisar
# conhecer a camada de serviço (regra de dependência do README).
from src.servico.excecoes import (  # noqa: F401
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)


@dataclass(frozen=True)
class ClienteDTO:
    """Cópia somente-leitura dos dados do cliente, segura para a tela usar."""

    id_cliente: int
    nome: str
    cpf: str
    contato: str
    idade: Optional[int]
    endereco: Optional[str]
    qtd_veiculos: int

    @staticmethod
    def de_modelo(cliente: Cliente) -> "ClienteDTO":
        return ClienteDTO(
            id_cliente=cliente.id_cliente,
            nome=cliente.nome,
            cpf=cliente.cpf,
            contato=cliente.contato,
            idade=cliente.idade,
            endereco=cliente.endereco,
            qtd_veiculos=len(cliente.veiculos),
        )


class ClienteController:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def listar(self, termo: str = "") -> List[ClienteDTO]:
        """Sem termo lista todos; com 11 dígitos busca por CPF; senão, por nome."""
        termo = (termo or "").strip()
        with self._session_factory() as session:
            servico = ClienteService(session)
            if not termo:
                clientes = servico.listar()
            elif len(somente_digitos(termo)) == 11:
                encontrado = servico.buscar_por_cpf(termo)
                clientes = [encontrado] if encontrado else []
            else:
                clientes = servico.buscar_por_nome(termo)
            return [ClienteDTO.de_modelo(c) for c in clientes]

    def obter(self, id_cliente: int) -> ClienteDTO:
        """Leitura fresca de um cliente (levanta RegistroNaoEncontradoError se sumiu)."""
        with self._session_factory() as session:
            return ClienteDTO.de_modelo(ClienteService(session).obter(id_cliente))

    def cadastrar(
        self,
        nome: str,
        cpf: str,
        contato: str,
        idade: Optional[int] = None,
        endereco: Optional[str] = None,
    ) -> ClienteDTO:
        with self._session_factory() as session:
            cliente = ClienteService(session).cadastrar(nome, cpf, contato, idade, endereco)
            return ClienteDTO.de_modelo(cliente)

    def atualizar(
        self,
        id_cliente: int,
        nome: str,
        cpf: str,
        contato: str,
        idade: Optional[int] = None,
        endereco: Optional[str] = None,
    ) -> ClienteDTO:
        with self._session_factory() as session:
            cliente = ClienteService(session).atualizar(
                id_cliente, nome, cpf, contato, idade, endereco
            )
            return ClienteDTO.de_modelo(cliente)

    def excluir(self, id_cliente: int) -> None:
        with self._session_factory() as session:
            ClienteService(session).excluir(id_cliente)
