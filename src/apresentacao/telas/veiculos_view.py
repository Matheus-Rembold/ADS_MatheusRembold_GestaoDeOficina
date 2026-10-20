"""
Tela de Veículos (RF02): lista, busca, cadastro, edição, exclusão e histórico.

Mesmas decisões de usabilidade da tela de Clientes (Nielsen, RNF01):
- Visibilidade do estado do sistema: contador de resultados e mensagem de
  sucesso após cada operação.
- Prevenção de erros: Editar/Excluir/Histórico ficam desabilitados sem
  seleção; a confirmação de exclusão tem "Cancelar" como padrão.
- Reconhecimento em vez de memorização: busca imediata enquanto digita e
  duplo clique na linha para editar.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.apresentacao.componentes import aviso, confirmar, erro_inesperado
from src.apresentacao.telas.veiculo_dialog import VeiculoDialog
from src.apresentacao.telas.veiculo_historico_dialog import VeiculoHistoricoDialog
from src.controle.veiculo_controller import (
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    VeiculoController,
    VeiculoDTO,
)

COLUNAS = ["Placa", "Modelo", "Marca", "Ano", "Motor", "Cliente"]
COL_PLACA, COL_MODELO, COL_MARCA, COL_ANO, COL_MOTOR, COL_CLIENTE = range(6)


class VeiculosView(QWidget):
    def __init__(self, controller: Optional[VeiculoController] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagina")
        self._controller = controller or VeiculoController()

        # Espera o usuário parar de digitar antes de consultar o banco.
        self._timer_busca = QTimer(self, singleShot=True, interval=250)
        self._timer_feedback = QTimer(self, singleShot=True, interval=5000)

        self._montar_interface()
        self._conectar_sinais()
        self._atualizar_botoes()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------
    def _montar_interface(self) -> None:
        titulo = QLabel("Veículos")
        titulo.setObjectName("titulo")
        subtitulo = QLabel("Cadastro e consulta dos veículos atendidos pela oficina")
        subtitulo.setObjectName("subtitulo")
        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        bloco_titulo.addWidget(titulo)
        bloco_titulo.addWidget(subtitulo)

        self._btn_novo = QPushButton("+  Novo veículo")
        self._btn_novo.setObjectName("primario")

        cabecalho = QHBoxLayout()
        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch(1)
        cabecalho.addWidget(self._btn_novo, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("Buscar por placa, modelo, marca ou nome do cliente…")
        self._busca.setClearButtonEnabled(True)

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
        cab.setSectionResizeMode(COL_PLACA, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_MODELO, QHeaderView.ResizeMode.Stretch)
        cab.setSectionResizeMode(COL_MARCA, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_ANO, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_MOTOR, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_CLIENTE, QHeaderView.ResizeMode.Stretch)

        self._lbl_vazio = QLabel("Nenhum veículo encontrado.")
        self._lbl_vazio.setObjectName("vazio")
        self._lbl_vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_vazio.hide()

        self._lbl_total = QLabel()
        self._lbl_total.setObjectName("rodape")
        self._lbl_feedback = QLabel()
        self._lbl_feedback.setObjectName("feedbackOk")

        self._btn_historico = QPushButton("Histórico")
        self._btn_editar = QPushButton("Editar")
        self._btn_excluir = QPushButton("Excluir")
        self._btn_excluir.setObjectName("perigo")

        rodape = QHBoxLayout()
        rodape.addWidget(self._lbl_total)
        rodape.addSpacing(16)
        rodape.addWidget(self._lbl_feedback, stretch=1)  # ocupa o espaço livre: texto nunca é cortado
        rodape.addWidget(self._btn_historico)
        rodape.addWidget(self._btn_editar)
        rodape.addWidget(self._btn_excluir)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(14)
        raiz.addLayout(cabecalho)
        raiz.addWidget(self._busca)
        raiz.addWidget(self._tabela, stretch=1)
        raiz.addWidget(self._lbl_vazio, stretch=1)
        raiz.addLayout(rodape)

    def _conectar_sinais(self) -> None:
        self._btn_novo.clicked.connect(self._novo)
        self._btn_editar.clicked.connect(self._editar)
        self._btn_excluir.clicked.connect(self._excluir)
        self._btn_historico.clicked.connect(self._ver_historico)
        self._busca.textChanged.connect(lambda _texto: self._timer_busca.start())
        self._timer_busca.timeout.connect(self.recarregar)
        self._timer_feedback.timeout.connect(lambda: self._lbl_feedback.setText(""))
        self._tabela.itemSelectionChanged.connect(self._atualizar_botoes)
        self._tabela.itemDoubleClicked.connect(lambda _item: self._editar())

    # ------------------------------------------------------------------
    # Dados
    # ------------------------------------------------------------------
    def showEvent(self, evento) -> None:  # noqa: N802 (nome imposto pelo Qt)
        """Recarrega sempre que a tela aparece (dados podem ter mudado)."""
        super().showEvent(evento)
        self.recarregar()

    def recarregar(self, selecionar_id: Optional[int] = None) -> None:
        if selecionar_id is None:
            selecionar_id = self._id_selecionado()
        try:
            veiculos = self._controller.listar(self._busca.text())
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível carregar os veículos.")
            return
        self._preencher_tabela(veiculos, selecionar_id)

    def _preencher_tabela(self, veiculos: List[VeiculoDTO], selecionar_id: Optional[int]) -> None:
        self._tabela.setRowCount(len(veiculos))
        linha_selecionada = -1
        for linha, v in enumerate(veiculos):
            valores = [
                v.placa,
                v.modelo,
                v.marca,
                "—" if v.ano is None else str(v.ano),
                v.motor or "—",
                v.nome_cliente,
            ]
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == COL_PLACA:
                    item.setData(Qt.ItemDataRole.UserRole, v.id_veiculo)
                self._tabela.setItem(linha, coluna, item)
            if v.id_veiculo == selecionar_id:
                linha_selecionada = linha

        if linha_selecionada >= 0:
            self._tabela.selectRow(linha_selecionada)
        else:
            self._tabela.clearSelection()

        tem_dados = bool(veiculos)
        self._tabela.setVisible(tem_dados)
        self._lbl_vazio.setVisible(not tem_dados)
        self._lbl_total.setText(
            "1 veículo" if len(veiculos) == 1 else f"{len(veiculos)} veículos"
        )
        self._atualizar_botoes()

    def _id_selecionado(self) -> Optional[int]:
        linhas = self._tabela.selectionModel().selectedRows() if self._tabela.selectionModel() else []
        if not linhas:
            return None
        return self._tabela.item(linhas[0].row(), COL_PLACA).data(Qt.ItemDataRole.UserRole)

    def _atualizar_botoes(self) -> None:
        tem_selecao = self._id_selecionado() is not None
        self._btn_editar.setEnabled(tem_selecao)
        self._btn_excluir.setEnabled(tem_selecao)
        self._btn_historico.setEnabled(tem_selecao)

    def _mostrar_feedback(self, texto: str) -> None:
        self._lbl_feedback.setText(texto)
        self._timer_feedback.start()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _novo(self) -> None:
        dialogo = VeiculoDialog(self._controller, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.resultado:
            # Limpa a busca, senão o veículo novo poderia ficar escondido pelo filtro.
            self._busca.blockSignals(True)
            self._busca.clear()
            self._busca.blockSignals(False)
            self.recarregar(selecionar_id=dialogo.resultado.id_veiculo)
            self._mostrar_feedback(f"Veículo {dialogo.resultado.placa} cadastrado com sucesso.")

    def _editar(self) -> None:
        id_veiculo = self._id_selecionado()
        if id_veiculo is None:
            return
        try:
            veiculo = self._controller.obter(id_veiculo)  # leitura fresca do banco
        except ErroDeNegocio as erro:  # ex.: removido em outra janela
            aviso(self, "Veículo indisponível", str(erro))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível abrir o veículo.")
            return

        dialogo = VeiculoDialog(self._controller, veiculo=veiculo, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.resultado:
            self.recarregar(selecionar_id=dialogo.resultado.id_veiculo)
            self._mostrar_feedback(f"Veículo {dialogo.resultado.placa} atualizado com sucesso.")

    def _excluir(self) -> None:
        id_veiculo = self._id_selecionado()
        if id_veiculo is None:
            return
        placa = self._tabela.item(self._tabela.currentRow(), COL_PLACA).text()

        if not confirmar(
            self,
            "Excluir veículo",
            f"Deseja realmente excluir o veículo {placa}?\nEsta ação não pode ser desfeita.",
            rotulo_confirmar="Excluir",
        ):
            return

        try:
            self._controller.excluir(id_veiculo)
        except OperacaoNaoPermitidaError as erro:  # a regra de negócio recusou
            aviso(self, "Exclusão não permitida", str(erro))
            return
        except ErroDeNegocio as erro:
            aviso(self, "Não foi possível excluir", str(erro))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível excluir o veículo.")
            return

        self.recarregar()
        self._mostrar_feedback(f"Veículo {placa} excluído.")

    def _ver_historico(self) -> None:
        id_veiculo = self._id_selecionado()
        if id_veiculo is None:
            return
        try:
            veiculo = self._controller.obter(id_veiculo)
            historico = self._controller.historico(id_veiculo)
        except ErroDeNegocio as erro:
            aviso(self, "Veículo indisponível", str(erro))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível carregar o histórico.")
            return
        VeiculoHistoricoDialog(veiculo, historico, parent=self).exec()
