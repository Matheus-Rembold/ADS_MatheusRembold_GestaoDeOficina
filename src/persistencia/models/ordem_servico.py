"""
Model da tabela ORDEM_SERVICO (RF04) — entidade central do domínio.

Ciclo de vida (enum StatusOrdemServico):

    orcamento <-> andamento <-> pronto <-> aguardando_pagamento -> entregue

- "orcamento" NÃO baixa o estoque; a partir de "andamento" as peças da OS já
  saíram do estoque (a baixa é feita pelo OrdemServicoService).
- "entregue" é o fim do ciclo (pago e veículo entregue); entregue_em guarda
  quando aconteceu e é a data que o RF07 usa para contar os 7 dias.
- Em "pronto" ou depois a OS fica travada: peças e valores não mudam mais,
  para o valor cobrado bater com o valor faturado (RF08).
"""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import FrozenSet, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class StatusOrdemServico(str, enum.Enum):
    """Situação da OS. O valor (texto) é o que fica gravado no banco."""

    ORCAMENTO = "orcamento"
    ANDAMENTO = "andamento"
    PRONTO = "pronto"
    AGUARDANDO_PAGAMENTO = "aguardando_pagamento"
    ENTREGUE = "entregue"

    @property
    def rotulo(self) -> str:
        """Nome exibido ao usuário."""
        return _ROTULOS[self]

    @property
    def consome_estoque(self) -> bool:
        """Em qualquer situação diferente de orçamento as peças já saíram do estoque."""
        return self is not StatusOrdemServico.ORCAMENTO

    @property
    def editavel(self) -> bool:
        """Só orçamento e andamento aceitam mudar peças, valores e dados da OS."""
        return self in (StatusOrdemServico.ORCAMENTO, StatusOrdemServico.ANDAMENTO)

    @property
    def proximos(self) -> FrozenSet["StatusOrdemServico"]:
        """Situações para as quais é permitido passar a partir desta."""
        return _TRANSICOES[self]


_ROTULOS = {
    StatusOrdemServico.ORCAMENTO: "Somente orçamento",
    StatusOrdemServico.ANDAMENTO: "Em andamento",
    StatusOrdemServico.PRONTO: "Pronto",
    StatusOrdemServico.AGUARDANDO_PAGAMENTO: "Aguardando pagamento",
    StatusOrdemServico.ENTREGUE: "Entregue",
}

_S = StatusOrdemServico
_TRANSICOES = {
    _S.ORCAMENTO: frozenset({_S.ANDAMENTO}),
    _S.ANDAMENTO: frozenset({_S.ORCAMENTO, _S.PRONTO}),
    _S.PRONTO: frozenset({_S.ANDAMENTO, _S.AGUARDANDO_PAGAMENTO}),
    _S.AGUARDANDO_PAGAMENTO: frozenset({_S.PRONTO, _S.ENTREGUE}),
    _S.ENTREGUE: frozenset(),
}

# Passos "para trás": só são permitidos se a OS ainda não tem nota fiscal.
TRANSICOES_DE_VOLTA = frozenset({
    (_S.ANDAMENTO, _S.ORCAMENTO),
    (_S.PRONTO, _S.ANDAMENTO),
    (_S.AGUARDANDO_PAGAMENTO, _S.PRONTO),
})


class OrdemServico(Base):
    __tablename__ = "ordem_servico"
    __table_args__ = (
        CheckConstraint(
            "status IN ('orcamento', 'andamento', 'pronto', 'aguardando_pagamento', 'entregue')",
            name="ck_ordem_servico_status",
        ),
        CheckConstraint("valor_mao_de_obra >= 0", name="ck_os_valor_mao_de_obra"),
        # entregue_em preenchido se, e somente se, a OS está entregue.
        CheckConstraint(
            "(status = 'entregue') = (entregue_em IS NOT NULL)",
            name="ck_os_entregue_em",
        ),
    )

    id_ordem_servico: Mapped[int] = mapped_column(primary_key=True)
    id_cliente: Mapped[int] = mapped_column(ForeignKey("cliente.id_cliente"), nullable=False)
    id_veiculo: Mapped[int] = mapped_column(ForeignKey("veiculo.id_veiculo"), nullable=False)
    # unique=True aqui é o que faz o banco garantir a cardinalidade (0,1)
    # do lado da NotaFiscal — uma nota não pode ser reaproveitada em
    # duas ordens de serviço diferentes.
    id_nota_fiscal: Mapped[Optional[int]] = mapped_column(
        ForeignKey("nota_fiscal.id_nota_fiscal"), unique=True
    )
    descricao_problema: Mapped[Optional[str]] = mapped_column(Text)
    quilometragem: Mapped[Optional[int]] = mapped_column(Integer)
    # Categoria do serviço (ex.: "Revisão", "Freios"): é o que o RF06 usa para
    # contar os serviços mais prestados.
    tipo_servico: Mapped[Optional[str]] = mapped_column(String(150))
    # Mão de obra cobrada: um valor único por OS (as peças são somadas à parte).
    valor_mao_de_obra: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[StatusOrdemServico] = mapped_column(
        Enum(
            StatusOrdemServico,
            native_enum=False,  # VARCHAR + CHECK (padrão do projeto), não ENUM do PostgreSQL
            create_constraint=False,  # o CHECK nomeado acima já cobre
            length=25,
            values_callable=lambda membros: [m.value for m in membros],
        ),
        nullable=False,
        default=StatusOrdemServico.ORCAMENTO,
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    entregue_em: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # --- Lado "muitos" com Cliente e Veiculo (many-to-one, escalar) ---
    cliente: Mapped["Cliente"] = relationship(back_populates="ordens_servico")
    veiculo: Mapped["Veiculo"] = relationship(back_populates="ordens_servico")

    # --- Lado "muitos" do 1:1 com NotaFiscal (escalar, sem uselist aqui
    # porque o FK mora NESTA tabela — já é naturalmente um objeto só) ---
    nota_fiscal: Mapped[Optional["NotaFiscal"]] = relationship(back_populates="ordem_servico")

    # --- Lado "um" com OsProduto (1:N) ---
    os_produtos: Mapped[List["OsProduto"]] = relationship(
        back_populates="ordem_servico", cascade="all, delete-orphan"
    )

    # --- Lado "um" do 1:1 com Notificacao (0,1 — ver Notificacao) ---
    notificacao: Mapped[Optional["Notificacao"]] = relationship(
        back_populates="ordem_servico", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def valor_pecas(self) -> Decimal:
        """Soma de (quantidade x preço cobrado) de todas as peças da OS."""
        return sum(
            (i.quantidade_utilizada * i.preco_unitario for i in self.os_produtos), Decimal("0")
        )

    @property
    def valor_total(self) -> Decimal:
        """Peças + mão de obra. Calculado na hora, nunca guardado."""
        return self.valor_pecas + self.valor_mao_de_obra

    def __repr__(self) -> str:
        return f"<OrdemServico id={self.id_ordem_servico} status={self.status.value!r}>"
