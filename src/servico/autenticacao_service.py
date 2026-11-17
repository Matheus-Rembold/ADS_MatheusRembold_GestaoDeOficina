"""
Serviço de Autenticação (RF10).

Fluxo: banco disponível -> (nenhum usuário? configuração inicial) -> login.

Regras de segurança (e o porquê de cada uma):
- Mensagem SEMPRE "Usuário ou senha inválidos." para login inexistente,
  senha errada ou usuário inativo: não ajuda quem tenta descobrir logins.
- Login inexistente confere a senha contra um hash falso: o tempo de
  resposta não revela quem existe (seguranca_senha.HASH_FALSO).
- Após MAX_TENTATIVAS falhas seguidas, o usuário fica bloqueado por
  BLOQUEIO_MINUTOS. Contador e bloqueio ficam no BANCO (reiniciar o sistema
  não zera) e voltam a zero no login correto. Durante o bloqueio a senha nem
  é conferida (senão o bloqueio não impediria os chutes).
- O relógio é um parâmetro (injeção de dependência): os testes "avançam" o
  tempo sem esperar minutos de verdade.
- O log registra quem entrou ou falhou, NUNCA a senha.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.persistencia.models import PerfilUsuario, Usuario
from src.persistencia.repositories.usuario_repository import UsuarioRepository
from src.servico.excecoes import (
    CredenciaisInvalidasError,
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    UsuarioBloqueadoError,
    ValidacaoError,
)
from src.servico.seguranca_senha import gerar_hash, senha_confere
from src.servico.usuario_service import normalizar_login, validar_dados, validar_senha_nova

logger = logging.getLogger(__name__)

MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 5
_TRAVA_CONFIGURACAO = 50060  # duas janelas na configuração inicial não criam dois "primeiros donos"


class AutenticacaoService:
    def __init__(self, session: Session, relogio: Callable[[], datetime] = datetime.now) -> None:
        self._session = session
        self._repo = UsuarioRepository(session)
        self._relogio = relogio

    # ------------------------------------------------------------------
    def precisa_configuracao_inicial(self) -> bool:
        """Sem nenhum usuário cadastrado, o sistema pede para criar o dono."""
        return not self._repo.existe_algum()

    def criar_primeiro_usuario(
        self, nome: Optional[str], login: Optional[str], senha: Optional[str], confirmacao: Optional[str]
    ) -> Usuario:
        """Cria o primeiro usuário, SEMPRE dono. Só funciona com a tabela vazia."""
        erros = []
        nome, login, perfil = validar_dados(nome, login, PerfilUsuario.DONO, erros)
        validar_senha_nova(senha, confirmacao, login, erros)
        if erros:
            raise ValidacaoError(erros)
        if self._session.get_bind().dialect.name == "postgresql":
            self._session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _TRAVA_CONFIGURACAO})
        if self._repo.existe_algum():
            self._session.rollback()
            raise OperacaoNaoPermitidaError("O sistema já foi configurado: entre com um usuário existente.")
        usuario = self._repo.adicionar(
            Usuario(nome=nome, login=login, senha_hash=gerar_hash(senha), perfil=PerfilUsuario.DONO, ativo=True)
        )
        try:
            self._session.commit()
        except Exception as exc:
            self._session.rollback()
            raise RegistroDuplicadoError("Não foi possível criar o usuário.") from exc
        logger.info("Configuração inicial: dono %s criado", login)
        return usuario

    def autenticar(self, login: Optional[str], senha: Optional[str]) -> Usuario:
        """Devolve o usuário autenticado ou levanta CredenciaisInvalidasError / UsuarioBloqueadoError."""
        login = normalizar_login(login)
        agora = self._relogio()
        usuario = self._repo.buscar_por_login(login, travar=True) if login else None

        if usuario is not None and usuario.bloqueado_ate is not None and usuario.bloqueado_ate > agora:
            restante = (usuario.bloqueado_ate - agora).total_seconds()
            self._session.rollback()
            logger.warning("Tentativa de login em usuário bloqueado: %s", login)
            raise UsuarioBloqueadoError(restante)

        correta = senha_confere(senha, usuario.senha_hash if usuario is not None else None)

        if usuario is None:
            self._session.rollback()
            logger.warning("Falha de login: usuário inexistente %r", login)
            raise CredenciaisInvalidasError()

        if not correta:
            usuario.tentativas_falhas += 1
            bloqueou = usuario.tentativas_falhas >= MAX_TENTATIVAS
            if bloqueou:
                usuario.bloqueado_ate = agora + timedelta(minutes=BLOQUEIO_MINUTOS)
                usuario.tentativas_falhas = 0  # depois do bloqueio, mais 5 chances
            self._session.commit()
            logger.warning("Falha de login: %s%s", login, " (bloqueado)" if bloqueou else "")
            if bloqueou:
                raise UsuarioBloqueadoError(BLOQUEIO_MINUTOS * 60)
            raise CredenciaisInvalidasError()

        if not usuario.ativo:  # mesma mensagem: não revela que o usuário existe mas está inativo
            self._session.rollback()
            logger.warning("Falha de login: usuário inativo %s", login)
            raise CredenciaisInvalidasError()

        usuario.tentativas_falhas, usuario.bloqueado_ate = 0, None
        usuario.ultimo_login_em = agora
        self._session.commit()
        logger.info("Login: %s (%s)", login, usuario.perfil.value)
        return usuario

    def usuario_vigente(self, id_usuario: int) -> Optional[Usuario]:
        """Usuário atual do banco, se ainda existir e estiver ativo (o guard revalida por aqui)."""
        usuario = self._repo.buscar_por_id(id_usuario)
        return usuario if usuario is not None and usuario.ativo else None
