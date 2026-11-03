"""
Controller de Ordem de Serviço (RF04) - Camada de Controle (DVP, seção 2.1).

Mesmo papel dos outros controllers: abre/fecha a Session de cada operação,
devolve DTOs (nunca objetos ORM) e deixa as ErroDeNegocio subirem para a tela.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, List, Optional, Sequence, Union

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.persistencia.models import OrdemServico, StatusOrdemServico
from src.persistencia.repositories.ordem_servico_repository import OrdemServicoRepository
from src.servico.ordem_servico_service import ItemOS, OrdemServicoService
from src.servico.cliente_service import ClienteService

# Reexportadas de propósito: a tela importa tudo DAQUI.
from src.servico.excecoes import (  # noqa: F401
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)

__all__ = [
    "ClienteOpcaoDTO",
    "ErroDeNegocio",
    "ItemOS",
    "ItemOSDTO",
    "OperacaoNaoPermitidaError",
    "OrdemServicoController",
    "OrdemServicoDTO",
    "ProdutoParaOSDTO",
    "RegistroNaoEncontradoError",
    "StatusOrdemServico",
    "ValidacaoError",
    "VeiculoOpcaoDTO",
]

Numero = Union[int, float, Decimal]


@dataclass(frozen=True)
class ItemOSDTO:
    id_produto: int
    nome_produto: str
    quantidade: int
    preco_unitario: Decimal
    custo_unitario: Optional[Decimal]
    subtotal: Decimal


@dataclass(frozen=True)
class OrdemServicoDTO:
    """Cópia somente-leitura de uma OS, segura para a tela usar."""

    id_ordem_servico: int
    id_cliente: int
    nome_cliente: str
    id_veiculo: int
    placa: str
    modelo: str
    quilometragem: Optional[int]
    descricao_problema: Optional[str]
    tipo_servico: Optional[str]
    valor_mao_de_obra: Decimal
    valor_pecas: Decimal
    valor_total: Decimal
    status: StatusOrdemServico
    possui_nota_fiscal: bool
    criado_em: datetime
    entregue_em: Optional[datetime]
    itens: tuple
    transicoes: tuple  # status para onde a OS pode ir agora

    @staticmethod
    def de_modelo(o: OrdemServico) -> "OrdemServicoDTO":
        itens = tuple(
            ItemOSDTO(
                id_produto=i.id_produto,
                nome_produto=i.produto.nome,
                quantidade=i.quantidade_utilizada,
                preco_unitario=i.preco_unitario,
                custo_unitario=i.custo_unitario,
                subtotal=i.subtotal,
            )
            for i in sorted(o.os_produtos, key=lambda x: x.produto.nome.lower())
        )
        return OrdemServicoDTO(
            id_ordem_servico=o.id_ordem_servico,
            id_cliente=o.id_cliente,
            nome_cliente=o.cliente.nome,
            id_veiculo=o.id_veiculo,
            placa=o.veiculo.placa,
            modelo=o.veiculo.modelo,
            quilometragem=o.quilometragem,
            descricao_problema=o.descricao_problema,
            tipo_servico=o.tipo_servico,
            valor_mao_de_obra=o.valor_mao_de_obra,
            valor_pecas=o.valor_pecas,
            valor_total=o.valor_total,
            status=o.status,
            possui_nota_fiscal=o.id_nota_fiscal is not None,
            criado_em=o.criado_em,
            entregue_em=o.entregue_em,
            itens=itens,
            transicoes=tuple(OrdemServicoService.transicoes_permitidas(o)),
        )


@dataclass(frozen=True)
class ClienteOpcaoDTO:
    id_cliente: int
    nome: str


@dataclass(frozen=True)
class VeiculoOpcaoDTO:
    id_veiculo: int
    rotulo: str  # "ABC1D23 – Gol"


@dataclass(frozen=True)
class ProdutoParaOSDTO:
    id_produto: int
    nome: str
    quantidade: int
    valor_unitario: Optional[Decimal]  # último valor pago (referência)


class OrdemServicoController:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    # ---------------- listas de apoio para os campos da tela ----------------
    def listar_clientes(self) -> List[ClienteOpcaoDTO]:
        with self._session_factory() as session:
            return [ClienteOpcaoDTO(c.id_cliente, c.nome) for c in ClienteService(session).listar()]

    def listar_veiculos_do_cliente(self, id_cliente: int) -> List[VeiculoOpcaoDTO]:
        with self._session_factory() as session:
            repo = OrdemServicoRepository(session)
            return [
                VeiculoOpcaoDTO(v.id_veiculo, f"{v.placa} – {v.modelo}")
                for v in repo.listar_veiculos_do_cliente(id_cliente)
            ]

    def listar_produtos(self) -> List[ProdutoParaOSDTO]:
        with self._session_factory() as session:
            return [
                ProdutoParaOSDTO(p.id_produto, p.nome, p.quantidade, p.valor_unitario)
                for p in OrdemServicoRepository(session).listar_produtos()
            ]

    def listar_tipos_servico(self) -> List[str]:
        with self._session_factory() as session:
            return OrdemServicoService(session).listar_tipos_servico()

    def aviso_quilometragem(
        self, id_veiculo: Optional[int], quilometragem: Optional[int], id_os: Optional[int] = None
    ) -> Optional[str]:
        with self._session_factory() as session:
            return OrdemServicoService(session).aviso_quilometragem(id_veiculo, quilometragem, id_os)

    # ---------------- OS ----------------
    def listar(self, termo: str = "", status: Optional[StatusOrdemServico] = None) -> List[OrdemServicoDTO]:
        with self._session_factory() as session:
            return [
                OrdemServicoDTO.de_modelo(o)
                for o in OrdemServicoService(session).listar(termo, status)
            ]

    def listar_por_veiculo(self, id_veiculo: int) -> List[OrdemServicoDTO]:
        with self._session_factory() as session:
            return [
                OrdemServicoDTO.de_modelo(o)
                for o in OrdemServicoService(session).listar_por_veiculo(id_veiculo)
            ]

    def obter(self, id_os: int) -> OrdemServicoDTO:
        with self._session_factory() as session:
            return OrdemServicoDTO.de_modelo(OrdemServicoService(session).obter(id_os))

    def cadastrar(
        self,
        id_cliente: Optional[int],
        id_veiculo: Optional[int],
        quilometragem: Optional[int],
        descricao_problema: Optional[str],
        tipo_servico: Optional[str],
        valor_mao_de_obra: Optional[Numero] = None,
        itens: Sequence[ItemOS] = (),
        status: StatusOrdemServico = StatusOrdemServico.ORCAMENTO,
    ) -> OrdemServicoDTO:
        with self._session_factory() as session:
            os_ = OrdemServicoService(session).cadastrar(
                id_cliente, id_veiculo, quilometragem, descricao_problema,
                tipo_servico, valor_mao_de_obra, itens, status,
            )
            return OrdemServicoDTO.de_modelo(os_)

    def atualizar(
        self,
        id_os: int,
        id_cliente: Optional[int],
        id_veiculo: Optional[int],
        quilometragem: Optional[int],
        descricao_problema: Optional[str],
        tipo_servico: Optional[str],
        valor_mao_de_obra: Optional[Numero] = None,
        itens: Sequence[ItemOS] = (),
    ) -> OrdemServicoDTO:
        with self._session_factory() as session:
            os_ = OrdemServicoService(session).atualizar(
                id_os, id_cliente, id_veiculo, quilometragem, descricao_problema,
                tipo_servico, valor_mao_de_obra, itens,
            )
            return OrdemServicoDTO.de_modelo(os_)

    def alterar_status(self, id_os: int, novo_status: StatusOrdemServico) -> OrdemServicoDTO:
        with self._session_factory() as session:
            return OrdemServicoDTO.de_modelo(
                OrdemServicoService(session).alterar_status(id_os, novo_status)
            )

    def excluir(self, id_os: int) -> None:
        with self._session_factory() as session:
            OrdemServicoService(session).excluir(id_os)
