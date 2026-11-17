"""
Controller de Autenticação (RF10): configuração inicial, entrar e sair.

É o único controller SEM @protegido: é por ele que a pessoa entra.
Devolve UsuarioLogadoDTO (sem o hash da senha) e guarda-o na sessão.
"""
from __future__ import annotations

from typing import Callable, Optional

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.controle.sessao import UsuarioLogadoDTO, sessao
from src.persistencia.models import PerfilUsuario, Usuario
from src.servico.autenticacao_service import BLOQUEIO_MINUTOS, MAX_TENTATIVAS, AutenticacaoService
from src.servico.permissoes import Permissao  # noqa: F401 (reexportado para a tela)
from src.servico.seguranca_senha import SENHA_MAXIMA, SENHA_MINIMA  # noqa: F401 (texto de ajuda da tela)

# Reexportadas de propósito: a tela importa as exceções DAQUI.
from src.servico.excecoes import (  # noqa: F401
    CredenciaisInvalidasError,
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    UsuarioBloqueadoError,
    ValidacaoError,
)


def _dto(u: Usuario) -> UsuarioLogadoDTO:
    return UsuarioLogadoDTO(u.id_usuario, u.nome, u.login, PerfilUsuario(u.perfil))


class AutenticacaoController:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def precisa_configuracao_inicial(self) -> bool:
        with self._session_factory() as s:
            return AutenticacaoService(s).precisa_configuracao_inicial()

    def criar_primeiro_usuario(self, nome: str, login: str, senha: str, confirmacao: str) -> UsuarioLogadoDTO:
        """Cria o dono e já entra com ele (a mesma pessoa acabou de digitar a senha)."""
        with self._session_factory() as s:
            usuario = _dto(AutenticacaoService(s).criar_primeiro_usuario(nome, login, senha, confirmacao))
        sessao.entrar(usuario)
        return usuario

    def entrar(self, login: str, senha: str) -> UsuarioLogadoDTO:
        with self._session_factory() as s:
            usuario = _dto(AutenticacaoService(s).autenticar(login, senha))
        sessao.entrar(usuario)
        return usuario

    @staticmethod
    def sair() -> None:
        sessao.sair()

    @staticmethod
    def usuario_logado() -> Optional[UsuarioLogadoDTO]:
        return sessao.usuario

    @staticmethod
    def pode(permissao: Permissao) -> bool:
        return sessao.pode(permissao)

    @staticmethod
    def politica_bloqueio() -> str:
        return f"{MAX_TENTATIVAS} tentativas erradas bloqueiam o usuário por {BLOQUEIO_MINUTOS} minutos."
