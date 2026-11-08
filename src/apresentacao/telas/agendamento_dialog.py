"""
Janelas do RF05: novo/editar agendamento e converter agendamento em OS.

Decisões de usabilidade (Nielsen):
- Prevenção de erros: o veículo só lista os do cliente escolhido; a duração é
  um campo numérico com limites; a janela já mostra, ANTES de salvar, quantas
  das 2 vagas do horário estão ocupadas.
- Visibilidade do estado do sistema: "Previsão de término" atualiza enquanto
  o usuário muda hora e duração (é a resposta ao "quanto tempo o veículo
  fica na oficina", do RF05).
- Ajuda para se recuperar de erros: a janela não fecha quando há erro (ex.:
  horário lotado); o que foi digitado fica.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from PyQt6.QtCore import QDate, QLocale, Qt, QTime
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
)

from src.apresentacao.componentes import confirmar
from src.apresentacao.tema import ERRO, SUCESSO
from src.controle.agendamento_controller import (
    LIMITE_SIMULTANEOS,
    AgendamentoController,
    AgendamentoDTO,
    ErroDeNegocio,
    ValidacaoError,
)

logger = logging.getLogger(__name__)


def _mostrar_erros(rotulo: QLabel, erros: List[str]) -> None:
    if erros:
        rotulo.setText("\n".join(f"• {e}" for e in erros))
        rotulo.show()
    else:
        rotulo.clear()
        rotulo.hide()


def _rotulo_erro() -> QLabel:
    r = QLabel()
    r.setObjectName("erroForm")
    r.setWordWrap(True)
    r.setTextFormat(Qt.TextFormat.PlainText)
    r.hide()
    return r


class AgendamentoDialog(QDialog):
    def __init__(
        self,
        controller: AgendamentoController,
        agendamento: Optional[AgendamentoDTO] = None,
        dia_inicial: Optional[date] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._ag = agendamento
        self.resultado: Optional[AgendamentoDTO] = None
        self.setWindowTitle("Novo agendamento" if agendamento is None
                            else f"Editar agendamento #{agendamento.id_agendamento}")
        self.setModal(True)
        self.setMinimumWidth(520)

        self._cliente = QComboBox()
        self._veiculo = QComboBox()
        self._tipo = QComboBox()
        self._tipo.setEditable(True)
        self._tipo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._tipo.lineEdit().setMaxLength(150)
        self._tipo.lineEdit().setPlaceholderText("Ex.: Revisão, Freios, Alinhamento")
        self._data = QDateEdit()
        self._data.setCalendarPopup(True)
        self._data.setDisplayFormat("dd/MM/yyyy")
        self._hora = QTimeEdit(QTime(8, 0))
        self._hora.setDisplayFormat("HH:mm")
        self._duracao = QDoubleSpinBox()
        self._duracao.setRange(0.25, 12.0)
        self._duracao.setSingleStep(0.25)
        self._duracao.setDecimals(2)
        self._duracao.setSuffix(" h")
        self._duracao.setLocale(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))  # vírgula decimal
        self._duracao.setValue(1.0)

        self._termino = QLabel()
        self._vagas = QLabel()
        self._vagas.setWordWrap(True)
        self._erro = _rotulo_erro()

        quando = QHBoxLayout()
        quando.addWidget(self._data, stretch=2)
        quando.addWidget(self._hora, stretch=1)
        quando.addWidget(self._duracao, stretch=1)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(10)
        form.addRow("Cliente *", self._cliente)
        form.addRow("Veículo *", self._veiculo)
        form.addRow("Serviço *", self._tipo)
        form.addRow("Data, hora e duração *", quando)

        self._btn_cancelar = QPushButton("Cancelar")
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
        layout.addLayout(form)
        layout.addWidget(self._termino)
        layout.addWidget(self._vagas)
        layout.addWidget(self._erro)
        layout.addLayout(botoes)

        self._carregar_listas()
        hoje = QDate.currentDate()
        if agendamento is None:
            dia = QDate(dia_inicial.year, dia_inicial.month, dia_inicial.day) if dia_inicial else hoje
            self._data.setMinimumDate(hoje)
            self._data.setDate(max(dia, hoje))
        else:
            self._preencher(agendamento)

        self._cliente.currentIndexChanged.connect(self._ao_trocar_cliente)
        for sinal in (self._data.dateChanged, self._hora.timeChanged, self._duracao.valueChanged):
            sinal.connect(lambda *_a: self._atualizar_previsao())
        self._atualizar_previsao()

    # ------------------------------------------------------------------
    def _carregar_listas(self) -> None:
        try:
            clientes = self._controller.listar_clientes()
            tipos = self._controller.listar_tipos_servico()
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao carregar listas do agendamento")
            clientes, tipos = [], []
            _mostrar_erros(self._erro, ["Não foi possível carregar os clientes. Verifique a conexão com o banco."])
        self._cliente.blockSignals(True)
        self._cliente.addItem("Selecione o cliente…", None)
        for c in clientes:
            self._cliente.addItem(c.nome, c.id_cliente)
        self._cliente.blockSignals(False)
        self._veiculo.addItem("Escolha primeiro o cliente", None)
        self._tipo.addItems(tipos)
        self._tipo.setCurrentIndex(-1)

    def _preencher(self, a: AgendamentoDTO) -> None:
        self._cliente.setCurrentIndex(max(self._cliente.findData(a.id_cliente), 0))
        idx = self._veiculo.findData(a.id_veiculo)
        if idx >= 0:
            self._veiculo.setCurrentIndex(idx)
        self._tipo.setCurrentText(a.tipo_servico)
        self._data.setDate(QDate(a.data_hora.year, a.data_hora.month, a.data_hora.day))
        self._hora.setTime(QTime(a.data_hora.hour, a.data_hora.minute))
        if a.duracao_horas is not None:
            self._duracao.setValue(float(a.duracao_horas))

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

    def _data_hora(self) -> datetime:
        d, h = self._data.date(), self._hora.time()
        return datetime(d.year(), d.month(), d.day(), h.hour(), h.minute())

    def _atualizar_previsao(self) -> None:
        inicio = self._data_hora()
        fim = inicio + timedelta(minutes=round(self._duracao.value() * 60))
        mesmo_dia = fim.date() == inicio.date()
        self._termino.setText(
            f"Previsão de término: {fim:%H:%M}" if mesmo_dia else f"Previsão de término: {fim:%d/%m} às {fim:%H:%M}"
        )
        try:
            ocupados = self._controller.ocupacao_no_intervalo(
                inicio, self._duracao.value(), self._ag.id_agendamento if self._ag else None
            )
        except Exception:  # noqa: BLE001
            ocupados = None
        if ocupados is None:
            self._vagas.setText("")
        elif ocupados >= LIMITE_SIMULTANEOS:
            self._vagas.setStyleSheet(f"color: {ERRO}; font-weight: 600;")
            self._vagas.setText(f"Horário lotado: {ocupados} de {LIMITE_SIMULTANEOS} vagas ocupadas. Escolha outro horário.")
        else:
            self._vagas.setStyleSheet(f"color: {SUCESSO}; font-weight: 600;")
            self._vagas.setText(f"Vagas ocupadas neste horário: {ocupados} de {LIMITE_SIMULTANEOS}.")

    # ------------------------------------------------------------------
    def _salvar(self) -> None:
        _mostrar_erros(self._erro, [])
        args = (
            self._cliente.currentData(), self._veiculo.currentData(), self._tipo.currentText(),
            self._data_hora(), self._duracao.value(),
        )
        try:
            if self._ag is None:
                self.resultado = self._controller.criar(*args)
            else:
                self.resultado = self._controller.atualizar(self._ag.id_agendamento, *args)
        except ValidacaoError as exc:
            _mostrar_erros(self._erro, exc.erros)
        except ErroDeNegocio as exc:
            _mostrar_erros(self._erro, [str(exc)])
        except Exception:
            logger.exception("Falha inesperada ao salvar o agendamento")
            _mostrar_erros(self._erro, ["Não foi possível salvar. Verifique a conexão com o banco de dados e tente novamente."])
        else:
            self.accept()


class ConverterEmOsDialog(QDialog):
    """Pede os dois dados que a OS exige e o agendamento não tem: quilometragem e problema."""

    def __init__(self, controller: AgendamentoController, agendamento: AgendamentoDTO, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._ag = agendamento
        self.resultado: Optional[AgendamentoDTO] = None
        self.setWindowTitle(f"Converter agendamento #{agendamento.id_agendamento} em OS")
        self.setModal(True)
        self.setMinimumWidth(480)

        resumo = QLabel(
            f"<b>{agendamento.nome_cliente}</b><br>{agendamento.placa} – {agendamento.modelo}<br>"
            f"{agendamento.tipo_servico} • {agendamento.data_hora:%d/%m/%Y %H:%M}"
        )
        self._km = QLineEdit()
        self._km.setValidator(QIntValidator(0, 10_000_000, self))
        self._km.setPlaceholderText("Ex.: 52000")
        self._problema = QPlainTextEdit(agendamento.tipo_servico)
        self._problema.setFixedHeight(70)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Quilometragem *", self._km)
        form.addRow("Problema *", self._problema)

        nota = QLabel("A OS é criada em “Somente orçamento” com cliente, veículo e serviço deste "
                      "agendamento. Depois, é só abrir a OS e lançar as peças e a mão de obra.")
        nota.setObjectName("subtitulo")
        nota.setWordWrap(True)
        self._erro = _rotulo_erro()

        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        self._ok = QPushButton("Criar OS")
        self._ok.setObjectName("primario")
        self._ok.setDefault(True)
        self._ok.clicked.connect(self._converter)
        botoes = QHBoxLayout()
        botoes.addStretch()
        botoes.addWidget(cancelar)
        botoes.addWidget(self._ok)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(resumo)
        layout.addLayout(form)
        layout.addWidget(nota)
        layout.addWidget(self._erro)
        layout.addLayout(botoes)

    def _converter(self) -> None:
        _mostrar_erros(self._erro, [])
        texto = self._km.text().strip()
        km = int(texto) if texto else None
        try:
            aviso = self._controller.aviso_quilometragem(self._ag.id_veiculo, km)
        except Exception:  # noqa: BLE001
            aviso = None
        if aviso and not confirmar(self, "Quilometragem", aviso + "\n\nDeseja continuar mesmo assim?", "Continuar"):
            return
        try:
            self.resultado = self._controller.converter_em_os(
                self._ag.id_agendamento, km, self._problema.toPlainText()
            )
        except ValidacaoError as exc:
            _mostrar_erros(self._erro, exc.erros)
        except ErroDeNegocio as exc:
            _mostrar_erros(self._erro, [str(exc)])
        except Exception:
            logger.exception("Falha inesperada ao converter agendamento em OS")
            _mostrar_erros(self._erro, ["Não foi possível converter. Verifique a conexão com o banco de dados e tente novamente."])
        else:
            self.accept()
