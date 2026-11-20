"""
Serviço de Notificação (RF07) — mensagens pelo WhatsApp (link wa.me).

Envio SEMIAUTOMÁTICO (decidido em 15/11/2026): o sistema cria a notificação
sozinho, na data certa, e monta a mensagem; uma pessoa confere e clica em
"Enviar". Assim não há custo, cadastro na Meta nem risco de banimento.

Tipos
-----
- Pós-venda: criada quando a OS passa a "entregue"; prevista para 7 dias
  depois da entrega (DIAS_POS_VENDA).
- Lembrete de agendamento: criado com o agendamento; previsto para a véspera
  (ou para hoje, se o horário é hoje ou amanhã). Mudar o horário remarca;
  cancelar ou converter o agendamento em OS cancela o lembrete.

Regras
------
- Cliente que não aceita mensagens (LGPD / RNF04): a notificação já nasce
  cancelada ("Cliente não aceita mensagens"). Desmarcar o aceite cancela as
  pendentes; marcar de novo reativa as que foram canceladas por esse motivo
  (se ainda fizerem sentido).
- Atrasada (data prevista já passou) continua em "Para enviar", com aviso:
  não expira. Exceção: lembrete de um horário que já passou não pode mais ser
  enviado (só cancelado).
- Só se envia notificação pendente, de cliente que aceita mensagens e com
  celular válido. Enviada e cancelada são finais.
- O texto realmente enviado fica gravado (histórico).

Os métodos chamados por OUTROS serviços (criar_pos_venda, criar_lembrete,
sincronizar_lembrete, cancelar_lembrete, aceite_alterado) só fazem flush:
quem chamou é o dono da transação, e tudo é gravado junto ou nada é.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional, Tuple

from sqlalchemy.orm import Session

from src.integracao.whatsapp import ProvedorMensagens, normalizar_celular, provedor_padrao
from src.persistencia.models import (
    Agendamento, Notificacao, OrdemServico, StatusAgendamento, StatusEnvio, TipoNotificacao,
)
from src.persistencia.repositories.notificacao_repository import (  # noqa: F401 (abas reexportadas)
    ABAS, CANCELADAS, ENVIADAS, PARA_ENVIAR, PROXIMAS, NotificacaoRepository,
)
from src.servico.excecoes import (
    OperacaoNaoPermitidaError, RegistroNaoEncontradoError, ValidacaoError,
)
from src.servico.paginacao import POR_PAGINA, Pagina, montar_pagina

DIAS_POS_VENDA = 7
DIAS_LEMBRETE = 1
MENSAGEM_MAXIMA = 2000
MOTIVO_MAXIMO = 150
MOTIVO_SEM_ACEITE = "Cliente não aceita mensagens"
MOTIVO_AGENDAMENTO_CANCELADO = "Agendamento cancelado"
MOTIVO_AGENDAMENTO_CONVERTIDO = "Agendamento convertido em OS"
MOTIVO_PADRAO = "Cancelada pelo usuário"

_DIAS_SEMANA = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                "sexta-feira", "sábado", "domingo")


# ----------------------------------------------------------------------
# Funções puras (testáveis sem banco)
# ----------------------------------------------------------------------
def data_pos_venda(entregue_em: datetime) -> date:
    return entregue_em.date() + timedelta(days=DIAS_POS_VENDA)


def data_lembrete(data_hora: datetime, hoje: date) -> date:
    """Véspera do horário; se a véspera já passou (agendado para hoje/amanhã), hoje."""
    return max(data_hora.date() - timedelta(days=DIAS_LEMBRETE), hoje)


def nome_da_oficina() -> str:
    return " ".join((os.getenv("OFICINA_NOME") or "").split())


def _apresentacao() -> str:
    nome = nome_da_oficina()
    return f"Aqui é da oficina {nome}" if nome else "Aqui é da oficina"


def _primeiro_nome(nome: str) -> str:
    partes = (nome or "").split()
    return partes[0].capitalize() if partes else "tudo bem"


def _veiculo(v) -> str:
    """'Gol (ABC1D23)'; sem placa (RF02) fica só 'Gol'."""
    return f"{v.modelo} ({v.placa})" if v.placa else v.modelo


def mensagem_pos_venda(os_: OrdemServico) -> str:
    servico = " ".join((os_.tipo_servico or "").split()).lower() or "manutenção"
    v = os_.veiculo
    return (
        f"Olá, {_primeiro_nome(os_.cliente.nome)}! {_apresentacao()}.\n"
        f"Faz uma semana que o seu {_veiculo(v)} saiu daqui com o serviço de "
        f"{servico} (OS nº {os_.id_ordem_servico}). Está tudo certo com o veículo?\n"
        f"Se notar qualquer coisa, é só responder esta mensagem. Obrigado pela confiança!"
    )


def mensagem_lembrete(ag: Agendamento, hoje: date) -> str:
    dia = ag.data_hora.date()
    data = f"{_DIAS_SEMANA[dia.weekday()]}, {dia:%d/%m}"
    if dia == hoje:
        quando_texto = f"hoje ({data})"
    elif dia == hoje + timedelta(days=1):
        quando_texto = f"amanhã ({data})"
    else:
        quando_texto = f"{'no' if dia.weekday() >= 5 else 'na'} {data}"
    v = ag.veiculo
    return (
        f"Olá, {_primeiro_nome(ag.cliente.nome)}! {_apresentacao()}.\n"
        f"Passando para lembrar do seu agendamento {quando_texto}, às {ag.data_hora:%H:%M}: "
        f"{' '.join(ag.tipo_servico.split()).lower()} no {_veiculo(v)}.\n"
        f"Se não puder vir, é só responder esta mensagem que a gente remarca. Até lá!"
    )


@dataclass(frozen=True)
class EnvioPreparado:
    id_notificacao: int
    numero: str     # 55 + DDD + celular
    mensagem: str
    endereco: str   # link que a tela abre (wa.me)
    provedor: str


class NotificacaoService:
    def __init__(
        self,
        session: Session,
        relogio: Callable[[], datetime] = datetime.now,
        provedor: Optional[ProvedorMensagens] = None,
    ) -> None:
        self._session = session
        self._repo = NotificacaoRepository(session)
        self._relogio = relogio
        self._provedor = provedor or provedor_padrao()

    def _hoje(self) -> date:
        return self._relogio().date()

    # ------------------------------------------------------------------
    # Ganchos chamados por outros serviços (só flush)
    # ------------------------------------------------------------------
    def criar_pos_venda(self, os_: OrdemServico) -> Notificacao:
        existente = self._repo.buscar_da_os(os_.id_ordem_servico)
        if existente is not None:  # entregue é final, mas por segurança não duplica
            return existente
        return self._repo.adicionar(self._nova(
            TipoNotificacao.POS_VENDA, os_.cliente.aceita_mensagens,
            data_pos_venda(os_.entregue_em or self._relogio()),
            id_ordem_servico=os_.id_ordem_servico,
        ))

    def criar_lembrete(self, ag: Agendamento) -> Notificacao:
        return self._repo.adicionar(self._nova(
            TipoNotificacao.LEMBRETE_AGENDAMENTO, ag.cliente.aceita_mensagens,
            data_lembrete(ag.data_hora, self._hoje()), id_agendamento=ag.id_agendamento,
        ))

    def sincronizar_lembrete(self, ag: Agendamento) -> Optional[Notificacao]:
        """Agendamento editado (horário ou cliente): remarca o lembrete ainda pendente."""
        n = self._repo.buscar_do_agendamento(ag.id_agendamento)
        if n is None:
            return self.criar_lembrete(ag)
        if n.status_envio is StatusEnvio.ENVIADO:
            return n  # já foi; a pessoa avisa o cliente da mudança pelo próprio WhatsApp
        if n.status_envio is StatusEnvio.CANCELADO and n.motivo_cancelamento != MOTIVO_SEM_ACEITE:
            return n  # cancelado de propósito pelo usuário
        n.data_envio_prevista = data_lembrete(ag.data_hora, self._hoje())
        self._aplicar_aceite(n, ag.cliente.aceita_mensagens)
        self._repo.flush()
        return n

    def cancelar_lembrete(self, ag: Agendamento, motivo: str) -> None:
        n = self._repo.buscar_do_agendamento(ag.id_agendamento)
        if n is not None and n.status_envio is StatusEnvio.PENDENTE:
            n.status_envio, n.motivo_cancelamento = StatusEnvio.CANCELADO, motivo
            self._repo.flush()

    def aceite_alterado(self, id_cliente: int, aceita: bool) -> int:
        """
        Cliente mudou a opção de receber mensagens.
        False: cancela as pendentes. True: reativa as canceladas por esse motivo,
        menos lembretes de agendamentos que já não estão agendados ou já passaram.
        Devolve quantas notificações mudaram.
        """
        if not aceita:
            return self._repo.cancelar_pendentes_do_cliente(id_cliente, MOTIVO_SEM_ACEITE)
        agora, mudou = self._relogio(), 0
        for n in self._repo.reativar_do_cliente(id_cliente, MOTIVO_SEM_ACEITE):
            ag = n.agendamento
            if ag is not None and (ag.status is not StatusAgendamento.AGENDADO or ag.data_hora <= agora):
                continue
            n.status_envio, n.motivo_cancelamento = StatusEnvio.PENDENTE, None
            mudou += 1
        self._repo.flush()
        return mudou

    def _nova(self, tipo: TipoNotificacao, aceita: bool, prevista: date, **alvo) -> Notificacao:
        n = Notificacao(tipo=tipo, data_envio_prevista=prevista, **alvo)
        self._aplicar_aceite(n, aceita)
        return n

    @staticmethod
    def _aplicar_aceite(n: Notificacao, aceita: bool) -> None:
        if aceita:
            n.status_envio, n.motivo_cancelamento = StatusEnvio.PENDENTE, None
        else:
            n.status_envio, n.motivo_cancelamento = StatusEnvio.CANCELADO, MOTIVO_SEM_ACEITE

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def obter(self, id_notificacao: int) -> Notificacao:
        n = self._repo.buscar_por_id(id_notificacao)
        if n is None:
            raise RegistroNaoEncontradoError(f"Notificação {id_notificacao} não encontrada.")
        return n

    def listar_pagina(self, aba: str = PARA_ENVIAR, termo: str = "", pagina: int = 1,
                      por_pagina: int = POR_PAGINA) -> Pagina:
        if aba not in ABAS:
            raise ValidacaoError("A aba informada é inválida.")
        termo, hoje = (termo or "").strip(), self._hoje()
        return montar_pagina(
            self._repo.contar(aba, hoje, termo), pagina,
            lambda limite, desloc: self._repo.listar_pagina(aba, hoje, termo, limite, desloc),
            por_pagina, resumo=self._repo.contar_por_aba(hoje, termo),
        )

    def contar_para_enviar(self) -> int:
        """Quantas estão na aba "Para enviar" (selo do menu e aviso ao entrar)."""
        return self._repo.contar(PARA_ENVIAR, self._hoje())

    def mensagem_padrao(self, n: Notificacao) -> str:
        if n.tipo is TipoNotificacao.POS_VENDA:
            return mensagem_pos_venda(n.ordem_servico)
        return mensagem_lembrete(n.agendamento, self._hoje())

    def texto(self, n: Notificacao) -> str:
        """O texto enviado (se já foi) ou o que seria enviado agora."""
        return n.mensagem or self.mensagem_padrao(n)

    def bloqueio(self, n: Notificacao) -> Optional[Tuple[str, str]]:
        """(texto curto, explicação) de por que não dá para enviar agora; None = pode."""
        if n.status_envio is not StatusEnvio.PENDENTE:
            situacao = n.status_envio.rotulo.lower()
            return situacao.capitalize(), f"A notificação já está “{situacao}”."
        cliente = (n.ordem_servico or n.agendamento).cliente
        if not cliente.aceita_mensagens:
            return "Não aceita mensagens", "O cliente não aceita receber mensagens."
        if normalizar_celular(cliente.contato) is None:
            return "Sem celular", (f"O contato do cliente ({cliente.contato}) não é um celular válido. "
                                   "Corrija o cadastro do cliente.")
        if n.agendamento is not None and n.agendamento.data_hora <= self._relogio():
            return "Horário já passou", "O horário do agendamento já passou. Cancele este lembrete."
        return None

    def impedimento(self, n: Notificacao) -> Optional[str]:
        """Explicação de por que esta notificação não pode ser enviada agora (None = pode)."""
        b = self.bloqueio(n)
        return b[1] if b else None

    @staticmethod
    def atrasada(n: Notificacao, hoje: date) -> bool:
        return (n.status_envio is StatusEnvio.PENDENTE and n.data_envio_prevista is not None
                and n.data_envio_prevista < hoje)

    # ------------------------------------------------------------------
    # Envio (semiautomático) e cancelamento
    # ------------------------------------------------------------------
    def preparar_envio(self, id_notificacao: int, mensagem: Optional[str] = None) -> EnvioPreparado:
        """Confere as regras e monta o link. Não grava nada: o envio é confirmado depois."""
        n = self.obter(id_notificacao)
        motivo = self.impedimento(n)
        if motivo:
            raise OperacaoNaoPermitidaError(motivo)
        texto = self._validar_mensagem(mensagem if mensagem is not None else self.mensagem_padrao(n))
        cliente = (n.ordem_servico or n.agendamento).cliente
        numero = normalizar_celular(cliente.contato)
        return EnvioPreparado(n.id_notificacao, numero, texto,
                              self._provedor.preparar(numero, texto), self._provedor.nome)

    def confirmar_envio(self, id_notificacao: int, mensagem: str) -> Notificacao:
        """A pessoa confirmou que enviou: grava a data e o texto exato."""
        texto = self._validar_mensagem(mensagem)
        n = self._obter_travada(id_notificacao)
        motivo = self.impedimento(n)
        if motivo:
            self._session.rollback()
            raise OperacaoNaoPermitidaError(motivo)
        n.status_envio = StatusEnvio.ENVIADO
        n.data_envio_real = self._relogio().replace(microsecond=0)
        n.mensagem = texto
        self._confirmar()
        return self.obter(id_notificacao)

    def cancelar(self, id_notificacao: int, motivo: Optional[str] = None) -> Notificacao:
        motivo = " ".join((motivo or "").split()) or MOTIVO_PADRAO
        if len(motivo) > MOTIVO_MAXIMO:
            raise ValidacaoError(f"O motivo deve ter no máximo {MOTIVO_MAXIMO} caracteres.")
        n = self._obter_travada(id_notificacao)
        if n.status_envio is not StatusEnvio.PENDENTE:
            situacao = n.status_envio.rotulo.lower()
            self._session.rollback()
            raise OperacaoNaoPermitidaError(f"Só é possível cancelar notificação pendente; esta já está “{situacao}”.")
        n.status_envio, n.motivo_cancelamento = StatusEnvio.CANCELADO, motivo
        self._confirmar()
        return self.obter(id_notificacao)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    @staticmethod
    def _validar_mensagem(mensagem: Optional[str]) -> str:
        texto = (mensagem or "").strip()
        if not texto:
            raise ValidacaoError("A mensagem não pode ficar vazia.")
        if len(texto) > MENSAGEM_MAXIMA:
            raise ValidacaoError(f"A mensagem deve ter no máximo {MENSAGEM_MAXIMA} caracteres.")
        return texto

    def _obter_travada(self, id_notificacao: int) -> Notificacao:
        n = self._repo.buscar_por_id(id_notificacao, travar=True)
        if n is None:
            self._session.rollback()
            raise RegistroNaoEncontradoError(f"Notificação {id_notificacao} não encontrada.")
        return n

    def _confirmar(self) -> None:
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

