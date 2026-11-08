"""
Repository de Agendamento (RF05).

Mesmo padrão dos outros repositories: a Session vem de fora e nenhum método
faz commit (só flush); o commit é do serviço.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, joinedload

from src.persistencia.models import Agendamento, Cliente, StatusAgendamento, Veiculo


class AgendamentoRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def adicionar(self, agendamento: Agendamento) -> Agendamento:
        self._session.add(agendamento)
        self._session.flush()
        return agendamento

    def flush(self) -> None:
        self._session.flush()

    def travar_agenda(self) -> None:
        """
        Serializa quem mexe na agenda: duas janelas marcando ao mesmo tempo
        poderiam, juntas, estourar o limite de 2 serviços por horário. Usa um
        lock consultivo do PostgreSQL, liberado sozinho no commit/rollback.
        """
        if self._session.get_bind().dialect.name == "postgresql":
            self._session.execute(text("SELECT pg_advisory_xact_lock(50050)"))

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def _base(self):
        return select(Agendamento).options(
            joinedload(Agendamento.cliente), joinedload(Agendamento.veiculo)
        )

    def buscar_por_id(self, id_agendamento: int, travar: bool = False) -> Optional[Agendamento]:
        stmt = self._base().where(Agendamento.id_agendamento == id_agendamento)
        if travar:
            stmt = stmt.with_for_update(of=Agendamento).execution_options(populate_existing=True)
        return self._session.scalars(stmt).unique().first()

    def listar(
        self,
        termo: str = "",
        status: Optional[StatusAgendamento] = None,
        data_inicio: Optional[date] = None,
        data_fim: Optional[date] = None,
    ) -> List[Agendamento]:
        """Ordem cronológica. data_fim é inclusivo (o dia inteiro)."""
        stmt = self._base().join(Agendamento.cliente).join(Agendamento.veiculo)
        if termo:
            stmt = stmt.where(or_(
                Cliente.nome.icontains(termo, autoescape=True),
                Veiculo.placa.icontains(termo, autoescape=True),
                Veiculo.modelo.icontains(termo, autoescape=True),
                Agendamento.tipo_servico.icontains(termo, autoescape=True),
            ))
        if status is not None:
            stmt = stmt.where(Agendamento.status == status)
        if data_inicio is not None:
            stmt = stmt.where(Agendamento.data_hora >= datetime.combine(data_inicio, datetime.min.time()))
        if data_fim is not None:
            stmt = stmt.where(
                Agendamento.data_hora < datetime.combine(data_fim + timedelta(days=1), datetime.min.time())
            )
        stmt = stmt.order_by(Agendamento.data_hora, Agendamento.id_agendamento)
        return list(self._session.scalars(stmt).unique().all())

    def listar_ativos_no_periodo(
        self, inicio: datetime, fim: datetime, ignorar_id: Optional[int] = None
    ) -> List[Agendamento]:
        """
        Agendamentos 'agendado' que se SOBREPÕEM ao intervalo [inicio, fim).
        Há sobreposição quando começa antes do fim E termina depois do início.
        O término é calculado em Python (início + duração), por isso buscamos
        os que começam antes de 'fim' e filtramos o término depois.
        """
        stmt = self._base().where(
            Agendamento.status == StatusAgendamento.AGENDADO,
            Agendamento.data_hora < fim,
            # nenhum serviço dura mais de 24 h: limita a busca sem perder resultado
            Agendamento.data_hora > inicio - timedelta(days=1),
        )
        if ignorar_id is not None:
            stmt = stmt.where(Agendamento.id_agendamento != ignorar_id)
        candidatos = self._session.scalars(stmt).unique().all()
        return [a for a in candidatos if a.termino_previsto > inicio]

    def contar_por_dia(self, inicio: date, fim: date) -> dict:
        """{data: quantidade de agendamentos 'agendado'} entre inicio e fim (inclusivos)."""
        dia = func.date(Agendamento.data_hora)
        stmt = (
            select(dia, func.count())
            .where(
                Agendamento.status == StatusAgendamento.AGENDADO,
                Agendamento.data_hora >= datetime.combine(inicio, datetime.min.time()),
                Agendamento.data_hora < datetime.combine(fim + timedelta(days=1), datetime.min.time()),
            )
            .group_by(dia)
        )
        resultado = {}
        for d, n in self._session.execute(stmt).all():
            resultado[d if isinstance(d, date) else date.fromisoformat(str(d))] = n
        return resultado

    def buscar_cliente(self, id_cliente: int) -> Optional[Cliente]:
        return self._session.get(Cliente, id_cliente)

    def buscar_veiculo(self, id_veiculo: int) -> Optional[Veiculo]:
        return self._session.get(Veiculo, id_veiculo)
