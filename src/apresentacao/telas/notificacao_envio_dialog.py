"""
Envio de uma notificação pelo WhatsApp (RF07) — e consulta das já enviadas.

Fluxo semiautomático (decidido em 15/11/2026):
1. a tela mostra a mensagem pronta (editável) e para quem vai;
2. "Abrir no WhatsApp" abre o link wa.me com o número e o texto;
3. a pessoa aperta "Enviar" no WhatsApp e volta: o sistema PERGUNTA se a
   mensagem foi enviada, porque o link não tem como saber (o envio acontece
   fora do sistema). Só com o "sim" a notificação vira "Enviada".

Usabilidade (Nielsen):
- Visibilidade do estado: destinatário, celular e situação no topo.
- Prevenção de erros: quando não dá para enviar (cliente recusou, telefone
  fixo, horário passado) o botão fica desabilitado e o MOTIVO aparece.
- Controle e liberdade: o texto pode ser ajustado e há "Restaurar texto".
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from src.apresentacao.componentes import aviso, confirmar, destacar, erro_inesperado
from src.controle.notificacao_controller import (
    ErroDeNegocio,
    NotificacaoController,
    NotificacaoDTO,
    StatusEnvio,
    ValidacaoError,
)

logger = logging.getLogger(__name__)

LIMITE_TEXTO = 2000


class NotificacaoEnvioDialog(QDialog):
    # Trocável nos testes (para não abrir o navegador de verdade).
    abrir_endereco = staticmethod(lambda endereco: QDesktopServices.openUrl(QUrl(endereco)))
    # Pergunta "foi enviada?"; trocável nos testes.
    perguntar_se_enviou = None

    def __init__(self, controller: NotificacaoController, notificacao: NotificacaoDTO, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._n = notificacao
        self.resultado: Optional[NotificacaoDTO] = None  # preenchido quando o envio é confirmado

        pode_enviar = notificacao.pendente and notificacao.pode_enviar
        self.setWindowTitle("Enviar pelo WhatsApp" if pode_enviar else "Mensagem")
        self.setModal(True)
        self.setMinimumWidth(560)

        info = QFormLayout()
        info.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        info.setVerticalSpacing(6)
        info.addRow("Tipo:", QLabel(notificacao.tipo.rotulo))
        info.addRow("Cliente:", QLabel(notificacao.nome_cliente))
        info.addRow("Celular:", QLabel(notificacao.celular or f"{notificacao.contato} (não é celular)"))
        info.addRow("Veículo:", QLabel(notificacao.veiculo))
        info.addRow("Referência:", QLabel(notificacao.referencia))
        info.addRow("Situação:", QLabel(self._situacao()))

        self._texto = QPlainTextEdit(notificacao.texto)
        self._texto.setReadOnly(not pode_enviar)
        self._texto.setMinimumHeight(170)
        self._texto.textChanged.connect(self._atualizar_contador)
        self._contador = QLabel()
        self._contador.setObjectName("subtitulo")

        self._impedimento = QLabel(notificacao.impedimento or "")
        self._impedimento.setObjectName("subtitulo")
        self._impedimento.setWordWrap(True)
        self._impedimento.setVisible(notificacao.pendente and not notificacao.pode_enviar)
        destacar(self._impedimento, "alerta", True)

        self._btn_restaurar = QPushButton("Restaurar texto")
        self._btn_restaurar.setVisible(pode_enviar)
        self._btn_restaurar.clicked.connect(lambda: self._texto.setPlainText(notificacao.texto))
        self._btn_fechar = QPushButton("Fechar")
        self._btn_fechar.clicked.connect(self.reject)
        self.btn_enviar = QPushButton("Abrir no WhatsApp")
        self.btn_enviar.setObjectName("primario")
        self.btn_enviar.setVisible(notificacao.pendente)
        self.btn_enviar.setEnabled(pode_enviar)
        self.btn_enviar.setToolTip("Abre o WhatsApp com o número e a mensagem prontos; "
                                   "lá você só aperta Enviar.")
        self.btn_enviar.clicked.connect(self._enviar)

        botoes = QHBoxLayout()
        botoes.addWidget(self._btn_restaurar)
        botoes.addStretch()
        botoes.addWidget(self._btn_fechar)
        botoes.addWidget(self.btn_enviar)

        linha_texto = QHBoxLayout()
        rotulo = QLabel("Mensagem" + (" (pode ajustar antes de enviar)" if pode_enviar else ""))
        rotulo.setObjectName("subtitulo")
        linha_texto.addWidget(rotulo)
        linha_texto.addStretch()
        linha_texto.addWidget(self._contador)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addLayout(info)
        layout.addLayout(linha_texto)
        layout.addWidget(self._texto)
        layout.addWidget(self._impedimento)
        layout.addLayout(botoes)
        self._atualizar_contador()
        if pode_enviar:
            self.btn_enviar.setDefault(True)

    def _situacao(self) -> str:
        n = self._n
        if n.status is StatusEnvio.ENVIADO and n.data_envio:
            return f"Enviada em {n.data_envio:%d/%m/%Y às %H:%M}"
        if n.status is StatusEnvio.CANCELADO:
            return f"Cancelada — {n.motivo_cancelamento or 'sem motivo'}"
        prevista = f"{n.data_prevista:%d/%m/%Y}" if n.data_prevista else "—"
        return f"Pendente, prevista para {prevista}" + (" (atrasada)" if n.atrasada else "")

    def _atualizar_contador(self) -> None:
        tamanho = len(self._texto.toPlainText().strip())
        self._contador.setText(f"{tamanho}/{LIMITE_TEXTO}")
        destacar(self._contador, "alerta", tamanho > LIMITE_TEXTO or tamanho == 0)

    def _enviar(self) -> None:
        try:
            envio = self._controller.preparar_envio(self._n.id_notificacao, self._texto.toPlainText())
        except ValidacaoError as erro:
            aviso(self, "Mensagem inválida", "\n".join(erro.erros))
            return
        except ErroDeNegocio as erro:
            aviso(self, "Não é possível enviar", str(erro))
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível preparar o envio.")
            return

        if not type(self).abrir_endereco(envio.endereco):
            aviso(self, "WhatsApp não abriu",
                  "Não foi possível abrir o WhatsApp neste computador.\n"
                  "Verifique se há um navegador padrão ou o WhatsApp Desktop instalado.")
            return

        if not self._confirmar_envio():
            return  # continua aberto: a pessoa pode tentar de novo ou fechar
        try:
            self.resultado = self._controller.confirmar_envio(self._n.id_notificacao, envio.mensagem)
        except ErroDeNegocio as erro:
            aviso(self, "Não foi possível registrar", str(erro))
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível registrar o envio.")
            return
        self.accept()

    def _confirmar_envio(self) -> bool:
        if self.perguntar_se_enviou is not None:
            return self.perguntar_se_enviou()
        return confirmar(
            self, "Confirmar envio",
            "O WhatsApp foi aberto com a mensagem pronta.\n\n"
            "Você apertou “Enviar” no WhatsApp e a mensagem foi enviada?",
            rotulo_confirmar="Sim, foi enviada", rotulo_cancelar="Ainda não",
        )
