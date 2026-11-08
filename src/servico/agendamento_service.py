"""
Serviço de Agendamento (RF05).

Camada de Serviço (DVP, seção 2.1): concentra as REGRAS DE NEGÓCIO e é a
dona da transação.

Regras principais
-----------------
- Obrigatórios: cliente, veículo (que pertença ao cliente), tipo de serviço,
  data/hora e duração estimada em horas (HU13).
- Até DOIS serviços ao mesmo tempo (RF05/HU13): o sistema BLOQUEIA o terceiro.
  O conflito considera a duração: um serviço de 2 h ocupa 2 h da agenda.
  Dois serviços "se encontram" quando um começa antes de o outro terminar.
- O mesmo veículo não pode ter dois agendamentos sobrepostos.
- Só agendamentos "agendado" ocupam a agenda: cancelar libera o horário (HU15).
- Não se agenda no passado (ao criar ou ao mudar o horário).
- Só agendamentos "agendado" podem ser editados, cancelados ou convertidos.
- Converter em OS cria a OS em orçamento (cliente, veículo e tipo de serviço
  copiados) e marca o agendamento como "concluído", na MESMA transação.
- Mexer na agenda é serializado por um lock do banco, para duas janelas não
  furarem o limite de 2 ao mesmo tempo.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.persistencia.models import Agendamento, StatusAgendamento
from src.persistencia.repositories.agendamento_repository import AgendamentoRepository
from src.servico.excecoes import (
    OperacaoNaoPermitidaError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)
from src.servico.ordem_servico_service import OrdemServicoService

LIMITE_SIMULTANEOS = 2
DURACAO_MAXIMA = Decimal("12")
TIPO_SERVICO_MAXIMO = 150
ABERTURA, FECHAMENTO = 7, 19  # faixa de horas mostrada na agenda do dia

Numero = Union[int, float, Decimal]


def maximo_simultaneos(agendamentos: Sequence[Agendamento], inicio: datetime, fim: datetime) -> int:
    """
    Maior quantidade de agendamentos acontecendo AO MESMO TEMPO dentro de
    [inicio, fim). Basta olhar o começo da janela e o começo de cada
    agendamento: a contagem só aumenta nesses instantes.
    """
    pontos = {inicio} | {a.data_hora for a in agendamentos if inicio <= a.data_hora < fim}
    melhor = 0
    for t in pontos:
        n = sum(1 for a in agendamentos if a.data_hora <= t < a.termino_previsto)
        melhor = max(melhor, n)
    return melhor


class AgendamentoService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = AgendamentoRepository(session)

    # ------------------------------------------------------------------
    # Criar / editar
    # ------------------------------------------------------------------
    def criar(
        self,
        id_cliente: Optional[int],
        id_veiculo: Optional[int],
        tipo_servico: Optional[str],
        data_hora: Optional[datetime],
        duracao_horas: Optional[Numero],
    ) -> Agendamento:
        dados = self._validar(id_cliente, id_veiculo, tipo_servico, data_hora, duracao_horas, exigir_futuro=True)
        self._validar_cliente_e_veiculo(id_cliente, id_veiculo)
        self._repo.travar_agenda()
        self._verificar_conflitos(id_veiculo, dados["data_hora"], dados["duracao"], None)
        ag = self._repo.adicionar(Agendamento(
            id_cliente=id_cliente, id_veiculo=id_veiculo, tipo_servico=dados["tipo"],
            data_hora=dados["data_hora"], duracao_estimada_horas=dados["duracao"],
            status=StatusAgendamento.AGENDADO,
        ))
        self._confirmar()
        return self.obter(ag.id_agendamento)

    def atualizar(
        self,
        id_agendamento: int,
        id_cliente: Optional[int],
        id_veiculo: Optional[int],
        tipo_servico: Optional[str],
        data_hora: Optional[datetime],
        duracao_horas: Optional[Numero],
    ) -> Agendamento:
        self._repo.travar_agenda()
        ag = self._obter_travado(id_agendamento)
        self._exigir_agendado(ag, "editado")
        mudou_horario = (
            isinstance(data_hora, datetime)
            and data_hora.replace(second=0, microsecond=0, tzinfo=None)
            != ag.data_hora.replace(second=0, microsecond=0)
        )
        try:
            dados = self._validar(id_cliente, id_veiculo, tipo_servico, data_hora, duracao_horas,
                                  exigir_futuro=mudou_horario)
            self._validar_cliente_e_veiculo(id_cliente, id_veiculo)
            self._verificar_conflitos(id_veiculo, dados["data_hora"], dados["duracao"], id_agendamento)
        except Exception:
            self._session.rollback()
            raise
        ag.id_cliente, ag.id_veiculo = id_cliente, id_veiculo
        ag.tipo_servico, ag.data_hora = dados["tipo"], dados["data_hora"]
        ag.duracao_estimada_horas = dados["duracao"]
        self._repo.flush()
        self._confirmar()
        return self.obter(id_agendamento)

    # ------------------------------------------------------------------
    # Cancelar / converter em OS
    # ------------------------------------------------------------------
    def cancelar(self, id_agendamento: int) -> Agendamento:
        ag = self._obter_travado(id_agendamento)
        self._exigir_agendado(ag, "cancelado")
        ag.status = StatusAgendamento.CANCELADO
        self._repo.flush()
        self._confirmar()
        return self.obter(id_agendamento)

    def converter_em_os(
        self,
        id_agendamento: int,
        quilometragem: Optional[int],
        descricao_problema: Optional[str],
    ) -> Agendamento:
        """Cria a OS (em orçamento) e conclui o agendamento, tudo ou nada."""
        ag = self._obter_travado(id_agendamento)
        self._exigir_agendado(ag, "convertido em OS")
        try:
            os_ = OrdemServicoService(self._session).cadastrar(
                ag.id_cliente, ag.id_veiculo, quilometragem, descricao_problema,
                ag.tipo_servico, confirmar=False,
            )
            ag.status = StatusAgendamento.CONCLUIDO
            ag.id_ordem_servico = os_.id_ordem_servico
            self._repo.flush()
        except Exception:
            self._session.rollback()
            raise
        self._confirmar()
        return self.obter(id_agendamento)

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def obter(self, id_agendamento: int) -> Agendamento:
        ag = self._repo.buscar_por_id(id_agendamento)
        if ag is None:
            raise RegistroNaoEncontradoError(f"Agendamento {id_agendamento} não encontrado.")
        return ag

    def listar(
        self,
        termo: str = "",
        status: Optional[StatusAgendamento] = None,
        data_inicio: Optional[date] = None,
        data_fim: Optional[date] = None,
    ) -> List[Agendamento]:
        return self._repo.listar((termo or "").strip(), status, data_inicio, data_fim)

    def agenda_do_dia(self, dia: date, incluir_cancelados: bool = False) -> List[Agendamento]:
        lista = self._repo.listar(data_inicio=dia, data_fim=dia)
        if not incluir_cancelados:
            lista = [a for a in lista if a.status is not StatusAgendamento.CANCELADO]
        return lista

    def dias_ocupados(self, ano: int, mes: int) -> Dict[date, int]:
        """{dia: quantos agendamentos ativos} no mês, para marcar o calendário."""
        primeiro = date(ano, mes, 1)
        ultimo = (date(ano + (mes == 12), mes % 12 + 1, 1)) - timedelta(days=1)
        return self._repo.contar_por_dia(primeiro, ultimo)

    def ocupacao_do_dia(self, dia: date) -> List[Tuple[int, int, List[Agendamento]]]:
        """
        Para cada hora do dia: (hora, ocupação máxima naquela hora, agendamentos
        que tocam a hora). Ocupação de 0 a LIMITE_SIMULTANEOS = vagas ocupadas.
        """
        ativos = [a for a in self._repo.listar(data_inicio=dia - timedelta(days=1), data_fim=dia)
                  if a.status is StatusAgendamento.AGENDADO]
        h0, h1 = ABERTURA, FECHAMENTO
        inicio_dia = datetime.combine(dia, time.min)
        fim_dia = inicio_dia + timedelta(days=1)
        for a in ativos:
            if a.termino_previsto <= inicio_dia or a.data_hora >= fim_dia:
                continue  # não toca este dia
            h0 = min(h0, 0 if a.data_hora < inicio_dia else a.data_hora.hour)
            fim_visivel = min(a.termino_previsto, fim_dia)
            horas_ate_o_fim = -(-int((fim_visivel - inicio_dia).total_seconds()) // 3600)  # arredonda p/ cima
            h1 = max(h1, horas_ate_o_fim)
        resultado = []
        for h in range(h0, h1):
            ini = inicio_dia + timedelta(hours=h)
            fim = ini + timedelta(hours=1)
            tocam = [a for a in ativos if a.data_hora < fim and a.termino_previsto > ini]
            resultado.append((h, maximo_simultaneos(tocam, ini, fim), tocam))
        return resultado

    def ocupacao_no_intervalo(
        self, data_hora: Optional[datetime], duracao_horas: Optional[Numero],
        ignorar_id: Optional[int] = None,
    ) -> Optional[int]:
        """Quantos serviços já ocupam o intervalo (0..2), para avisar na tela. None se inválido."""
        if not isinstance(data_hora, datetime):
            return None
        duracao = self._normalizar_duracao(duracao_horas)
        if duracao is None:
            return None
        ini = data_hora.replace(second=0, microsecond=0)
        fim = ini + timedelta(minutes=float(duracao) * 60)
        existentes = self._repo.listar_ativos_no_periodo(ini, fim, ignorar_id)
        return maximo_simultaneos(existentes, ini, fim)

    def listar_tipos_servico(self) -> List[str]:
        return OrdemServicoService(self._session).listar_tipos_servico()

    # ------------------------------------------------------------------
    # Internos: validação e regras
    # ------------------------------------------------------------------
    @staticmethod
    def _normalizar_duracao(duracao: Optional[Numero]) -> Optional[Decimal]:
        if duracao is None or isinstance(duracao, bool) or not isinstance(duracao, (int, float, Decimal)):
            return None
        try:
            d = Decimal(str(duracao)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:  # noqa: BLE001  (NaN, infinito...)
            return None
        return d if Decimal("0") < d <= DURACAO_MAXIMA else None

    def _validar(self, id_cliente, id_veiculo, tipo_servico, data_hora, duracao, exigir_futuro: bool) -> dict:
        erros: List[str] = []
        if id_cliente is None:
            erros.append("O cliente é obrigatório.")
        if id_veiculo is None:
            erros.append("O veículo é obrigatório.")
        tipo = " ".join((tipo_servico or "").split())
        if not tipo:
            erros.append("O tipo de serviço é obrigatório.")
        elif len(tipo) > TIPO_SERVICO_MAXIMO:
            erros.append(f"O tipo de serviço deve ter no máximo {TIPO_SERVICO_MAXIMO} caracteres.")
        if not isinstance(data_hora, datetime):
            erros.append("A data e a hora são obrigatórias.")
        else:
            data_hora = data_hora.replace(second=0, microsecond=0, tzinfo=None)
            if exigir_futuro and data_hora < datetime.now().replace(second=0, microsecond=0):
                erros.append("Não é possível agendar em um horário que já passou.")
        d = self._normalizar_duracao(duracao)
        if d is None:
            erros.append(f"A duração estimada é obrigatória: informe as horas, de 0,01 a {DURACAO_MAXIMA} h.")
        if erros:
            raise ValidacaoError(erros)
        return {"tipo": tipo, "data_hora": data_hora, "duracao": d}

    def _validar_cliente_e_veiculo(self, id_cliente: int, id_veiculo: int) -> None:
        if self._repo.buscar_cliente(id_cliente) is None:
            raise ValidacaoError("O cliente informado não existe.")
        veiculo = self._repo.buscar_veiculo(id_veiculo)
        if veiculo is None:
            raise ValidacaoError("O veículo informado não existe.")
        if veiculo.id_cliente != id_cliente:
            raise ValidacaoError("O veículo informado não pertence ao cliente escolhido.")

    def _verificar_conflitos(
        self, id_veiculo: int, inicio: datetime, duracao: Decimal, ignorar_id: Optional[int]
    ) -> None:
        fim = inicio + timedelta(minutes=float(duracao) * 60)
        existentes = self._repo.listar_ativos_no_periodo(inicio, fim, ignorar_id)
        mesmo_veiculo = [a for a in existentes if a.id_veiculo == id_veiculo]
        if mesmo_veiculo:
            a = mesmo_veiculo[0]
            self._recusar_se_aberta(
                f"Este veículo já tem um agendamento nesse período "
                f"({a.data_hora:%d/%m %H:%M} às {a.termino_previsto:%H:%M}: {a.tipo_servico})."
            )
        if maximo_simultaneos(existentes, inicio, fim) >= LIMITE_SIMULTANEOS:
            detalhe = "; ".join(
                f"{a.veiculo.placa} {a.data_hora:%H:%M}–{a.termino_previsto:%H:%M}" for a in existentes
            )
            self._recusar_se_aberta(
                f"Horário lotado: já há {LIMITE_SIMULTANEOS} serviços em andamento entre "
                f"{inicio:%H:%M} e {fim:%H:%M} ({detalhe}). Escolha outro horário."
            )

    def _recusar_se_aberta(self, mensagem: str) -> None:
        self._session.rollback()  # libera o lock da agenda
        raise OperacaoNaoPermitidaError(mensagem)

    def _obter_travado(self, id_agendamento: int) -> Agendamento:
        ag = self._repo.buscar_por_id(id_agendamento, travar=True)
        if ag is None:
            self._session.rollback()
            raise RegistroNaoEncontradoError(f"Agendamento {id_agendamento} não encontrado.")
        return ag

    def _exigir_agendado(self, ag: Agendamento, acao: str) -> None:
        if ag.status is not StatusAgendamento.AGENDADO:
            mensagem = (
                f"O agendamento {ag.id_agendamento} está “{ag.status.rotulo}” e não pode ser {acao}."
            )
            self._session.rollback()
            raise OperacaoNaoPermitidaError(mensagem)

    def _confirmar(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise OperacaoNaoPermitidaError(
                "O banco de dados recusou a operação por violar uma regra de integridade."
            ) from exc
        except Exception:
            self._session.rollback()
            raise
