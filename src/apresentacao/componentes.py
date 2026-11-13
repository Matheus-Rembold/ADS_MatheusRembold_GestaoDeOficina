"""
Componentes de interface reutilizáveis por todas as telas.

As caixas de mensagem são montadas com botões em português de forma
explícita (os botões padrão do Qt aparecem em inglês se não houver
tradução instalada).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from decimal import Decimal
from typing import Iterator, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QWidget,
)

log = logging.getLogger(__name__)


def confirmar(
    parent: Optional[QWidget],
    titulo: str,
    texto: str,
    rotulo_confirmar: str = "Confirmar",
    rotulo_cancelar: str = "Cancelar",
) -> bool:
    """Pergunta sim/não. O padrão (Enter) é CANCELAR, para evitar acidentes."""
    caixa = QMessageBox(parent)
    caixa.setIcon(QMessageBox.Icon.Question)
    caixa.setWindowTitle(titulo)
    caixa.setText(texto)
    botao_ok = caixa.addButton(rotulo_confirmar, QMessageBox.ButtonRole.AcceptRole)
    botao_cancelar = caixa.addButton(rotulo_cancelar, QMessageBox.ButtonRole.RejectRole)
    caixa.setDefaultButton(botao_cancelar)
    caixa.exec()
    return caixa.clickedButton() is botao_ok


def aviso(parent: Optional[QWidget], titulo: str, texto: str) -> None:
    """Informa uma regra de negócio que impediu a operação."""
    caixa = QMessageBox(parent)
    caixa.setIcon(QMessageBox.Icon.Warning)
    caixa.setWindowTitle(titulo)
    caixa.setText(texto)
    caixa.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    caixa.exec()


def erro_inesperado(
    parent: Optional[QWidget],
    excecao: BaseException,
    mensagem: str = "Ocorreu um erro inesperado.",
) -> None:
    """Erro de verdade (banco fora do ar, bug...). Registra no log e avisa."""
    log.error("%s", mensagem, exc_info=excecao)
    caixa = QMessageBox(parent)
    caixa.setIcon(QMessageBox.Icon.Critical)
    caixa.setWindowTitle("Erro")
    caixa.setText(mensagem)
    caixa.setInformativeText("Tente novamente. Se o problema continuar, avise o suporte.")
    caixa.setDetailedText(f"{type(excecao).__name__}: {excecao}")
    caixa.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    caixa.exec()


def formatar_moeda(valor: Optional[Decimal]) -> str:
    """Decimal('1250.9') -> 'R$ 1.250,90' (formato brasileiro)."""
    if valor is None:
        return "—"
    texto = f"{valor:,.2f}"  # 1,250.90
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_moeda_com_sinal(valor: Optional[Decimal]) -> str:
    """Decimal('-14.84') -> '−R$ 14,84': o sinal fica visível (não depender só da cor)."""
    if valor is None:
        return "—"
    return ("−" if valor < 0 else "") + formatar_moeda(abs(valor))


def formatar_percentual(fracao: Optional[Decimal]) -> str:
    """Decimal('0.2') -> '20,0%'; Decimal('-0.0833') -> '−8,3%'. None -> '—'."""
    if fracao is None:
        return "—"
    texto = f"{fracao * 100:.1f}".replace(".", ",").replace("-", "−")
    return texto + "%"


def destacar(widget: QWidget, propriedade: str, ligado: bool) -> None:
    """Liga/desliga uma propriedade de estilo do tema (ex.: negativa) e reaplica o QSS."""
    widget.setProperty(propriedade, ligado)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def converter_valor(texto: str) -> Optional[Decimal]:
    """'1.234,56' ou '1234.56' -> Decimal('1234.56'). Vazio -> None.
    Levanta decimal.InvalidOperation se o texto não for número."""
    t = texto.strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:  # formato brasileiro: ponto separa milhar, vírgula separa centavos
        t = t.replace(".", "").replace(",", ".")
    return Decimal(t)


# ----------------------------------------------------------------------
# Tabelas e paginação (09/11/2026)
# ----------------------------------------------------------------------
@contextmanager
def preenchendo_tabela(tabela: QTableWidget) -> Iterator[None]:
    """
    Use em volta de QUALQUER preenchimento de tabela:

        with preenchendo_tabela(self._tabela):
            ... setRowCount / setItem ...

    Por quê: coluna em ResizeToContents faz o Qt recalcular a largura a cada
    setItem, relendo a coluna inteira. Com a tabela já na tela isso tem custo
    quadrático (medido: 1.035 OS levavam 203 s na segunda entrada na tela).
    Aqui o ajuste fica desligado durante o preenchimento e é feito UMA vez no
    fim (as mesmas 1.035 linhas: cerca de 100 ms).
    """
    cabecalho = tabela.horizontalHeader()
    modos = [cabecalho.sectionResizeMode(i) for i in range(cabecalho.count())]
    automatico = QHeaderView.ResizeMode.ResizeToContents
    tabela.setUpdatesEnabled(False)
    for i, modo in enumerate(modos):
        if modo == automatico:
            cabecalho.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
    try:
        yield
    finally:
        for i, modo in enumerate(modos):
            if modo == automatico:
                cabecalho.setSectionResizeMode(i, automatico)
        tabela.setUpdatesEnabled(True)


def _milhar(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def texto_contagem(pagina, singular: str, plural: str) -> str:
    """'55 clientes' quando cabe numa página; 'Mostrando 51–100 de 1.035 clientes' quando não."""
    if pagina.total == 1:
        return f"1 {singular}"
    if pagina.total_paginas == 1:
        return f"{_milhar(pagina.total)} {plural}"
    return f"Mostrando {_milhar(pagina.primeiro)}–{_milhar(pagina.ultimo)} de {_milhar(pagina.total)} {plural}"


class BarraPaginacao(QWidget):
    """
    ‹ Anterior   Página 2 de 21   Próxima ›

    Fica escondida quando tudo cabe numa página (Nielsen: estética e design
    minimalista, sem controle que não serve para nada). Os botões se
    desabilitam na primeira/última página (prevenção de erros) e o texto
    "Página X de Y" mostra onde o usuário está (visibilidade do estado).
    Emite `pagina_pedida(numero)`; quem busca os dados é a tela.
    """

    pagina_pedida = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pagina = 1
        self._anterior = QPushButton("‹ Anterior")
        self._proxima = QPushButton("Próxima ›")
        self._rotulo = QLabel()
        self._rotulo.setObjectName("rodape")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._anterior)
        layout.addWidget(self._rotulo)
        layout.addWidget(self._proxima)
        self._anterior.clicked.connect(lambda: self.pagina_pedida.emit(self._pagina - 1))
        self._proxima.clicked.connect(lambda: self.pagina_pedida.emit(self._pagina + 1))
        self.hide()

    def atualizar(self, pagina) -> None:
        """Recebe a Pagina devolvida pelo controller."""
        self._pagina = pagina.pagina
        self._rotulo.setText(f"Página {pagina.pagina} de {pagina.total_paginas}")
        self._anterior.setEnabled(pagina.tem_anterior)
        self._proxima.setEnabled(pagina.tem_proxima)
        self.setVisible(pagina.total_paginas > 1)
