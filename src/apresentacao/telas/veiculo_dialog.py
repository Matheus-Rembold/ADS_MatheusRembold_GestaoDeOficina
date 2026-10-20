"""
Janela de cadastro/edição de veículo (RF02 - HU04 e HU06).

Mesma decisão de usabilidade do ClienteDialog: a janela NÃO fecha quando há
erro; os erros aparecem num aviso dentro dela e o usuário corrige sem perder
o que já digitou (Nielsen: ajudar a reconhecer, diagnosticar e se recuperar).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.controle.veiculo_controller import (
    ErroDeNegocio,
    ValidacaoError,
    VeiculoController,
    VeiculoDTO,
)

logger = logging.getLogger(__name__)


def _mascara_placa(texto: str) -> str:
    """Maiúsculas, sem símbolos, até 7 caracteres; põe o hífen só no padrão antigo."""
    t = "".join(ch for ch in texto if ch.isalnum()).upper()[:7]
    # Padrão antigo tem 4 dígitos seguidos (ABC1234); Mercosul tem letra na 5ª posição.
    if len(t) > 3 and t[3:].isdigit() and (len(t) < 5 or t[4].isdigit()):
        return f"{t[:3]}-{t[3:]}"
    return t


class VeiculoDialog(QDialog):
    def __init__(
        self,
        controller: VeiculoController,
        veiculo: Optional[VeiculoDTO] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._veiculo = veiculo
        self.resultado: Optional[VeiculoDTO] = None  # preenchido após salvar com sucesso

        self.setWindowTitle("Editar veículo" if veiculo else "Novo veículo")
        self.setModal(True)
        self.setMinimumWidth(480)

        # --- Cliente: guardamos o ID no item (userData), nunca o texto ---
        self._cliente = QComboBox()
        self._carregar_clientes()

        self._placa = QLineEdit()
        self._placa.setMaxLength(8)
        self._placa.setPlaceholderText("ABC-1234 ou ABC1D23")
        self._placa.textEdited.connect(lambda t: self._placa.setText(_mascara_placa(t)))

        self._modelo = QLineEdit()
        self._modelo.setMaxLength(100)
        self._modelo.setPlaceholderText("Ex.: Camaro SS")

        self._marca = QLineEdit()
        self._marca.setMaxLength(100)
        self._marca.setPlaceholderText("Ex.: Chevrolet")

        self._ano = QLineEdit()
        self._ano.setValidator(QIntValidator(1900, date.today().year + 1, self))
        self._ano.setMaxLength(4)
        self._ano.setPlaceholderText("Opcional")

        self._motor = QLineEdit()
        self._motor.setMaxLength(50)
        self._motor.setPlaceholderText("Opcional. Ex.: 2.0 Turbo")

        if veiculo is not None:
            indice = self._cliente.findData(veiculo.id_cliente)
            if indice >= 0:
                self._cliente.setCurrentIndex(indice)
            self._placa.setText(_mascara_placa(veiculo.placa))
            self._modelo.setText(veiculo.modelo)
            self._marca.setText(veiculo.marca)
            self._ano.setText("" if veiculo.ano is None else str(veiculo.ano))
            self._motor.setText(veiculo.motor or "")

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Cliente *", self._cliente)
        formulario.addRow("Placa *", self._placa)
        formulario.addRow("Modelo *", self._modelo)
        formulario.addRow("Marca *", self._marca)
        formulario.addRow("Ano", self._ano)
        formulario.addRow("Motor", self._motor)

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

        self._placa.setFocus() if veiculo is None else self._modelo.setFocus()

    # ------------------------------------------------------------------
    def _carregar_clientes(self) -> None:
        try:
            clientes = self._controller.listar_clientes()
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao carregar a lista de clientes")
            clientes = []
        # Item vazio no início: obriga o usuário a escolher (prevenção de erro).
        self._cliente.addItem("Selecione o cliente…", None)
        for c in clientes:
            self._cliente.addItem(f"{c.nome}  —  {c.cpf}", c.id_cliente)

    def _salvar(self) -> None:
        self._mostrar_erros([])

        texto_ano = self._ano.text().strip()
        ano = int(texto_ano) if texto_ano else None
        dados = (
            self._cliente.currentData(),
            self._modelo.text(),
            self._marca.text(),
            self._placa.text(),
            ano,
            self._motor.text(),
        )

        try:
            if self._veiculo is None:
                self.resultado = self._controller.cadastrar(*dados)
            else:
                self.resultado = self._controller.atualizar(self._veiculo.id_veiculo, *dados)
        except ValidacaoError as exc:
            self._mostrar_erros(exc.erros)
        except ErroDeNegocio as exc:
            self._mostrar_erros([str(exc)])
        except Exception:
            logger.exception("Falha inesperada ao salvar veículo")
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
