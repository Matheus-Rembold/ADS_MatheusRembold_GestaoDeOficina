"""
Janela de cadastro/edição de produto (RF03).

Mesma decisão de usabilidade dos outros diálogos: a janela NÃO fecha quando
há erro; os erros aparecem num aviso dentro dela e o usuário corrige sem
perder o que já digitou (Nielsen: ajudar a reconhecer, diagnosticar e se
recuperar de erros).

A quantidade em estoque e o custo NÃO são editáveis aqui: na edição aparecem
só como informação, porque quem os altera é a movimentação de estoque (RF09).

Preço de venda (Nielsen):
- Visibilidade do estado do sistema: a caixa "Calcular automaticamente" deixa
  claro se o preço acompanha as compras ou foi definido à mão; a margem
  sobre o custo é recalculada enquanto o usuário digita e fica vermelha
  (com o texto "abaixo do custo") se for negativa.
- Controle e liberdade do usuário: dá para definir o preço à mão e voltar
  ao automático a qualquer momento.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.apresentacao.componentes import (
    converter_valor,
    destacar,
    formatar_moeda,
    formatar_percentual,
)
from src.controle.produto_controller import (
    MARKUP_PADRAO,
    ErroDeNegocio,
    ProdutoController,
    ProdutoDTO,
    ValidacaoError,
    calcular_preco_venda,
    margem_sobre_custo,
)

logger = logging.getLogger(__name__)


def _texto_valor(valor: Optional[Decimal]) -> str:
    """Decimal('60.00') -> '60,00' (para pôr num campo editável)."""
    return "" if valor is None else f"{valor:.2f}".replace(".", ",")


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
        self._custo: Optional[Decimal] = produto.valor_unitario if produto else None
        self.resultado: Optional[ProdutoDTO] = None  # preenchido após salvar com sucesso

        self.setWindowTitle("Editar produto" if produto else "Novo produto")
        self.setModal(True)
        self.setMinimumWidth(520)

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

        # ---- preço de venda ----
        percentual = formatar_percentual(MARKUP_PADRAO).replace(",0%", "%")
        self._automatico = QCheckBox(f"Calcular automaticamente (custo + {percentual})")
        self._preco = QLineEdit()
        self._preco.setPlaceholderText("0,00")
        self._margem = QLabel()
        self._margem.setObjectName("margem")
        self._margem.setWordWrap(True)

        if produto is not None:
            self._nome.setText(produto.nome)
            self._categoria.setText(produto.categoria or "")
            self._prateleira.setText(produto.prateleira or "")
            self._minimo.setText(str(produto.quantidade_minima))
            self._automatico.setChecked(not produto.preco_venda_manual)
            self._preco.setText(_texto_valor(produto.preco_venda))
        else:
            self._automatico.setChecked(True)

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Nome *", self._nome)
        formulario.addRow("Categoria", self._categoria)
        formulario.addRow("Prateleira", self._prateleira)
        formulario.addRow("Qtd. mínima", self._minimo)
        if produto is not None:
            formulario.addRow("Em estoque", QLabel(str(produto.quantidade)))
        # Só leitura: quem atualiza o custo é o registro de uma compra no Estoque (RF09).
        custo = "—  (nenhuma compra registrada)" if self._custo is None else (
            formatar_moeda(self._custo) + "  (por unidade; vem da última compra)"
        )
        formulario.addRow("Custo", QLabel(custo))
        formulario.addRow("", self._automatico)
        formulario.addRow("Preço de venda (R$)", self._preco)
        formulario.addRow("Margem", self._margem)

        dica = QLabel(
            "* campo obrigatório. A quantidade em estoque e o custo são atualizados pelas "
            "movimentações de estoque; a quantidade mínima define o alerta de estoque baixo. "
            "No modo automático o preço de venda acompanha cada compra; definido à mão, "
            "ele é mantido e a compra só avisa o novo valor sugerido."
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

        self._automatico.toggled.connect(self._aplicar_modo_preco)
        self._preco.textChanged.connect(lambda _t: self._atualizar_margem())
        self._aplicar_modo_preco()
        self._nome.setFocus()

    # ------------------------------------------------------------------
    # Preço de venda
    # ------------------------------------------------------------------
    def _aplicar_modo_preco(self) -> None:
        """Automático: campo travado mostrando custo + markup. Manual: campo livre."""
        automatico = self._automatico.isChecked()
        self._preco.setReadOnly(automatico)
        if automatico:
            sugerido = calcular_preco_venda(self._custo)
            self._preco.setText(_texto_valor(sugerido))
            self._preco.setPlaceholderText("definido na primeira compra")
        else:
            self._preco.setPlaceholderText("0,00")
            self._preco.setFocus()
            self._preco.selectAll()
        self._atualizar_margem()

    def _preco_digitado(self) -> Optional[Decimal]:
        try:
            return converter_valor(self._preco.text())
        except InvalidOperation:
            return None

    def _atualizar_margem(self) -> None:
        preco = self._preco_digitado()
        margem = margem_sobre_custo(preco, self._custo)
        if self._custo is None:
            texto = "—  (sem custo: registre uma compra para calcular)"
        elif preco is None:
            texto = "—"
        elif margem is None:
            texto = "—  (custo zero)"
        else:
            lucro = preco - self._custo
            texto = f"{formatar_percentual(margem)} sobre o custo  ({formatar_moeda(lucro)} por unidade)"
            if margem < 0:
                texto += "  — abaixo do custo"
        self._margem.setText(texto)
        destacar(self._margem, "negativa", margem is not None and margem < 0)

    # ------------------------------------------------------------------
    def _salvar(self) -> None:
        self._mostrar_erros([])

        manual = not self._automatico.isChecked()
        preco = None
        if manual:
            try:
                preco = converter_valor(self._preco.text())
            except InvalidOperation:
                self._mostrar_erros(["O preço de venda é inválido. Use números, por exemplo 89,90."])
                return

        texto_minimo = self._minimo.text().strip()
        minimo = int(texto_minimo) if texto_minimo else 0
        dados = (self._nome.text(), self._categoria.text(), self._prateleira.text(), minimo)

        try:
            if self._produto is None:
                self.resultado = self._controller.cadastrar(*dados, manual, preco)
            else:
                self.resultado = self._controller.atualizar(self._produto.id_produto, *dados, manual, preco)
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
