"""
Repository de Notificação (RF07).

Só acesso a dados: flush, nunca commit (a transação é do serviço).

Uma notificação aponta para uma OS (pós-venda) OU para um agendamento
(lembrete). Para buscar pelo nome do cliente ou pela placa, as consultas
fazem LEFT JOIN nos dois caminhos e usam COALESCE para chegar ao cliente e
ao veículo certos.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from src.persistencia.models import (
    Agendamento, Cliente, Notificacao, OrdemServico, StatusEnvio, Veiculo,
)
from src.persistencia.repositories import paginacao

# Abas da tela (a regra de cada uma fica aqui porque vira WHERE)
PARA_ENVIAR, PROXIMAS, ENVIADAS, CANCELADAS = "enviar", "proximas", "enviadas", "canceladas"
ABAS = (PARA_ENVIAR, PROXIMAS, ENVIADAS, CANCELADAS)

_CARGA = (
    joinedload(Notificacao.ordem_servico).joinedload(OrdemServico.cliente),
    joinedload(Notificacao.ordem_servico).joinedload(OrdemServico.veiculo),
    joinedload(Notificacao.agendamento).joinedload(Agendamento.cliente),
    joinedload(Notificacao.agendamento).joinedload(Agendamento.veiculo),
)


def _condicao_da_aba(aba: str, hoje: date):
    pendente = Notificacao.status_envio == StatusEnvio.PENDENTE
    if aba == PARA_ENVIAR:
        return pendente & (Notificacao.data_envio_prevista <= hoje)
    if aba == PROXIMAS:
        return pendente & (Notificacao.data_envio_prevista > hoje)
    if aba == ENVIADAS:
        return Notificacao.status_envio == StatusEnvio.ENVIADO
    return Notificacao.status_envio == StatusEnvio.CANCELADO


def _ordem_da_aba(aba: str):
    if aba in (PARA_ENVIAR, PROXIMAS):  # as mais antigas (atrasadas) primeiro
        return (Notificacao.data_envio_prevista, Notificacao.id_notificacao)
    if aba == ENVIADAS:
        return (Notificacao.data_envio_real.desc(), Notificacao.id_notificacao.desc())
    return (Notificacao.id_notificacao.desc(),)


class NotificacaoRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def adicionar(self, notificacao: Notificacao) -> Notificacao:
        self._session.add(notificacao)
        self._session.flush()
        return notificacao

    def flush(self) -> None:
        self._session.flush()

    def cancelar_pendentes_do_cliente(self, id_cliente: int, motivo: str) -> int:
        """Cliente deixou de aceitar mensagens: cancela tudo o que ainda não saiu."""
        ids = self._ids_do_cliente(id_cliente, StatusEnvio.PENDENTE)
        return self._mudar_status(ids, StatusEnvio.CANCELADO, motivo)

    def reativar_do_cliente(self, id_cliente: int, motivo: str) -> List[Notificacao]:
        """Notificações do cliente canceladas por `motivo` (para o serviço decidir quais voltam)."""
        ids = self._ids_do_cliente(id_cliente, StatusEnvio.CANCELADO)
        if not ids:
            return []
        stmt = (select(Notificacao).options(*_CARGA)
                .where(Notificacao.id_notificacao.in_(ids), Notificacao.motivo_cancelamento == motivo))
        return list(self._session.scalars(stmt).unique().all())

    def _ids_do_cliente(self, id_cliente: int, status: StatusEnvio) -> List[int]:
        stmt = (
            select(Notificacao.id_notificacao)
            .outerjoin(OrdemServico, OrdemServico.id_ordem_servico == Notificacao.id_ordem_servico)
            .outerjoin(Agendamento, Agendamento.id_agendamento == Notificacao.id_agendamento)
            .where(Notificacao.status_envio == status,
                   func.coalesce(OrdemServico.id_cliente, Agendamento.id_cliente) == id_cliente)
        )
        return list(self._session.scalars(stmt).all())

    def _mudar_status(self, ids: List[int], status: StatusEnvio, motivo: Optional[str]) -> int:
        if not ids:
            return 0
        self._session.execute(
            update(Notificacao).where(Notificacao.id_notificacao.in_(ids))
            .values(status_envio=status, motivo_cancelamento=motivo)
            .execution_options(synchronize_session="fetch")
        )
        self._session.flush()
        return len(ids)

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def buscar_por_id(self, id_notificacao: int, travar: bool = False) -> Optional[Notificacao]:
        stmt = select(Notificacao).options(*_CARGA).where(Notificacao.id_notificacao == id_notificacao)
        if travar:  # trava só a notificação (lado não nulo dos LEFT JOINs)
            stmt = stmt.with_for_update(of=Notificacao).execution_options(populate_existing=True)
        return self._session.scalars(stmt).unique().first()

    def buscar_da_os(self, id_os: int) -> Optional[Notificacao]:
        return self._session.scalars(
            select(Notificacao).where(Notificacao.id_ordem_servico == id_os)).first()

    def buscar_do_agendamento(self, id_agendamento: int) -> Optional[Notificacao]:
        return self._session.scalars(
            select(Notificacao).where(Notificacao.id_agendamento == id_agendamento)).first()

    @staticmethod
    def _consulta(termo: str = ""):
        stmt = select(Notificacao)
        if termo:
            id_cliente = func.coalesce(OrdemServico.id_cliente, Agendamento.id_cliente)
            id_veiculo = func.coalesce(OrdemServico.id_veiculo, Agendamento.id_veiculo)
            stmt = (
                stmt.outerjoin(OrdemServico, OrdemServico.id_ordem_servico == Notificacao.id_ordem_servico)
                .outerjoin(Agendamento, Agendamento.id_agendamento == Notificacao.id_agendamento)
                .join(Cliente, Cliente.id_cliente == id_cliente)
                .join(Veiculo, Veiculo.id_veiculo == id_veiculo)
                .where(or_(Cliente.nome.icontains(termo, autoescape=True),
                           Veiculo.placa.icontains(termo, autoescape=True)))
            )
        return stmt

    def contar(self, aba: str, hoje: date, termo: str = "") -> int:
        return paginacao.contar(self._session, self._consulta(termo).where(_condicao_da_aba(aba, hoje)))

    def contar_por_aba(self, hoje: date, termo: str = "") -> Dict[str, int]:
        """Quantas notificações em cada aba, numa consulta só (para os títulos das abas)."""
        sub = self._consulta(termo).subquery()
        colunas = [
            func.count(case((_condicao_da_aba(aba, hoje), 1))).label(aba) for aba in ABAS
        ]
        stmt = select(*colunas).select_from(Notificacao).where(
            Notificacao.id_notificacao.in_(select(sub.c.id_notificacao)))
        linha = self._session.execute(stmt).one()
        return {aba: int(getattr(linha, aba)) for aba in ABAS}

    def listar_pagina(self, aba: str, hoje: date, termo: str, limite: int, deslocamento: int) -> List[Notificacao]:
        return paginacao.buscar_pagina(
            self._session, self._consulta(termo).where(_condicao_da_aba(aba, hoje)),
            ordem=_ordem_da_aba(aba), opcoes=_CARGA, limite=limite, deslocamento=deslocamento,
        )
