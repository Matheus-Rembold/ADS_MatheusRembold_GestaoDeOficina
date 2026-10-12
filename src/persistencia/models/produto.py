"""
Model da tabela PRODUTO (RF03).

quantidade_minima é o que alimenta o alerta de estoque baixo (HU09).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Integer, DateTime, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class Produto(Base):
    __tablename__ = "produto"
    __table_args__ = (
        CheckConstraint("quantidade >= 0", name="ck_produto_quantidade_positiva"),
        CheckConstraint("quantidade_minima >= 0", name="ck_produto_quantidade_minima_positiva"),
    )

    id_produto: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria: Mapped[Optional[str]] = mapped_column(String(100))
    prateleira: Mapped[Optional[str]] = mapped_column(String(50))
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantidade_minima: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # --- Lado "um" dos relacionamentos com OsProduto/EntradaEstoque ---
    os_produtos: Mapped[List["OsProduto"]] = relationship(back_populates="produto")
    entradas_estoque: Mapped[List["EntradaEstoque"]] = relationship(back_populates="produto")

    @property
    def estoque_baixo(self) -> bool:
        """Regra de negócio do HU09, exposta direto no model."""
        return self.quantidade < self.quantidade_minima

    def __repr__(self) -> str:
        return f"<Produto id={self.id_produto} nome={self.nome!r}>"
