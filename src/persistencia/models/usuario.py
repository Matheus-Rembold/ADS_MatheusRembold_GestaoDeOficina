"""
Model da tabela USUARIO (RF10 - Autenticação e perfis).

A senha NUNCA é guardada: só o hash bcrypt (60 caracteres, com o sal
embutido). O hash não sai da camada de serviço; os controllers devolvem DTOs
sem ele.

O contador de falhas e o bloqueio ficam no BANCO (e não em memória): fechar
e abrir o sistema não zera as tentativas.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Index, Integer, String, func, text, true
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class PerfilUsuario(str, enum.Enum):
    """Perfil de acesso. O valor (texto) é o que fica gravado no banco."""

    DONO = "dono"
    MECANICO = "mecanico"

    @property
    def rotulo(self) -> str:
        # Na tela: Administrador e Funcionário (decidido em 20/11/2026). O valor
        # gravado continua "dono"/"mecanico": trocar só o rótulo dispensa migração.
        return {"dono": "Administrador", "mecanico": "Funcionário"}[self.value]


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint("login = LOWER(login)", name="ck_usuario_login_minusculo"),
        CheckConstraint("perfil IN ('dono', 'mecanico')", name="ck_usuario_perfil"),
        CheckConstraint("tentativas_falhas >= 0", name="ck_usuario_tentativas"),
    )

    id_usuario: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    login: Mapped[str] = mapped_column(String(30), nullable=False)  # sempre em minúsculas
    senha_hash: Mapped[str] = mapped_column(String(60), nullable=False)
    perfil: Mapped[PerfilUsuario] = mapped_column(
        Enum(
            PerfilUsuario,
            native_enum=False,  # VARCHAR + CHECK (padrão do projeto)
            create_constraint=False,
            length=20,
            values_callable=lambda membros: [m.value for m in membros],
        ),
        nullable=False,
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    tentativas_falhas: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    bloqueado_ate: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ultimo_login_em: Mapped[Optional[datetime]] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:  # sem o hash, de propósito
        return f"<Usuario id={self.id_usuario} login={self.login!r} perfil={self.perfil.value}>"


# Login único sem diferenciar maiúsculas (o service já grava em minúsculas;
# o índice é a última linha de defesa, igual ao uq_produto_nome).
Index("uq_usuario_login", func.lower(Usuario.login), unique=True)
