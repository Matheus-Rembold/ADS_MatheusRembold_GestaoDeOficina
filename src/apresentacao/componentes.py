"""
Componentes de interface reutilizáveis por todas as telas.

As caixas de mensagem são montadas com botões em português de forma
explícita (os botões padrão do Qt aparecem em inglês se não houver
tradução instalada).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from PyQt6.QtWidgets import QMessageBox, QWidget

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


def converter_valor(texto: str) -> Optional[Decimal]:
    """'1.234,56' ou '1234.56' -> Decimal('1234.56'). Vazio -> None.
    Levanta decimal.InvalidOperation se o texto não for número."""
    t = texto.strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:  # formato brasileiro: ponto separa milhar, vírgula separa centavos
        t = t.replace(".", "").replace(",", ".")
    return Decimal(t)
