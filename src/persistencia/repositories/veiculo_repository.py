"""
Repository de Veículo (RF02 - Gerenciar Veículos).

Segue o mesmo padrão do ClienteRepository:
- a Session é recebida de fora (quem chama controla a transação);
- nenhum método faz commit; usam flush(). O commit é do serviço.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, joinedload

from src.persistencia.models import Agendamento, Cliente, OrdemServico, Veiculo


class VeiculoRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def adicionar(self, veiculo: Veiculo) -> Veiculo:
        """Insere um novo veículo. Após o flush, veiculo.id_veiculo já existe."""
        self._session.add(veiculo)
        self._session.flush()
        return veiculo

    def remover(self, veiculo: Veiculo) -> None:
        self._session.delete(veiculo)
        self._session.flush()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def buscar_por_id(self, id_veiculo: int) -> Optional[Veiculo]:
        return self._session.get(Veiculo, id_veiculo)

    def buscar_por_placa(self, placa: str) -> Optional[Veiculo]:
        """Placa é única (NOT NULL UNIQUE): no máximo um resultado."""
        stmt = select(Veiculo).where(Veiculo.placa == placa)
        return self._session.scalars(stmt).first()

    def listar_todos(self) -> List[Veiculo]:
        """
        Lista todos os veículos já trazendo o cliente de cada um.

        joinedload faz um JOIN e traz o cliente na MESMA query, evitando o
        problema N+1 (uma query por linha da tabela só para mostrar o dono).
        """
        stmt = (
            select(Veiculo)
            .options(joinedload(Veiculo.cliente))
            .order_by(Veiculo.placa)
        )
        return list(self._session.scalars(stmt).all())

    def buscar(self, termo: str) -> List[Veiculo]:
        """Busca parcial por placa, modelo, marca ou nome do cliente."""
        stmt = (
            select(Veiculo)
            .join(Veiculo.cliente)
            .options(joinedload(Veiculo.cliente))
            .where(
                or_(
                    Veiculo.placa.icontains(termo, autoescape=True),
                    Veiculo.modelo.icontains(termo, autoescape=True),
                    Veiculo.marca.icontains(termo, autoescape=True),
                    Cliente.nome.icontains(termo, autoescape=True),
                )
            )
            .order_by(Veiculo.placa)
        )
        return list(self._session.scalars(stmt).all())

    def listar_por_cliente(self, id_cliente: int) -> List[Veiculo]:
        stmt = (
            select(Veiculo)
            .options(joinedload(Veiculo.cliente))
            .where(Veiculo.id_cliente == id_cliente)
            .order_by(Veiculo.placa)
        )
        return list(self._session.scalars(stmt).all())

    def historico_os(self, id_veiculo: int) -> List[OrdemServico]:
        """HU05: ordens de serviço do veículo, da mais recente para a mais antiga."""
        stmt = (
            select(OrdemServico)
            .where(OrdemServico.id_veiculo == id_veiculo)
            .order_by(OrdemServico.criado_em.desc(), OrdemServico.id_ordem_servico.desc())
        )
        return list(self._session.scalars(stmt).all())

    # ------------------------------------------------------------------
    # Consultas de apoio às regras de negócio (a decisão fica no serviço)
    # ------------------------------------------------------------------
    def possui_os_em_andamento(self, id_veiculo: int) -> bool:
        stmt = select(
            exists().where(
                OrdemServico.id_veiculo == id_veiculo,
                OrdemServico.status == "andamento",
            )
        )
        return bool(self._session.scalar(stmt))

    def possui_vinculos(self, id_veiculo: int) -> bool:
        """True se o veículo tem alguma OS ou agendamento (histórico da oficina)."""
        stmt = select(
            exists().where(OrdemServico.id_veiculo == id_veiculo)
            | exists().where(Agendamento.id_veiculo == id_veiculo)
        )
        return bool(self._session.scalar(stmt))
