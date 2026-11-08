"""
Montagem dos gráficos do RF06 com PyQt6-Charts.

Usado pela tela de Relatórios E pelo PDF: os dois desenham com o mesmo
código, então o que se imprime é exatamente o que se vê.

Decisões de visualização (CLAUDE.md, seção 5 / RF06):
- Entradas x Saídas: COLUNAS AGRUPADAS, um eixo só (R$). Empilhar seria
  errado (entrada e saída não se somam) e dois eixos enganam o leitor.
- Serviços: BARRAS HORIZONTAIS em ordem decrescente (nomes longos cabem
  melhor na horizontal; pizza compara mal fatias parecidas).
- Cor nunca sozinha: legenda com texto, tooltip com o valor exato e, na tela,
  a tabela com os mesmos números (Nielsen: reconhecer em vez de lembrar;
  acessibilidade para daltonismo).
- Sem animação: o gráfico aparece pronto (RNF01, interface ágil) e o PDF
  nunca captura um quadro no meio da animação.
"""
from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QHorizontalBarSeries,
    QValueAxis,
)
from PyQt6.QtCore import QMargins, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QPen
from PyQt6.QtWidgets import QToolTip

from src.apresentacao.componentes import formatar_moeda
from src.apresentacao.tema import (
    COR_ENTRADAS,
    COR_GRADE,
    COR_SAIDAS,
    COR_SERIE_UNICA,
    TEXTO,
    TEXTO_SUAVE,
)
from src.controle.relatorio_controller import AGRUPA_DIA, Relatorio


FAMILIA = "Segoe UI"  # o QSS do tema não chega dentro do QChart: a fonte é passada aqui


def _fonte(tamanho: float, negrito: bool = False) -> QFont:
    fonte = QFont(FAMILIA)
    fonte.setPointSizeF(tamanho)
    fonte.setBold(negrito)
    return fonte


def _grafico_base(titulo: str) -> QChart:
    grafico = QChart()
    grafico.setTitle(titulo)
    grafico.setTitleFont(_fonte(10.5, True))
    grafico.setTitleBrush(QColor(TEXTO))
    grafico.setAnimationOptions(QChart.AnimationOption.NoAnimation)
    grafico.setBackgroundVisible(False)
    grafico.setMargins(QMargins(4, 4, 4, 4))
    grafico.legend().setLabelColor(QColor(TEXTO))
    grafico.legend().setFont(_fonte(9))
    return grafico


def _eixo_valor(minimo: float, maximo: float, formato: str) -> QValueAxis:
    eixo = QValueAxis()
    if maximo <= minimo:  # período sem movimento: escala 0..1 em vez de eixo "achatado"
        maximo = minimo + 1
    eixo.setRange(minimo, maximo)
    eixo.applyNiceNumbers()
    eixo.setLabelFormat(formato)
    eixo.setLabelsColor(QColor(TEXTO_SUAVE))
    eixo.setLabelsFont(_fonte(8.5))
    eixo.setGridLineColor(QColor(COR_GRADE))
    eixo.setLinePen(QPen(Qt.PenStyle.NoPen))  # eixo discreto: os dados chamam a atenção
    return eixo


