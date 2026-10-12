"""
Serviço de Cliente (RF01 - Gerenciar Clientes; HU01, HU02 e HU03).

Camada de Serviço (DVP, seção 2.1): concentra as REGRAS DE NEGÓCIO e é a
dona da transação. Divisão de responsabilidades:

    Repository  -> "o que existe no banco?"
    Service     -> "o que o negócio permite fazer?" (+ commit/rollback)

Os métodos de escrita só fazem commit se todas as regras passaram; se algo
falhar, levantam uma ErroDeNegocio e nada é gravado.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.persistencia.models import Cliente
from src.persistencia.repositories.cliente_repository import ClienteRepository
from src.servico.excecoes import (
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)
from src.servico.validadores import cpf_valido, formatar_cpf, somente_digitos


class ClienteService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = ClienteRepository(session)

    # ------------------------------------------------------------------
    # HU01 - Cadastrar cliente
    # ------------------------------------------------------------------
    def cadastrar(
        self,
        nome: str,
        cpf: str,
        contato: str,
        idade: Optional[int] = None,
        endereco: Optional[str] = None,
    ) -> Cliente:
        dados = self._validar_dados(nome, cpf, contato, idade, endereco)

        if self._repo.buscar_por_cpf(dados["cpf"]) is not None:
            raise RegistroDuplicadoError("Já existe um cliente cadastrado com este CPF.")

        cliente = self._repo.adicionar(Cliente(**dados))
        self._confirmar()
        return cliente

    # ------------------------------------------------------------------
    # HU02 - Atualizar dados do cliente
    # ------------------------------------------------------------------
    def atualizar(
        self,
        id_cliente: int,
        nome: str,
        cpf: str,
        contato: str,
        idade: Optional[int] = None,
        endereco: Optional[str] = None,
    ) -> Cliente:
        cliente = self.obter(id_cliente)  # regra: só edita quem já existe
        dados = self._validar_dados(nome, cpf, contato, idade, endereco)

        # O CPF pode repetir apenas se pertencer ao PRÓPRIO cliente editado.
        outro = self._repo.buscar_por_cpf(dados["cpf"])
        if outro is not None and outro.id_cliente != cliente.id_cliente:
            raise RegistroDuplicadoError("Já existe outro cliente com este CPF.")

        for campo, valor in dados.items():
            setattr(cliente, campo, valor)  # o UPDATE é gerado no commit
        self._confirmar()
        return cliente

    # ------------------------------------------------------------------
    # HU03 - Excluir cliente
    # ------------------------------------------------------------------
    def excluir(self, id_cliente: int) -> None:
        cliente = self.obter(id_cliente)

        if self._repo.possui_os_em_andamento(id_cliente):
            raise OperacaoNaoPermitidaError(
                "Não é possível excluir: o cliente possui ordens de serviço em andamento."
            )
        if self._repo.possui_vinculos(id_cliente):
            raise OperacaoNaoPermitidaError(
                "Não é possível excluir: o cliente possui veículos, ordens de serviço "
                "ou agendamentos vinculados, que fazem parte do histórico da oficina."
            )

        self._repo.remover(cliente)
        self._confirmar()

    # ------------------------------------------------------------------
    # Consultas (não precisam de commit)
    # ------------------------------------------------------------------
    def obter(self, id_cliente: int) -> Cliente:
        cliente = self._repo.buscar_por_id(id_cliente)
        if cliente is None:
            raise RegistroNaoEncontradoError(f"Cliente {id_cliente} não encontrado.")
        return cliente

    def buscar_por_cpf(self, cpf: str) -> Optional[Cliente]:
        digitos = somente_digitos(cpf)
        return self._repo.buscar_por_cpf(formatar_cpf(digitos)) if len(digitos) == 11 else None

    def buscar_por_nome(self, termo: str) -> List[Cliente]:
        return self._repo.buscar_por_nome(termo.strip())

    def listar(self) -> List[Cliente]:
        return self._repo.listar_todos()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    @staticmethod
    def _validar_dados(
        nome: Optional[str],
        cpf: Optional[str],
        contato: Optional[str],
        idade: Optional[int],
        endereco: Optional[str],
    ) -> Dict[str, Any]:
        """
        Valida e normaliza os dados. Acumula TODOS os erros e levanta uma
        única ValidacaoError, para a tela mostrar tudo de uma vez.
        """
        erros: List[str] = []

        nome = (nome or "").strip()
        if not nome:
            erros.append("O nome é obrigatório.")
        elif len(nome) > 150:
            erros.append("O nome deve ter no máximo 150 caracteres.")

        contato = (contato or "").strip()
        if not contato:
            erros.append("O contato é obrigatório.")
        elif len(contato) > 20:
            erros.append("O contato deve ter no máximo 20 caracteres.")

        digitos = somente_digitos(cpf)
        if not digitos:
            erros.append("O CPF é obrigatório.")
        elif not cpf_valido(digitos):
            erros.append("O CPF informado é inválido.")

        if idade is not None and not (isinstance(idade, int) and 0 <= idade <= 120):
            erros.append("A idade deve ser um número inteiro entre 0 e 120.")

        endereco = (endereco or "").strip() or None
        if endereco is not None and len(endereco) > 255:
            erros.append("O endereço deve ter no máximo 255 caracteres.")

        if erros:
            raise ValidacaoError(erros)

        return {
            "nome": nome,
            "cpf": formatar_cpf(digitos),  # sempre salvo como 000.000.000-00
            "contato": contato,
            "idade": idade,
            "endereco": endereco,
        }

    def _confirmar(self) -> None:
        """
        Faz o commit. Se o banco recusar, desfaz tudo (rollback).

        O IntegrityError é a "última linha de defesa": a checagem de CPF
        duplicado acima pode falhar numa corrida entre duas janelas, mas a
        constraint UNIQUE do banco nunca falha.
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
