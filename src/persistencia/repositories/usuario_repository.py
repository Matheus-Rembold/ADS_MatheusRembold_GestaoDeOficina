"""
Repository de Usuário (RF10).

Mesmo padrão dos outros: a Session vem de fora e nenhum método faz commit
(só flush); o commit é do serviço.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.persistencia.models import PerfilUsuario, Usuario


class UsuarioRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def adicionar(self, usuario: Usuario) -> Usuario:
        self._session.add(usuario)
        self._session.flush()  # gera o id
        return usuario

    def flush(self) -> None:
        self._session.flush()

    def buscar_por_id(self, id_usuario: int, travar: bool = False) -> Optional[Usuario]:
        stmt = select(Usuario).where(Usuario.id_usuario == id_usuario)
        if travar:  # duas janelas mudando o mesmo usuário não se atropelam
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self._session.scalars(stmt).first()

    def buscar_por_login(self, login: str, travar: bool = False) -> Optional[Usuario]:
        stmt = select(Usuario).where(func.lower(Usuario.login) == func.lower(login))
        if travar:  # o contador de falhas é lido e gravado na mesma transação
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self._session.scalars(stmt).first()

    def existe_algum(self) -> bool:
        return self._session.scalar(select(func.count()).select_from(Usuario)) > 0

    def contar_donos_ativos(self) -> int:
        return self._session.scalar(
            select(func.count()).select_from(Usuario).where(
                Usuario.perfil == PerfilUsuario.DONO, Usuario.ativo.is_(True)
            )
        )

    def listar(self) -> List[Usuario]:
        stmt = select(Usuario).order_by(Usuario.ativo.desc(), func.lower(Usuario.nome), Usuario.id_usuario)
        return list(self._session.scalars(stmt).all())
