"""
Janela de nova movimentação de estoque (RF09).

Decisões de usabilidade (Nielsen):
- Prevenção de erros: os campos que o tipo escolhido NÃO usa ficam desabilitados
  e os obrigatórios ganham "*"; a data não aceita dia futuro.
- Visibilidade do estado do sistema: uma linha de "saldo atual → saldo após"
  mostra o efeito ANTES de salvar, e fica vermelha se o saldo ficaria negativo.
- Ajuda para reconhecer, diagnosticar e se recuperar de erros: a janela não
  fecha quando há erro; os erros aparecem nela e nada do que foi digitado se perde.

O ajuste não pede "quantidade a somar ou subtrair": o usuário informa a
quantidade CONTADA na prateleira e o sistema calcula a diferença.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.controle.movimentacao_estoque_controller import (
    ErroDeNegocio,
    MovimentacaoDTO,
    MovimentacaoEstoqueController,
    ProdutoOpcaoDTO,
    TipoMovimentacao,
    ValidacaoError,
)

logger = logging.getLogger(__name__)

# Por tipo: rótulos dos campos e quais campos ficam ativos.
# "o" = obrigatório | "p" = opcional | "-" = não usa
CONFIG: Dict[TipoMovimentacao, dict] = {
    TipoMovimentacao.COMPRA: {
        "qtd": "Quantidade comprada", "valor": ("Valor pago (R$)", "o"),
        "forn": ("Fornecedor", "o"), "obs": ("Observação", "p"),
        "dica": "Entrada de peças compradas. O estoque aumenta.",
    },
    TipoMovimentacao.DOACAO: {
        "qtd": "Quantidade recebida", "valor": ("Valor", "-"),
        "forn": ("Doador", "p"), "obs": ("Observação", "p"),
        "dica": "Peças recebidas sem custo. O estoque aumenta.",
    },
    TipoMovimentacao.DEVOLUCAO_FORNECEDOR: {
        "qtd": "Quantidade devolvida", "valor": ("Valor ressarcido (R$)", "p"),
        "forn": ("Fornecedor", "o"), "obs": ("Observação", "p"),
        "dica": "Peças devolvidas pela oficina ao fornecedor. O estoque diminui.",
    },
    TipoMovimentacao.VENDA_AVULSA: {
        "qtd": "Quantidade vendida", "valor": ("Valor recebido (R$)", "o"),
        "forn": ("Fornecedor", "-"), "obs": ("Observação", "p"),
        "dica": "Venda de peças fora de uma ordem de serviço. O estoque diminui.",
    },
    TipoMovimentacao.AJUSTE: {
        "qtd": "Quantidade contada", "valor": ("Valor", "-"),
        "forn": ("Fornecedor", "-"), "obs": ("Justificativa", "o"),
        "dica": "Iguala o estoque do sistema à contagem física. Informe quanto você CONTOU.",
    },
}


def _converter_valor(texto: str) -> Optional[Decimal]:
    """'1.234,56' ou '1234.56' -> Decimal('1234.56'). Vazio -> None."""
    t = texto.strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:  # formato brasileiro: ponto separa milhar, vírgula separa centavos
        t = t.replace(".", "").replace(",", ".")
    return Decimal(t)  # pode levantar InvalidOperation


class MovimentacaoDialog(QDialog):
    def __init__(self, controller: MovimentacaoEstoqueController, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.resultado: Optional[MovimentacaoDTO] = None  # preenchido após salvar com sucesso
        self._produtos: Dict[int, ProdutoOpcaoDTO] = {}

        self.setWindowTitle("Nova movimentação de estoque")
        self.setModal(True)
        self.setMinimumWidth(520)

        self._produto = QComboBox()
        self._carregar_produtos()

        self._tipo = QComboBox()
        for tipo in TipoMovimentacao:
            self._tipo.addItem(tipo.rotulo, tipo)

        self._data = QDateEdit(QDate.currentDate())
        self._data.setCalendarPopup(True)
        self._data.setDisplayFormat("dd/MM/yyyy")
        self._data.setMaximumDate(QDate.currentDate())  # não aceita data futura

        self._quantidade = QLineEdit()
        self._quantidade.setValidator(QIntValidator(0, 1_000_000, self))
        self._valor = QLineEdit()
        self._valor.setPlaceholderText("0,00")
        self._fornecedor = QLineEdit()
        self._fornecedor.setMaxLength(150)
        self._observacao = QLineEdit()
        self._observacao.setMaxLength(500)

        self._rot_qtd, self._rot_valor = QLabel(), QLabel()
        self._rot_forn, self._rot_obs = QLabel(), QLabel()

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Produto *", self._produto)
        formulario.addRow("Tipo *", self._tipo)
        formulario.addRow("Data *", self._data)
        formulario.addRow(self._rot_qtd, self._quantidade)
        formulario.addRow(self._rot_valor, self._valor)
        formulario.addRow(self._rot_forn, self._fornecedor)
        formulario.addRow(self._rot_obs, self._observacao)

        self._dica = QLabel()
        self._dica.setObjectName("subtitulo")
        self._dica.setWordWrap(True)

        self._efeito = QLabel()  # "Saldo atual: 12  →  após: 17"
        self._efeito.setWordWrap(True)

        self._erro = QLabel()
        self._erro.setObjectName("erroForm")
        self._erro.setWordWrap(True)
        self._erro.setTextFormat(Qt.TextFormat.PlainText)
        self._erro.hide()

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.clicked.connect(self.reject)
        self._botao_salvar = QPushButton("Registrar")
        self._botao_salvar.setObjectName("primario")
        self._botao_salvar.setDefault(True)  # Enter também registra
        self._botao_salvar.clicked.connect(self._salvar)

        botoes = QHBoxLayout()
        botoes.addStretch()
        botoes.addWidget(self._botao_cancelar)
        botoes.addWidget(self._botao_salvar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(formulario)
        layout.addWidget(self._dica)
        layout.addWidget(self._efeito)
        layout.addWidget(QLabel("* campo obrigatório. A movimentação não poderá ser editada nem "
                                "excluída depois; um erro se corrige com um ajuste."))
        layout.itemAt(layout.count() - 1).widget().setObjectName("subtitulo")
        layout.itemAt(layout.count() - 1).widget().setWordWrap(True)
        layout.addWidget(self._erro)
        layout.addLayout(botoes)

        self._tipo.currentIndexChanged.connect(self._aplicar_tipo)
        self._produto.currentIndexChanged.connect(self._atualizar_efeito)
        self._quantidade.textChanged.connect(self._atualizar_efeito)
        self._aplicar_tipo()
        self._produto.setFocus()

    # ------------------------------------------------------------------
    def _carregar_produtos(self) -> None:
        try:
            produtos = self._controller.listar_produtos()
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao carregar a lista de produtos")
            produtos = []
        # Item vazio no início: obriga o usuário a escolher (prevenção de erro).
        self._produto.addItem("Selecione o produto…", None)
        for p in produtos:
            self._produtos[p.id_produto] = p
            self._produto.addItem(f"{p.nome}  —  em estoque: {p.quantidade}", p.id_produto)

    def _tipo_atual(self) -> TipoMovimentacao:
        return self._tipo.currentData()

    def _aplicar_tipo(self) -> None:
        """Ajusta rótulos e habilita só os campos que o tipo usa."""
        cfg = CONFIG[self._tipo_atual()]
        self._rot_qtd.setText(cfg["qtd"] + " *")
        for rotulo, campo, (texto, uso) in (
            (self._rot_valor, self._valor, cfg["valor"]),
            (self._rot_forn, self._fornecedor, cfg["forn"]),
            (self._rot_obs, self._observacao, cfg["obs"]),
        ):
            rotulo.setText(texto + (" *" if uso == "o" else ""))
            campo.setEnabled(uso != "-")
            if uso == "-":
                campo.clear()
        self._dica.setText(cfg["dica"])
        self._atualizar_efeito()

    def _delta_previsto(self) -> Optional[int]:
        """Variação de saldo que a tela prevê (None se ainda não dá para calcular)."""
        id_produto = self._produto.currentData()
        texto = self._quantidade.text().strip()
        if id_produto is None or not texto:
            return None
        quantidade = int(texto)
        tipo = self._tipo_atual()
        if tipo is TipoMovimentacao.AJUSTE:  # quantidade = o que foi CONTADO
            return quantidade - self._produtos[id_produto].quantidade
        return quantidade * tipo.sinal

    def _atualizar_efeito(self) -> None:
        id_produto = self._produto.currentData()
        if id_produto is None:
            self._efeito.setText("")
            return
        atual = self._produtos[id_produto].quantidade
        delta = self._delta_previsto()
        if delta is None:
            self._efeito.setText(f"Saldo atual: {atual}")
            self._efeito.setStyleSheet("")
            return
        depois = atual + delta
        sinal = f"{delta:+d}".replace("-", "−")
        texto = f"Saldo atual: {atual}   {sinal}   →   saldo após: {depois}"
        if depois < 0:
            texto += "   (saldo insuficiente)"
            self._efeito.setStyleSheet("color: #C92A2A; font-weight: 600;")  # cor do tema (ERRO)
        else:
            self._efeito.setStyleSheet("font-weight: 600;")
        self._efeito.setText(texto)

    # ------------------------------------------------------------------
    def _salvar(self) -> None:
        self._mostrar_erros([])

        try:
            valor = _converter_valor(self._valor.text()) if self._valor.isEnabled() else None
        except InvalidOperation:
            self._mostrar_erros(["O valor informado é inválido. Use números, por exemplo 1.250,90."])
            return

        texto_qtd = self._quantidade.text().strip()
        quantidade = int(texto_qtd) if texto_qtd else None
        data_mov: date = self._data.date().toPyDate()
        id_produto = self._produto.currentData()
        tipo = self._tipo_atual()
        fornecedor = self._fornecedor.text() if self._fornecedor.isEnabled() else None
        observacao = self._observacao.text() if self._observacao.isEnabled() else None

        try:
            if tipo is TipoMovimentacao.AJUSTE:
                self.resultado = self._controller.ajustar_para_contagem(
                    id_produto, quantidade, observacao, data_mov
                )
            else:
                self.resultado = self._controller.registrar(
                    id_produto, tipo, quantidade, data_mov, valor, fornecedor, observacao
                )
        except ValidacaoError as exc:
            self._mostrar_erros(exc.erros)
        except ErroDeNegocio as exc:
            self._mostrar_erros([str(exc)])
        except Exception:
            logger.exception("Falha inesperada ao registrar movimentação de estoque")
            self._mostrar_erros(
                ["Não foi possível registrar. Verifique a conexão com o banco de dados e tente novamente."]
            )
        else:
            self.accept()

    def _mostrar_erros(self, erros: List[str]) -> None:
        if erros:
            self._erro.setText("\n".join(f"• {e}" for e in erros))
            self._erro.show()
        else:
            self._erro.clear()
            self._erro.hide()
