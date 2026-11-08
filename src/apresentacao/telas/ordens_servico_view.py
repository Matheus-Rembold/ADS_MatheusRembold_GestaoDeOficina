"""
Tela de Ordens de Serviço (RF04): lista, busca, filtro por situação e ações.

Decisões de usabilidade (Nielsen, RNF01):
- Prevenção de erros: "Alterar situação" só oferece os passos permitidos a
  partir da situação atual; "Excluir" só fica ativo para orçamento; passos com
  efeito no estoque ou sem volta pedem confirmação.
- Visibilidade do estado do sistema: a situação aparece em texto e cor; o
  rodapé mostra quantas OS e o valor somado das listadas.
- Reconhecimento em vez de memorização: a busca aceita cliente, placa,
  modelo, tipo de serviço, problema ou número da OS (histórico por cliente
  e por veículo = buscar pelo nome ou placa).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.apresentacao.componentes import aviso, confirmar, erro_inesperado, formatar_moeda
from src.apresentacao.telas.ordem_servico_dialog import OrdemServicoDialog
from src.apresentacao.tema import ERRO, SUCESSO
from src.controle.ordem_servico_controller import (
    ErroDeNegocio,
    OrdemServicoController,
    OrdemServicoDTO,
    StatusOrdemServico,
)

COLUNAS = ["OS", "Data", "Cliente", "Veículo", "Serviço", "Situação", "Total"]
COL_OS, COL_DATA, COL_CLIENTE, COL_VEICULO, COL_SERVICO, COL_STATUS, COL_TOTAL = range(7)

_COR_STATUS: Dict[StatusOrdemServico, str] = {
    StatusOrdemServico.ORCAMENTO: "#868E96",
    StatusOrdemServico.ANDAMENTO: "#1C7ED6",
    StatusOrdemServico.PRONTO: "#E67700",
    StatusOrdemServico.AGUARDANDO_PAGAMENTO: ERRO,
    StatusOrdemServico.ENTREGUE: SUCESSO,
}


class OrdensServicoView(QWidget):
    def __init__(self, controller: Optional[OrdemServicoController] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagina")
        self._controller = controller or OrdemServicoController()
        self._dtos: List[OrdemServicoDTO] = []
        self._timer_busca = QTimer(self, singleShot=True, interval=250)
        self._timer_feedback = QTimer(self, singleShot=True, interval=5000)
        self._montar_interface()
        self._conectar_sinais()

    # ------------------------------------------------------------------
    def _montar_interface(self) -> None:
        titulo = QLabel("Ordens de Serviço")
        titulo.setObjectName("titulo")
        subtitulo = QLabel("Orçamentos e serviços da oficina: peças, mão de obra e situação")
        subtitulo.setObjectName("subtitulo")
        bloco = QVBoxLayout()
        bloco.setSpacing(2)
        bloco.addWidget(titulo)
        bloco.addWidget(subtitulo)

        self._btn_nova = QPushButton("+  Nova OS")
        self._btn_nova.setObjectName("primario")
        self._btn_abrir = QPushButton("Abrir")
        self._btn_status = QPushButton("Alterar situação  ▾")
        self._btn_excluir = QPushButton("Excluir")
        self._btn_excluir.setObjectName("perigo")
        for b in (self._btn_abrir, self._btn_status, self._btn_excluir):
            b.setEnabled(False)

        cabecalho = QHBoxLayout()
        cabecalho.addLayout(bloco)
        cabecalho.addStretch(1)
        cabecalho.addWidget(self._btn_abrir)
        cabecalho.addWidget(self._btn_status)
        cabecalho.addWidget(self._btn_excluir)
        cabecalho.addWidget(self._btn_nova)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("Buscar por cliente, placa, modelo, serviço, problema ou nº da OS…")
        self._busca.setClearButtonEnabled(True)
        self._filtro = QComboBox()
        self._filtro.addItem("Todas as situações", None)
        for s in StatusOrdemServico:
            self._filtro.addItem(s.rotulo, s)
        filtros = QHBoxLayout()
        filtros.addWidget(self._busca, stretch=1)
        filtros.addWidget(self._filtro)

        self._tabela = QTableWidget(0, len(COLUNAS))
        self._tabela.setHorizontalHeaderLabels(COLUNAS)
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.setShowGrid(False)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.verticalHeader().setDefaultSectionSize(40)
        cab = self._tabela.horizontalHeader()
        cab.setHighlightSections(False)
        cab.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for c in (COL_OS, COL_DATA, COL_VEICULO, COL_STATUS, COL_TOTAL):
            cab.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_CLIENTE, QHeaderView.ResizeMode.Stretch)
        cab.setSectionResizeMode(COL_SERVICO, QHeaderView.ResizeMode.Stretch)

        self._lbl_vazio = QLabel("Nenhuma ordem de serviço encontrada.")
        self._lbl_vazio.setObjectName("vazio")
        self._lbl_vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_vazio.hide()
        self._lbl_total = QLabel()
        self._lbl_total.setObjectName("rodape")
        self._lbl_feedback = QLabel()
        self._lbl_feedback.setObjectName("feedbackOk")
        rodape = QHBoxLayout()
        rodape.addWidget(self._lbl_total)
        rodape.addSpacing(16)
        rodape.addWidget(self._lbl_feedback, stretch=1)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(14)
        raiz.addLayout(cabecalho)
        raiz.addLayout(filtros)
        raiz.addWidget(self._tabela, stretch=1)
        raiz.addWidget(self._lbl_vazio, stretch=1)
        raiz.addLayout(rodape)

    def _conectar_sinais(self) -> None:
        self._btn_nova.clicked.connect(self._nova)
        self._btn_abrir.clicked.connect(self._abrir)
        self._btn_status.clicked.connect(self._menu_status)
        self._btn_excluir.clicked.connect(self._excluir)
        self._tabela.itemSelectionChanged.connect(self._atualizar_botoes)
        self._tabela.itemDoubleClicked.connect(lambda _i: self._abrir())
        self._busca.textChanged.connect(lambda _t: self._timer_busca.start())
        self._timer_busca.timeout.connect(self.recarregar)
        self._filtro.currentIndexChanged.connect(lambda _i: self.recarregar())
        self._timer_feedback.timeout.connect(lambda: self._lbl_feedback.setText(""))

    # ------------------------------------------------------------------
    def showEvent(self, evento) -> None:  # noqa: N802
        super().showEvent(evento)
        self.recarregar()

    def recarregar(self, selecionar: Optional[int] = None) -> None:
        try:
            self._dtos = self._controller.listar(self._busca.text(), self._filtro.currentData())
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível carregar as ordens de serviço.")
            return
        self._preencher(selecionar)

    def _preencher(self, selecionar: Optional[int]) -> None:
        self._tabela.blockSignals(True)
        self._tabela.setRowCount(len(self._dtos))
        linha_sel = -1
        for linha, o in enumerate(self._dtos):
            valores = [
                f"#{o.id_ordem_servico}",
                o.criado_em.strftime("%d/%m/%Y"),
                o.nome_cliente,
                f"{o.placa} – {o.modelo}",
                o.tipo_servico or "—",
                o.status.rotulo,
                formatar_moeda(o.valor_total),
            ]
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == COL_STATUS:
                    item.setForeground(QBrush(QColor(_COR_STATUS[o.status])))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif coluna == COL_TOTAL:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._tabela.setItem(linha, coluna, item)
            if selecionar == o.id_ordem_servico:
                linha_sel = linha
        self._tabela.blockSignals(False)
        if linha_sel >= 0:
            self._tabela.selectRow(linha_sel)
        else:
            self._tabela.clearSelection()
        self._atualizar_botoes()

        tem = bool(self._dtos)
        self._tabela.setVisible(tem)
        self._lbl_vazio.setVisible(not tem)
        soma = sum((o.valor_total for o in self._dtos), Decimal("0"))
        n = len(self._dtos)
        texto = "1 ordem de serviço" if n == 1 else f"{n} ordens de serviço"
        self._lbl_total.setText(f"{texto}  •  total listado: {formatar_moeda(soma)}" if n else texto)

    def _selecionada(self) -> Optional[OrdemServicoDTO]:
        linha = self._tabela.currentRow()
        if linha < 0 or not self._tabela.selectedItems() or linha >= len(self._dtos):
            return None
        return self._dtos[linha]

    def _atualizar_botoes(self) -> None:
        o = self._selecionada()
        self._btn_abrir.setEnabled(o is not None)
        self._btn_abrir.setText("Editar" if o is not None and o.status.editavel else "Abrir")
        self._btn_status.setEnabled(o is not None and bool(o.transicoes))
        self._btn_excluir.setEnabled(o is not None and o.status is StatusOrdemServico.ORCAMENTO)

    def _mostrar_feedback(self, texto: str) -> None:
        self._lbl_feedback.setText(texto)
        self._timer_feedback.start()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _nova(self) -> None:
        d = OrdemServicoDialog(self._controller, parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self._busca.blockSignals(True)
            self._filtro.blockSignals(True)
            self._busca.clear()
            self._filtro.setCurrentIndex(0)
            self._busca.blockSignals(False)
            self._filtro.blockSignals(False)
            self.recarregar(d.resultado.id_ordem_servico)
            self._mostrar_feedback(f"OS #{d.resultado.id_ordem_servico} criada.")

    def _abrir(self) -> None:
        o = self._selecionada()
        if o is None:
            return
        try:
            atual = self._controller.obter(o.id_ordem_servico)  # leitura fresca
        except ErroDeNegocio as exc:
            aviso(self, "Ordem de serviço", str(exc))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível abrir a ordem de serviço.")
            return
        d = OrdemServicoDialog(self._controller, atual, parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self.recarregar(d.resultado.id_ordem_servico)
            self._mostrar_feedback(f"OS #{d.resultado.id_ordem_servico} atualizada.")

    def _menu_status(self) -> None:
        o = self._selecionada()
        if o is None:
            return
        menu = QMenu(self)
        # Guardamos a ligação ação -> situação em Python (não em QAction.setData):
        # assim não depende de como o Qt devolve o enum, em nenhuma versão/sistema.
        destinos = {}
        for destino in o.transicoes:
            destinos[menu.addAction(destino.rotulo)] = destino
        escolhida = menu.exec(self._btn_status.mapToGlobal(self._btn_status.rect().bottomLeft()))
        if escolhida is None or escolhida not in destinos:
            return
        try:
            self._mudar_status(o, destinos[escolhida])
        except Exception as erro:  # noqa: BLE001  (nunca falhar em silêncio dentro de um slot)
            erro_inesperado(self, erro, "Não foi possível alterar a situação da OS.")

    def _mudar_status(self, o: OrdemServicoDTO, destino: StatusOrdemServico) -> None:
        destino = StatusOrdemServico(destino)
        if o.status is StatusOrdemServico.ORCAMENTO and destino is StatusOrdemServico.ANDAMENTO:
            texto = "As peças da OS vão sair do estoque agora."
        elif destino is StatusOrdemServico.ORCAMENTO:
            texto = "As peças da OS voltam para o estoque."
        elif destino is StatusOrdemServico.ENTREGUE:
            texto = "Isto marca o pagamento e a entrega do veículo. Depois não há como voltar."
        elif destino in (StatusOrdemServico.PRONTO, StatusOrdemServico.AGUARDANDO_PAGAMENTO) \
                and o.status.editavel:
            texto = "A partir daí peças e valores ficam travados para edição."
        else:
            texto = ""
        if texto and not confirmar(
            self, "Alterar situação",
            f"Passar a OS #{o.id_ordem_servico} para “{destino.rotulo}”?\n\n{texto}",
            "Confirmar",
        ):
            return
        try:
            novo = self._controller.alterar_status(o.id_ordem_servico, destino)
        except ErroDeNegocio as exc:
            aviso(self, "Não foi possível alterar a situação", str(exc))
            self.recarregar(o.id_ordem_servico)
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível alterar a situação da OS.")
            return
        self.recarregar(novo.id_ordem_servico)
        self._mostrar_feedback(f"OS #{novo.id_ordem_servico}: {novo.status.rotulo}.")

    def _excluir(self) -> None:
        o = self._selecionada()
        if o is None:
            return
        if not confirmar(
            self, "Excluir ordem de serviço",
            f"Excluir o orçamento #{o.id_ordem_servico} de {o.nome_cliente}?\nEsta ação não pode ser desfeita.",
            "Excluir",
        ):
            return
        try:
            self._controller.excluir(o.id_ordem_servico)
        except ErroDeNegocio as exc:
            aviso(self, "Não foi possível excluir", str(exc))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível excluir a ordem de serviço.")
            return
        self.recarregar()
        self._mostrar_feedback(f"Orçamento #{o.id_ordem_servico} excluído.")
