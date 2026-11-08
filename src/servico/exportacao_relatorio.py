"""
Exportação do relatório em CSV (RF06 / HU18).

HU18: "o arquivo exportado mantém os filtros aplicados na visualização". Por
isso o CSV começa com o período, o agrupamento e a data em que foi gerado, e
traz EXATAMENTE os números do Relatorio que a tela está mostrando (a tela e o
arquivo saem do mesmo objeto, não de duas consultas).

Formato pensado para o Excel em português:
- separador ";" (o Excel brasileiro usa a vírgula como decimal);
- valores com vírgula decimal e SEM separador de milhar (1234,56), para o
  Excel reconhecer como número;
- quem grava o arquivo usa UTF-8 COM BOM ("utf-8-sig"); sem o BOM o Excel
  abre os acentos quebrados.

É uma função pura (recebe o Relatorio, devolve texto): fácil de testar.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.servico.relatorio_service import Relatorio

TITULO = "Camaro - Gestão de Oficina Mecânica"
CODIFICACAO = "utf-8-sig"


def numero(valor: Decimal) -> str:
    """Decimal('1234.5') -> '1234,50' (formato que o Excel pt-BR lê como número)."""
    return f"{valor:.2f}".replace(".", ",")


def gerar_csv(relatorio: Relatorio, gerado_em: Optional[datetime] = None) -> str:
    gerado_em = gerado_em or datetime.now()
    r = relatorio.resumo
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")

    # --- cabeçalho com os filtros aplicados (HU18) ---
    w.writerow([TITULO])
    w.writerow(["Relatório de ganhos, gastos e serviços"])
    w.writerow(["Período", relatorio.descricao_periodo])
    w.writerow(["Gerado em", f"{gerado_em:%d/%m/%Y %H:%M}"])
    w.writerow(["Regra", "Entradas = OS entregues (data de entrega) + vendas por fora; "
                         "Saídas = compras - ressarcimentos de devolução"])
    w.writerow([])

    # --- resumo ---
    w.writerow(["RESUMO", "Valor (R$)"])
    for rotulo, valor in (
        (f"Receita das OS entregues ({r.qtd_os} OS)", r.receita_os),
        (f"Vendas por fora ({r.qtd_vendas})", r.vendas_avulsas),
        ("Entradas", r.entradas),
        (f"Compras ({r.qtd_compras})", r.compras),
        ("Ressarcimentos de devolução", r.ressarcimentos),
        ("Saídas", r.saidas),
        ("Saldo de caixa", r.saldo),
        ("Custo das peças usadas nas OS (CMV)", r.custo_pecas),
        ("Lucro bruto das OS", r.lucro_bruto_os),
        (f"A receber ({r.qtd_a_receber} OS aguardando pagamento)", r.a_receber),
    ):
        w.writerow([rotulo, numero(valor)])
    if r.pecas_sem_custo:
        w.writerow([f"Atenção: {r.pecas_sem_custo} peça(s) sem custo registrado entraram com custo zero"])
    w.writerow([])

    # --- por período ---
    w.writerow(["ENTRADAS X SAÍDAS", "OS entregues", "Receita das OS (R$)", "Vendas por fora (R$)",
                "Entradas (R$)", "Compras (R$)", "Ressarcimentos (R$)", "Saídas (R$)", "Saldo (R$)"])
    for p in relatorio.pontos:
        w.writerow([p.rotulo, p.qtd_os, numero(p.receita_os), numero(p.vendas_avulsas),
                    numero(p.entradas), numero(p.compras), numero(p.ressarcimentos),
                    numero(p.saidas), numero(p.saldo)])
    w.writerow(["Total", r.qtd_os, numero(r.receita_os), numero(r.vendas_avulsas),
                numero(r.entradas), numero(r.compras), numero(r.ressarcimentos),
                numero(r.saidas), numero(r.saldo)])
    w.writerow([])

    # --- serviços ---
    w.writerow(["SERVIÇOS MAIS PRESTADOS (OS entregues)", "Quantidade de OS",
                "Faturamento (R$)", "Ticket médio (R$)"])
    if not relatorio.servicos:
        w.writerow(["Nenhuma OS entregue no período"])
    for s in relatorio.servicos:
        w.writerow([s.tipo, s.quantidade, numero(s.faturamento), numero(s.ticket_medio)])
    return saida.getvalue()
