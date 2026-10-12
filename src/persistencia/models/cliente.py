"""
Model da tabela CLIENTE (RF01).

CLIENTE é a entidade raiz do domínio: não depende de nenhuma outra
tabela, mas é referenciada por VEICULO, ORDEM_SERVICO e AGENDAMENTO.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, SmallInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base


class Cliente(Base):
    __tablename__ = "cliente"

    id_cliente: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    idade: Mapped[Optional[int]] = mapped_column(SmallInteger)
    cpf: Mapped[str] = mapped_column(String(14), nullable=False, unique=True)
    contato: Mapped[str] = mapped_column(String(20), nullable=False)
    endereco: Mapped[Optional[str]] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # --- Relacionamentos (1 Cliente -> N Veiculo/OrdemServico/Agendamento) ---
    # back_populates="cliente" diz: "o outro lado desse relacionamento se
    # chama 'cliente' dentro da classe Veiculo/OrdemServico/Agendamento".
    veiculos: Mapped[List["Veiculo"]] = relationship(back_populates="cliente")
    ordens_servico: Mapped[List["OrdemServico"]] = relationship(back_populates="cliente")
    agendamentos: Mapped[List["Agendamento"]] = relationship(back_populates="cliente")

    def __repr__(self) -> str:
        return f"<Cliente id={self.id_cliente} nome={self.nome!r}>"
