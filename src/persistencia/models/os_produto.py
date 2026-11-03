"""
Model da tabela OS_PRODUTO — associativa N:N entre ORDEM_SERVICO e
PRODUTO, com colunas extras (quantidade e preços daquela OS).

Por carregar dados próprios, é modelada como entidade completa, não como
relationship(secondary=...) simples do SQLAlchemy (essa técnica só serve para
tabelas de associação SEM colunas extras).

preco_unitario e custo_unitario são GRAVADOS na OS (cópia do momento): se o
produto mudar de valor depois, as OS antigas continuam como foram cobradas.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import Integer, Numeric, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class OsProduto(Base):
    __tablename__ = "os_produto"
    __table_args__ = (
        UniqueConstraint("id_ordem_servico", "id_produto", name="uq_os_produto"),
        CheckConstraint("quantidade_utilizada > 0", name="ck_os_produto_quantidade"),
        CheckConstraint("preco_unitario >= 0", name="ck_os_produto_preco"),
        CheckConstraint("custo_unitario IS NULL OR custo_unitario >= 0", name="ck_os_produto_custo"),
    )

    id_os_produto: Mapped[int] = mapped_column(primary_key=True)
    id_ordem_servico: Mapped[int] = mapped_column(
        ForeignKey("ordem_servico.id_ordem_servico"), nullable=False
    )
    id_produto: Mapped[int] = mapped_column(ForeignKey("produto.id_produto"), nullable=False)
    quantidade_utilizada: Mapped[int] = mapped_column(Integer, nullable=False)
    # Preço cobrado do cliente por unidade, digitado na OS.
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Último valor pago pela oficina por unidade, no momento em que a peça entrou
    # na OS (referência para calcular margem). Vazio se o produto nunca foi comprado.
    custo_unitario: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))

    # --- Lados "muitos" com OrdemServico e Produto ---
    ordem_servico: Mapped["OrdemServico"] = relationship(back_populates="os_produtos")
    produto: Mapped["Produto"] = relationship(back_populates="os_produtos")

    @property
    def subtotal(self) -> Decimal:
        return self.quantidade_utilizada * self.preco_unitario

    def __repr__(self) -> str:
        return f"<OsProduto os={self.id_ordem_servico} produto={self.id_produto} qtd={self.quantidade_utilizada}>"
