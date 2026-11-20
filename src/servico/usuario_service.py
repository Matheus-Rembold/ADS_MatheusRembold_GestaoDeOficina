"""
Serviço de Usuários (RF10) — tela de Usuários, só para o dono.

Regras:
- login único sem diferenciar maiúsculas (gravado em minúsculas), 3 a 30
  caracteres: letras, números, ponto, hífen e sublinhado;
- mesma política de senha e mesmo bcrypt do login (seguranca_senha.py);
- não existe exclusão de usuário, só desativação (o histórico de quem fez o
  quê pode ser útil no futuro, e a configuração inicial nunca reaparece);
- PROTEÇÃO DO ÚLTIMO DONO: não se pode desativar nem rebaixar o último dono
  ativo; e ninguém desativa ou muda o próprio perfil (para não se trancar
  fora). Por isso os métodos recebem `id_ator` (quem está fazendo).
- redefinir a senha também desbloqueia o usuário (o dono "destrava" um
  mecânico que errou a senha 5 vezes).

A permissão (só o dono acessa) é checada no controller; aqui ficam as regras.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Union

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.persistencia.models import PerfilUsuario, Usuario
from src.persistencia.repositories.usuario_repository import UsuarioRepository
from src.servico.excecoes import (
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)
from src.servico.seguranca_senha import gerar_hash, problemas_da_senha

logger = logging.getLogger(__name__)

NOME_MAXIMO = 100
_LOGIN_VALIDO = re.compile(r"^[a-z0-9._-]{3,30}$")
# Trava da administração de usuários: evita que dois donos, em duas janelas,
# desativem um ao outro ao mesmo tempo e deixem o sistema sem dono (só PostgreSQL).
_TRAVA_USUARIOS = 50061


def normalizar_login(login: Optional[str]) -> str:
    return (login or "").strip().lower()


def validar_dados(nome, login, perfil, erros: List[str]):
    """Valida nome, login e perfil (acumula os erros). Devolve os valores normalizados."""
    nome = " ".join((nome or "").split())
    if not nome:
        erros.append("O nome é obrigatório.")
    elif len(nome) > NOME_MAXIMO:
        erros.append(f"O nome deve ter no máximo {NOME_MAXIMO} caracteres.")
    login = normalizar_login(login)
    if login is not None and not _LOGIN_VALIDO.match(login):
        erros.append("O usuário deve ter de 3 a 30 caracteres: letras sem acento, números, ponto, hífen ou sublinhado.")
    try:
        perfil = PerfilUsuario(perfil)
    except ValueError:
        erros.append("Escolha o perfil: administrador ou funcionário.")
        perfil = None
    return nome, login, perfil


def validar_senha_nova(senha, confirmacao, login, erros: List[str]) -> None:
    erros.extend(problemas_da_senha(senha, login))
    if isinstance(senha, str) and senha and senha != confirmacao:
        erros.append("A confirmação não é igual à senha.")


class UsuarioService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = UsuarioRepository(session)

    # ------------------------------------------------------------------
    def listar(self) -> List[Usuario]:
        return self._repo.listar()

    def obter(self, id_usuario: int) -> Usuario:
        usuario = self._repo.buscar_por_id(id_usuario)
        if usuario is None:
            raise RegistroNaoEncontradoError(f"Usuário {id_usuario} não encontrado.")
        return usuario

    def cadastrar(
        self,
        nome: Optional[str],
        login: Optional[str],
        senha: Optional[str],
        confirmacao: Optional[str],
        perfil: Union[PerfilUsuario, str, None],
    ) -> Usuario:
        erros: List[str] = []
        nome, login, perfil = validar_dados(nome, login, perfil, erros)
        validar_senha_nova(senha, confirmacao, login, erros)
        if erros:
            raise ValidacaoError(erros)
        if self._repo.buscar_por_login(login) is not None:
            raise RegistroDuplicadoError(f"Já existe um usuário “{login}”.")
        usuario = self._repo.adicionar(
            Usuario(nome=nome, login=login, senha_hash=gerar_hash(senha), perfil=perfil, ativo=True)
        )
        self._confirmar()
        logger.info("Usuário criado: %s (%s)", login, perfil.value)
        return usuario

    def alterar(
        self, id_usuario: int, nome: Optional[str], perfil: Union[PerfilUsuario, str, None], id_ator: int
    ) -> Usuario:
        """Muda nome e perfil (o login não muda: é a identidade do usuário)."""
        erros: List[str] = []
        nome, _login, perfil = validar_dados(nome, "login", perfil, erros)
        if erros:
            raise ValidacaoError(erros)
        self._travar()
        usuario = self._obter_travado(id_usuario)
        if perfil is not usuario.perfil:
            if usuario.id_usuario == id_ator:
                self._recusar("Você não pode alterar o seu próprio perfil.")
            if self._eh_ultimo_dono_ativo(usuario):
                self._recusar("Não é possível rebaixar o último administrador ativo: o sistema ficaria sem administrador.")
        usuario.nome, usuario.perfil = nome, perfil
        self._confirmar()
        return usuario

    def definir_ativo(self, id_usuario: int, ativo: bool, id_ator: int) -> Usuario:
        self._travar()
        usuario = self._obter_travado(id_usuario)
        if not ativo:
            if usuario.id_usuario == id_ator:
                self._recusar("Você não pode desativar o seu próprio usuário.")
            if self._eh_ultimo_dono_ativo(usuario):
                self._recusar("Não é possível desativar o último administrador ativo: o sistema ficaria sem administrador.")
        else:  # reativar começa do zero
            usuario.tentativas_falhas, usuario.bloqueado_ate = 0, None
        usuario.ativo = bool(ativo)
        self._confirmar()
        logger.info("Usuário %s %s", usuario.login, "ativado" if ativo else "desativado")
        return usuario

    def redefinir_senha(self, id_usuario: int, senha: Optional[str], confirmacao: Optional[str]) -> Usuario:
        usuario = self.obter(id_usuario)
        erros: List[str] = []
        validar_senha_nova(senha, confirmacao, usuario.login, erros)
        if erros:
            raise ValidacaoError(erros)
        usuario = self._obter_travado(id_usuario)
        usuario.senha_hash = gerar_hash(senha)
        usuario.tentativas_falhas, usuario.bloqueado_ate = 0, None  # destrava
        self._confirmar()
        logger.info("Senha redefinida para %s", usuario.login)
        return usuario

    # ------------------------------------------------------------------
    def _eh_ultimo_dono_ativo(self, usuario: Usuario) -> bool:
        return (
            usuario.perfil is PerfilUsuario.DONO
            and usuario.ativo
            and self._repo.contar_donos_ativos() <= 1
        )

    def _travar(self) -> None:
        if self._session.get_bind().dialect.name == "postgresql":
            self._session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _TRAVA_USUARIOS})

    def _obter_travado(self, id_usuario: int) -> Usuario:
        usuario = self._repo.buscar_por_id(id_usuario, travar=True)
        if usuario is None:
            self._session.rollback()
            raise RegistroNaoEncontradoError(f"Usuário {id_usuario} não encontrado.")
        return usuario

    def _recusar(self, mensagem: str) -> None:
        self._session.rollback()
        raise OperacaoNaoPermitidaError(mensagem)

    def _confirmar(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise RegistroDuplicadoError("Já existe um usuário com este login.") from exc
        except Exception:
            self._session.rollback()
            raise
