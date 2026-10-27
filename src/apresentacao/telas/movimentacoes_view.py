"""
Tela de Estoque (RF09): consulta das movimentações e registro de novas.

Decisões de usabilidade (Nielsen, RNF01):
- Visibilidade do estado do sistema: o sinal (+/−) da quantidade aparece em
  texto, não só em cor; o rodapé resume o período filtrado (compras e vendas
  avulsas), útil para o fechamento do mês.
- Prevenção de erros: não há botões de editar/excluir. A movimentação é um
  registro histórico; o erro se corrige com um novo lançamento de ajuste.
- Reconhecimento em vez de memorização: busca imediata enquanto digita e
  filtros por tipo e por período.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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

from src.apresentacao.componentes import erro_inesperado
from src.apresentacao.telas.movimentacao_dialog import MovimentacaoDialog
from src.apresentacao.tema import ERRO, SUCESSO
from src.controle.movimentacao_estoque_controller import (
    MovimentacaoDTO,
    MovimentacaoEstoqueController,
    TipoMovimentacao,
)

COLUNAS = ["Data", "Produto", "Tipo", "Quantidade", "Valor", "Fornecedor", "Observação"]
COL_DATA, COL_PRODUTO, COL_TIPO, COL_QTD, COL_VALOR, COL_FORNECEDOR, COL_OBS = range(7)

PERIODOS = ["Todo o período", "Este mês", "Mês passado", "Últimos 30 dias"]


def formatar_moeda(valor: Optional[Decimal]) -> str:
    """Decimal('1250.9') -> 'R$ 1.250,90' (formato brasileiro)."""
    if valor is None:
        return "—"
    texto = f"{valor:,.2f}"  # 1,250.90
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def intervalo_do_periodo(periodo: str, hoje: Optional[date] = None) -> Tuple[Optional[date], Optional[date]]:
    """Converte a opção do filtro em (data_inicio, data_fim); (None, None) = sem filtro."""
    hoje = hoje or date.today()
    primeiro_deste_mes = hoje.replace(day=1)
    if periodo == "Este mês":
        return primeiro_deste_mes, hoje
    if periodo == "Mês passado":
        ultimo_mes_passado = primeiro_deste_mes - timedelta(days=1)
        return ultimo_mes_passado.replace(day=1), ultimo_mes_passado
    if periodo == "Últimos 30 dias":
        return hoje - timedelta(days=30), hoje
    return None, None


class MovimentacoesView(QWidget):
    def __init__(self, controller: Optional[MovimentacaoEstoqueController] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagina")
        self._controller = controller or MovimentacaoEstoqueController()

        # Espera o usuário parar de digitar antes de consultar o banco.
        self._timer_busca = QTimer(self, singleShot=True, interval=250)
        self._timer_feedback = QTimer(self, singleShot=True, interval=5000)

        self._montar_interface()
        self._conectar_sinais()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------
    def _montar_interface(self) -> None:
        titulo = QLabel("Estoque")
        titulo.setObjectName("titulo")
        subtitulo = QLabel(
            "Movimentações de estoque: compras, doações, devoluções, vendas avulsas e ajustes"
        )
        subtitulo.setObjectName("subtitulo")
        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        bloco_titulo.addWidget(titulo)
        bloco_titulo.addWidget(subtitulo)

        self._btn_novo = QPushButton("+  Nova movimentação")
        self._btn_novo.setObjectName("primario")

        cabecalho = QHBoxLayout()
        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch(1)
        cabecalho.addWidget(self._btn_novo, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("Buscar por produto, fornecedor ou observação…")
        self._busca.setClearButtonEnabled(True)

        self._filtro_tipo = QComboBox()
        self._filtro_tipo.addItem("Todos os tipos", None)
        for tipo in TipoMovimentacao:
            self._filtro_tipo.addItem(tipo.rotulo, tipo)

        self._filtro_periodo = QComboBox()
        self._filtro_periodo.addItems(PERIODOS)

        filtros = QHBoxLayout()
        filtros.addWidget(self._busca, stretch=1)
        filtros.addWidget(self._filtro_tipo)
        filtros.addWidget(self._filtro_periodo)

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
        self._tabela.horizontalHeaderItem(COL_QTD).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tabela.horizontalHeaderItem(COL_VALOR).setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        # O nome do produto ocupa o que precisar (não é cortado); a observação,
        # que costuma ser o texto mais longo, ocupa o espaço que sobrar.
        for coluna in (COL_DATA, COL_PRODUTO, COL_TIPO, COL_QTD, COL_VALOR, COL_FORNECEDOR):
            cab.setSectionResizeMode(coluna, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_OBS, QHeaderView.ResizeMode.Stretch)

        self._lbl_vazio = QLabel("Nenhuma movimentação encontrada.")
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
        rodape.addWidget(self._lbl_feedback, stretch=1)  # ocupa o espaço livre: texto nunca é cortado

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(14)
        raiz.addLayout(cabecalho)
        raiz.addLayout(filtros)
        raiz.addWidget(self._tabela, stretch=1)
        raiz.addWidget(self._lbl_vazio, stretch=1)
        raiz.addLayout(rodape)

    def _conectar_sinais(self) -> None:
        self._btn_novo.clicked.connect(self._nova)
        self._busca.textChanged.connect(lambda _texto: self._timer_busca.start())
        self._timer_busca.timeout.connect(self.recarregar)
        self._filtro_tipo.currentIndexChanged.connect(lambda _i: self.recarregar())
        self._filtro_periodo.currentIndexChanged.connect(lambda _i: self.recarregar())
        self._timer_feedback.timeout.connect(lambda: self._lbl_feedback.setText(""))

    # ------------------------------------------------------------------
    # Dados
    # ------------------------------------------------------------------
    def showEvent(self, evento) -> None:  # noqa: N802 (nome imposto pelo Qt)
        """Recarrega sempre que a tela aparece (os dados podem ter mudado)."""
        super().showEvent(evento)
        self.recarregar()

    def recarregar(self) -> None:
        inicio, fim = intervalo_do_periodo(self._filtro_periodo.currentText())
        try:
            movimentacoes = self._controller.listar(
                self._busca.text(), self._filtro_tipo.currentData(), inicio, fim
            )
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível carregar as movimentações.")
            return
        self._preencher_tabela(movimentacoes)

    def _preencher_tabela(self, movimentacoes: List[MovimentacaoDTO]) -> None:
        self._tabela.setRowCount(len(movimentacoes))
        for linha, m in enumerate(movimentacoes):
            sinal = f"{m.quantidade:+d}".replace("-", "−")  # −4 em vez de -4
            valores = [
                m.data_movimentacao.strftime("%d/%m/%Y"),
                m.nome_produto,
                m.tipo.rotulo,
                sinal,
                formatar_moeda(m.valor),
                m.fornecedor or "—",
                m.observacao or "—",
            ]
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == COL_QTD:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    # O sinal já informa; cor e negrito só reforçam.
                    item.setForeground(QBrush(QColor(SUCESSO if m.quantidade > 0 else ERRO)))
                    fonte = QFont(item.font())
                    fonte.setBold(True)
                    item.setFont(fonte)
                elif coluna == COL_VALOR:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                elif coluna == COL_OBS and m.observacao:
                    item.setToolTip(m.observacao)  # texto longo aparece inteiro ao passar o mouse
                self._tabela.setItem(linha, coluna, item)

        tem_dados = bool(movimentacoes)
        self._tabela.setVisible(tem_dados)
        self._lbl_vazio.setVisible(not tem_dados)

        total = "1 movimentação" if len(movimentacoes) == 1 else f"{len(movimentacoes)} movimentações"
        compras = sum((m.valor for m in movimentacoes
                       if m.tipo is TipoMovimentacao.COMPRA and m.valor is not None), Decimal("0"))
        vendas = sum((m.valor for m in movimentacoes
                      if m.tipo is TipoMovimentacao.VENDA_AVULSA and m.valor is not None), Decimal("0"))
        partes = [total]
        if compras:
            partes.append(f"compras: {formatar_moeda(compras)}")
        if vendas:
            partes.append(f"vendas avulsas: {formatar_moeda(vendas)}")
        self._lbl_total.setText("  •  ".join(partes))

    def _mostrar_feedback(self, texto: str) -> None:
        self._lbl_feedback.setText(texto)
        self._timer_feedback.start()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _nova(self) -> None:
        dialogo = MovimentacaoDialog(self._controller, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.resultado:
            # Limpa os filtros, senão a movimentação nova poderia ficar escondida por eles.
            for campo in (self._busca, self._filtro_tipo, self._filtro_periodo):
                campo.blockSignals(True)
            self._busca.clear()
            self._filtro_tipo.setCurrentIndex(0)
            self._filtro_periodo.setCurrentIndex(0)
            for campo in (self._busca, self._filtro_tipo, self._filtro_periodo):
                campo.blockSignals(False)
            self.recarregar()
            r = dialogo.resultado
            sinal = f"{r.quantidade:+d}".replace("-", "−")
            self._mostrar_feedback(f"{r.tipo.rotulo} de “{r.nome_produto}” registrada ({sinal}).")
