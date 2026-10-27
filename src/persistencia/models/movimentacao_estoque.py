"""
Model da tabela MOVIMENTACAO_ESTOQUE (RF09 - Gerenciar Estoque).

Cada linha é UM registro manual que mudou o saldo de um produto. O tipo
(enum TipoMovimentacao) diz o motivo; a QUANTIDADE é guardada COM SINAL:
positiva aumenta o estoque, negativa diminui.

    tipo                  sinal   fornecedor     valor
    compra                  +     obrigatório    obrigatório (valor pago)
    doacao                  +     opcional       não usa
    devolucao_fornecedor    -     obrigatório    opcional (valor ressarcido)
    venda_avulsa            -     não usa        obrigatório (valor recebido)
    ajuste                 +/-    não usa        não usa     (observação obrigatória)

Essas regras valem em DUAS camadas: o MovimentacaoEstoqueService dá a
mensagem amigável e os CHECK abaixo garantem no banco, mesmo que alguém
grave por fora do sistema.

O consumo de peças em ordem de serviço NÃO é uma movimentação: é registrado
em OS_PRODUTO (RF04), que também baixa o saldo do produto.
"""
from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class TipoMovimentacao(str, enum.Enum):
    """Motivo da movimentação. O valor (texto) é o que fica gravado no banco."""

    COMPRA = "compra"
    DOACAO = "doacao"
    DEVOLUCAO_FORNECEDOR = "devolucao_fornecedor"
    VENDA_AVULSA = "venda_avulsa"
    AJUSTE = "ajuste"

    @property
    def rotulo(self) -> str:
        """Nome exibido ao usuário."""
        return _ROTULOS[self]

    @property
    def sinal(self) -> Optional[int]:
        """+1 aumenta o saldo, -1 diminui, None quando o próprio lançamento define (ajuste)."""
        return _SINAIS[self]


_ROTULOS = {
    TipoMovimentacao.COMPRA: "Compra",
    TipoMovimentacao.DOACAO: "Doação",
    TipoMovimentacao.DEVOLUCAO_FORNECEDOR: "Devolução ao fornecedor",
    TipoMovimentacao.VENDA_AVULSA: "Venda avulsa",
    TipoMovimentacao.AJUSTE: "Ajuste de estoque",
}
_SINAIS = {
    TipoMovimentacao.COMPRA: 1,
    TipoMovimentacao.DOACAO: 1,
    TipoMovimentacao.DEVOLUCAO_FORNECEDOR: -1,
    TipoMovimentacao.VENDA_AVULSA: -1,
    TipoMovimentacao.AJUSTE: None,
}


class MovimentacaoEstoque(Base):
    __tablename__ = "movimentacao_estoque"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('compra', 'doacao', 'devolucao_fornecedor', 'venda_avulsa', 'ajuste')",
            name="ck_mov_estoque_tipo",
        ),
        CheckConstraint("quantidade <> 0", name="ck_mov_estoque_quantidade"),
        CheckConstraint(
            "(tipo IN ('compra', 'doacao') AND quantidade > 0)"
            " OR (tipo IN ('devolucao_fornecedor', 'venda_avulsa') AND quantidade < 0)"
            " OR tipo = 'ajuste'",
            name="ck_mov_estoque_sinal",
        ),
        CheckConstraint("valor IS NULL OR valor >= 0", name="ck_mov_estoque_valor"),
        CheckConstraint(
            "tipo NOT IN ('compra', 'venda_avulsa') OR valor IS NOT NULL",
            name="ck_mov_estoque_valor_obrigatorio",
        ),
        CheckConstraint(
            "tipo NOT IN ('compra', 'devolucao_fornecedor') OR fornecedor IS NOT NULL",
            name="ck_mov_estoque_fornecedor_obrigatorio",
        ),
        CheckConstraint(
            "tipo <> 'ajuste' OR observacao IS NOT NULL",
            name="ck_mov_estoque_ajuste_observacao",
        ),
        Index("idx_movimentacao_produto", "id_produto"),
        Index("idx_movimentacao_data", "data_movimentacao"),
    )

    id_movimentacao_estoque: Mapped[int] = mapped_column(primary_key=True)
    id_produto: Mapped[int] = mapped_column(ForeignKey("produto.id_produto"), nullable=False)
    tipo: Mapped[TipoMovimentacao] = mapped_column(
        Enum(
            TipoMovimentacao,
            native_enum=False,  # VARCHAR + CHECK (padrão do projeto), não ENUM do PostgreSQL
            create_constraint=False,  # o CHECK nomeado acima já cobre
            length=25,
            values_callable=lambda membros: [m.value for m in membros],
        ),
        nullable=False,
    )
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)  # COM SINAL
    valor: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    data_movimentacao: Mapped[date] = mapped_column(Date, nullable=False)
    fornecedor: Mapped[Optional[str]] = mapped_column(String(150))
    observacao: Mapped[Optional[str]] = mapped_column(Text)

    produto: Mapped["Produto"] = relationship(back_populates="movimentacoes_estoque")

    def __repr__(self) -> str:
        return (
            f"<MovimentacaoEstoque id={self.id_movimentacao_estoque} "
            f"produto={self.id_produto} tipo={self.tipo.value} qtd={self.quantidade:+d}>"
        )
