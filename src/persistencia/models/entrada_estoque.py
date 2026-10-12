"""
Model da tabela ENTRADA_ESTOQUE (RF09).

O produto referenciado precisa já existir — a própria ForeignKey já
garante isso (não é possível inserir uma entrada apontando para um
id_produto inexistente).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Integer, String, Numeric, Date, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class EntradaEstoque(Base):
    __tablename__ = "entrada_estoque"
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="ck_entrada_estoque_quantidade"),
        CheckConstraint("valor_pago >= 0", name="ck_entrada_estoque_valor_pago"),
    )

    id_entrada_estoque: Mapped[int] = mapped_column(primary_key=True)
    id_produto: Mapped[int] = mapped_column(ForeignKey("produto.id_produto"), nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_pago: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    data_compra: Mapped[date] = mapped_column(Date, nullable=False)
    fornecedor: Mapped[str] = mapped_column(String(150), nullable=False)

    produto: Mapped["Produto"] = relationship(back_populates="entradas_estoque")

    def __repr__(self) -> str:
        return f"<EntradaEstoque id={self.id_entrada_estoque} produto={self.id_produto}>"