def grafico_financeiro(relatorio: Relatorio) -> QChart:
    """Colunas agrupadas: Entradas (laranja) x Saídas (grafite) por dia ou mês."""
    grafico = _grafico_base("Entradas x Saídas por " + ("dia" if relatorio.agrupamento == AGRUPA_DIA else "mês"))
    entradas = QBarSet("Entradas")
    saidas = QBarSet("Saídas (compras)")
    for barra, cor in ((entradas, COR_ENTRADAS), (saidas, COR_SAIDAS)):
        barra.setColor(QColor(cor))
        barra.setBorderColor(QColor(cor))
    for p in relatorio.pontos:
        entradas.append(float(p.entradas))
        saidas.append(float(p.saidas))

    serie = QBarSeries()
    serie.append(entradas)
    serie.append(saidas)
    serie.setBarWidth(0.75)
    grafico.addSeries(serie)

    rotulos = [p.rotulo for p in relatorio.pontos]
    eixo_x = QBarCategoryAxis()
    # No eixo, "dez/25" vira duas linhas ("dez" / "25"): cabe na horizontal sem
    # inclinar (inclinado, o 1º e o último mês saíam da borda e sumiam).
    # Acima de 16 rótulos (ex.: 2 meses por dia) eles ficam em pé, numa linha só.
    em_pe = len(rotulos) > 16
    eixo_x.append([r if em_pe else r.replace("/", "<br>") for r in rotulos])
    eixo_x.setLabelsColor(QColor(TEXTO_SUAVE))
    eixo_x.setGridLineVisible(False)
    eixo_x.setLabelsFont(_fonte(8.5))
    eixo_x.setTruncateLabels(False)  # "dez/25" inteiro, nunca "de…"
    if em_pe:
        eixo_x.setLabelsAngle(-90)
        eixo_x.setLabelsFont(_fonte(7))
    grafico.addAxis(eixo_x, Qt.AlignmentFlag.AlignBottom)
    serie.attachAxis(eixo_x)

    valores = [float(p.entradas) for p in relatorio.pontos] + [float(p.saidas) for p in relatorio.pontos]
    eixo_y = _eixo_valor(min(0.0, *valores) if valores else 0.0, max(valores, default=0.0), "R$ %.0f")
    grafico.addAxis(eixo_y, Qt.AlignmentFlag.AlignLeft)
    serie.attachAxis(eixo_y)

    grafico.legend().setAlignment(Qt.AlignmentFlag.AlignTop)

    def ao_passar(dentro: bool, indice: int, barra: QBarSet) -> None:
        if dentro and 0 <= indice < len(rotulos):
            valor = Decimal(str(barra.at(indice))).quantize(Decimal("0.01"))
            QToolTip.showText(QCursor.pos(), f"{rotulos[indice]} · {barra.label()}: {formatar_moeda(valor)}")
        else:
            QToolTip.hideText()

    serie.hovered.connect(ao_passar)
    return grafico


def grafico_servicos(relatorio: Relatorio) -> QChart:
    """Barras horizontais: quantidade de OS entregues por tipo de serviço."""
    grafico = _grafico_base("Serviços mais prestados (OS entregues)")
    servicos = list(relatorio.servicos)
    barra = QBarSet("OS entregues")
    barra.setColor(QColor(COR_SERIE_UNICA))
    barra.setBorderColor(QColor(COR_SERIE_UNICA))
    barra.setLabelColor(QColor(TEXTO))  # o número ao lado da barra usa cor de texto, não a da série
    barra.setLabelFont(_fonte(8.5, True))
    # O eixo horizontal desenha o 1º item EMBAIXO; invertendo, o mais prestado fica no topo.
    for s in reversed(servicos):
        barra.append(s.quantidade)

    serie = QHorizontalBarSeries()
    serie.append(barra)
    serie.setBarWidth(0.65)
    serie.setLabelsVisible(True)
    serie.setLabelsPosition(QHorizontalBarSeries.LabelsPosition.LabelsOutsideEnd)
    serie.setLabelsFormat("@value")
    grafico.addSeries(serie)
    grafico.legend().setVisible(False)  # uma série só: o título já diz o que é

    eixo_y = QBarCategoryAxis()
    # nomes longos são cortados no gráfico (completos na tabela e no tooltip)
    eixo_y.append([s.tipo if len(s.tipo) <= 24 else s.tipo[:23] + "…" for s in reversed(servicos)])
    eixo_y.setLabelsColor(QColor(TEXTO))
    eixo_y.setLabelsFont(_fonte(9))
    eixo_y.setTruncateLabels(False)  # sem isso o Qt troca nomes inteiros por "…"
    eixo_y.setGridLineVisible(False)
    eixo_y.setLinePen(QPen(Qt.PenStyle.NoPen))
    grafico.addAxis(eixo_y, Qt.AlignmentFlag.AlignLeft)
    serie.attachAxis(eixo_y)

    maior = max((s.quantidade for s in servicos), default=0)
    eixo_x = _eixo_valor(0, maior * 1.15 if maior else 1, "%d")
    grafico.addAxis(eixo_x, Qt.AlignmentFlag.AlignBottom)
    serie.attachAxis(eixo_x)

    nomes = [s for s in reversed(servicos)]

    def ao_passar(dentro: bool, indice: int, _barra: QBarSet) -> None:
        if dentro and 0 <= indice < len(nomes):
            s = nomes[indice]
            QToolTip.showText(
                QCursor.pos(),
                f"{s.tipo}: {s.quantidade} OS · {formatar_moeda(s.faturamento)} "
                f"(ticket médio {formatar_moeda(s.ticket_medio)})",
            )
        else:
            QToolTip.hideText()

    serie.hovered.connect(ao_passar)
    return grafico
