"""
Tela de Relatórios (RF06): ganhos x gastos, serviços mais prestados e
exportação (HU16, HU17 e HU18).

Decisões de usabilidade (Nielsen):
- Visibilidade do estado do sistema: cartões com os totais do período e a
  linha "Período: ... (agrupado por mês)" deixam claro o que está na tela.
- Correspondência com o mundo real: "Entradas", "Saídas", "Saldo de caixa",
  "A receber" — palavras do dono da oficina, não do banco de dados.
- Eficiência: o relatório abre pronto (últimos 12 meses) e atualiza sozinho
  ao mudar o filtro, sem botão "Aplicar".
- Reconhecer em vez de lembrar / acessibilidade: além da cor, os gráficos têm
  legenda e tooltip, e as abas abaixo trazem a TABELA com os números exatos.
  Valor negativo aparece com "−" e em vermelho (não só a cor).
- Prevenção de erros: data inicial depois da final mostra o aviso na própria
  tela, sem apagar o que estava sendo visto; exportar fica desabilitado
  enquanto não há relatório válido.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from PyQt6.QtCharts import QChartView
from PyQt6.QtCore import QDate, QLocale, Qt, QTimer
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.apresentacao.componentes import (
    destacar,
    erro_inesperado,
    formatar_moeda,
    formatar_moeda_com_sinal,
    preenchendo_tabela,
)
from src.apresentacao.graficos_relatorio import grafico_financeiro, grafico_servicos
from src.apresentacao.relatorio_pdf import salvar_pdf
from src.controle.relatorio_controller import (
    PERIODOS,
    PERSONALIZADO,
    ULTIMOS_12_MESES,
    ErroDeNegocio,
    Relatorio,
    RelatorioController,
    ValidacaoError,
)

logger = logging.getLogger(__name__)

# Abaixo disso: gráficos um embaixo do outro e cartões em 2 x 2. A janela
# padrão (1180 px - 230 da barra lateral = 950) ainda fica lado a lado.
LARGURA_LADO_A_LADO = 900
PT_BR = QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil)


class _Cartao(QFrame):
    """Cartão de resumo: título, valor grande e uma linha de detalhe."""

    def __init__(self, titulo: str) -> None:
        super().__init__()
        self.setObjectName("cartao")
        self.titulo = QLabel(titulo)
        self.titulo.setObjectName("cartaoTitulo")
        self.valor = QLabel("—")
        self.valor.setObjectName("cartaoValor")
        # O valor não dita a largura mínima da tela: quem decide é a grade
        # (4 por linha ou 2 x 2), senão a tela não caberia numa janela estreita.
        self.valor.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.titulo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(140)
        self.detalhe = QLabel("")
        self.detalhe.setObjectName("cartaoDetalhe")
        self.detalhe.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(self.titulo)
        layout.addWidget(self.valor)
        layout.addWidget(self.detalhe)

    def mostrar(self, valor, detalhe: str, alerta: bool = False) -> None:
        self.valor.setText(formatar_moeda_com_sinal(valor))
        destacar(self.valor, "negativa", valor < 0)
        self.detalhe.setText(detalhe)
        destacar(self.detalhe, "alerta", alerta)


class RelatoriosView(QWidget):
    def __init__(self, controller: Optional[RelatorioController] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagina")
        self._controller = controller or RelatorioController()
        self.relatorio: Optional[Relatorio] = None

        self._timer = QTimer(self, singleShot=True, interval=250)  # espera o usuário parar de mexer
        self._timer_feedback = QTimer(self, singleShot=True, interval=6000)

        self._montar_interface()
        self._conectar_sinais()
        self._aplicar_periodo_pronto(ULTIMOS_12_MESES)

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------
    def _montar_interface(self) -> None:
        titulo = QLabel("Relatórios")
        titulo.setObjectName("titulo")
        subtitulo = QLabel("Ganhos, gastos e serviços mais prestados da oficina")
        subtitulo.setObjectName("subtitulo")
        subtitulo.setWordWrap(True)
        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        bloco_titulo.addWidget(titulo)
        bloco_titulo.addWidget(subtitulo)

        self._btn_csv = QPushButton("Exportar CSV")
        self._btn_pdf = QPushButton("Exportar PDF")
        self._btn_pdf.setObjectName("primario")
        for botao in (self._btn_csv, self._btn_pdf):
            botao.setEnabled(False)  # só depois que houver um relatório válido na tela
        cabecalho = QHBoxLayout()
        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch(1)
        cabecalho.addWidget(self._btn_csv, alignment=Qt.AlignmentFlag.AlignVCenter)
        cabecalho.addWidget(self._btn_pdf, alignment=Qt.AlignmentFlag.AlignVCenter)

        # ---- filtros ----
        self._periodo = QComboBox()
        self._periodo.addItems(PERIODOS)
        self._de = self._campo_data()
        self._ate = self._campo_data()
        self._lbl_periodo = QLabel()
        self._lbl_periodo.setObjectName("subtitulo")
        self._lbl_periodo.setWordWrap(True)
        filtros = QHBoxLayout()
        filtros.setSpacing(8)
        filtros.addWidget(QLabel("Período"))
        filtros.addWidget(self._periodo)
        filtros.addSpacing(12)
        filtros.addWidget(QLabel("De"))
        filtros.addWidget(self._de)
        filtros.addWidget(QLabel("Até"))
        filtros.addWidget(self._ate)
        filtros.addStretch(1)

        self._erro = QLabel()
        self._erro.setObjectName("erroForm")
        self._erro.setWordWrap(True)
        self._erro.hide()

        # ---- cartões ----
        self._c_entradas = _Cartao("Entradas")
        self._c_saidas = _Cartao("Saídas (compras)")
        self._c_saldo = _Cartao("Saldo de caixa")
        self._c_lucro = _Cartao("Lucro bruto das OS")
        # Grade: 4 cartões numa linha; com a janela estreita, 2 x 2 (ver resizeEvent).
        self._cartoes = QGridLayout()
        self._cartoes.setSpacing(12)
        self._cartoes_por_linha = 0
        self._distribuir_cartoes(4)
        self._lbl_receber = QLabel()
        self._lbl_receber.setObjectName("subtitulo")
        self._lbl_receber.setWordWrap(True)

        # ---- gráficos ----
        self._visao_financeiro = self._visao_grafico()
        self._visao_servicos = self._visao_grafico()
        self._graficos = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._graficos.setSpacing(12)
        for visao in (self._visao_financeiro, self._visao_servicos):
            painel = QFrame()
            painel.setObjectName("painelGrafico")
            caixa = QVBoxLayout(painel)
            caixa.setContentsMargins(6, 6, 6, 6)
            caixa.addWidget(visao)
            self._graficos.addWidget(painel, stretch=1)

        # ---- tabelas ----
        self._tab_periodos = self._tabela(
            ["Período", "OS entregues", "Receita das OS", "Vendas por fora", "Entradas", "Saídas", "Saldo"])
        self._tab_servicos = self._tabela(["Serviço", "OS entregues", "Faturamento", "Ticket médio"])
        self._abas = QTabWidget()
        self._abas.addTab(self._tab_periodos, "Tabela por período")
        self._abas.addTab(self._tab_servicos, "Tabela de serviços")
        self._abas.setMinimumHeight(260)

        self._lbl_feedback = QLabel()
        self._lbl_feedback.setObjectName("feedbackOk")

        # A página rola na vertical: na janela padrão (720 px de altura) cartões,
        # gráficos e tabela não cabem juntos sem esmagar a tabela.
        conteudo = QWidget()
        conteudo.setObjectName("pagina")
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rolagem.setWidget(conteudo)
        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.addWidget(rolagem)

        raiz = QVBoxLayout(conteudo)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(12)
        raiz.addLayout(cabecalho)
        raiz.addLayout(filtros)
        raiz.addWidget(self._lbl_periodo)
        raiz.addWidget(self._erro)
        raiz.addLayout(self._cartoes)
        raiz.addWidget(self._lbl_receber)
        raiz.addLayout(self._graficos)
        raiz.addWidget(self._abas)
        raiz.addWidget(self._lbl_feedback)

    def _distribuir_cartoes(self, por_linha: int) -> None:
        if por_linha == self._cartoes_por_linha:
            return
        self._cartoes_por_linha = por_linha
        cartoes = (self._c_entradas, self._c_saidas, self._c_saldo, self._c_lucro)
        for c in cartoes:
            self._cartoes.removeWidget(c)
        for i, c in enumerate(cartoes):
            self._cartoes.addWidget(c, i // por_linha, i % por_linha)
        for coluna in range(4):
            self._cartoes.setColumnStretch(coluna, 1 if coluna < por_linha else 0)

    def _campo_data(self) -> QDateEdit:
        campo = QDateEdit()
        campo.setCalendarPopup(True)
        campo.setDisplayFormat("dd/MM/yyyy")
        campo.setLocale(PT_BR)
        campo.calendarWidget().setLocale(PT_BR)
        campo.setMaximumDate(QDate.currentDate())  # não há movimento no futuro
        return campo

    @staticmethod
    def _visao_grafico() -> QChartView:
        visao = QChartView()
        visao.setRenderHint(QPainter.RenderHint.Antialiasing)
        visao.setMinimumHeight(300)
        visao.setStyleSheet("background: transparent;")
        return visao

    @staticmethod
    def _tabela(colunas) -> QTableWidget:
        t = QTableWidget(0, len(colunas))
        t.setHorizontalHeaderLabels(colunas)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        t.setShowGrid(False)
        t.verticalHeader().setVisible(False)
        cab = t.horizontalHeader()
        cab.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, len(colunas)):
            cab.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
            t.horizontalHeaderItem(c).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return t

    def _conectar_sinais(self) -> None:
        self._periodo.currentTextChanged.connect(self._ao_trocar_periodo)
        self._de.dateChanged.connect(self._ao_mexer_nas_datas)
        self._ate.dateChanged.connect(self._ao_mexer_nas_datas)
        self._timer.timeout.connect(self.recarregar)
        self._timer_feedback.timeout.connect(lambda: self._lbl_feedback.setText(""))
        self._btn_csv.clicked.connect(self._exportar_csv)
        self._btn_pdf.clicked.connect(self._exportar_pdf)

    # ------------------------------------------------------------------
    # Filtros
    # ------------------------------------------------------------------
    def _aplicar_periodo_pronto(self, nome: str) -> None:
        inicio, fim = self._controller.datas_do_periodo(nome)
        for campo, valor in ((self._de, inicio), (self._ate, fim)):
            campo.blockSignals(True)
            campo.setDate(QDate(valor.year, valor.month, valor.day))
            campo.blockSignals(False)
        self._periodo.blockSignals(True)
        self._periodo.setCurrentText(nome)
        self._periodo.blockSignals(False)
        self._timer.start()

    def _ao_trocar_periodo(self, nome: str) -> None:
        if nome != PERSONALIZADO:
            self._aplicar_periodo_pronto(nome)

    def _ao_mexer_nas_datas(self) -> None:
        """Mexeu nas datas à mão: o período passa a ser 'Personalizado'."""
        self._periodo.blockSignals(True)
        self._periodo.setCurrentText(PERSONALIZADO)
        self._periodo.blockSignals(False)
        self._timer.start()

    # ------------------------------------------------------------------
    # Dados
    # ------------------------------------------------------------------
    def showEvent(self, evento) -> None:  # noqa: N802 (nome imposto pelo Qt)
        """Recarrega ao aparecer: OS e compras podem ter mudado em outra tela."""
        super().showEvent(evento)
        self._timer.start()

    def recarregar(self) -> None:
        inicio = self._de.date().toPyDate()
        fim = self._ate.date().toPyDate()
        try:
            relatorio = self._controller.gerar(inicio, fim)
        except ValidacaoError as exc:
            self._mostrar_erro(" ".join(exc.erros))
            return
        except ErroDeNegocio as exc:
            self._mostrar_erro(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            erro_inesperado(self, exc, "Não foi possível gerar o relatório.")
            return
        self.relatorio = relatorio
        self._mostrar_erro("")
        self._preencher(relatorio)

    def _mostrar_erro(self, texto: str) -> None:
        self._erro.setText(texto)
        self._erro.setVisible(bool(texto))
        habilitar = not texto and self.relatorio is not None
        self._btn_csv.setEnabled(habilitar)
        self._btn_pdf.setEnabled(habilitar)

    def _preencher(self, rel: Relatorio) -> None:
        r = rel.resumo
        self._lbl_periodo.setText(
            f"{rel.descricao_periodo}" + ("   •   nenhum movimento no período" if rel.vazio else "")
        )
        self._c_entradas.mostrar(
            r.entradas, f"{r.qtd_os} OS entregues ({formatar_moeda(r.receita_os)}) + "
                        f"{r.qtd_vendas} vendas por fora ({formatar_moeda(r.vendas_avulsas)})")
        self._c_saidas.mostrar(
            r.saidas, f"{r.qtd_compras} compras" + (
                f" − {formatar_moeda(r.ressarcimentos)} ressarcidos" if r.ressarcimentos else ""))
        self._c_saldo.mostrar(r.saldo, "entradas − saídas no período")
        if r.pecas_sem_custo:
            detalhe_lucro = f"⚠ {r.pecas_sem_custo} peça(s) sem custo registrado (contadas como zero)"
        else:
            detalhe_lucro = f"receita das OS − custo das peças ({formatar_moeda(r.custo_pecas)})"
        self._c_lucro.mostrar(r.lucro_bruto_os, detalhe_lucro, alerta=bool(r.pecas_sem_custo))
        self._lbl_receber.setText(
            f"A receber: {formatar_moeda(r.a_receber)} ({r.qtd_a_receber} OS aguardando pagamento, "
            "independente do período)"
        )

        self._trocar_grafico(self._visao_financeiro, grafico_financeiro(rel))
        self._trocar_grafico(self._visao_servicos, grafico_servicos(rel))
        self._preencher_tabelas(rel)

    @staticmethod
    def _trocar_grafico(visao: QChartView, novo) -> None:
        antigo = visao.chart()
        visao.setChart(novo)
        if antigo is not None:
            antigo.deleteLater()  # o QChartView não apaga o gráfico anterior sozinho

    def _preencher_tabelas(self, rel: Relatorio) -> None:
        r = rel.resumo
        linhas = [[p.rotulo, str(p.qtd_os), p.receita_os, p.vendas_avulsas, p.entradas, p.saidas, p.saldo]
                  for p in rel.pontos]
        linhas.append(["Total", str(r.qtd_os), r.receita_os, r.vendas_avulsas, r.entradas, r.saidas, r.saldo])
        self._encher(self._tab_periodos, linhas, negrito_ultima=True)
        self._encher(self._tab_servicos,
                     [[s.tipo, str(s.quantidade), s.faturamento, s.ticket_medio] for s in rel.servicos])

    @staticmethod
    def _encher(tabela: QTableWidget, linhas, negrito_ultima: bool = False) -> None:
        with preenchendo_tabela(tabela):
            RelatoriosView._encher_linhas(tabela, linhas, negrito_ultima)

    @staticmethod
    def _encher_linhas(tabela: QTableWidget, linhas, negrito_ultima: bool = False) -> None:
        tabela.setRowCount(len(linhas))
        for i, linha in enumerate(linhas):
            for j, valor in enumerate(linha):
                texto = valor if isinstance(valor, str) else formatar_moeda_com_sinal(valor)
                item = QTableWidgetItem(texto)
                if j > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if negrito_ultima and i == len(linhas) - 1:
                    fonte = QFont(item.font())
                    fonte.setBold(True)
                    item.setFont(fonte)
                tabela.setItem(i, j, item)

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nome imposto pelo Qt)
        """Janela estreita: gráficos um embaixo do outro e cartões em 2 x 2."""
        super().resizeEvent(evento)
        larga = self.width() >= LARGURA_LADO_A_LADO
        direcao = QBoxLayout.Direction.LeftToRight if larga else QBoxLayout.Direction.TopToBottom
        if self._graficos.direction() != direcao:
            self._graficos.setDirection(direcao)
        self._distribuir_cartoes(4 if larga else 2)

    # ------------------------------------------------------------------
    # Exportação (HU18): o arquivo sai do MESMO relatório que está na tela
    # ------------------------------------------------------------------
    def _caminho_para_salvar(self, extensao: str, filtro: str) -> Optional[str]:
        sugerido = os.path.join(os.path.expanduser("~"), "Documents",
                                self._controller.nome_sugerido(self.relatorio, extensao))
        caminho, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", sugerido, filtro)
        return caminho or None

    def _exportar_csv(self) -> None:
        if self.relatorio is None:
            return
        caminho = self._caminho_para_salvar("csv", "Planilha CSV (*.csv)")
        if caminho:
            self.exportar_csv_para(caminho)

    def _exportar_pdf(self) -> None:
        if self.relatorio is None:
            return
        caminho = self._caminho_para_salvar("pdf", "Documento PDF (*.pdf)")
        if caminho:
            self.exportar_pdf_para(caminho)

    def exportar_csv_para(self, caminho: str) -> bool:
        try:
            self._controller.salvar_csv(self.relatorio, caminho)
        except OSError as exc:
            erro_inesperado(self, exc, "Não foi possível salvar o CSV. O arquivo pode estar aberto no Excel.")
            return False
        self._mostrar_feedback(f"Relatório salvo em {caminho}")
        return True

    def exportar_pdf_para(self, caminho: str) -> bool:
        try:
            salvar_pdf(self.relatorio, caminho)
        except Exception as exc:  # noqa: BLE001
            erro_inesperado(self, exc, "Não foi possível salvar o PDF. O arquivo pode estar aberto.")
            return False
        self._mostrar_feedback(f"Relatório salvo em {caminho}")
        return True

    def _mostrar_feedback(self, texto: str) -> None:
        self._lbl_feedback.setText(texto)
        self._timer_feedback.start()
