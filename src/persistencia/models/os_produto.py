"""
Model da tabela OS_PRODUTO — associativa N:N entre ORDEM_SERVICO e
PRODUTO, com a coluna extra quantidade_utilizada.

Por carregar um dado próprio (a quantidade), é modelada como entidade
completa, não como relationship(secondary=...) simples do SQLAlchemy
(essa técnica só serve para tabelas de associação SEM colunas extras).
"""
from __future__ import annotations

from sqlalchemy import Integer, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class OsProduto(Base):
    __tablename__ = "os_produto"
    __table_args__ = (
        UniqueConstraint("id_ordem_servico", "id_produto", name="uq_os_produto"),
        CheckConstraint("quantidade_utilizada > 0", name="ck_os_produto_quantidade"),
    )

    id_os_produto: Mapped[int] = mapped_column(primary_key=True)
    id_ordem_servico: Mapped[int] = mapped_column(
        ForeignKey("ordem_servico.id_ordem_servico"), nullable=False
    )
    id_produto: Mapped[int] = mapped_column(ForeignKey("produto.id_produto"), nullable=False)
    quantidade_utilizada: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Lados "muitos" com OrdemServico e Produto ---
    ordem_servico: Mapped["OrdemServico"] = relationship(back_populates="os_produtos")
    produto: Mapped["Produto"] = relationship(back_populates="os_produtos")

    def __repr__(self) -> str:
        return f"<OsProduto os={self.id_ordem_servico} produto={self.id_produto} qtd={self.quantidade_utilizada}>"
