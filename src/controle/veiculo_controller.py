"""
Controller de Veículo (RF02) - Camada de Controle (DVP, seção 2.1).

Mesmo papel do ClienteController: abre/fecha a Session de cada operação,
devolve DTOs (nunca objetos ORM) e deixa as ErroDeNegocio subirem para a tela.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.persistencia.models import OrdemServico, Veiculo
from src.servico.cliente_service import ClienteService
from src.servico.veiculo_service import VeiculoService

# Reexportadas de propósito: a tela importa as exceções DAQUI.
from src.servico.excecoes import (  # noqa: F401
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)


@dataclass(frozen=True)
class VeiculoDTO:
    """Cópia somente-leitura dos dados do veículo, segura para a tela usar."""

    id_veiculo: int
    id_cliente: int
    nome_cliente: str
    modelo: str
    marca: str
    ano: Optional[int]
    motor: Optional[str]
    placa: str

    @staticmethod
    def de_modelo(veiculo: Veiculo) -> "VeiculoDTO":
        return VeiculoDTO(
            id_veiculo=veiculo.id_veiculo,
            id_cliente=veiculo.id_cliente,
            nome_cliente=veiculo.cliente.nome,
            modelo=veiculo.modelo,
            marca=veiculo.marca,
            ano=veiculo.ano,
            motor=veiculo.motor,
            placa=veiculo.placa,
        )


@dataclass(frozen=True)
class ClienteOpcaoDTO:
    """Dados mínimos do cliente para preencher a lista de seleção do diálogo."""

    id_cliente: int
    nome: str
    cpf: str


@dataclass(frozen=True)
class OrdemServicoHistoricoDTO:
    """Uma linha do histórico de serviços do veículo (HU05)."""

    id_ordem_servico: int
    status: str
    descricao_problema: Optional[str]
    quilometragem: Optional[int]
    criado_em: datetime

    @staticmethod
    def de_modelo(os_: OrdemServico) -> "OrdemServicoHistoricoDTO":
        return OrdemServicoHistoricoDTO(
            id_ordem_servico=os_.id_ordem_servico,
            status=os_.status,
            descricao_problema=os_.descricao_problema,
            quilometragem=os_.quilometragem,
            criado_em=os_.criado_em,
        )


class VeiculoController:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def listar(self, termo: str = "") -> List[VeiculoDTO]:
        """Sem termo lista todos; com termo busca por placa, modelo, marca ou cliente."""
        termo = (termo or "").strip()
        with self._session_factory() as session:
            servico = VeiculoService(session)
            veiculos = servico.buscar(termo) if termo else servico.listar()
            return [VeiculoDTO.de_modelo(v) for v in veiculos]

    def obter(self, id_veiculo: int) -> VeiculoDTO:
        """Leitura fresca (levanta RegistroNaoEncontradoError se sumiu)."""
        with self._session_factory() as session:
            return VeiculoDTO.de_modelo(VeiculoService(session).obter(id_veiculo))

    def listar_clientes(self) -> List[ClienteOpcaoDTO]:
        """Clientes em ordem alfabética, para o campo 'Cliente' do diálogo."""
        with self._session_factory() as session:
            return [
                ClienteOpcaoDTO(c.id_cliente, c.nome, c.cpf)
                for c in ClienteService(session).listar()
            ]

    def cadastrar(
        self,
        id_cliente: Optional[int],
        modelo: str,
        marca: str,
        placa: str,
        ano: Optional[int] = None,
        motor: Optional[str] = None,
    ) -> VeiculoDTO:
        with self._session_factory() as session:
            veiculo = VeiculoService(session).cadastrar(id_cliente, modelo, marca, placa, ano, motor)
            return VeiculoDTO.de_modelo(veiculo)

    def atualizar(
        self,
        id_veiculo: int,
        id_cliente: Optional[int],
        modelo: str,
        marca: str,
        placa: str,
        ano: Optional[int] = None,
        motor: Optional[str] = None,
    ) -> VeiculoDTO:
        with self._session_factory() as session:
            veiculo = VeiculoService(session).atualizar(
                id_veiculo, id_cliente, modelo, marca, placa, ano, motor
            )
            return VeiculoDTO.de_modelo(veiculo)

    def excluir(self, id_veiculo: int) -> None:
        with self._session_factory() as session:
            VeiculoService(session).excluir(id_veiculo)

    def historico(self, id_veiculo: int) -> List[OrdemServicoHistoricoDTO]:
        """HU05: histórico de ordens de serviço do veículo."""
        with self._session_factory() as session:
            return [
                OrdemServicoHistoricoDTO.de_modelo(o)
                for o in VeiculoService(session).historico(id_veiculo)
            ]
