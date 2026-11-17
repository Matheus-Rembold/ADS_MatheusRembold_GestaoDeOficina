"""
Tela de Notificações (RF07): mensagens pelo WhatsApp (pós-venda e lembretes).

Abas por situação: Para enviar (hoje e atrasadas), Próximas, Enviadas e
Canceladas, cada uma com a quantidade no título.

Usabilidade (Nielsen):
- Visibilidade do estado do sistema: contagem nas abas e no menu lateral;
  atrasadas marcadas com ⚠; o motivo de não poder enviar aparece na linha.
- Prevenção de erros: botões desabilitados sem seleção ou quando a ação não
  vale para a linha; cancelar pede confirmação.
- Consistência: mesmo padrão das outras listas (busca, paginação, ações no
  cabeçalho com o botão principal no canto direito).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.apresentacao.componentes import (
    BarraPaginacao,
    aviso,
    erro_inesperado,
    preenchendo_tabela,
    texto_contagem,
)
from src.apresentacao.telas.notificacao_envio_dialog import NotificacaoEnvioDialog
from src.apresentacao.tema import ERRO, LARANJA_ESCURO
from src.controle.notificacao_controller import (
    CANCELADAS,
    DIAS_POS_VENDA,
    ENVIADAS,
    PARA_ENVIAR,
    PROXIMAS,
    ErroDeNegocio,
    NotificacaoController,
    NotificacaoDTO,
    StatusEnvio,
    TipoNotificacao,
)

ABAS_TELA = [  # (chave, título, cabeçalho da coluna de data)
    (PARA_ENVIAR, "Para enviar", "Previsto para"),
    (PROXIMAS, "Próximas", "Previsto para"),
    (ENVIADAS, "Enviadas", "Enviada em"),
    (CANCELADAS, "Canceladas", "Previsto para"),
]
COLUNAS = ["Data", "Tipo", "Cliente", "Celular", "Veículo", "Referência", "Situação"]
COL_DATA, COL_TIPO, COL_CLIENTE, COL_CELULAR, COL_VEICULO, COL_REF, COL_SITUACAO = range(7)


def _situacao(n: NotificacaoDTO, hoje: date) -> tuple:
    """(texto curto, explicação para o tooltip, cor ou None) da coluna Situação."""
    if n.status is StatusEnvio.ENVIADO:
        return "Enviada", "", None
    if n.status is StatusEnvio.CANCELADO:
        motivo = n.motivo_cancelamento or "Cancelada"
        return motivo, motivo, None
    if n.impedimento:
        return f"⛔ {n.impedimento_curto}", n.impedimento, ERRO
    if n.atrasada:
        dias = (hoje - n.data_prevista).days
        return (f"⚠ Atrasada há {dias} dia{'s' if dias > 1 else ''}",
                "Ainda pode ser enviada: a notificação não expira.", LARANJA_ESCURO)
    if n.data_prevista and n.data_prevista > hoje:
        return "Aguardando a data", "Vai para “Para enviar” na data prevista.", None
    return "Pronta para enviar", "", None


class NotificacoesView(QWidget):
    # Quantas estão em "Para enviar" (a janela principal mostra no menu)
    contagem_mudou = pyqtSignal(int)

    def __init__(self, controller: Optional[NotificacaoController] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagina")
        self._controller = controller or NotificacaoController()
        self._pagina = 1
        self._itens: List[NotificacaoDTO] = []
        self._timer_busca = QTimer(self, singleShot=True, interval=250)
        self._timer_feedback = QTimer(self, singleShot=True, interval=5000)
        self._montar_interface()
        self._conectar_sinais()
        self._atualizar_botoes()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------
    def _montar_interface(self) -> None:
        titulo = QLabel("Notificações")
        titulo.setObjectName("titulo")
        subtitulo = QLabel(f"Mensagens pelo WhatsApp: pós-venda ({DIAS_POS_VENDA} dias após a entrega) "
                           "e lembrete na véspera do agendamento")
        subtitulo.setObjectName("subtitulo")
        subtitulo.setWordWrap(True)
        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        bloco_titulo.addWidget(titulo)
        bloco_titulo.addWidget(subtitulo)

        self.btn_ver = QPushButton("Ver mensagem")
        self.btn_cancelar = QPushButton("Cancelar notificação")
        self.btn_cancelar.setObjectName("perigo")
        self.btn_enviar = QPushButton("Enviar pelo WhatsApp")
        self.btn_enviar.setObjectName("primario")

        cabecalho = QHBoxLayout()
        cabecalho.addLayout(bloco_titulo, 1)
        for botao in (self.btn_ver, self.btn_cancelar):
            cabecalho.addWidget(botao, alignment=Qt.AlignmentFlag.AlignVCenter)
        cabecalho.addSpacing(12)
        cabecalho.addWidget(self.btn_enviar, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.abas = QTabBar()
        self.abas.setExpanding(False)
        self.abas.setDrawBase(False)
        for _chave, rotulo, _data in ABAS_TELA:
            self.abas.addTab(rotulo)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("Buscar por cliente ou placa…")
        self._busca.setClearButtonEnabled(True)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setShowGrid(False)
        self.tabela.setWordWrap(False)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.verticalHeader().setDefaultSectionSize(40)
        cab = self.tabela.horizontalHeader()
        cab.setHighlightSections(False)
        cab.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for col in range(len(COLUNAS)):
            cab.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_CLIENTE, QHeaderView.ResizeMode.Stretch)  # o resto vai para o nome

        self._lbl_vazio = QLabel()
        self._lbl_vazio.setObjectName("vazio")
        self._lbl_vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_vazio.hide()

        self._lbl_total = QLabel()
        self._lbl_total.setObjectName("rodape")
        self._lbl_feedback = QLabel()
        self._lbl_feedback.setObjectName("feedbackOk")
        self._paginacao = BarraPaginacao()
        rodape = QHBoxLayout()
        rodape.addWidget(self._lbl_total)
        rodape.addSpacing(16)
        rodape.addWidget(self._lbl_feedback, stretch=1)
        rodape.addWidget(self._paginacao)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(12)
        raiz.addLayout(cabecalho)
        raiz.addWidget(self.abas)
        raiz.addWidget(self._busca)
        raiz.addWidget(self.tabela, stretch=1)
        raiz.addWidget(self._lbl_vazio, stretch=1)
        raiz.addLayout(rodape)

    def _conectar_sinais(self) -> None:
        self.btn_enviar.clicked.connect(self._abrir)
        self.btn_ver.clicked.connect(self._abrir)
        self.btn_cancelar.clicked.connect(self._cancelar)
        self.abas.currentChanged.connect(lambda _i: self.recarregar(pagina=1, selecionar_id=-1))
        self._busca.textChanged.connect(lambda _t: self._timer_busca.start())
        self._timer_busca.timeout.connect(lambda: self.recarregar(pagina=1))
        self._paginacao.pagina_pedida.connect(lambda p: self.recarregar(pagina=p))
        self._timer_feedback.timeout.connect(lambda: self._lbl_feedback.setText(""))
        self.tabela.itemSelectionChanged.connect(self._atualizar_botoes)
        self.tabela.itemDoubleClicked.connect(lambda _item: self._abrir())

    # ------------------------------------------------------------------
    # Dados
    # ------------------------------------------------------------------
    @property
    def aba_atual(self) -> str:
        return ABAS_TELA[max(0, self.abas.currentIndex())][0]

    def contar_para_enviar(self) -> int:
        """Para o selo do menu e o aviso ao entrar (sem abrir a tela)."""
        return self._controller.contar_para_enviar()

    def showEvent(self, evento) -> None:  # noqa: N802
        super().showEvent(evento)
        self.recarregar()

    def recarregar(self, selecionar_id: Optional[int] = None, pagina: Optional[int] = None) -> None:
        if selecionar_id is None:
            selecionar_id = self._id_selecionado()
        if pagina is not None:
            self._pagina = pagina
        try:
            resultado = self._controller.listar_pagina(self.aba_atual, self._busca.text(), self._pagina)
            para_enviar = self._controller.contar_para_enviar()  # sem o filtro da busca (menu)
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível carregar as notificações.")
            return
        self._pagina = resultado.pagina
        self._itens = list(resultado.itens)
        for i, (chave, rotulo, _data) in enumerate(ABAS_TELA):
            self.abas.setTabText(i, f"{rotulo} ({resultado.resumo.get(chave, 0)})")
        self.tabela.horizontalHeaderItem(COL_DATA).setText(ABAS_TELA[self.abas.currentIndex()][2])
        with preenchendo_tabela(self.tabela):
            self._preencher_linhas(selecionar_id)
        self._lbl_total.setText(texto_contagem(resultado, "notificação", "notificações"))
        self._paginacao.atualizar(resultado)
        self.contagem_mudou.emit(para_enviar)

    def _preencher_linhas(self, selecionar_id: Optional[int]) -> None:
        hoje = date.today()
        self.tabela.setRowCount(len(self._itens))
        alvo = -1
        for linha, n in enumerate(self._itens):
            if self.aba_atual == ENVIADAS and n.data_envio:
                data = f"{n.data_envio:%d/%m/%Y %H:%M}"
            else:
                data = f"{n.data_prevista:%d/%m/%Y}" if n.data_prevista else "—"
            situacao, explicacao, cor = _situacao(n, hoje)
            valores = [data, "Pós-venda" if n.tipo is TipoNotificacao.POS_VENDA else "Lembrete", n.nome_cliente, n.celular or n.contato,
                       n.veiculo, n.referencia, situacao]
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == COL_DATA:
                    item.setData(Qt.ItemDataRole.UserRole, n.id_notificacao)
                if coluna == COL_SITUACAO:
                    item.setToolTip(explicacao or valor)
                    if cor:
                        item.setForeground(QBrush(QColor(cor)))
                if coluna == COL_CELULAR and not n.celular:
                    item.setForeground(QBrush(QColor(ERRO)))
                    item.setToolTip("Não é um celular válido: corrija o contato no cadastro do cliente.")
                self.tabela.setItem(linha, coluna, item)
            if n.id_notificacao == selecionar_id:
                alvo = linha
        if alvo >= 0:
            self.tabela.selectRow(alvo)
        else:
            self.tabela.clearSelection()
        vazio = {
            PARA_ENVIAR: "Nada para enviar hoje.",
            PROXIMAS: "Nenhuma notificação programada.",
            ENVIADAS: "Nenhuma mensagem enviada ainda.",
            CANCELADAS: "Nenhuma notificação cancelada.",
        }[self.aba_atual]
        self._lbl_vazio.setText(vazio if not self._busca.text().strip() else "Nenhuma notificação encontrada.")
        self.tabela.setVisible(bool(self._itens))
        self._lbl_vazio.setVisible(not self._itens)
        self._atualizar_botoes()

    def _selecionada(self) -> Optional[NotificacaoDTO]:
        id_ = self._id_selecionado()
        return next((n for n in self._itens if n.id_notificacao == id_), None)

    def _id_selecionado(self) -> Optional[int]:
        modelo = self.tabela.selectionModel()
        linhas = modelo.selectedRows() if modelo else []
        if not linhas:
            return None
        return self.tabela.item(linhas[0].row(), COL_DATA).data(Qt.ItemDataRole.UserRole)

    def _atualizar_botoes(self) -> None:
        n = self._selecionada()
        self.btn_ver.setEnabled(n is not None)
        self.btn_cancelar.setEnabled(n is not None and n.pendente)
        self.btn_enviar.setEnabled(n is not None and n.pendente and n.pode_enviar)
        self.btn_enviar.setToolTip(
            n.impedimento if n is not None and n.pendente and n.impedimento else
            "Abre o WhatsApp com a mensagem pronta"
        )

    def _mostrar_feedback(self, texto: str) -> None:
        self._lbl_feedback.setText(texto)
        self._timer_feedback.start()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _abrir(self) -> None:
        n = self._selecionada()
        if n is None:
            return
        try:
            n = self._controller.obter(n.id_notificacao)  # leitura fresca
        except ErroDeNegocio as erro:
            aviso(self, "Notificação indisponível", str(erro))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível abrir a notificação.")
            return
        dialogo = NotificacaoEnvioDialog(self._controller, n, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.resultado:
            self.recarregar()
            self._mostrar_feedback(f"Mensagem para “{n.nome_cliente}” registrada como enviada.")
        else:
            self.recarregar(selecionar_id=n.id_notificacao)

    def _cancelar(self) -> None:
        n = self._selecionada()
        if n is None or not n.pendente:
            return
        motivo, ok = QInputDialog.getText(
            self, "Cancelar notificação",
            f"A mensagem para “{n.nome_cliente}” ({n.tipo.rotulo.lower()}) não será enviada.\n\n"
            "Motivo (opcional):",
        )
        if not ok:
            return
        try:
            self._controller.cancelar(n.id_notificacao, motivo)
        except ErroDeNegocio as erro:
            aviso(self, "Não foi possível cancelar", str(erro))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível cancelar a notificação.")
            return
        self.recarregar()
        self._mostrar_feedback(f"Notificação de “{n.nome_cliente}” cancelada.")
