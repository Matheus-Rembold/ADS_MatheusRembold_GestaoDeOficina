"""
Exportação do relatório em PDF (RF06 / HU18).

Usa o QPdfWriter do próprio Qt: nenhuma biblioteca nova no executável
(RNF07). Fica na camada de apresentação porque DESENHA (fontes, gráficos,
páginas); os números vêm prontos do mesmo Relatorio que a tela mostra.

Conteúdo, nesta ordem: cabeçalho com o período e a data de geração (HU18:
mantém os filtros), resumo, os dois gráficos e as duas tabelas. Quebra de
página automática quando a tabela não cabe.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence

from PyQt6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PyQt6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen
from PyQt6.QtWidgets import QGraphicsScene

from src.apresentacao.componentes import formatar_moeda, formatar_moeda_com_sinal
from src.apresentacao.graficos_relatorio import grafico_financeiro, grafico_servicos
from src.apresentacao.tema import BORDA, ERRO, LARANJA, TEXTO, TEXTO_SUAVE
from src.controle.relatorio_controller import Relatorio

TITULO = "Camaro — Gestão de Oficina Mecânica"
_RESOLUCAO = 120  # dpi: suficiente para impressão sem gerar arquivo enorme


class _Pagina:
    """Cursor de escrita: guarda a posição vertical e cria página nova quando enche."""

    def __init__(self, escritor: QPdfWriter, pintor: QPainter) -> None:
        self.escritor, self.pintor = escritor, pintor
        self.largura = escritor.width()
        self.altura = escritor.height()
        self.y = 0.0

    def mm(self, valor: float) -> float:
        return valor * _RESOLUCAO / 25.4

    def garantir(self, altura: float) -> None:
        if self.y + altura > self.altura:
            self.escritor.newPage()
            self.y = 0.0

    def texto(self, conteudo: str, tamanho: float = 9, negrito: bool = False,
              cor: str = TEXTO, espaco_depois: float = 1.5) -> None:
        fonte = QFont("Segoe UI")
        fonte.setPointSizeF(tamanho)
        fonte.setBold(negrito)
        self.pintor.setFont(fonte)
        altura = self.pintor.fontMetrics().height()
        self.garantir(altura)
        self.pintor.setPen(QColor(cor))
        self.pintor.drawText(QRectF(0, self.y, self.largura, altura),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, conteudo)
        self.y += altura + self.mm(espaco_depois)

    def linha(self) -> None:
        self.pintor.setPen(QPen(QColor(BORDA), 1))
        self.pintor.drawLine(0, int(self.y), int(self.largura), int(self.y))
        self.y += self.mm(2)

    def secao(self, titulo: str) -> None:
        """Título de seção nunca fica sozinho no pé da página: exige espaço para algumas linhas."""
        self.garantir(self.mm(30))
        self.texto(titulo, 11, True, TEXTO, 2)

    def grafico(self, chart, altura_mm: float) -> None:
        """
        Desenha o gráfico numa cena com tamanho FIXO (em pixels de tela) e escala
        para a área do papel. Usar um QChartView que nunca foi exibido não
        funciona: ele não tem tamanho e o gráfico sai minúsculo.
        """
        altura = self.mm(altura_mm)
        self.garantir(altura)
        largura_px = 900.0
        altura_px = largura_px * altura / self.largura  # mesma proporção da área no papel
        cena = QGraphicsScene()
        cena.addItem(chart)
        chart.resize(QSizeF(largura_px, altura_px))
        if chart.layout() is not None:
            chart.layout().activate()  # aplica o tamanho novo antes de desenhar
        self.pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        cena.render(self.pintor, QRectF(0, self.y, self.largura, altura), QRectF(0, 0, largura_px, altura_px))
        cena.removeItem(chart)
        chart.deleteLater()
        self.y += altura + self.mm(4)

    def tabela(self, cabecalho: Sequence[str], linhas: List[Sequence[str]],
               larguras: Sequence[float], destacar_ultima: bool = False) -> None:
        fonte = QFont("Segoe UI")
        fonte.setPointSizeF(8.5)
        self.pintor.setFont(fonte)
        altura = self.pintor.fontMetrics().height() * 1.45
        total = sum(larguras)
        xs, x = [], 0.0
        for w in larguras:
            xs.append(x)
            x += self.largura * w / total

        def desenhar(celulas, negrito, cor_texto):
            fonte.setBold(negrito)
            self.pintor.setFont(fonte)
            self.pintor.setPen(QColor(cor_texto))
            for i, valor in enumerate(celulas):
                w = self.largura * larguras[i] / total
                alinhamento = (Qt.AlignmentFlag.AlignLeft if i == 0 else Qt.AlignmentFlag.AlignRight) \
                    | Qt.AlignmentFlag.AlignVCenter
                self.pintor.drawText(QRectF(xs[i] + 4, self.y, w - 8, altura), alinhamento, str(valor))
            self.y += altura

        def cabecalho_tabela():
            desenhar(cabecalho, True, TEXTO_SUAVE)
            self.linha()

        self.garantir(altura * 3)
        cabecalho_tabela()
        for n, celulas in enumerate(linhas):
            if self.y + altura > self.altura:  # quebra de página repete o cabeçalho
                self.escritor.newPage()
                self.y = 0.0
                cabecalho_tabela()
            ultima = destacar_ultima and n == len(linhas) - 1
            desenhar(celulas, ultima, TEXTO)
        self.y += self.mm(4)


def salvar_pdf(relatorio: Relatorio, caminho: str, gerado_em: Optional[datetime] = None) -> None:
    gerado_em = gerado_em or datetime.now()
    escritor = QPdfWriter(caminho)
    escritor.setResolution(_RESOLUCAO)
    escritor.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                       QPageLayout.Orientation.Portrait, QMarginsF(15, 15, 15, 15)))
    escritor.setTitle("Relatório Camaro")
    escritor.setCreator(TITULO)

    pintor = QPainter(escritor)
    try:
        pg = _Pagina(escritor, pintor)
        r = relatorio.resumo

        # --- cabeçalho: os filtros aplicados na tela (HU18) ---
        pg.texto(TITULO, 9, True, LARANJA, 0.5)
        pg.texto("Relatório de ganhos, gastos e serviços", 16, True, TEXTO, 1)
        pg.texto(f"Período: {relatorio.descricao_periodo}", 10, False, TEXTO, 0.5)
        pg.texto(f"Gerado em {gerado_em:%d/%m/%Y às %H:%M}", 8.5, False, TEXTO_SUAVE, 2)
        pg.linha()

        # --- resumo ---
        pg.secao("Resumo")
        resumo = [
            ("Entradas", r.entradas, f"{r.qtd_os} OS entregues ({formatar_moeda(r.receita_os)}) + "
                                     f"{r.qtd_vendas} vendas por fora ({formatar_moeda(r.vendas_avulsas)})"),
            ("Saídas (compras)", r.saidas, f"{r.qtd_compras} compras ({formatar_moeda(r.compras)}) − "
                                           f"ressarcimentos ({formatar_moeda(r.ressarcimentos)})"),
            ("Saldo de caixa", r.saldo, "entradas − saídas"),
            ("Lucro bruto das OS", r.lucro_bruto_os, f"receita das OS − custo das peças ({formatar_moeda(r.custo_pecas)})"),
            ("A receber", r.a_receber, f"{r.qtd_a_receber} OS aguardando pagamento (todas, sem filtro de data)"),
        ]
        for rotulo, valor, detalhe in resumo:
            cor = ERRO if valor < 0 else TEXTO
            pg.texto(f"{rotulo}: {formatar_moeda_com_sinal(valor)}   ({detalhe})", 9.5, False, cor, 1)
        if r.pecas_sem_custo:
            pg.texto(f"Atenção: {r.pecas_sem_custo} peça(s) sem custo registrado entraram com custo zero "
                     "no lucro bruto.", 8.5, True, ERRO, 1)
        pg.y += pg.mm(3)

        # --- gráficos ---
        pg.grafico(grafico_financeiro(relatorio), 85)
        altura_servicos = 30 + 8 * max(len(relatorio.servicos), 1)
        pg.grafico(grafico_servicos(relatorio), min(altura_servicos, 110))

        # --- tabelas ---
        pg.secao("Entradas x Saídas")
        m = formatar_moeda_com_sinal
        linhas = [[p.rotulo, str(p.qtd_os), m(p.receita_os), m(p.vendas_avulsas), m(p.entradas), m(p.saidas), m(p.saldo)]
                  for p in relatorio.pontos]
        linhas.append(["Total", str(r.qtd_os), m(r.receita_os), m(r.vendas_avulsas), m(r.entradas), m(r.saidas), m(r.saldo)])
        pg.tabela(["Período", "OS", "Receita OS", "Vendas por fora", "Entradas", "Saídas", "Saldo"],
                  linhas, [1.1, 0.6, 1.4, 1.4, 1.4, 1.4, 1.4], destacar_ultima=True)

        pg.secao("Serviços mais prestados (OS entregues)")
        if relatorio.servicos:
            pg.tabela(["Serviço", "OS", "Faturamento", "Ticket médio"],
                      [[s.tipo, str(s.quantidade), formatar_moeda(s.faturamento), formatar_moeda(s.ticket_medio)]
                       for s in relatorio.servicos],
                      [3.2, 0.8, 1.5, 1.5])
        else:
            pg.texto("Nenhuma OS entregue no período.", 9, False, TEXTO_SUAVE)
    finally:
        pintor.end()
