"""
Model da tabela NOTIFICACAO (RF07).

Dois tipos de mensagem pelo WhatsApp (link wa.me, envio semiautomático):
    pos_venda            -> 0..1 por ORDEM_SERVICO, 7 dias após a entrega
    lembrete_agendamento -> 0..1 por AGENDAMENTO, na véspera do horário

O CHECK ck_notificacao_alvo garante que cada tipo aponte só para o seu
registro (OS ou agendamento). Os UNIQUE nas FKs garantem no máximo uma
notificação por OS e por agendamento.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint, Date, DateTime, Enum, ForeignKey, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


def _enum(classe, tamanho: int) -> Enum:
    """VARCHAR + CHECK nomeado no SQL (padrão do projeto)."""
    return Enum(
        classe,
        native_enum=False,
        create_constraint=False,
        length=tamanho,
        values_callable=lambda membros: [m.value for m in membros],
    )


class TipoNotificacao(str, enum.Enum):
    POS_VENDA = "pos_venda"
    LEMBRETE_AGENDAMENTO = "lembrete_agendamento"

    @property
    def rotulo(self) -> str:
        return {
            TipoNotificacao.POS_VENDA: "Pós-venda",
            TipoNotificacao.LEMBRETE_AGENDAMENTO: "Lembrete de agendamento",
        }[self]


class StatusEnvio(str, enum.Enum):
    PENDENTE = "pendente"
    ENVIADO = "enviado"
    CANCELADO = "cancelado"

    @property
    def rotulo(self) -> str:
        return {
            StatusEnvio.PENDENTE: "Pendente",
            StatusEnvio.ENVIADO: "Enviada",
            StatusEnvio.CANCELADO: "Cancelada",
        }[self]


class Notificacao(Base):
    __tablename__ = "notificacao"
    __table_args__ = (
        CheckConstraint(
            "status_envio IN ('pendente', 'enviado', 'cancelado')",
            name="ck_notificacao_status_envio",
        ),
        CheckConstraint(
            "tipo IN ('pos_venda', 'lembrete_agendamento')",
            name="ck_notificacao_tipo",
        ),
        CheckConstraint(
            "(tipo = 'pos_venda' AND id_ordem_servico IS NOT NULL AND id_agendamento IS NULL)"
            " OR (tipo = 'lembrete_agendamento' AND id_agendamento IS NOT NULL"
            " AND id_ordem_servico IS NULL)",
            name="ck_notificacao_alvo",
        ),
    )

    id_notificacao: Mapped[int] = mapped_column(primary_key=True)
    id_ordem_servico: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ordem_servico.id_ordem_servico"), unique=True
    )
    status_envio: Mapped[StatusEnvio] = mapped_column(
        _enum(StatusEnvio, 20), nullable=False, default=StatusEnvio.PENDENTE
    )
    data_envio_prevista: Mapped[Optional[date]] = mapped_column(Date)
    data_envio_real: Mapped[Optional[datetime]] = mapped_column(DateTime)
    tipo: Mapped[TipoNotificacao] = mapped_column(
        _enum(TipoNotificacao, 25), nullable=False, default=TipoNotificacao.POS_VENDA
    )
    id_agendamento: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agendamento.id_agendamento", ondelete="CASCADE"), unique=True
    )
    mensagem: Mapped[Optional[str]] = mapped_column(Text)  # texto exato enviado
    motivo_cancelamento: Mapped[Optional[str]] = mapped_column(String(150))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ordem_servico: Mapped[Optional["OrdemServico"]] = relationship(back_populates="notificacao")
    agendamento: Mapped[Optional["Agendamento"]] = relationship(back_populates="notificacao")

    def __repr__(self) -> str:
        return (f"<Notificacao id={self.id_notificacao} tipo={self.tipo!r} "
                f"status_envio={self.status_envio!r}>")
