"""
Model da tabela ORDEM_SERVICO (RF04) — entidade central do domínio.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class OrdemServico(Base):
    __tablename__ = "ordem_servico"
    __table_args__ = (
        CheckConstraint(
            "status IN ('orcamento', 'andamento', 'pronto', 'aguardando_pagamento')",
            name="ck_ordem_servico_status",
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
    status: Mapped[str] = mapped_column(String(25), nullable=False, default="orcamento")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

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

    def __repr__(self) -> str:
        return f"<OrdemServico id={self.id_ordem_servico} status={self.status!r}>"
