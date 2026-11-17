"""
Sessão do usuário logado e guard de autorização dos controllers (RF10).

Autorização em DUAS camadas (defesa em profundidade):
1. Apresentação: a barra lateral mostra só os módulos que o perfil pode usar.
2. Controle (este módulo): todo método público de um controller decorado
   com @protegido confere a permissão ANTES de executar. Mesmo que uma tela
   restrita seja aberta de outro jeito, a operação é recusada com uma
   OperacaoNaoPermitidaError clara.

Por que no controller e não no service: o controller é a porta de entrada
da aplicação (a tela só fala com ele). O service continua cuidando só da
regra de negócio, e os testes e scripts que o chamam direto não mudam.
A MATRIZ de quem pode o quê fica num lugar só: src/servico/permissoes.py.

A cada operação o guard REVALIDA o usuário no banco (consulta pela chave
primária, cerca de 1 ms): se o dono desativar ou rebaixar alguém, a próxima
ação dessa pessoa já é recusada. O menu só se ajusta no próximo login.

A sessão guarda um DTO congelado, SEM o hash da senha.
"""
from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass
from typing import Optional

from src.config.database import SessionLocal
from src.persistencia.models import PerfilUsuario
from src.servico.autenticacao_service import AutenticacaoService
from src.servico.excecoes import OperacaoNaoPermitidaError
from src.servico.permissoes import Permissao, exigir, permissoes_do_perfil


@dataclass(frozen=True)
class UsuarioLogadoDTO:
    id_usuario: int
    nome: str
    login: str
    perfil: PerfilUsuario
    sistema: bool = False  # sessão interna (autodiagnóstico / testes): não existe no banco

    @property
    def perfil_rotulo(self) -> str:
        return self.perfil.rotulo


class Sessao:
    """Quem está usando o sistema agora. Um objeto só, para a aplicação inteira."""

    def __init__(self) -> None:
        self._usuario: Optional[UsuarioLogadoDTO] = None

    @property
    def usuario(self) -> Optional[UsuarioLogadoDTO]:
        return self._usuario

    def entrar(self, usuario: UsuarioLogadoDTO) -> None:
        self._usuario = usuario

    def entrar_sistema(self) -> None:
        """
        Sessão interna com perfil de dono, só em memória, para o autodiagnóstico
        (Camaro.exe --verificar) e para os testes automatizados. Não grava nada
        no banco e não existe na tela de login.
        """
        self._usuario = UsuarioLogadoDTO(0, "Sistema", "sistema", PerfilUsuario.DONO, sistema=True)

    def sair(self) -> None:
        self._usuario = None

    def pode(self, permissao: Permissao) -> bool:
        """Pelo perfil do login (usado pelo menu e para esconder custos). Sem login: não pode nada."""
        u = self._usuario
        return u is not None and permissao in permissoes_do_perfil(u.perfil)

    def exigir(self, permissao: Permissao) -> None:
        """Checagem do guard: revalida o usuário no banco e confere o perfil ATUAL."""
        u = self._usuario
        if u is None:
            raise OperacaoNaoPermitidaError("Entre no sistema para continuar.")
        if u.sistema:
            exigir(u.perfil, permissao)
            return
        with SessionLocal() as s:
            atual = AutenticacaoService(s).usuario_vigente(u.id_usuario)
            if atual is None:
                raise OperacaoNaoPermitidaError("Seu usuário foi desativado. Entre novamente.")
            if atual.perfil is not u.perfil and permissao not in permissoes_do_perfil(atual.perfil):
                raise OperacaoNaoPermitidaError("Suas permissões mudaram. Saia e entre novamente.")
            exigir(atual.perfil, permissao)


sessao = Sessao()


def protegido(padrao: Permissao, **por_metodo: Permissao):
    """
    Decorador de CLASSE para controllers: cada método público exige a
    permissão `padrao`, ou a indicada para ele em `por_metodo`.

        @protegido(Permissao.PRODUTOS_CONSULTAR, cadastrar=Permissao.PRODUTOS_GERENCIAR)
        class ProdutoController: ...

    Métodos novos já nascem protegidos (não dá para "esquecer" a checagem).
    Métodos estáticos não são envolvidos (não acessam o banco).
    """
    def decorar(classe):
        desconhecidos = set(por_metodo) - set(vars(classe))
        if desconhecidos:  # erro de digitação no nome do método: falha ao importar, não em produção
            raise TypeError(f"{classe.__name__}: métodos inexistentes em @protegido: {sorted(desconhecidos)}")
        for nome, atributo in list(vars(classe).items()):
            if nome.startswith("_") or not inspect.isfunction(atributo):
                continue
            classe_permissao = por_metodo.get(nome, padrao)
            setattr(classe, nome, _envolver(atributo, classe_permissao))
        classe.PERMISSAO_PADRAO = padrao
        return classe
    return decorar


def _envolver(metodo, permissao: Permissao):
    @functools.wraps(metodo)
    def guardado(*args, **kwargs):
        sessao.exigir(permissao)
        return metodo(*args, **kwargs)
    guardado.permissao = permissao
    return guardado
