"""
Tela de Produtos (RF03): lista, busca, cadastro, edição e exclusão.

Mesmas decisões de usabilidade das telas de Clientes e Veículos (Nielsen):
- Visibilidade do estado do sistema: contador de resultados, mensagem de
  sucesso após cada operação e coluna "Situação" que destaca o estoque baixo
  (quantidade abaixo da mínima, HU09), sem depender só da cor.
- Prevenção de erros: Editar/Excluir ficam desabilitados sem seleção; a
  confirmação de exclusão tem "Cancelar" como padrão.
- Reconhecimento em vez de memorização: busca imediata enquanto digita e
  duplo clique na linha para editar.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont
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
from src.apresentacao.telas.produto_dialog import ProdutoDialog
from src.apresentacao.tema import ERRO
from src.controle.produto_controller import (
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    ProdutoController,
    ProdutoDTO,
)

COLUNAS = ["Nome", "Categoria", "Prateleira", "Estoque", "Mínimo", "Situação"]
COL_NOME, COL_CATEGORIA, COL_PRATELEIRA, COL_ESTOQUE, COL_MINIMO, COL_SITUACAO = range(6)


class ProdutosView(QWidget):
    def __init__(self, controller: Optional[ProdutoController] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagina")
        self._controller = controller or ProdutoController()

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
        titulo = QLabel("Produtos")
        titulo.setObjectName("titulo")
        subtitulo = QLabel("Cadastro e consulta dos produtos e peças da oficina")
        subtitulo.setObjectName("subtitulo")
        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        bloco_titulo.addWidget(titulo)
        bloco_titulo.addWidget(subtitulo)

        self._btn_novo = QPushButton("+  Novo produto")
        self._btn_novo.setObjectName("primario")

        cabecalho = QHBoxLayout()
        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch(1)
        cabecalho.addWidget(self._btn_novo, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("Buscar por nome, categoria ou prateleira…")
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
        for coluna in (COL_ESTOQUE, COL_MINIMO):  # números: título centralizado como os dados
            self._tabela.horizontalHeaderItem(coluna).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        cab.setSectionResizeMode(COL_NOME, QHeaderView.ResizeMode.Stretch)
        cab.setSectionResizeMode(COL_CATEGORIA, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_PRATELEIRA, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_ESTOQUE, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_MINIMO, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_SITUACAO, QHeaderView.ResizeMode.ResizeToContents)

        self._lbl_vazio = QLabel("Nenhum produto encontrado.")
        self._lbl_vazio.setObjectName("vazio")
        self._lbl_vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_vazio.hide()

        self._lbl_total = QLabel()
        self._lbl_total.setObjectName("rodape")
        self._lbl_feedback = QLabel()
        self._lbl_feedback.setObjectName("feedbackOk")

        self._btn_editar = QPushButton("Editar")
        self._btn_excluir = QPushButton("Excluir")
        self._btn_excluir.setObjectName("perigo")

        rodape = QHBoxLayout()
        rodape.addWidget(self._lbl_total)
        rodape.addSpacing(16)
        rodape.addWidget(self._lbl_feedback, stretch=1)  # ocupa o espaço livre: texto nunca é cortado
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
        self._busca.textChanged.connect(lambda _texto: self._timer_busca.start())
        self._timer_busca.timeout.connect(self.recarregar)
        self._timer_feedback.timeout.connect(lambda: self._lbl_feedback.setText(""))
        self._tabela.itemSelectionChanged.connect(self._atualizar_botoes)
        self._tabela.itemDoubleClicked.connect(lambda _item: self._editar())

    # ------------------------------------------------------------------
    # Dados
    # ------------------------------------------------------------------
    def showEvent(self, evento) -> None:  # noqa: N802 (nome imposto pelo Qt)
        """Recarrega sempre que a tela aparece (o estoque pode ter mudado)."""
        super().showEvent(evento)
        self.recarregar()

    def recarregar(self, selecionar_id: Optional[int] = None) -> None:
        if selecionar_id is None:
            selecionar_id = self._id_selecionado()
        try:
            produtos = self._controller.listar(self._busca.text())
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível carregar os produtos.")
            return
        self._preencher_tabela(produtos, selecionar_id)

    def _preencher_tabela(self, produtos: List[ProdutoDTO], selecionar_id: Optional[int]) -> None:
        self._tabela.setRowCount(len(produtos))
        linha_selecionada = -1
        for linha, p in enumerate(produtos):
            valores = [
                p.nome,
                p.categoria or "—",
                p.prateleira or "—",
                str(p.quantidade),
                str(p.quantidade_minima),
                "Estoque baixo" if p.estoque_baixo else "OK",
            ]
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == COL_NOME:
                    item.setData(Qt.ItemDataRole.UserRole, p.id_produto)
                if coluna in (COL_ESTOQUE, COL_MINIMO):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if p.estoque_baixo and coluna in (COL_ESTOQUE, COL_SITUACAO):
                    # O texto "Estoque baixo" já informa; cor e negrito só reforçam.
                    item.setForeground(QBrush(QColor(ERRO)))
                    fonte = QFont(item.font())
                    fonte.setBold(True)
                    item.setFont(fonte)
                self._tabela.setItem(linha, coluna, item)
            if p.id_produto == selecionar_id:
                linha_selecionada = linha

        if linha_selecionada >= 0:
            self._tabela.selectRow(linha_selecionada)
        else:
            self._tabela.clearSelection()

        tem_dados = bool(produtos)
        self._tabela.setVisible(tem_dados)
        self._lbl_vazio.setVisible(not tem_dados)
        baixos = sum(1 for p in produtos if p.estoque_baixo)
        total = "1 produto" if len(produtos) == 1 else f"{len(produtos)} produtos"
        self._lbl_total.setText(total + (f"  •  {baixos} com estoque baixo" if baixos else ""))
        self._atualizar_botoes()

    def _id_selecionado(self) -> Optional[int]:
        linhas = self._tabela.selectionModel().selectedRows() if self._tabela.selectionModel() else []
        if not linhas:
            return None
        return self._tabela.item(linhas[0].row(), COL_NOME).data(Qt.ItemDataRole.UserRole)

    def _atualizar_botoes(self) -> None:
        tem_selecao = self._id_selecionado() is not None
        self._btn_editar.setEnabled(tem_selecao)
        self._btn_excluir.setEnabled(tem_selecao)

    def _mostrar_feedback(self, texto: str) -> None:
        self._lbl_feedback.setText(texto)
        self._timer_feedback.start()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _novo(self) -> None:
        dialogo = ProdutoDialog(self._controller, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.resultado:
            # Limpa a busca, senão o produto novo poderia ficar escondido pelo filtro.
            self._busca.blockSignals(True)
            self._busca.clear()
            self._busca.blockSignals(False)
            self.recarregar(selecionar_id=dialogo.resultado.id_produto)
            self._mostrar_feedback(f"Produto “{dialogo.resultado.nome}” cadastrado com sucesso.")

    def _editar(self) -> None:
        id_produto = self._id_selecionado()
        if id_produto is None:
            return
        try:
            produto = self._controller.obter(id_produto)  # leitura fresca do banco
        except ErroDeNegocio as erro:  # ex.: removido em outra janela
            aviso(self, "Produto indisponível", str(erro))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível abrir o produto.")
            return

        dialogo = ProdutoDialog(self._controller, produto=produto, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.resultado:
            self.recarregar(selecionar_id=dialogo.resultado.id_produto)
            self._mostrar_feedback(f"Produto “{dialogo.resultado.nome}” atualizado com sucesso.")

    def _excluir(self) -> None:
        id_produto = self._id_selecionado()
        if id_produto is None:
            return
        nome = self._tabela.item(self._tabela.currentRow(), COL_NOME).text()

        if not confirmar(
            self,
            "Excluir produto",
            f"Deseja realmente excluir o produto “{nome}”?\nEsta ação não pode ser desfeita.",
            rotulo_confirmar="Excluir",
        ):
            return

        try:
            self._controller.excluir(id_produto)
        except OperacaoNaoPermitidaError as erro:  # a regra de negócio recusou
            aviso(self, "Exclusão não permitida", str(erro))
            return
        except ErroDeNegocio as erro:
            aviso(self, "Não foi possível excluir", str(erro))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível excluir o produto.")
            return

        self.recarregar()
        self._mostrar_feedback(f"Produto “{nome}” excluído.")
