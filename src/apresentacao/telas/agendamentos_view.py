"""
Tela de Agendamentos (RF05): calendário + agenda do dia.

Decisões de usabilidade (Nielsen, RNF01):
- Visibilidade do estado do sistema: os dias com serviço marcado ficam em
  destaque no calendário; a "ocupação por horário" mostra, hora a hora, quantas
  das 2 vagas estão ocupadas (em texto e cor, nunca só cor). Tudo é lido do
  banco ao abrir a tela e a cada ação, então reflete os agendamentos atuais.
- Prevenção de erros: só agendamentos "agendados" podem ser editados,
  cancelados ou convertidos (os botões já aparecem desativados nos demais);
  cancelar pede confirmação.
- Reconhecimento em vez de memorização: clicar no dia mostra a agenda dele;
  "Novo agendamento" já vem com o dia selecionado.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from PyQt6.QtCore import QDate, QLocale, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QTextCharFormat
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.apresentacao.componentes import aviso, confirmar, erro_inesperado, preenchendo_tabela
from src.apresentacao.telas.agendamento_dialog import AgendamentoDialog, ConverterEmOsDialog
from src.apresentacao.tema import ERRO, LARANJA, LARANJA_SUAVE, SUCESSO, TEXTO_SUAVE
from src.controle.agendamento_controller import (
    LIMITE_SIMULTANEOS,
    AgendamentoController,
    AgendamentoDTO,
    ErroDeNegocio,
    HoraDoDiaDTO,
    StatusAgendamento,
)

COLUNAS = ["Horário", "Cliente", "Veículo", "Serviço", "Situação"]
COL_HORARIO, COL_CLIENTE, COL_VEICULO, COL_SERVICO, COL_STATUS = range(5)

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
_COR_STATUS = {
    StatusAgendamento.AGENDADO: LARANJA,
    StatusAgendamento.CANCELADO: TEXTO_SUAVE,
    StatusAgendamento.CONCLUIDO: SUCESSO,
}


def _tabela(colunas: List[str]) -> QTableWidget:
    t = QTableWidget(0, len(colunas))
    t.setHorizontalHeaderLabels(colunas)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(36)
    t.horizontalHeader().setHighlightSections(False)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return t


class AgendamentosView(QWidget):
    def __init__(self, controller: Optional[AgendamentoController] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagina")
        self._controller = controller or AgendamentoController()
        self._dtos: List[AgendamentoDTO] = []
        self._montar_interface()
        self._conectar_sinais()

    # ------------------------------------------------------------------
    def _montar_interface(self) -> None:
        titulo = QLabel("Agendamentos")
        titulo.setObjectName("titulo")
        subtitulo = QLabel("Calendário da oficina: até 2 serviços ao mesmo tempo")
        subtitulo.setObjectName("subtitulo")
        bloco = QVBoxLayout()
        bloco.setSpacing(2)
        bloco.addWidget(titulo)
        bloco.addWidget(subtitulo)

        self._btn_novo = QPushButton("+  Novo agendamento")
        self._btn_novo.setObjectName("primario")
        self._btn_editar = QPushButton("Editar")
        self._btn_converter = QPushButton("Converter em OS")
        self._btn_cancelar = QPushButton("Cancelar agendamento")
        self._btn_cancelar.setObjectName("perigo")
        for b in (self._btn_editar, self._btn_converter, self._btn_cancelar):
            b.setEnabled(False)
        cabecalho = QHBoxLayout()
        cabecalho.addLayout(bloco)
        cabecalho.addStretch(1)
        for b in (self._btn_editar, self._btn_converter, self._btn_cancelar, self._btn_novo):
            cabecalho.addWidget(b, alignment=Qt.AlignmentFlag.AlignVCenter)

        # ---- coluna do calendário ----
        self._calendario = QCalendarWidget()
        self._calendario.setLocale(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
        self._calendario.setGridVisible(False)
        self._calendario.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._calendario.setFirstDayOfWeek(Qt.DayOfWeek.Sunday)
        self._calendario.setMinimumWidth(330)
        self._calendario.setMaximumWidth(380)
        self._btn_hoje = QPushButton("Hoje")
        legenda = QLabel("Dias em laranja têm serviço agendado.")
        legenda.setObjectName("subtitulo")
        legenda.setWordWrap(True)
        coluna_esq = QVBoxLayout()
        coluna_esq.setSpacing(8)
        coluna_esq.addWidget(self._calendario)
        coluna_esq.addWidget(legenda)
        coluna_esq.addWidget(self._btn_hoje, alignment=Qt.AlignmentFlag.AlignLeft)
        coluna_esq.addStretch(1)

        # ---- coluna do dia ----
        self._lbl_dia = QLabel()
        self._lbl_dia.setObjectName("titulo")
        self._lbl_resumo = QLabel()
        self._lbl_resumo.setObjectName("subtitulo")
        self._chk_cancelados = QCheckBox("Mostrar cancelados")
        titulo_dia = QVBoxLayout()
        titulo_dia.setSpacing(0)
        titulo_dia.addWidget(self._lbl_dia)
        titulo_dia.addWidget(self._lbl_resumo)
        topo_dia = QHBoxLayout()
        topo_dia.addLayout(titulo_dia)
        topo_dia.addStretch(1)
        topo_dia.addWidget(self._chk_cancelados, alignment=Qt.AlignmentFlag.AlignBottom)

        self._tabela = _tabela(COLUNAS)
        cab = self._tabela.horizontalHeader()
        for c in (COL_HORARIO, COL_VEICULO, COL_STATUS):
            cab.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(COL_CLIENTE, QHeaderView.ResizeMode.Stretch)
        cab.setSectionResizeMode(COL_SERVICO, QHeaderView.ResizeMode.Stretch)
        self._lbl_vazio = QLabel("Nenhum agendamento neste dia.")
        self._lbl_vazio.setObjectName("vazio")
        self._lbl_vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub_ocupacao = QLabel("Ocupação por horário")
        sub_ocupacao.setObjectName("titulo")
        self._grade = _tabela(["Horário", "Vagas", "Serviços"])
        self._grade.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        gcab = self._grade.horizontalHeader()
        gcab.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        gcab.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        gcab.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._grade.verticalHeader().setDefaultSectionSize(30)

        self._lbl_feedback = QLabel()
        self._lbl_feedback.setObjectName("feedbackOk")

        coluna_dir = QVBoxLayout()
        coluna_dir.setSpacing(8)
        coluna_dir.addLayout(topo_dia)
        coluna_dir.addWidget(self._tabela, stretch=3)
        coluna_dir.addWidget(self._lbl_vazio, stretch=3)
        coluna_dir.addWidget(sub_ocupacao)
        coluna_dir.addWidget(self._grade, stretch=4)
        coluna_dir.addWidget(self._lbl_feedback)

        corpo = QHBoxLayout()
        corpo.setSpacing(20)
        corpo.addLayout(coluna_esq)
        corpo.addLayout(coluna_dir, stretch=1)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(14)
        raiz.addLayout(cabecalho)
        raiz.addLayout(corpo, stretch=1)

    def _conectar_sinais(self) -> None:
        self._btn_novo.clicked.connect(self._novo)
        self._btn_editar.clicked.connect(self._editar)
        self._btn_converter.clicked.connect(self._converter)
        self._btn_cancelar.clicked.connect(self._cancelar)
        self._btn_hoje.clicked.connect(lambda: self._calendario.setSelectedDate(QDate.currentDate()))
        self._calendario.selectionChanged.connect(self.recarregar)
        self._calendario.currentPageChanged.connect(lambda _a, _m: self._marcar_dias())
        self._chk_cancelados.toggled.connect(lambda _c: self.recarregar())
        self._tabela.itemSelectionChanged.connect(self._atualizar_botoes)
        self._tabela.itemDoubleClicked.connect(lambda _i: self._editar())

    # ------------------------------------------------------------------
    def showEvent(self, evento) -> None:  # noqa: N802
        super().showEvent(evento)
        self.recarregar()

    def _dia(self) -> date:
        return self._calendario.selectedDate().toPyDate()

    def recarregar(self, selecionar: Optional[int] = None) -> None:
        dia = self._dia()
        try:
            self._dtos = self._controller.agenda_do_dia(dia, self._chk_cancelados.isChecked())
            grade = self._controller.ocupacao_do_dia(dia)
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível carregar os agendamentos.")
            return
        self._marcar_dias()
        self._preencher_dia(dia, selecionar)
        self._preencher_grade(grade)

    def _marcar_dias(self) -> None:
        """Destaca no calendário os dias do mês visível que têm serviço agendado."""
        try:
            ocupados = self._controller.dias_ocupados(self._calendario.yearShown(), self._calendario.monthShown())
        except Exception:  # noqa: BLE001
            return
        self._calendario.setDateTextFormat(QDate(), QTextCharFormat())  # limpa os destaques antigos
        formato = QTextCharFormat()
        formato.setBackground(QBrush(QColor(LARANJA_SUAVE)))
        formato.setForeground(QBrush(QColor(LARANJA)))
        formato.setFontWeight(QFont.Weight.Bold)
        for d in ocupados:
            self._calendario.setDateTextFormat(QDate(d.year, d.month, d.day), formato)

    def _preencher_dia(self, dia: date, selecionar: Optional[int]) -> None:
        # Ajuste de colunas desligado durante o preenchimento (evita o travamento quadrático).
        with preenchendo_tabela(self._tabela):
            self._preencher_dia_linhas(dia, selecionar)

    def _preencher_dia_linhas(self, dia: date, selecionar: Optional[int]) -> None:
        ativos = sum(1 for a in self._dtos if a.status is StatusAgendamento.AGENDADO)
        n = f"{ativos} agendamento" + ("" if ativos == 1 else "s")
        self._lbl_dia.setText(f"{DIAS[dia.weekday()].capitalize()}, {dia:%d/%m/%Y}")
        self._lbl_resumo.setText(n)
        self._tabela.blockSignals(True)
        self._tabela.setRowCount(len(self._dtos))
        linha_sel = -1
        for linha, a in enumerate(self._dtos):
            valores = [
                f"{a.data_hora:%H:%M} – {a.termino_previsto:%H:%M}",
                a.nome_cliente,
                f"{a.placa} – {a.modelo}",
                a.tipo_servico,
                a.status.rotulo,
            ]
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if coluna == COL_STATUS:
                    item.setForeground(QBrush(QColor(_COR_STATUS[a.status])))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self._tabela.setItem(linha, coluna, item)
            if a.id_agendamento == selecionar:
                linha_sel = linha
        self._tabela.blockSignals(False)
        if linha_sel >= 0:
            self._tabela.selectRow(linha_sel)
        else:
            self._tabela.clearSelection()
        self._tabela.setVisible(bool(self._dtos))
        self._lbl_vazio.setVisible(not self._dtos)
        self._atualizar_botoes()

    def _preencher_grade(self, grade: List[HoraDoDiaDTO]) -> None:
        # Ajuste de colunas desligado durante o preenchimento (evita o travamento quadrático).
        with preenchendo_tabela(self._grade):
            self._preencher_grade_linhas(grade)

    def _preencher_grade_linhas(self, grade: List[HoraDoDiaDTO]) -> None:
        self._grade.setRowCount(len(grade))
        for linha, h in enumerate(grade):
            if h.ocupacao >= LIMITE_SIMULTANEOS:
                texto, cor = f"{h.ocupacao} de {LIMITE_SIMULTANEOS} — lotado", ERRO
            elif h.ocupacao > 0:
                texto, cor = f"{h.ocupacao} de {LIMITE_SIMULTANEOS}", LARANJA
            else:
                texto, cor = "livre", SUCESSO
            servicos = "; ".join(f"{a.data_hora:%H:%M} {a.placa} {a.tipo_servico}" for a in h.agendamentos) or "—"
            for coluna, valor in enumerate((f"{h.hora:02d}:00", texto, servicos)):
                item = QTableWidgetItem(valor)
                if coluna == 1:
                    item.setForeground(QBrush(QColor(cor)))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self._grade.setItem(linha, coluna, item)

    def _selecionado(self) -> Optional[AgendamentoDTO]:
        linha = self._tabela.currentRow()
        if linha < 0 or not self._tabela.selectedItems() or linha >= len(self._dtos):
            return None
        return self._dtos[linha]

    def _atualizar_botoes(self) -> None:
        a = self._selecionado()
        ativo = a is not None and a.status is StatusAgendamento.AGENDADO
        for b in (self._btn_editar, self._btn_converter, self._btn_cancelar):
            b.setEnabled(ativo)

    def _feedback(self, texto: str) -> None:
        self._lbl_feedback.setText(texto)

    def _ir_para(self, a: AgendamentoDTO) -> None:
        """Vai para o dia do agendamento (útil depois de criar/mover para outra data)."""
        self._calendario.blockSignals(True)
        self._calendario.setSelectedDate(QDate(a.data_hora.year, a.data_hora.month, a.data_hora.day))
        self._calendario.blockSignals(False)
        self.recarregar(a.id_agendamento)

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _novo(self) -> None:
        d = AgendamentoDialog(self._controller, dia_inicial=self._dia(), parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self._ir_para(d.resultado)
            self._feedback(f"Agendamento #{d.resultado.id_agendamento} criado. Término previsto: "
                           f"{d.resultado.termino_previsto:%H:%M}.")

    def _editar(self) -> None:
        a = self._selecionado()
        if a is None or a.status is not StatusAgendamento.AGENDADO:
            return
        try:
            atual = self._controller.obter(a.id_agendamento)
        except ErroDeNegocio as exc:
            aviso(self, "Agendamento", str(exc))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível abrir o agendamento.")
            return
        d = AgendamentoDialog(self._controller, atual, parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self._ir_para(d.resultado)
            self._feedback(f"Agendamento #{d.resultado.id_agendamento} atualizado.")

    def _cancelar(self) -> None:
        a = self._selecionado()
        if a is None:
            return
        if not confirmar(
            self, "Cancelar agendamento",
            f"Cancelar o agendamento de {a.nome_cliente} ({a.placa}) em {a.data_hora:%d/%m às %H:%M}?\n"
            "O horário ficará livre para novos agendamentos.",
            "Cancelar agendamento", "Voltar",
        ):
            return
        try:
            self._controller.cancelar(a.id_agendamento)
        except ErroDeNegocio as exc:
            aviso(self, "Não foi possível cancelar", str(exc))
            self.recarregar()
            return
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível cancelar o agendamento.")
            return
        self.recarregar()
        self._feedback(f"Agendamento #{a.id_agendamento} cancelado; horário liberado.")

    def _converter(self) -> None:
        a = self._selecionado()
        if a is None:
            return
        d = ConverterEmOsDialog(self._controller, a, parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self.recarregar(d.resultado.id_agendamento)
            self._feedback(f"OS #{d.resultado.id_ordem_servico} criada em orçamento a partir do agendamento "
                           f"#{d.resultado.id_agendamento}. Abra “Ordens de Serviço” para lançar peças e mão de obra.")
