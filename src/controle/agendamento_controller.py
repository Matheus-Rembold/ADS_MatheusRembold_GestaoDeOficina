"""
Controller de Agendamento (RF05) - Camada de Controle (DVP, seção 2.1).

Mesmo papel dos outros controllers: abre/fecha a Session de cada operação,
devolve DTOs (nunca objetos ORM) e deixa as ErroDeNegocio subirem para a tela.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Union

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.controle.ordem_servico_controller import (  # noqa: F401  (reexportados para a tela)
    ClienteOpcaoDTO,
    OrdemServicoController,
    VeiculoOpcaoDTO,
)
from src.persistencia.models import Agendamento, StatusAgendamento
from src.servico.agendamento_service import (  # noqa: F401
    ABERTURA,
    FECHAMENTO,
    LIMITE_SIMULTANEOS,
    AgendamentoService,
)
from src.servico.excecoes import (  # noqa: F401
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)

__all__ = [
    "AgendamentoController",
    "AgendamentoDTO",
    "ClienteOpcaoDTO",
    "ErroDeNegocio",
    "HoraDoDiaDTO",
    "LIMITE_SIMULTANEOS",
    "OperacaoNaoPermitidaError",
    "RegistroNaoEncontradoError",
    "StatusAgendamento",
    "ValidacaoError",
    "VeiculoOpcaoDTO",
]

Numero = Union[int, float, Decimal]


@dataclass(frozen=True)
class AgendamentoDTO:
    id_agendamento: int
    id_cliente: int
    nome_cliente: str
    id_veiculo: int
    placa: str
    modelo: str
    tipo_servico: str
    data_hora: datetime
    duracao_horas: Optional[Decimal]
    termino_previsto: datetime
    status: StatusAgendamento
    id_ordem_servico: Optional[int]

    @staticmethod
    def de_modelo(a: Agendamento) -> "AgendamentoDTO":
        return AgendamentoDTO(
            id_agendamento=a.id_agendamento,
            id_cliente=a.id_cliente,
            nome_cliente=a.cliente.nome,
            id_veiculo=a.id_veiculo,
            placa=a.veiculo.placa,
            modelo=a.veiculo.modelo,
            tipo_servico=a.tipo_servico,
            data_hora=a.data_hora,
            duracao_horas=a.duracao_estimada_horas,
            termino_previsto=a.termino_previsto,
            status=a.status,
            id_ordem_servico=a.id_ordem_servico,
        )


@dataclass(frozen=True)
class HoraDoDiaDTO:
    """Uma linha da agenda do dia: quantas vagas (0 a 2) estão ocupadas naquela hora."""

    hora: int
    ocupacao: int
    agendamentos: tuple


class AgendamentoController:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    # ---------------- listas de apoio ----------------
    def listar_clientes(self) -> List[ClienteOpcaoDTO]:
        return OrdemServicoController(self._session_factory).listar_clientes()

    def listar_veiculos_do_cliente(self, id_cliente: int) -> List[VeiculoOpcaoDTO]:
        return OrdemServicoController(self._session_factory).listar_veiculos_do_cliente(id_cliente)

    def aviso_quilometragem(self, id_veiculo: Optional[int], quilometragem: Optional[int]) -> Optional[str]:
        return OrdemServicoController(self._session_factory).aviso_quilometragem(id_veiculo, quilometragem)

    def listar_tipos_servico(self) -> List[str]:
        with self._session_factory() as session:
            return AgendamentoService(session).listar_tipos_servico()

    # ---------------- consultas ----------------
    def obter(self, id_agendamento: int) -> AgendamentoDTO:
        with self._session_factory() as session:
            return AgendamentoDTO.de_modelo(AgendamentoService(session).obter(id_agendamento))

    def listar(
        self, termo: str = "", status: Optional[StatusAgendamento] = None,
        data_inicio: Optional[date] = None, data_fim: Optional[date] = None,
    ) -> List[AgendamentoDTO]:
        with self._session_factory() as session:
            return [AgendamentoDTO.de_modelo(a)
                    for a in AgendamentoService(session).listar(termo, status, data_inicio, data_fim)]

    def agenda_do_dia(self, dia: date, incluir_cancelados: bool = False) -> List[AgendamentoDTO]:
        with self._session_factory() as session:
            return [AgendamentoDTO.de_modelo(a)
                    for a in AgendamentoService(session).agenda_do_dia(dia, incluir_cancelados)]

    def dias_ocupados(self, ano: int, mes: int) -> Dict[date, int]:
        with self._session_factory() as session:
            return AgendamentoService(session).dias_ocupados(ano, mes)

    def ocupacao_do_dia(self, dia: date) -> List[HoraDoDiaDTO]:
        with self._session_factory() as session:
            return [
                HoraDoDiaDTO(h, n, tuple(AgendamentoDTO.de_modelo(a) for a in itens))
                for h, n, itens in AgendamentoService(session).ocupacao_do_dia(dia)
            ]

    def ocupacao_no_intervalo(
        self, data_hora: Optional[datetime], duracao_horas: Optional[Numero],
        ignorar_id: Optional[int] = None,
    ) -> Optional[int]:
        with self._session_factory() as session:
            return AgendamentoService(session).ocupacao_no_intervalo(data_hora, duracao_horas, ignorar_id)

    # ---------------- ações ----------------
    def criar(self, id_cliente, id_veiculo, tipo_servico, data_hora, duracao_horas) -> AgendamentoDTO:
        with self._session_factory() as session:
            return AgendamentoDTO.de_modelo(AgendamentoService(session).criar(
                id_cliente, id_veiculo, tipo_servico, data_hora, duracao_horas))

    def atualizar(self, id_agendamento, id_cliente, id_veiculo, tipo_servico, data_hora, duracao_horas) -> AgendamentoDTO:
        with self._session_factory() as session:
            return AgendamentoDTO.de_modelo(AgendamentoService(session).atualizar(
                id_agendamento, id_cliente, id_veiculo, tipo_servico, data_hora, duracao_horas))

    def cancelar(self, id_agendamento: int) -> AgendamentoDTO:
        with self._session_factory() as session:
            return AgendamentoDTO.de_modelo(AgendamentoService(session).cancelar(id_agendamento))

    def converter_em_os(
        self, id_agendamento: int, quilometragem: Optional[int], descricao_problema: Optional[str]
    ) -> AgendamentoDTO:
        with self._session_factory() as session:
            return AgendamentoDTO.de_modelo(AgendamentoService(session).converter_em_os(
                id_agendamento, quilometragem, descricao_problema))
