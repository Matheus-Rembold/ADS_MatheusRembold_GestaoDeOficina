"""
Model da tabela AGENDAMENTO (RF05).

A regra "no máximo 2 serviços no mesmo horário" (DVP, RF05/HU13) fica na
Camada de Serviço: não dá para expressá-la com uma constraint simples do
PostgreSQL, porque depende da sobreposição de intervalos de tempo.

Situações (StatusAgendamento):
    agendado  -> ocupa a agenda
    cancelado -> libera o horário (HU15)
    concluido -> o cliente veio e o agendamento virou uma OS (id_ordem_servico)
"""
from __future__ import annotations

import enum
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class StatusAgendamento(str, enum.Enum):
    AGENDADO = "agendado"
    CANCELADO = "cancelado"
    CONCLUIDO = "concluido"

    @property
    def rotulo(self) -> str:
        return {
            StatusAgendamento.AGENDADO: "Agendado",
            StatusAgendamento.CANCELADO: "Cancelado",
            StatusAgendamento.CONCLUIDO: "Concluído",
        }[self]


class Agendamento(Base):
    __tablename__ = "agendamento"
    __table_args__ = (
        CheckConstraint(
            "status IN ('agendado', 'cancelado', 'concluido')",
            name="ck_agendamento_status",
        ),
        CheckConstraint(
            "duracao_estimada_horas IS NULL OR duracao_estimada_horas > 0",
            name="ck_agendamento_duracao",
        ),
    )

    id_agendamento: Mapped[int] = mapped_column(primary_key=True)
    id_cliente: Mapped[int] = mapped_column(ForeignKey("cliente.id_cliente"), nullable=False)
    id_veiculo: Mapped[int] = mapped_column(ForeignKey("veiculo.id_veiculo"), nullable=False)
    tipo_servico: Mapped[str] = mapped_column(String(150), nullable=False)
    data_hora: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duracao_estimada_horas: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    status: Mapped[StatusAgendamento] = mapped_column(
        Enum(
            StatusAgendamento,
            native_enum=False,  # VARCHAR + CHECK (padrão do projeto)
            create_constraint=False,
            length=20,
            values_callable=lambda membros: [m.value for m in membros],
        ),
        nullable=False,
        default=StatusAgendamento.AGENDADO,
    )
    # OS gerada a partir deste agendamento (preenchida na conversão). Se a OS for
    # excluída, o vínculo some (ON DELETE SET NULL) e o agendamento continua concluído.
    id_ordem_servico: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ordem_servico.id_ordem_servico", ondelete="SET NULL"), unique=True
    )

    cliente: Mapped["Cliente"] = relationship(back_populates="agendamentos")
    veiculo: Mapped["Veiculo"] = relationship(back_populates="agendamentos")

    @property
    def termino_previsto(self) -> datetime:
        """Quando o veículo deve ficar pronto (início + duração estimada)."""
        horas = self.duracao_estimada_horas or Decimal("0")
        return self.data_hora + timedelta(minutes=float(horas) * 60)

    def __repr__(self) -> str:
        return f"<Agendamento id={self.id_agendamento} data_hora={self.data_hora}>"
