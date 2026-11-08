"""
Model da tabela PRODUTO (RF03).

quantidade_minima é o que alimenta o alerta de estoque baixo (HU09).
valor_unitario é o CUSTO (último valor pago); preco_venda é o que se cobra.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, String, Integer, Numeric, DateTime, CheckConstraint, Index, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class Produto(Base):
    __tablename__ = "produto"
    __table_args__ = (
        CheckConstraint("quantidade >= 0", name="ck_produto_quantidade_positiva"),
        CheckConstraint("quantidade_minima >= 0", name="ck_produto_quantidade_minima_positiva"),
        CheckConstraint("valor_unitario IS NULL OR valor_unitario >= 0", name="ck_produto_valor_unitario"),
        CheckConstraint("preco_venda IS NULL OR preco_venda >= 0", name="ck_produto_preco_venda"),
        # Preço manual sem valor não faz sentido: o banco também garante isso.
        CheckConstraint(
            "NOT preco_venda_manual OR preco_venda IS NOT NULL", name="ck_produto_preco_manual"
        ),
    )

    id_produto: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria: Mapped[Optional[str]] = mapped_column(String(100))
    prateleira: Mapped[Optional[str]] = mapped_column(String(50))
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantidade_minima: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Valor pago por UNIDADE na compra mais recente (valor da compra ÷ quantidade).
    # Quem atualiza é o RF09, ao registrar uma compra; vazio se nunca foi comprado.
    valor_unitario: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Preço cobrado do cliente por unidade (2 casas, igual a os_produto.preco_unitario).
    # Automático: custo × (1 + MARKUP_PADRAO), recalculado a cada compra
    # (src/servico/precificacao.py). Manual: definido na tela de Produtos e
    # mantido pelas compras. Vazio enquanto não houver custo nem preço manual.
    # As colunas ficam DEPOIS de criado_em porque o ALTER TABLE ... ADD COLUMN
    # da migração sempre acrescenta no fim; assim banco novo e migrado ficam iguais.
    preco_venda: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    preco_venda_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # --- Lado "um" dos relacionamentos com OsProduto/MovimentacaoEstoque ---
    os_produtos: Mapped[List["OsProduto"]] = relationship(back_populates="produto")
    movimentacoes_estoque: Mapped[List["MovimentacaoEstoque"]] = relationship(back_populates="produto")

    @property
    def estoque_baixo(self) -> bool:
        """Regra de negócio do HU09, exposta direto no model."""
        return self.quantidade < self.quantidade_minima

    def __repr__(self) -> str:
        return f"<Produto id={self.id_produto} nome={self.nome!r}>"


# Nome do produto único SEM diferenciar maiúsculas/minúsculas
# ("Filtro de Óleo" e "filtro de óleo" são o mesmo produto). É um índice
# único sobre LOWER(nome); no PostgreSQL ele é criado pelo script
# alterar_produto_nome_unico.sql (o banco já existente não é recriado).
Index("uq_produto_nome", func.lower(Produto.nome), unique=True)
