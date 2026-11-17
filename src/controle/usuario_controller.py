"""
Controller de Usuários (RF10) — só o dono (Permissao.USUARIOS).

Os DTOs nunca levam o hash da senha. Quem está fazendo a operação (id_ator)
vem da sessão, para o serviço aplicar "ninguém desativa nem rebaixa a si mesmo".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.controle.sessao import protegido, sessao
from src.persistencia.models import PerfilUsuario, Usuario
from src.servico.permissoes import Permissao
from src.servico.usuario_service import UsuarioService

# Reexportadas de propósito: a tela importa tudo DAQUI.
from src.servico.excecoes import (  # noqa: F401
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)
from src.servico.seguranca_senha import SENHA_MAXIMA, SENHA_MINIMA  # noqa: F401


@dataclass(frozen=True)
class UsuarioDTO:
    id_usuario: int
    nome: str
    login: str
    perfil: PerfilUsuario
    ativo: bool
    bloqueado_ate: Optional[datetime]
    ultimo_login_em: Optional[datetime]
    eh_voce: bool  # o usuário logado (não pode se desativar nem mudar o próprio perfil)

    @property
    def perfil_rotulo(self) -> str:
        return self.perfil.rotulo

    @property
    def bloqueado(self) -> bool:
        return self.bloqueado_ate is not None and self.bloqueado_ate > datetime.now()

    @staticmethod
    def de_modelo(u: Usuario) -> "UsuarioDTO":
        logado = sessao.usuario
        return UsuarioDTO(
            u.id_usuario, u.nome, u.login, PerfilUsuario(u.perfil), u.ativo, u.bloqueado_ate,
            u.ultimo_login_em, logado is not None and logado.id_usuario == u.id_usuario,
        )


def _id_ator() -> int:
    return sessao.usuario.id_usuario if sessao.usuario else 0


@protegido(Permissao.USUARIOS)
class UsuarioController:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def listar(self) -> List[UsuarioDTO]:
        with self._session_factory() as s:
            return [UsuarioDTO.de_modelo(u) for u in UsuarioService(s).listar()]

    def obter(self, id_usuario: int) -> UsuarioDTO:
        with self._session_factory() as s:
            return UsuarioDTO.de_modelo(UsuarioService(s).obter(id_usuario))

    def cadastrar(self, nome: str, login: str, senha: str, confirmacao: str, perfil: PerfilUsuario) -> UsuarioDTO:
        with self._session_factory() as s:
            return UsuarioDTO.de_modelo(UsuarioService(s).cadastrar(nome, login, senha, confirmacao, perfil))

    def alterar(self, id_usuario: int, nome: str, perfil: PerfilUsuario) -> UsuarioDTO:
        with self._session_factory() as s:
            return UsuarioDTO.de_modelo(UsuarioService(s).alterar(id_usuario, nome, perfil, _id_ator()))

    def definir_ativo(self, id_usuario: int, ativo: bool) -> UsuarioDTO:
        with self._session_factory() as s:
            return UsuarioDTO.de_modelo(UsuarioService(s).definir_ativo(id_usuario, ativo, _id_ator()))

    def redefinir_senha(self, id_usuario: int, senha: str, confirmacao: str) -> UsuarioDTO:
        with self._session_factory() as s:
            return UsuarioDTO.de_modelo(UsuarioService(s).redefinir_senha(id_usuario, senha, confirmacao))
