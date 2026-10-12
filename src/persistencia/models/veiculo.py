"""
Model da tabela VEICULO (RF02).

Cada veículo pertence a um único cliente (FK obrigatória).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, SmallInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class Veiculo(Base):
    __tablename__ = "veiculo"

    id_veiculo: Mapped[int] = mapped_column(primary_key=True)
    id_cliente: Mapped[int] = mapped_column(ForeignKey("cliente.id_cliente"), nullable=False)
    modelo: Mapped[str] = mapped_column(String(100), nullable=False)
    marca: Mapped[str] = mapped_column(String(100), nullable=False)
    ano: Mapped[Optional[int]] = mapped_column(SmallInteger)
    motor: Mapped[Optional[str]] = mapped_column(String(50))
    placa: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # --- Lado "muitos" do relacionamento com Cliente ---
    # Aqui o relationship() não precisa de List[...] porque cada veículo
    # tem só UM cliente (lado N de um 1:N apontando pra 1).
    cliente: Mapped["Cliente"] = relationship(back_populates="veiculos")

    # --- Lado "um" dos relacionamentos com OrdemServico/Agendamento ---
    ordens_servico: Mapped[List["OrdemServico"]] = relationship(back_populates="veiculo")
    agendamentos: Mapped[List["Agendamento"]] = relationship(back_populates="veiculo")

    def __repr__(self) -> str:
        return f"<Veiculo id={self.id_veiculo} placa={self.placa!r}>"
