"""
Model da tabela AGENDAMENTO (RF05).

A regra "no máximo 2 agendamentos no mesmo horário" fica na Camada de
Serviço (não é expressável com uma constraint simples do PostgreSQL).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class Agendamento(Base):
    __tablename__ = "agendamento"
    __table_args__ = (
        CheckConstraint(
            "status IN ('agendado', 'cancelado', 'concluido')",
            name="ck_agendamento_status",
        ),
    )

    id_agendamento: Mapped[int] = mapped_column(primary_key=True)
    id_cliente: Mapped[int] = mapped_column(ForeignKey("cliente.id_cliente"), nullable=False)
    id_veiculo: Mapped[int] = mapped_column(ForeignKey("veiculo.id_veiculo"), nullable=False)
    tipo_servico: Mapped[str] = mapped_column(String(150), nullable=False)
    data_hora: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duracao_estimada_horas: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="agendado")

    cliente: Mapped["Cliente"] = relationship(back_populates="agendamentos")
    veiculo: Mapped["Veiculo"] = relationship(back_populates="agendamentos")

    def __repr__(self) -> str:
        return f"<Agendamento id={self.id_agendamento} data_hora={self.data_hora}>"
