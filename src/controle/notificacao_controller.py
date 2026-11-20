"""
Controller de Notificação (RF07) - Camada de Controle (DVP, seção 2.1).

Mesmo papel dos outros controllers: abre/fecha a Session de cada operação,
devolve DTOs (nunca objetos ORM) e deixa as ErroDeNegocio subirem para a tela.
Dono e mecânico usam (Permissao.NOTIFICACOES).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.controle.sessao import protegido
from src.integracao.whatsapp import formatar_celular, normalizar_celular
from src.persistencia.models import Notificacao, StatusEnvio, TipoNotificacao
from src.servico.excecoes import (  # noqa: F401
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)
from src.servico.notificacao_service import (  # noqa: F401 (reexportadas para a tela)
    ABAS,
    CANCELADAS,
    DIAS_POS_VENDA,
    ENVIADAS,
    PARA_ENVIAR,
    PROXIMAS,
    EnvioPreparado,
    NotificacaoService,
)
from src.servico.paginacao import Pagina  # noqa: F401
from src.servico.permissoes import Permissao
from src.servico.validadores import exibir_placa

__all__ = [
    "ABAS", "CANCELADAS", "ENVIADAS", "PARA_ENVIAR", "PROXIMAS",
    "EnvioPreparado", "ErroDeNegocio", "NotificacaoController", "NotificacaoDTO",
    "OperacaoNaoPermitidaError", "Pagina", "RegistroNaoEncontradoError",
    "StatusEnvio", "TipoNotificacao", "ValidacaoError",
]


@dataclass(frozen=True)
class NotificacaoDTO:
    id_notificacao: int
    tipo: TipoNotificacao
    status: StatusEnvio
    data_prevista: Optional[date]
    data_envio: Optional[datetime]
    nome_cliente: str
    contato: str
    celular: Optional[str]          # "(54) 99999-1234" ou None se não for celular
    veiculo: str                    # "Gol (ABC1D23)"
    referencia: str                 # "OS nº 12" ou "Agendamento 20/11 08:00"
    servico: str
    atrasada: bool
    impedimento: Optional[str]      # por que não dá para enviar agora (None = pode)
    impedimento_curto: Optional[str]  # o mesmo, em poucas palavras (coluna da tabela)
    texto: str                      # mensagem enviada ou a que será enviada
    motivo_cancelamento: Optional[str]

    @property
    def pode_enviar(self) -> bool:
        return self.impedimento is None

    @property
    def pendente(self) -> bool:
        return self.status is StatusEnvio.PENDENTE


def _dto(servico: NotificacaoService, n: Notificacao, hoje: date) -> NotificacaoDTO:
    alvo = n.ordem_servico or n.agendamento
    cliente, veiculo = alvo.cliente, alvo.veiculo
    numero = normalizar_celular(cliente.contato)
    bloqueio = servico.bloqueio(n) if n.status_envio is StatusEnvio.PENDENTE else None
    if n.ordem_servico is not None:
        referencia = f"OS {n.ordem_servico.id_ordem_servico}"
        servico_txt = n.ordem_servico.tipo_servico or ""
    else:
        referencia = f"Agenda {n.agendamento.data_hora:%d/%m %H:%M}"
        servico_txt = n.agendamento.tipo_servico
    return NotificacaoDTO(
        id_notificacao=n.id_notificacao,
        tipo=n.tipo,
        status=n.status_envio,
        data_prevista=n.data_envio_prevista,
        data_envio=n.data_envio_real,
        nome_cliente=cliente.nome,
        contato=cliente.contato,
        celular=formatar_celular(numero) if numero else None,
        veiculo=f"{veiculo.modelo} ({exibir_placa(veiculo.placa)})",
        referencia=referencia,
        servico=servico_txt,
        atrasada=servico.atrasada(n, hoje),
        impedimento=bloqueio[1] if bloqueio else None,
        impedimento_curto=bloqueio[0] if bloqueio else None,
        texto=servico.texto(n),
        motivo_cancelamento=n.motivo_cancelamento,
    )


@protegido(Permissao.NOTIFICACOES)
class NotificacaoController:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        relogio: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._session_factory = session_factory
        self._relogio = relogio

    def _servico(self, session: Session) -> NotificacaoService:
        return NotificacaoService(session, relogio=self._relogio)

    def listar_pagina(self, aba: str = PARA_ENVIAR, termo: str = "", pagina: int = 1) -> Pagina:
        """Uma página da aba; `resumo` traz quantas há em cada aba (para os títulos)."""
        with self._session_factory() as session:
            servico, hoje = self._servico(session), self._relogio().date()
            resultado = servico.listar_pagina(aba, termo, pagina)
            return resultado.com_itens(_dto(servico, n, hoje) for n in resultado.itens)

    def obter(self, id_notificacao: int) -> NotificacaoDTO:
        with self._session_factory() as session:
            servico = self._servico(session)
            return _dto(servico, servico.obter(id_notificacao), self._relogio().date())

    def contar_para_enviar(self) -> int:
        with self._session_factory() as session:
            return self._servico(session).contar_para_enviar()

    def preparar_envio(self, id_notificacao: int, mensagem: Optional[str] = None) -> EnvioPreparado:
        with self._session_factory() as session:
            return self._servico(session).preparar_envio(id_notificacao, mensagem)

    def confirmar_envio(self, id_notificacao: int, mensagem: str) -> NotificacaoDTO:
        with self._session_factory() as session:
            servico = self._servico(session)
            return _dto(servico, servico.confirmar_envio(id_notificacao, mensagem), self._relogio().date())

    def cancelar(self, id_notificacao: int, motivo: Optional[str] = None) -> NotificacaoDTO:
        with self._session_factory() as session:
            servico = self._servico(session)
            return _dto(servico, servico.cancelar(id_notificacao, motivo), self._relogio().date())
