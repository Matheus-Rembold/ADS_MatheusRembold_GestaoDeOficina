"""
Janela de cadastro/edição de produto (RF03).

Mesma decisão de usabilidade dos outros diálogos: a janela NÃO fecha quando
há erro; os erros aparecem num aviso dentro dela e o usuário corrige sem
perder o que já digitou (Nielsen: ajudar a reconhecer, diagnosticar e se
recuperar de erros).

A quantidade em estoque NÃO é editável aqui: na edição ela aparece só como
informação, porque quem a altera é a entrada de estoque (RF09).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.controle.produto_controller import (
    ErroDeNegocio,
    ProdutoController,
    ProdutoDTO,
    ValidacaoError,
)

logger = logging.getLogger(__name__)


class ProdutoDialog(QDialog):
    def __init__(
        self,
        controller: ProdutoController,
        produto: Optional[ProdutoDTO] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._produto = produto
        self.resultado: Optional[ProdutoDTO] = None  # preenchido após salvar com sucesso

        self.setWindowTitle("Editar produto" if produto else "Novo produto")
        self.setModal(True)
        self.setMinimumWidth(480)

        self._nome = QLineEdit()
        self._nome.setMaxLength(150)
        self._nome.setPlaceholderText("Ex.: Filtro de Ar")

        self._categoria = QLineEdit()
        self._categoria.setMaxLength(100)
        self._categoria.setPlaceholderText("Opcional. Ex.: Filtros")

        self._prateleira = QLineEdit()
        self._prateleira.setMaxLength(50)
        self._prateleira.setPlaceholderText("Opcional. Ex.: A2")

        self._minimo = QLineEdit()
        self._minimo.setValidator(QIntValidator(0, 1_000_000, self))  # só aceita números
        self._minimo.setPlaceholderText("0")

        if produto is not None:
            self._nome.setText(produto.nome)
            self._categoria.setText(produto.categoria or "")
            self._prateleira.setText(produto.prateleira or "")
            self._minimo.setText(str(produto.quantidade_minima))

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Nome *", self._nome)
        formulario.addRow("Categoria", self._categoria)
        formulario.addRow("Prateleira", self._prateleira)
        formulario.addRow("Qtd. mínima", self._minimo)
        if produto is not None:
            formulario.addRow("Em estoque", QLabel(str(produto.quantidade)))

        dica = QLabel(
            "* campo obrigatório. A quantidade em estoque é atualizada pelas "
            "entradas de estoque; a quantidade mínima define o alerta de estoque baixo."
        )
        dica.setObjectName("subtitulo")
        dica.setWordWrap(True)

        self._erro = QLabel()
        self._erro.setObjectName("erroForm")
        self._erro.setWordWrap(True)
        self._erro.setTextFormat(Qt.TextFormat.PlainText)
        self._erro.hide()

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.clicked.connect(self.reject)
        self._botao_salvar = QPushButton("Salvar")
        self._botao_salvar.setObjectName("primario")
        self._botao_salvar.setDefault(True)  # Enter também salva
        self._botao_salvar.clicked.connect(self._salvar)

        botoes = QHBoxLayout()
        botoes.addStretch()
        botoes.addWidget(self._botao_cancelar)
        botoes.addWidget(self._botao_salvar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(formulario)
        layout.addWidget(dica)
        layout.addWidget(self._erro)
        layout.addLayout(botoes)

        self._nome.setFocus()

    # ------------------------------------------------------------------
    def _salvar(self) -> None:
        self._mostrar_erros([])

        texto_minimo = self._minimo.text().strip()
        minimo = int(texto_minimo) if texto_minimo else 0
        dados = (self._nome.text(), self._categoria.text(), self._prateleira.text(), minimo)

        try:
            if self._produto is None:
                self.resultado = self._controller.cadastrar(*dados)
            else:
                self.resultado = self._controller.atualizar(self._produto.id_produto, *dados)
        except ValidacaoError as exc:
            self._mostrar_erros(exc.erros)
        except ErroDeNegocio as exc:
            self._mostrar_erros([str(exc)])
        except Exception:
            logger.exception("Falha inesperada ao salvar produto")
            self._mostrar_erros(
                ["Não foi possível salvar. Verifique a conexão com o banco de dados e tente novamente."]
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
