"""
Componentes de interface reutilizáveis por todas as telas.

As caixas de mensagem são montadas com botões em português de forma
explícita (os botões padrão do Qt aparecem em inglês se não houver
tradução instalada).
"""
from __future__ import annotations

import logging
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
