"""
Janela de cadastro/edição de cliente (RF01 - HU01 e HU02).

Decisão de usabilidade: a janela NÃO fecha quando há erro. Os erros
aparecem num aviso dentro dela e o usuário corrige sem perder o que já
digitou (heurística de Nielsen: ajudar o usuário a reconhecer, diagnosticar
e se recuperar de erros).
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

from src.controle.cliente_controller import (
    ClienteController,
    ClienteDTO,
    ErroDeNegocio,
    ValidacaoError,
)

logger = logging.getLogger(__name__)


def _mascara_cpf(texto: str) -> str:
    """Formata enquanto digita: '52998' -> '529.98'; '52998224725' -> '529.982.247-25'."""
    d = "".join(ch for ch in texto if ch.isdigit())[:11]
    saida = d[:3]
    if d[3:6]:
        saida += "." + d[3:6]
    if d[6:9]:
        saida += "." + d[6:9]
    if d[9:11]:
        saida += "-" + d[9:11]
    return saida


class ClienteDialog(QDialog):
    def __init__(
        self,
        controller: ClienteController,
        cliente: Optional[ClienteDTO] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._cliente = cliente
        self.resultado: Optional[ClienteDTO] = None  # preenchido após salvar com sucesso

        self.setWindowTitle("Editar cliente" if cliente else "Novo cliente")
        self.setModal(True)
        self.setMinimumWidth(480)

        self._nome = QLineEdit()
        self._nome.setMaxLength(150)
        self._nome.setPlaceholderText("Nome completo")

        self._cpf = QLineEdit()
        self._cpf.setMaxLength(14)
        self._cpf.setPlaceholderText("000.000.000-00")
        self._cpf.textEdited.connect(lambda t: self._cpf.setText(_mascara_cpf(t)))

        self._contato = QLineEdit()
        self._contato.setMaxLength(20)
        self._contato.setPlaceholderText("(54) 99999-9999")

        self._idade = QLineEdit()
        self._idade.setValidator(QIntValidator(0, 120, self))  # só aceita números
        self._idade.setPlaceholderText("Opcional")

        self._endereco = QLineEdit()
        self._endereco.setMaxLength(255)
        self._endereco.setPlaceholderText("Opcional")

        if cliente is not None:
            self._nome.setText(cliente.nome)
            self._cpf.setText(cliente.cpf)
            self._contato.setText(cliente.contato)
            self._idade.setText("" if cliente.idade is None else str(cliente.idade))
            self._endereco.setText(cliente.endereco or "")

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Nome *", self._nome)
        formulario.addRow("CPF *", self._cpf)
        formulario.addRow("Contato *", self._contato)
        formulario.addRow("Idade", self._idade)
        formulario.addRow("Endereço", self._endereco)

        dica = QLabel("* campo obrigatório")
        dica.setObjectName("subtitulo")

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

        texto_idade = self._idade.text().strip()
        idade = int(texto_idade) if texto_idade else None
        dados = (
            self._nome.text(),
            self._cpf.text(),
            self._contato.text(),
            idade,
            self._endereco.text(),
        )

        try:
            if self._cliente is None:
                self.resultado = self._controller.cadastrar(*dados)
            else:
                self.resultado = self._controller.atualizar(self._cliente.id_cliente, *dados)
        except ValidacaoError as exc:
            self._mostrar_erros(exc.erros)
        except ErroDeNegocio as exc:
            self._mostrar_erros([str(exc)])
        except Exception:
            logger.exception("Falha inesperada ao salvar cliente")
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
