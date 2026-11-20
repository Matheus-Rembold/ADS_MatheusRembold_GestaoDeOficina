"""
Tela de Ordens de Serviço (RF04): lista, busca, filtro por situação e ações.

Decisões de usabilidade (Nielsen, RNF01):
- Prevenção de erros: "Alterar situação" só oferece os passos permitidos a
  partir da situação atual; "Excluir" só fica ativo para orçamento; passos com
  efeito no estoque ou sem volta pedem confirmação.
- Visibilidade do estado do sistema: a situação aparece em texto e cor; o
  rodapé mostra quantas OS e o valor somado das listadas; os cartões do topo
  mostram quantas OS estão em andamento, com serviço realizado e aguardando pagamento
  (a oficina inteira, sem depender da busca). Clicar num cartão filtra a
  lista por aquela situação; clicar de novo volta para "Todas".
- Reconhecimento em vez de memorização: a busca aceita cliente, placa,
  modelo, tipo de serviço, problema ou número da OS (histórico por cliente
  e por veículo = buscar pelo nome ou placa).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.apresentacao.componentes import (
    BarraPaginacao,
    aviso,
    confirmar,
    destacar,
    erro_inesperado,
    formatar_moeda,
    preenchendo_tabela,
    texto_contagem,
)
from src.apresentacao.documento_os import BotaoImprimir
from src.apresentacao.telas.ordem_servico_dialog import OrdemServicoDialog
from src.apresentacao.tema import (
    COR_OS_AGUARDANDO,
    COR_OS_ANDAMENTO,
    COR_OS_ENTREGUE,
    COR_OS_ORCAMENTO,
    COR_OS_PRONTO,
)
from src.controle.ordem_servico_controller import (
    ErroDeNegocio,
    OrdemServicoController,
    OrdemServicoDTO,
    ResumoSituacao,
    SITUACOES_DO_PAINEL,
    StatusOrdemServico,
)

COLUNAS = ["OS", "Data", "Cliente", "Veículo", "Serviço", "Situação", "Total"]
COL_OS, COL_DATA, COL_CLIENTE, COL_VEICULO, COL_SERVICO, COL_STATUS, COL_TOTAL = range(7)

_COR_STATUS: Dict[StatusOrdemServico, str] = {
    StatusOrdemServico.ORCAMENTO: COR_OS_ORCAMENTO,
    StatusOrdemServico.ANDAMENTO: COR_OS_ANDAMENTO,
    StatusOrdemServico.PRONTO: COR_OS_PRONTO,
    StatusOrdemServico.AGUARDANDO_PAGAMENTO: COR_OS_AGUARDANDO,
    StatusOrdemServico.ENTREGUE: COR_OS_ENTREGUE,
}

_TITULO_CARTAO = {
    StatusOrdemServico.ANDAMENTO: "EM ANDAMENTO",
    StatusOrdemServico.PRONTO: "SERVIÇO REALIZADO",
    StatusOrdemServico.AGUARDANDO_PAGAMENTO: "AGUARDANDO PAGAMENTO",
}


class CartaoSituacao(QFrame):
    """Cartão clicável: título, quantidade grande (na cor da situação) e valor."""

    clicado = pyqtSignal(object)  # StatusOrdemServico

    def __init__(self, status: StatusOrdemServico, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.status = status
        self.setObjectName("cartaoSituacao")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.titulo = QLabel(_TITULO_CARTAO[status])
        self.titulo.setObjectName("cartaoSituacaoTitulo")
        fonte = self.titulo.font()
        fonte.setLetterSpacing(fonte.SpacingType.AbsoluteSpacing, 1)
        self.titulo.setFont(fonte)
        self.quantidade = QLabel("—")
        self.quantidade.setObjectName("cartaoSituacaoValor")
        self.quantidade.setProperty("situacao", status.value)
        self.detalhe = QLabel("")
        self.detalhe.setObjectName("cartaoSituacaoDetalhe")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(0)
        for rotulo in (self.titulo, self.quantidade, self.detalhe):
            rotulo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(rotulo)

    def atualizar(self, resumo: ResumoSituacao) -> None:
        self.quantidade.setText(str(resumo.quantidade))
        valor = formatar_moeda(resumo.valor)
        a_receber = self.status is StatusOrdemServico.AGUARDANDO_PAGAMENTO
        self.detalhe.setText(f"{valor} a receber" if a_receber else valor)
        plural = "ordem de serviço" if resumo.quantidade == 1 else "ordens de serviço"
        self.setToolTip(f"{resumo.quantidade} {plural} “{self.status.rotulo}”. Clique para ver só elas.")

    def marcar(self, ativo: bool) -> None:
        destacar(self, "ativo", ativo)

    def mousePressEvent(self, evento) -> None:  # noqa: N802 (nome imposto pelo Qt)
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit(self.status)
        super().mousePressEvent(evento)


class OrdensServicoView(QWidget):
    def __init__(self, controller: Optional[OrdemServicoController] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagina")
        self._controller = controller or OrdemServicoController()
        self._pagina = 1  # paginação: 50 por vez
        self._ultima_pagina = None
        self._dtos: List[OrdemServicoDTO] = []
        self._timer_busca = QTimer(self, singleShot=True, interval=250)
        self._timer_feedback = QTimer(self, singleShot=True, interval=5000)
        self._montar_interface()
        self._conectar_sinais()

    # ------------------------------------------------------------------
    def _montar_interface(self) -> None:
        titulo = QLabel("Ordens de Serviço")
        titulo.setObjectName("titulo")
        subtitulo = QLabel("Orçamentos e serviços da oficina: peças, mão de obra e situação")
        subtitulo.setObjectName("subtitulo")
        bloco = QVBoxLayout()
        bloco.setSpacing(2)
        bloco.addWidget(titulo)
        bloco.addWidget(subtitulo)

        self._btn_nova = QPushButton("+  Nova OS")
        self._btn_nova.setObjectName("primario")
        self._btn_abrir = QPushButton("Abrir")
        self._btn_status = QPushButton("Alterar situação  ▾")
        # Imprimir / PDF da OS selecionada (20/11/2026)
        self.btn_imprimir = BotaoImprimir(
            self._controller, lambda: (self._selecionada().id_ordem_servico if self._selecionada() else None))
        self._btn_excluir = QPushButton("Excluir")
        self._btn_excluir.setObjectName("perigo")
        for b in (self._btn_abrir, self._btn_status, self.btn_imprimir, self._btn_excluir):
            b.setEnabled(False)

        cabecalho = QHBoxLayout()
        cabecalho.addLayout(bloco)
        cabecalho.addStretch(1)
        # Ordem pedida pelo Matheus (16/11/2026): Nova OS primeiro, depois as ações da
        # OS selecionada. O espaço separa a ação principal das ações da linha, e o
        # "Excluir" fica no extremo oposto do "Nova OS" (prevenção de erros).
        cabecalho.addWidget(self._btn_nova)
        cabecalho.addSpacing(12)
        cabecalho.addWidget(self._btn_abrir)
        cabecalho.addWidget(self._btn_status)
        cabecalho.addWidget(self.btn_imprimir)
        cabecalho.addWidget(self._btn_excluir)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("Buscar por cliente, placa, modelo, serviço, problema ou nº da OS…")
        self._busca.setClearButtonEnabled(True)
        self._filtro = QComboBox()
        self._filtro.addItem("Todas as situações", None)
        for s in StatusOrdemServico:
            self._filtro.addItem(s.rotulo, s)
        filtros = QHBoxLayout()
        filtros.addWidget(self._busca, stretch=1)
        filtros.addWidget(self._filtro)

        # Cartões de situação (Nielsen: visibilidade do estado do sistema)
        self.cartoes: Dict[StatusOrdemServico, CartaoSituacao] = {}
        linha_cartoes = QHBoxLayout()
        linha_cartoes.setSpacing(12)
        for status in SITUACOES_DO_PAINEL:
            cartao = CartaoSituacao(status)
            cartao.clicado.connect(self._filtrar_pelo_cartao)
            self.cartoes[status] = cartao
            linha_cartoes.addWidget(cartao, stretch=1)

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
        for c in (COL_OS, COL_DATA, COL_VEICULO, COL_STATUS, COL_TOTAL):
            cab.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_CLIENTE, QHeaderView.ResizeMode.Stretch)
        cab.setSectionResizeMode(COL_SERVICO, QHeaderView.ResizeMode.Stretch)

        self._lbl_vazio = QLabel("Nenhuma ordem de serviço encontrada.")
        self._lbl_vazio.setObjectName("vazio")
        self._lbl_vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_vazio.hide()
        self._lbl_total = QLabel()
        self._lbl_total.setObjectName("rodape")
        self._lbl_feedback = QLabel()
        self._lbl_feedback.setObjectName("feedbackOk")
        self._paginacao = BarraPaginacao()
        rodape = QHBoxLayout()
        rodape.addWidget(self._lbl_total)
        rodape.addSpacing(16)
        rodape.addWidget(self._lbl_feedback, stretch=1)
        rodape.addWidget(self._paginacao)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(14)
        raiz.addLayout(cabecalho)
        raiz.addLayout(linha_cartoes)
        raiz.addLayout(filtros)
        raiz.addWidget(self._tabela, stretch=1)
        raiz.addWidget(self._lbl_vazio, stretch=1)
        raiz.addLayout(rodape)

    def _conectar_sinais(self) -> None:
        self._btn_nova.clicked.connect(self._nova)
        self._btn_abrir.clicked.connect(self._abrir)
        self._btn_status.clicked.connect(self._menu_status)
        self._btn_excluir.clicked.connect(self._excluir)
        self._tabela.itemSelectionChanged.connect(self._atualizar_botoes)
        self._tabela.itemDoubleClicked.connect(lambda _i: self._abrir())
        self._busca.textChanged.connect(lambda _t: self._timer_busca.start())
        # busca ou filtro novo sempre volta para a página 1
        self._timer_busca.timeout.connect(lambda: self.recarregar(pagina=1))
        self._filtro.currentIndexChanged.connect(lambda _i: self.recarregar(pagina=1))
        self._paginacao.pagina_pedida.connect(lambda p: self.recarregar(pagina=p))
        self._timer_feedback.timeout.connect(lambda: self._lbl_feedback.setText(""))

    # ------------------------------------------------------------------
    def showEvent(self, evento) -> None:  # noqa: N802
        super().showEvent(evento)
        self.recarregar()

    def recarregar(self, selecionar: Optional[int] = None, pagina: Optional[int] = None) -> None:
        if pagina is not None:
            self._pagina = pagina
        try:
            self._ultima_pagina = self._controller.listar_pagina(
                self._busca.text(), self._filtro.currentData(), self._pagina
            )
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível carregar as ordens de serviço.")
            return
        self._pagina = self._ultima_pagina.pagina
        self._dtos = list(self._ultima_pagina.itens)
        self._atualizar_cartoes()
        with preenchendo_tabela(self._tabela):  # evita o travamento quadrático ao recarregar
            self._preencher(selecionar)

    def _preencher(self, selecionar: Optional[int]) -> None:
        self._tabela.blockSignals(True)
        self._tabela.setRowCount(len(self._dtos))
        linha_sel = -1
        for linha, o in enumerate(self._dtos):
            valores = [
                f"#{o.id_ordem_servico}",
                o.criado_em.strftime("%d/%m/%Y"),
                o.nome_cliente,
                f"{o.placa} – {o.modelo}",
                o.tipo_servico or "—",
                o.status.rotulo,
                formatar_moeda(o.valor_total),
            ]
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == COL_STATUS:
                    item.setForeground(QBrush(QColor(_COR_STATUS[o.status])))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif coluna == COL_TOTAL:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._tabela.setItem(linha, coluna, item)
            if selecionar == o.id_ordem_servico:
                linha_sel = linha
        self._tabela.blockSignals(False)
        if linha_sel >= 0:
            self._tabela.selectRow(linha_sel)
        else:
            self._tabela.clearSelection()
        self._atualizar_botoes()

        tem = bool(self._dtos)
        self._tabela.setVisible(tem)
        self._lbl_vazio.setVisible(not tem)
        pag = self._ultima_pagina
        texto = texto_contagem(pag, "ordem de serviço", "ordens de serviço")
        # valor somado no banco sobre TODAS as OS do filtro, não só as 50 da página
        soma = pag.resumo.get("valor_total", Decimal("0"))
        self._lbl_total.setText(f"{texto}  •  total listado: {formatar_moeda(soma)}" if pag.total else texto)
        self._paginacao.atualizar(pag)

    # ------------------------------------------------------------------
    # Cartões de situação
    # ------------------------------------------------------------------
    def _atualizar_cartoes(self) -> None:
        try:
            for resumo in self._controller.painel_situacao():
                self.cartoes[resumo.status].atualizar(resumo)
        except Exception:  # noqa: BLE001  (os cartões são um extra: a lista continua funcionando)
            for cartao in self.cartoes.values():
                cartao.quantidade.setText("—")
        filtro = self._filtro.currentData()
        for status, cartao in self.cartoes.items():
            cartao.marcar(status is filtro)

    def _filtrar_pelo_cartao(self, status: StatusOrdemServico) -> None:
        """Clique filtra por aquela situação; clicar no cartão já ativo volta para Todas."""
        destino = None if self._filtro.currentData() is status else status
        self._filtro.setCurrentIndex(self._filtro.findData(destino))  # o combo dispara o recarregar

    def _selecionada(self) -> Optional[OrdemServicoDTO]:
        linha = self._tabela.currentRow()
        if linha < 0 or not self._tabela.selectedItems() or linha >= len(self._dtos):
            return None
        return self._dtos[linha]

    def _atualizar_botoes(self) -> None:
        o = self._selecionada()
        self._btn_abrir.setEnabled(o is not None)
        self._btn_abrir.setText("Editar" if o is not None and o.status.editavel else "Abrir")
        self._btn_status.setEnabled(o is not None and bool(o.transicoes))
        self.btn_imprimir.setEnabled(o is not None)
        self._btn_excluir.setEnabled(o is not None and o.status is StatusOrdemServico.ORCAMENTO)

    def _mostrar_feedback(self, texto: str) -> None:
        self._lbl_feedback.setText(texto)
        self._timer_feedback.start()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _nova(self) -> None:
        d = OrdemServicoDialog(self._controller, parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self._busca.blockSignals(True)
            self._filtro.blockSignals(True)
            self._busca.clear()
            self._filtro.setCurrentIndex(0)
            self._busca.blockSignals(False)
            self._filtro.blockSignals(False)
            self.recarregar(d.resultado.id_ordem_servico, pagina=1)  # OS nova é a primeira da lista
            self._mostrar_feedback(f"OS #{d.resultado.id_ordem_servico} criada.")

    def _abrir(self) -> None:
        o = self._selecionada()
        if o is None:
            return
        try:
            atual = self._controller.obter(o.id_ordem_servico)  # leitura fresca
        except ErroDeNegocio as exc:
            aviso(self, "Ordem de serviço", str(exc))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível abrir a ordem de serviço.")
            return
        d = OrdemServicoDialog(self._controller, atual, parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self.recarregar(d.resultado.id_ordem_servico)
            self._mostrar_feedback(f"OS #{d.resultado.id_ordem_servico} atualizada.")

    def _menu_status(self) -> None:
        o = self._selecionada()
        if o is None:
            return
        menu = QMenu(self)
        # Guardamos a ligação ação -> situação em Python (não em QAction.setData):
        # assim não depende de como o Qt devolve o enum, em nenhuma versão/sistema.
        destinos = {}
        for destino in o.transicoes:
            destinos[menu.addAction(destino.rotulo)] = destino
        escolhida = menu.exec(self._btn_status.mapToGlobal(self._btn_status.rect().bottomLeft()))
        if escolhida is None or escolhida not in destinos:
            return
        try:
            self._mudar_status(o, destinos[escolhida])
        except Exception as erro:  # noqa: BLE001  (nunca falhar em silêncio dentro de um slot)
            erro_inesperado(self, erro, "Não foi possível alterar a situação da OS.")

    def _mudar_status(self, o: OrdemServicoDTO, destino: StatusOrdemServico) -> None:
        destino = StatusOrdemServico(destino)
        if o.status is StatusOrdemServico.ORCAMENTO and destino is StatusOrdemServico.ANDAMENTO:
            texto = "As peças da OS vão sair do estoque agora."
        elif destino is StatusOrdemServico.ORCAMENTO:
            texto = "As peças da OS voltam para o estoque."
        elif destino is StatusOrdemServico.ENTREGUE:
            texto = "Isto marca o pagamento e a entrega do veículo. Depois não há como voltar."
        elif destino in (StatusOrdemServico.PRONTO, StatusOrdemServico.AGUARDANDO_PAGAMENTO) \
                and o.status.editavel:
            texto = "A partir daí peças e valores ficam travados para edição."
        else:
            texto = ""
        if texto and not confirmar(
            self, "Alterar situação",
            f"Passar a OS #{o.id_ordem_servico} para “{destino.rotulo}”?\n\n{texto}",
            "Confirmar",
        ):
            return
        try:
            novo = self._controller.alterar_status(o.id_ordem_servico, destino)
        except ErroDeNegocio as exc:
            aviso(self, "Não foi possível alterar a situação", str(exc))
            self.recarregar(o.id_ordem_servico)
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível alterar a situação da OS.")
            return
        self.recarregar(novo.id_ordem_servico)
        self._mostrar_feedback(f"OS #{novo.id_ordem_servico}: {novo.status.rotulo}.")

    def _excluir(self) -> None:
        o = self._selecionada()
        if o is None:
            return
        if not confirmar(
            self, "Excluir ordem de serviço",
            f"Excluir o orçamento #{o.id_ordem_servico} de {o.nome_cliente}?\nEsta ação não pode ser desfeita.",
            "Excluir",
        ):
            return
        try:
            self._controller.excluir(o.id_ordem_servico)
        except ErroDeNegocio as exc:
            aviso(self, "Não foi possível excluir", str(exc))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível excluir a ordem de serviço.")
            return
        self.recarregar()
        self._mostrar_feedback(f"Orçamento #{o.id_ordem_servico} excluído.")
