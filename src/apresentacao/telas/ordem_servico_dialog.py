"""
Janela de nova OS / edição / visualização de OS (RF04).

Decisões de usabilidade (Nielsen):
- Prevenção de erros: o veículo só lista os do cliente escolhido; a quantidade
  só aceita inteiros; OS em "pronto" ou depois abre SOMENTE para leitura (os
  valores não podem mudar depois de prontos); a quilometragem menor que a da
  última OS apenas AVISA e pede confirmação.
- Visibilidade do estado do sistema: totais (peças, mão de obra, total)
  recalculados na hora; ao escolher uma peça aparece o saldo em estoque e o
  último valor pago, como referência para definir o preço.
- Ajuda para se recuperar de erros: a janela não fecha quando há erro (ex.:
  estoque insuficiente); tudo o que foi digitado é mantido.
- Reconhecimento em vez de memorização: o tipo de serviço é uma lista editável
  com os tipos já usados (digitar um novo também vale).
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.apresentacao.componentes import confirmar, converter_valor, formatar_moeda
from src.controle.ordem_servico_controller import (
    ErroDeNegocio,
    ItemOS,
    OrdemServicoController,
    OrdemServicoDTO,
    ProdutoParaOSDTO,
    StatusOrdemServico,
    ValidacaoError,
)

logger = logging.getLogger(__name__)

COLUNAS_PECAS = ["Peça", "Qtd", "Preço unit.", "Subtotal"]


class OrdemServicoDialog(QDialog):
    def __init__(
        self,
        controller: OrdemServicoController,
        os_: Optional[OrdemServicoDTO] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._os = os_
        self.resultado: Optional[OrdemServicoDTO] = None
        self._somente_leitura = os_ is not None and not os_.status.editavel
        self._produtos: Dict[int, ProdutoParaOSDTO] = {}
        # id_produto -> [quantidade, preço]
        self._itens: Dict[int, List] = {}

        if os_ is None:
            self.setWindowTitle("Nova ordem de serviço")
        elif self._somente_leitura:
            self.setWindowTitle(f"Ordem de serviço #{os_.id_ordem_servico} — {os_.status.rotulo}")
        else:
            self.setWindowTitle(f"Editar ordem de serviço #{os_.id_ordem_servico}")
        self.setModal(True)
        self.setMinimumSize(780, 780)

        self._montar_interface()
        self._carregar_listas()
        if os_ is not None:
            self._preencher(os_)
        self._atualizar_totais()
        if self._somente_leitura:
            self._travar()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------
    def _montar_interface(self) -> None:
        self._cliente = QComboBox()
        self._veiculo = QComboBox()
        self._km = QLineEdit()
        self._km.setValidator(QIntValidator(0, 10_000_000, self))
        self._km.setPlaceholderText("Ex.: 52000")
        self._tipo = QComboBox()
        self._tipo.setEditable(True)
        self._tipo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._tipo.lineEdit().setMaxLength(150)
        self._tipo.lineEdit().setPlaceholderText("Ex.: Revisão, Freios, Troca de óleo")
        self._descricao = QPlainTextEdit()
        self._descricao.setFixedHeight(70)
        self._descricao.setPlaceholderText("Descreva o problema relatado pelo cliente")
        self._mao_de_obra = QLineEdit()
        self._mao_de_obra.setPlaceholderText("0,00")
        self._status_inicial = QComboBox()
        self._status_inicial.addItem(StatusOrdemServico.ORCAMENTO.rotulo, StatusOrdemServico.ORCAMENTO)
        self._status_inicial.addItem(StatusOrdemServico.ANDAMENTO.rotulo, StatusOrdemServico.ANDAMENTO)

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        formulario.setVerticalSpacing(8)
        formulario.addRow("Cliente *", self._cliente)
        formulario.addRow("Veículo *", self._veiculo)
        formulario.addRow("Quilometragem *", self._km)
        formulario.addRow("Tipo de serviço *", self._tipo)
        formulario.addRow("Problema *", self._descricao)
        formulario.addRow("Mão de obra (R$)", self._mao_de_obra)
        if self._os is None:
            formulario.addRow("Situação inicial", self._status_inicial)
        else:
            self._lbl_status = QLabel(self._os.status.rotulo)
            formulario.addRow("Situação", self._lbl_status)

        # ---- peças ----
        titulo_pecas = QLabel("Peças utilizadas")
        titulo_pecas.setObjectName("titulo")
        self._produto = QComboBox()
        self._produto.addItem("Selecione a peça…", None)
        self._qtd = QLineEdit()
        self._qtd.setValidator(QIntValidator(1, 1_000_000, self))
        self._qtd.setPlaceholderText("Qtd")
        self._qtd.setMaximumWidth(80)
        self._preco = QLineEdit()
        self._preco.setPlaceholderText("Preço unit. (R$)")
        self._preco.setMaximumWidth(140)
        self._btn_peca = QPushButton("Adicionar")
        self._btn_remover = QPushButton("Remover")
        self._btn_remover.setObjectName("perigo")
        self._btn_remover.setEnabled(False)
        linha_peca = QHBoxLayout()
        linha_peca.addWidget(self._produto, stretch=1)
        linha_peca.addWidget(self._qtd)
        linha_peca.addWidget(self._preco)
        linha_peca.addWidget(self._btn_peca)
        linha_peca.addWidget(self._btn_remover)

        self._referencia = QLabel()
        self._referencia.setObjectName("subtitulo")

        self._tabela = QTableWidget(0, len(COLUNAS_PECAS))
        self._tabela.setHorizontalHeaderLabels(COLUNAS_PECAS)
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.setShowGrid(False)
        self._tabela.setMinimumHeight(150)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.verticalHeader().setDefaultSectionSize(34)
        cab = self._tabela.horizontalHeader()
        cab.setHighlightSections(False)
        cab.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            cab.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        self._totais = QLabel()
        self._totais.setStyleSheet("font-weight: 600;")
        self._totais.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._aviso_estoque = QLabel()
        self._aviso_estoque.setObjectName("subtitulo")
        self._aviso_estoque.setWordWrap(True)
        if self._os is None or self._os.status is StatusOrdemServico.ORCAMENTO:
            self._aviso_estoque.setText(
                "Em orçamento o estoque não é alterado; as peças saem do estoque quando a OS passa a “Em andamento”."
            )
        elif self._os.status is StatusOrdemServico.ANDAMENTO:
            self._aviso_estoque.setText(
                "OS em andamento: mudanças nas peças ajustam o estoque imediatamente."
            )

        self._erro = QLabel()
        self._erro.setObjectName("erroForm")
        self._erro.setWordWrap(True)
        self._erro.setTextFormat(Qt.TextFormat.PlainText)
        self._erro.hide()

        self._btn_cancelar = QPushButton("Fechar" if self._somente_leitura else "Cancelar")
        self._btn_cancelar.clicked.connect(self.reject)
        self._btn_salvar = QPushButton("Salvar")
        self._btn_salvar.setObjectName("primario")
        self._btn_salvar.setDefault(True)
        self._btn_salvar.clicked.connect(self._salvar)
        botoes = QHBoxLayout()
        botoes.addStretch()
        botoes.addWidget(self._btn_cancelar)
        botoes.addWidget(self._btn_salvar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addLayout(formulario)
        layout.addWidget(titulo_pecas)
        layout.addLayout(linha_peca)
        layout.addWidget(self._referencia)
        layout.addWidget(self._tabela, stretch=1)
        layout.addWidget(self._totais)
        layout.addWidget(self._aviso_estoque)
        layout.addWidget(self._erro)
        layout.addLayout(botoes)

        self._cliente.currentIndexChanged.connect(self._ao_trocar_cliente)
        self._produto.currentIndexChanged.connect(self._ao_escolher_produto)
        self._btn_peca.clicked.connect(self._adicionar_ou_atualizar_peca)
        self._btn_remover.clicked.connect(self._remover_peca)
        self._tabela.itemSelectionChanged.connect(self._ao_selecionar_linha)
        self._mao_de_obra.textChanged.connect(lambda _t: self._atualizar_totais())

    def _travar(self) -> None:
        """Modo somente leitura (OS pronta ou além)."""
        for w in (self._cliente, self._veiculo, self._km, self._tipo, self._descricao,
                  self._mao_de_obra, self._produto, self._qtd, self._preco,
                  self._btn_peca, self._btn_remover):
            w.setEnabled(False)
        self._btn_salvar.hide()
        for w in (self._produto, self._qtd, self._preco, self._btn_peca, self._btn_remover, self._referencia):
            w.hide()  # nada a adicionar em OS travada
        self._aviso_estoque.setText(
            "Esta OS está travada para edição (peças e valores não mudam depois de prontos). "
            "Só a situação pode ser alterada, na lista de ordens de serviço."
        )

    # ------------------------------------------------------------------
    # Carga de dados
    # ------------------------------------------------------------------
    def _carregar_listas(self) -> None:
        try:
            clientes = self._controller.listar_clientes()
            produtos = self._controller.listar_produtos()
            tipos = self._controller.listar_tipos_servico()
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao carregar listas da OS")
            clientes, produtos, tipos = [], [], []
            self._mostrar_erros(["Não foi possível carregar clientes e produtos. Verifique a conexão com o banco."])
        self._cliente.blockSignals(True)
        self._cliente.addItem("Selecione o cliente…", None)
        for c in clientes:
            self._cliente.addItem(c.nome, c.id_cliente)
        self._cliente.blockSignals(False)
        self._veiculo.addItem("Escolha primeiro o cliente", None)
        self._tipo.addItems(tipos)
        self._tipo.setCurrentIndex(-1)
        for p in produtos:
            self._produtos[p.id_produto] = p
            self._produto.addItem(f"{p.nome}  —  em estoque: {p.quantidade}", p.id_produto)

    def _preencher(self, os_: OrdemServicoDTO) -> None:
        idx = self._cliente.findData(os_.id_cliente)
        self._cliente.setCurrentIndex(max(idx, 0))  # dispara o carregamento dos veículos
        idx_v = self._veiculo.findData(os_.id_veiculo)
        if idx_v >= 0:
            self._veiculo.setCurrentIndex(idx_v)
        self._km.setText("" if os_.quilometragem is None else str(os_.quilometragem))
        self._tipo.setCurrentText(os_.tipo_servico or "")
        self._descricao.setPlainText(os_.descricao_problema or "")
        self._mao_de_obra.setText(f"{os_.valor_mao_de_obra:.2f}".replace(".", ","))
        for i in os_.itens:
            self._itens[i.id_produto] = [i.quantidade, i.preco_unitario]
            if i.id_produto not in self._produtos:  # produto sumiu da lista: mantém o nome
                self._produtos[i.id_produto] = ProdutoParaOSDTO(i.id_produto, i.nome_produto, 0, i.custo_unitario)
        self._redesenhar_pecas()

    def _ao_trocar_cliente(self) -> None:
        id_cliente = self._cliente.currentData()
        self._veiculo.clear()
        if id_cliente is None:
            self._veiculo.addItem("Escolha primeiro o cliente", None)
            return
        try:
            veiculos = self._controller.listar_veiculos_do_cliente(id_cliente)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao carregar veículos")
            veiculos = []
        if not veiculos:
            self._veiculo.addItem("Este cliente não tem veículo cadastrado", None)
            return
        self._veiculo.addItem("Selecione o veículo…", None)
        for v in veiculos:
            self._veiculo.addItem(v.rotulo, v.id_veiculo)
        if len(veiculos) == 1:
            self._veiculo.setCurrentIndex(1)

    # ------------------------------------------------------------------
    # Peças
    # ------------------------------------------------------------------
    def _ao_escolher_produto(self) -> None:
        id_produto = self._produto.currentData()
        if id_produto is None:
            self._referencia.setText("")
            return
        p = self._produtos[id_produto]
        ultimo = formatar_moeda(p.valor_unitario) if p.valor_unitario is not None else "sem compra registrada"
        self._referencia.setText(f"Último valor pago: {ultimo}   •   Em estoque: {p.quantidade}")
        if id_produto in self._itens:  # já está na OS: carrega para editar
            self._qtd.setText(str(self._itens[id_produto][0]))
            self._preco.setText(f"{self._itens[id_produto][1]:.2f}".replace(".", ","))
            self._btn_peca.setText("Atualizar")
        else:
            self._btn_peca.setText("Adicionar")

    def _adicionar_ou_atualizar_peca(self) -> None:
        self._mostrar_erros([])
        id_produto = self._produto.currentData()
        erros = []
        if id_produto is None:
            erros.append("Escolha a peça.")
        if not self._qtd.text().strip():
            erros.append("Informe a quantidade da peça.")
        preco = None
        try:
            preco = converter_valor(self._preco.text())
        except InvalidOperation:
            erros.append("O preço informado é inválido. Use números, por exemplo 89,90.")
        else:
            if preco is None:
                erros.append("Informe o preço cobrado por unidade.")
            elif preco < 0:
                erros.append("O preço não pode ser negativo.")
        if erros:
            self._mostrar_erros(erros)
            return
        self._itens[id_produto] = [int(self._qtd.text()), preco]
        self._redesenhar_pecas()
        self._produto.setCurrentIndex(0)
        self._qtd.clear()
        self._preco.clear()
        self._btn_peca.setText("Adicionar")

    def _remover_peca(self) -> None:
        linha = self._tabela.currentRow()
        if linha < 0:
            return
        id_produto = self._tabela.item(linha, 0).data(Qt.ItemDataRole.UserRole)
        self._itens.pop(id_produto, None)
        self._redesenhar_pecas()

    def _ao_selecionar_linha(self) -> None:
        linha = self._tabela.currentRow()
        selecionada = linha >= 0 and bool(self._tabela.selectedItems())
        self._btn_remover.setEnabled(selecionada and not self._somente_leitura)
        if selecionada:
            id_produto = self._tabela.item(linha, 0).data(Qt.ItemDataRole.UserRole)
            idx = self._produto.findData(id_produto)
            if idx >= 0:
                self._produto.setCurrentIndex(idx)  # carrega qtd/preço para editar

    def _redesenhar_pecas(self) -> None:
        self._tabela.blockSignals(True)
        ordenados = sorted(self._itens.items(), key=lambda kv: self._produtos[kv[0]].nome.lower())
        self._tabela.setRowCount(len(ordenados))
        for linha, (id_produto, (qtd, preco)) in enumerate(ordenados):
            valores = [self._produtos[id_produto].nome, str(qtd), formatar_moeda(preco), formatar_moeda(qtd * preco)]
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == 0:
                    item.setData(Qt.ItemDataRole.UserRole, id_produto)
                if coluna >= 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._tabela.setItem(linha, coluna, item)
        self._tabela.blockSignals(False)
        self._btn_remover.setEnabled(False)
        self._atualizar_totais()

    def _atualizar_totais(self) -> None:
        pecas = sum((Decimal(q) * p for q, p in self._itens.values()), Decimal("0"))
        try:
            mao = converter_valor(self._mao_de_obra.text()) or Decimal("0")
        except InvalidOperation:
            mao = Decimal("0")
        self._totais.setText(
            f"Peças: {formatar_moeda(pecas)}   +   Mão de obra: {formatar_moeda(mao)}   =   "
            f"Total: {formatar_moeda(pecas + mao)}"
        )

    # ------------------------------------------------------------------
    # Salvar
    # ------------------------------------------------------------------
    def _salvar(self) -> None:
        self._mostrar_erros([])
        try:
            mao = converter_valor(self._mao_de_obra.text())
        except InvalidOperation:
            self._mostrar_erros(["O valor da mão de obra é inválido. Use números, por exemplo 150,00."])
            return
        txt_km = self._km.text().strip()
        km = int(txt_km) if txt_km else None
        id_cliente = self._cliente.currentData()
        id_veiculo = self._veiculo.currentData()
        tipo = self._tipo.currentText()
        descricao = self._descricao.toPlainText()
        itens = [ItemOS(i, q, p) for i, (q, p) in self._itens.items()]
        id_os = self._os.id_ordem_servico if self._os else None

        try:
            aviso = self._controller.aviso_quilometragem(id_veiculo, km, id_os)
        except Exception:  # noqa: BLE001
            aviso = None
        if aviso and not confirmar(self, "Quilometragem", aviso + "\n\nDeseja salvar mesmo assim?", "Salvar mesmo assim"):
            return

        try:
            if self._os is None:
                self.resultado = self._controller.cadastrar(
                    id_cliente, id_veiculo, km, descricao, tipo, mao, itens,
                    self._status_inicial.currentData(),
                )
            else:
                self.resultado = self._controller.atualizar(
                    id_os, id_cliente, id_veiculo, km, descricao, tipo, mao, itens
                )
        except ValidacaoError as exc:
            self._mostrar_erros(exc.erros)
        except ErroDeNegocio as exc:
            self._mostrar_erros([str(exc)])
        except Exception:
            logger.exception("Falha inesperada ao salvar a OS")
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
