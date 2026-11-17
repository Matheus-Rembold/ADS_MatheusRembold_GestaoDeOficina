"""
Matriz de permissões (RF10) — o ÚNICO lugar que diz quem pode o quê.

Duas camadas usam esta matriz (defesa em profundidade):
- a barra lateral mostra só os módulos permitidos ao perfil logado;
- o guard dos controllers (src/controle/sessao.py) recusa a operação mesmo
  que a tela seja aberta de outro jeito.
As duas leem daqui, então menu e guard nunca discordam.

Para um módulo novo (ex.: RF07, RF08): crie a Permissao, coloque-a nos
perfis que podem usá-la e decore o controller com @protegido(...).
"""
from __future__ import annotations

import enum
from typing import Dict, FrozenSet

from src.persistencia.models import PerfilUsuario
from src.servico.excecoes import OperacaoNaoPermitidaError


class Permissao(str, enum.Enum):
    CLIENTES = "clientes"
    VEICULOS = "veiculos"
    ORDENS_SERVICO = "ordens_servico"
    AGENDAMENTOS = "agendamentos"
    PRODUTOS_CONSULTAR = "produtos_consultar"
    PRODUTOS_GERENCIAR = "produtos_gerenciar"   # cadastrar, editar, excluir
    VER_CUSTOS = "ver_custos"                   # custo de compra e margem dos produtos
    ESTOQUE = "estoque"                         # movimentações (compra, ajuste, venda por fora...)
    RELATORIOS = "relatorios"
    NOTIFICACOES = "notificacoes"               # RF07 (WhatsApp): dono e mecânico
    NOTA_FISCAL = "nota_fiscal"                 # RF08 (futuro)
    USUARIOS = "usuarios"


_MATRIZ: Dict[PerfilUsuario, FrozenSet[Permissao]] = {
    PerfilUsuario.DONO: frozenset(Permissao),  # acesso total
    PerfilUsuario.MECANICO: frozenset({
        Permissao.CLIENTES,
        Permissao.VEICULOS,
        Permissao.ORDENS_SERVICO,
        Permissao.AGENDAMENTOS,
        Permissao.PRODUTOS_CONSULTAR,
        Permissao.NOTIFICACOES,
    }),
}

# Mensagem curta para quando o mecânico tenta algo do dono.
_ROTULOS = {
    Permissao.PRODUTOS_GERENCIAR: "cadastrar, editar ou excluir produtos",
    Permissao.VER_CUSTOS: "ver custos e margens",
    Permissao.ESTOQUE: "acessar o Estoque",
    Permissao.RELATORIOS: "acessar os Relatórios",
    Permissao.NOTA_FISCAL: "emitir notas fiscais",
    Permissao.USUARIOS: "gerenciar os usuários",
}


def permissoes_do_perfil(perfil: PerfilUsuario) -> FrozenSet[Permissao]:
    return _MATRIZ.get(PerfilUsuario(perfil), frozenset())


def pode(perfil: PerfilUsuario, permissao: Permissao) -> bool:
    return permissao in permissoes_do_perfil(perfil)


def exigir(perfil: PerfilUsuario, permissao: Permissao) -> None:
    """Levanta OperacaoNaoPermitidaError se o perfil não tem a permissão."""
    if not pode(perfil, permissao):
        acao = _ROTULOS.get(permissao, "fazer esta operação")
        raise OperacaoNaoPermitidaError(
            f"Seu perfil ({PerfilUsuario(perfil).rotulo}) não tem permissão para {acao}."
        )
