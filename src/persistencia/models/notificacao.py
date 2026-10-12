"""
Model da tabela NOTIFICACAO (RF07).

Relacionamento 0..1 com ORDEM_SERVICO: unique=True na FK garante que
uma ordem de serviço tenha no máximo uma notificação vinculada.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Date, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class Notificacao(Base):
    __tablename__ = "notificacao"
    __table_args__ = (
        CheckConstraint(
            "status_envio IN ('pendente', 'enviado', 'cancelado')",
            name="ck_notificacao_status_envio",
        ),
    )

    id_notificacao: Mapped[int] = mapped_column(primary_key=True)
    id_ordem_servico: Mapped[int] = mapped_column(
        ForeignKey("ordem_servico.id_ordem_servico"), nullable=False, unique=True
    )
    status_envio: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    data_envio_prevista: Mapped[Optional[date]] = mapped_column(Date)
    data_envio_real: Mapped[Optional[datetime]] = mapped_column(DateTime)

    ordem_servico: Mapped["OrdemServico"] = relationship(back_populates="notificacao")

    def __repr__(self) -> str:
        return f"<Notificacao id={self.id_notificacao} status_envio={self.status_envio!r}>"
