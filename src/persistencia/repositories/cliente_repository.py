"""
Repository de Cliente (RF01 - Gerenciar Clientes).

Camada de Persistência (DVP, seção 2.1): é a ÚNICA parte do sistema que
sabe como consultar a tabela CLIENTE. Serviços e telas chamam estes
métodos e nunca escrevem consultas por conta própria.

Duas regras de projeto:
- A Session é recebida de fora (quem chama controla a transação).
- Nenhum método faz commit; usam flush() para enviar o SQL ao banco
  dentro da transação aberta. O commit é decidido pela Camada de Serviço.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from src.persistencia.models import Agendamento, Cliente, OrdemServico, StatusOrdemServico, Veiculo
from src.persistencia.repositories import paginacao


class ClienteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def adicionar(self, cliente: Cliente) -> Cliente:
        """Insere um novo cliente. Após o flush, cliente.id_cliente já existe."""
        self._session.add(cliente)
        self._session.flush()
        return cliente

    def remover(self, cliente: Cliente) -> None:
        """Marca o cliente para exclusão e envia o DELETE ao banco."""
        self._session.delete(cliente)
        self._session.flush()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def buscar_por_id(self, id_cliente: int) -> Optional[Cliente]:
        """session.get() busca pela chave primária (e usa cache da sessão)."""
        return self._session.get(Cliente, id_cliente)

    def buscar_por_cpf(self, cpf: str) -> Optional[Cliente]:
        """CPF é único (NOT NULL UNIQUE), então há no máximo um resultado."""
        stmt = select(Cliente).where(Cliente.cpf == cpf)
        return self._session.scalars(stmt).first()

    def buscar_por_nome(self, termo: str) -> List[Cliente]:
        """Busca parcial, sem diferenciar maiúsculas de minúsculas."""
        stmt = (
            select(Cliente)
            .where(Cliente.nome.icontains(termo, autoescape=True))
            .order_by(Cliente.nome)
        )
        return list(self._session.scalars(stmt).all())

    def listar_todos(self) -> List[Cliente]:
        """
        Lista todos os clientes já trazendo os veículos de cada um.

        selectinload carrega os veículos de TODOS os clientes em uma única
        query extra, evitando o problema N+1 (uma query por cliente).
        """
        stmt = (
            select(Cliente)
            .options(selectinload(Cliente.veiculos))
            .order_by(Cliente.nome)
        )
        return list(self._session.scalars(stmt).all())

    # ------------------------------------------------------------------
    # Paginação (09/11/2026): filtro, contagem e uma página por vez
    # ------------------------------------------------------------------
    @staticmethod
    def _consulta(nome: str = "", cpf: Optional[str] = None):
        stmt = select(Cliente)
        if cpf is not None:
            stmt = stmt.where(Cliente.cpf == cpf)
        elif nome:
            stmt = stmt.where(Cliente.nome.icontains(nome, autoescape=True))
        return stmt

    def contar(self, nome: str = "", cpf: Optional[str] = None) -> int:
        return paginacao.contar(self._session, self._consulta(nome, cpf))

    def listar_pagina(self, nome: str, cpf: Optional[str], limite: int, deslocamento: int) -> List[Cliente]:
        return paginacao.buscar_pagina(
            self._session, self._consulta(nome, cpf),
            ordem=(Cliente.nome, Cliente.id_cliente),
            opcoes=(selectinload(Cliente.veiculos),),  # para mostrar quantos veículos cada um tem
            limite=limite, deslocamento=deslocamento,
        )

    # ------------------------------------------------------------------
    # Consultas de apoio às regras de negócio (a decisão fica no serviço)
    # ------------------------------------------------------------------
    def possui_os_em_andamento(self, id_cliente: int) -> bool:
        """RF01/HU03: cliente com OS em andamento não pode ser excluído."""
        stmt = select(
            exists().where(
                OrdemServico.id_cliente == id_cliente,
                OrdemServico.status == StatusOrdemServico.ANDAMENTO,
            )
        )
        return bool(self._session.scalar(stmt))

    def possui_vinculos(self, id_cliente: int) -> bool:
        """True se o cliente tem veículo, OS ou agendamento cadastrado."""
        stmt = select(
            exists().where(Veiculo.id_cliente == id_cliente)
            | exists().where(OrdemServico.id_cliente == id_cliente)
            | exists().where(Agendamento.id_cliente == id_cliente)
        )
        return bool(self._session.scalar(stmt))
