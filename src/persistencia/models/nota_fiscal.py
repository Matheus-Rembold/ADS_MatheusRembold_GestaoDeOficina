"""
Model da tabela NOTA_FISCAL (RF08).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class NotaFiscal(Base):
    __tablename__ = "nota_fiscal"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pendente', 'emitida', 'falha')",
            name="ck_nota_fiscal_status",
        ),
    )

    id_nota_fiscal: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[Optional[str]] = mapped_column(String(50))
    chave_acesso: Mapped[Optional[str]] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    emitida_em: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # --- Lado "um" do relacionamento 1:1 com OrdemServico ---
    # uselist=False é o que diz "isso é um objeto único, não uma lista".
    # Sem isso, ordem_servico.nota_fiscal.ordens_servico seria lista.
    ordem_servico: Mapped[Optional["OrdemServico"]] = relationship(
        back_populates="nota_fiscal", uselist=False
    )

    def __repr__(self) -> str:
        return f"<NotaFiscal id={self.id_nota_fiscal} status={self.status!r}>"
