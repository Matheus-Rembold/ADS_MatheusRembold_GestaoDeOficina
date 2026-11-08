"""
Teste manual do RelatorioService contra o banco real (RF06 - Relatórios).

Rode da raiz do projeto, com o venv ativo:
    python testar_relatorio_service.py

PRÉ-REQUISITO: rodar uma vez o migrar_relatorios.sql (ou criar o banco com o
BancoDeDadods.sql atualizado). O índice não muda os números; só a velocidade.

ISOLAMENTO: todos os dados de teste ficam no ANO DE 2001, que nenhum outro
dado usa (nem o seed, nem os dados de exemplo). Assim as contas abaixo são
exatas mesmo num banco com movimento real. O "a receber" não tem filtro de
data, então é conferido pela DIFERENÇA antes/depois.

Os dados são gravados direto pela sessão (não pelos serviços), porque o teste
precisa fixar datas de entrega no passado; no fim, tudo é apagado.

Contas esperadas (conferíveis à mão):
  OS1 entregue 10/03/2001  "Freios"    peças 2 x 25 (custo 10) + MO 100 = 150 (CMV 20)
  OS2 entregue 31/03/2001 23:59:59 " FREIOS " só MO 50                 =  50
  OS3 entregue 01/04/2001 00:00   "Revisão"   1 x 40 (SEM custo) + 200 = 240
  OS4 PRONTO (sem data) MO 999                                  -> fora de tudo
  OS5 AGUARDANDO PAGAMENTO 1 x 30 + MO 70                       -> só "a receber" (100)
  OS6 entregue 15/06/2001  tipo vazio  MO 10                           =  10
  compras 05/03 R$ 300 e 01/05 R$ 100 | venda por fora 20/03 R$ 45
  devolução 10/04 ressarcida R$ 30 e 11/04 sem valor
"""
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select

from src.config.database import engine, get_session
from src.controle.relatorio_controller import RelatorioController
from src.persistencia.models import (
    Cliente, MovimentacaoEstoque, OrdemServico, OsProduto, Produto,
    StatusOrdemServico, TipoMovimentacao, Veiculo,
)
from src.servico.excecoes import ValidacaoError
from src.servico.exportacao_relatorio import gerar_csv
from src.servico.relatorio_service import (
    AGRUPA_DIA, AGRUPA_MES, ANO_PASSADO, ESTE_ANO, ESTE_MES, MES_PASSADO, ROTULO_OUTROS,
    ROTULO_SEM_TIPO, ULTIMOS_12_MESES, RelatorioService, periodo_predefinido, rotulo_periodo,
)

engine.echo = False

S = StatusOrdemServico
T = TipoMovimentacao
CPF = "REL-TESTE-01"
PLACA = "RELT001"
NOME_PX, NOME_PY = "Peça Relatório Teste X", "Peça Relatório Teste Y"
D = Decimal

resultados = []


def verificar(descricao: str, condicao: bool) -> None:
    resultados.append(condicao)
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}")


def esperar_erro(descricao: str, tipo_esperado, funcao) -> None:
    try:
        funcao()
    except tipo_esperado as erro:
        verificar(f"{descricao} -> {tipo_esperado.__name__}: {str(erro).splitlines()[0]}", True)
    except Exception as erro:  # noqa: BLE001
        verificar(f"{descricao} -> erro inesperado {type(erro).__name__}: {erro}", False)
    else:
        verificar(f"{descricao} -> deveria ter levantado {tipo_esperado.__name__}", False)


def limpar() -> None:
    with get_session() as s:
        ids_p = list(s.scalars(select(Produto.id_produto).where(Produto.nome.in_([NOME_PX, NOME_PY]))))
        ids_c = list(s.scalars(select(Cliente.id_cliente).where(Cliente.cpf == CPF)))
        ids_os = list(s.scalars(select(OrdemServico.id_ordem_servico).where(
            OrdemServico.id_cliente.in_(ids_c)))) if ids_c else []
        if ids_os:
            s.execute(delete(OsProduto).where(OsProduto.id_ordem_servico.in_(ids_os)))
            s.execute(delete(OrdemServico).where(OrdemServico.id_ordem_servico.in_(ids_os)))
        if ids_p:
            s.execute(delete(MovimentacaoEstoque).where(MovimentacaoEstoque.id_produto.in_(ids_p)))
            s.execute(delete(OsProduto).where(OsProduto.id_produto.in_(ids_p)))
            s.execute(delete(Produto).where(Produto.id_produto.in_(ids_p)))
        if ids_c:
            s.execute(delete(Veiculo).where(Veiculo.id_cliente.in_(ids_c)))
            s.execute(delete(Cliente).where(Cliente.id_cliente.in_(ids_c)))
        s.commit()


def criar_dados(s) -> None:
    c = Cliente(nome="Cliente Relatório Teste", cpf=CPF, contato="54999990099")
    s.add(c)
    s.flush()
    v = Veiculo(id_cliente=c.id_cliente, modelo="Teste", marca="Teste", placa=PLACA)
    px = Produto(nome=NOME_PX, quantidade=100, valor_unitario=D("10"))
    py = Produto(nome=NOME_PY, quantidade=100)
    s.add_all([v, px, py])
    s.flush()

    def os_(tipo, mo, status, entregue=None, itens=()):
        o = OrdemServico(id_cliente=c.id_cliente, id_veiculo=v.id_veiculo, tipo_servico=tipo,
                         valor_mao_de_obra=D(mo), status=status, entregue_em=entregue,
                         descricao_problema="teste relatório", quilometragem=1000)
        for produto, qtd, preco, custo in itens:
            o.os_produtos.append(OsProduto(id_produto=produto.id_produto, quantidade_utilizada=qtd,
                                           preco_unitario=D(preco), custo_unitario=custo))
        s.add(o)

    os_("Freios", 100, S.ENTREGUE, datetime(2001, 3, 10, 10, 0), [(px, 2, "25", D("10"))])
    os_(" FREIOS ", 50, S.ENTREGUE, datetime(2001, 3, 31, 23, 59, 59))
    os_("Revisão", 200, S.ENTREGUE, datetime(2001, 4, 1, 0, 0), [(py, 1, "40", None)])
    os_("Freios", 999, S.PRONTO)
    os_("Freios", 70, S.AGUARDANDO_PAGAMENTO, None, [(px, 1, "30", D("10"))])
    os_(None, 10, S.ENTREGUE, datetime(2001, 6, 15, 9, 0))

    def mov(tipo, qtd, valor, dia, fornecedor=None):
        s.add(MovimentacaoEstoque(id_produto=px.id_produto, tipo=tipo, quantidade=qtd,
                                  valor=None if valor is None else D(valor),
                                  data_movimentacao=dia, fornecedor=fornecedor))

    mov(T.COMPRA, 10, "300", date(2001, 3, 5), "Forn Teste")
    mov(T.VENDA_AVULSA, -1, "45", date(2001, 3, 20))
    mov(T.DEVOLUCAO_FORNECEDOR, -1, "30", date(2001, 4, 10), "Forn Teste")
    mov(T.DEVOLUCAO_FORNECEDOR, -1, None, date(2001, 4, 11), "Forn Teste")
    mov(T.COMPRA, 5, "100", date(2001, 5, 1), "Forn Teste")
    mov(T.DOACAO, 2, None, date(2001, 5, 2))  # doação não é dinheiro: não entra em nada
    s.commit()


def main() -> None:
    limpar()
    with get_session() as s0:
        ja_existe = s0.scalar(select(func.count()).select_from(OrdemServico).where(
            func.extract("year", OrdemServico.entregue_em) == 2001))
        if ja_existe:
            print(f"ATENÇÃO: o banco já tem {ja_existe} OS entregue(s) em 2001; as contas exatas vão falhar.")
        receber_antes = RelatorioService(s0).gerar(date(2001, 1, 1), date(2001, 1, 1)).resumo

    with get_session() as session:
        servico = RelatorioService(session)
        try:
            criar_dados(session)

            print("\n--- Ano de 2001 (agrupado por mês) ---")
            r = servico.gerar(date(2001, 1, 1), date(2001, 12, 31))
            m = r.resumo
            verificar("365 dias -> agrupado por MÊS, 12 pontos (meses vazios incluídos)",
                      r.agrupamento == AGRUPA_MES and len(r.pontos) == 12)
            verificar("rótulos dos meses: jan/01 ... dez/01",
                      r.pontos[0].rotulo == "jan/01" and r.pontos[-1].rotulo == "dez/01")
            verificar("receita das OS = 150 + 50 + 240 + 10 = 450 (pronto e aguardando FORA)",
                      m.receita_os == D("450.00"))
            verificar("4 OS entregues", m.qtd_os == 4)
            verificar("vendas por fora = 45 (1 venda)", m.vendas_avulsas == D("45.00") and m.qtd_vendas == 1)
            verificar("entradas = 450 + 45 = 495", m.entradas == D("495.00"))
            verificar("compras = 300 + 100 = 400 (2 compras); doação não conta",
                      m.compras == D("400.00") and m.qtd_compras == 2)
            verificar("ressarcimentos = 30 (devolução sem valor soma zero)", m.ressarcimentos == D("30.00"))
            verificar("saídas = 400 - 30 = 370", m.saidas == D("370.00"))
            verificar("saldo de caixa = 495 - 370 = 125", m.saldo == D("125.00"))
            verificar("CMV = 2 x 10 = 20 (peça sem custo entra como zero)", m.custo_pecas == D("20.00"))
            verificar("lucro bruto das OS = 450 - 20 = 430", m.lucro_bruto_os == D("430.00"))
            verificar("1 peça sem custo contada no aviso", m.pecas_sem_custo == 1)
            verificar("a receber subiu exatamente 100 (30 + 70) e 1 OS",
                      m.a_receber - receber_antes.a_receber == D("100.00")
                      and m.qtd_a_receber - receber_antes.qtd_a_receber == 1)

            mar, abr, mai, jun, jul = (r.pontos[i] for i in (2, 3, 4, 5, 6))
            verificar("março: OS 200 (inclui a das 23:59:59 do dia 31), venda 45, compra 300",
                      (mar.receita_os, mar.vendas_avulsas, mar.compras, mar.qtd_os) == (D("200.00"), D("45.00"), D("300.00"), 2))
            verificar("março: entradas 245, saídas 300, saldo -55",
                      (mar.entradas, mar.saidas, mar.saldo) == (D("245.00"), D("300.00"), D("-55.00")))
            verificar("abril: OS 240 (a da 00:00 do dia 1º) e ressarcimento 30",
                      abr.receita_os == D("240.00") and abr.ressarcimentos == D("30.00"))
            verificar("maio: só compra 100 | junho: OS 10 | julho: zero",
                      mai.compras == D("100.00") and mai.entradas == 0 and jun.receita_os == D("10.00")
                      and (jul.entradas, jul.saidas) == (0, 0))
            verificar("soma dos pontos = totais do resumo",
                      sum(p.entradas for p in r.pontos) == m.entradas and sum(p.saidas for p in r.pontos) == m.saidas)

            print("\n--- Serviços mais prestados ---")
            sv = r.servicos
            verificar("3 grupos: freios (2), revisão (1), não informado (1)", len(sv) == 3)
            verificar("'Freios' e ' FREIOS ' viram UM grupo com 2 OS e R$ 200",
                      sv[0].tipo.lower() == "freios" and sv[0].quantidade == 2 and sv[0].faturamento == D("200.00"))
            verificar("empate em 1 OS: desempata pelo faturamento (Revisão 240 antes de 10)",
                      sv[1].tipo == "Revisão" and sv[2].tipo == ROTULO_SEM_TIPO)
            verificar("tipo vazio aparece como 'Não informado'", sv[2].faturamento == D("10.00"))
            verificar("ticket médio de freios = 200 / 2 = 100", sv[0].ticket_medio == D("100.00"))
            verificar("faturamento do ranking = receita das OS (a tela bate)",
                      sum(s.faturamento for s in sv) == m.receita_os)
            verificar("OS pronta e aguardando pagamento não contam como serviço prestado",
                      sum(s.quantidade for s in sv) == 4)

            print("\n--- Limites de data e agrupamento ---")
            r = servico.gerar(date(2001, 3, 1), date(2001, 3, 31))
            verificar("março inteiro (31 dias) -> por DIA, 31 pontos",
                      r.agrupamento == AGRUPA_DIA and len(r.pontos) == 31)
            verificar("OS das 23:59:59 do último dia ENTRA; a da 00:00 do dia seguinte NÃO",
                      r.resumo.receita_os == D("200.00"))
            verificar("ponto do dia 10/03 tem a OS de 150", r.pontos[9].rotulo == "10/03" and r.pontos[9].receita_os == D("150.00"))
            r = servico.gerar(date(2001, 4, 1), date(2001, 4, 1))
            verificar("período de um dia só (01/04): 1 ponto com 240", len(r.pontos) == 1 and r.resumo.receita_os == D("240.00"))
            verificar("62 dias -> ainda por dia", servico.gerar(date(2001, 3, 1), date(2001, 5, 1)).agrupamento == AGRUPA_DIA)
            verificar("63 dias -> por mês", servico.gerar(date(2001, 3, 1), date(2001, 5, 2)).agrupamento == AGRUPA_MES)
            r = servico.gerar(date(2001, 2, 15), date(2001, 7, 10))
            verificar("meses parciais: fev..jul = 6 pontos, totais só dentro das datas",
                      len(r.pontos) == 6 and r.pontos[0].rotulo == "fev/01" and r.resumo.receita_os == D("450.00"))

            print("\n--- Período vazio e validações ---")
            r = servico.gerar(date(1990, 1, 1), date(1990, 12, 31))
            verificar("período sem nada: vazio, 12 meses zerados, sem serviços",
                      r.vazio and len(r.pontos) == 12 and all(p.entradas == p.saidas == 0 for p in r.pontos) and r.servicos == ())
            esperar_erro("data inicial depois da final", ValidacaoError,
                         lambda: servico.gerar(date(2001, 5, 1), date(2001, 4, 1)))
            esperar_erro("datas vazias", ValidacaoError, lambda: servico.gerar(None, None))

            print("\n--- Top 10 + Outros ---")
            linhas = [(f"Serviço {i:02d}", 20 - i, D(i)) for i in range(12)]
            top = RelatorioService._montar_ranking(linhas)
            verificar("12 serviços -> 10 + 'Outros' (11 barras)", len(top) == 11 and top[-1].tipo == ROTULO_OUTROS)
            verificar("'Outros' soma os 2 últimos (qtd 10 + 9 = 19; R$ 10 + 11 = 21)",
                      top[-1].quantidade == 19 and top[-1].faturamento == D("21.00"))
            verificar("10 serviços ou menos: sem 'Outros'",
                      all(s.tipo != ROTULO_OUTROS for s in RelatorioService._montar_ranking(linhas[:10])))
            verificar("empate total: ordem alfabética",
                      [s.tipo for s in RelatorioService._montar_ranking([("b", 1, D(1)), ("A", 1, D(1))])] == ["A", "b"])

            print("\n--- Períodos prontos do filtro ---")
            hoje = date(2026, 11, 7)
            verificar("últimos 12 meses = 01/12/2025 a hoje", periodo_predefinido(ULTIMOS_12_MESES, hoje) == (date(2025, 12, 1), hoje))
            verificar("este mês = 01/11 a hoje", periodo_predefinido(ESTE_MES, hoje) == (date(2026, 11, 1), hoje))
            verificar("mês passado = outubro inteiro", periodo_predefinido(MES_PASSADO, hoje) == (date(2026, 10, 1), date(2026, 10, 31)))
            verificar("mês passado em janeiro = dezembro do ano anterior",
                      periodo_predefinido(MES_PASSADO, date(2026, 1, 15)) == (date(2025, 12, 1), date(2025, 12, 31)))
            verificar("este ano = 01/01 a hoje", periodo_predefinido(ESTE_ANO, hoje) == (date(2026, 1, 1), hoje))
            verificar("ano passado = 2025 inteiro", periodo_predefinido(ANO_PASSADO, hoje) == (date(2025, 1, 1), date(2025, 12, 31)))
            verificar("últimos 12 meses em janeiro atravessa o ano",
                      periodo_predefinido(ULTIMOS_12_MESES, date(2026, 1, 20)) == (date(2025, 2, 1), date(2026, 1, 20)))
            verificar("rótulos: 'nov/26' e '07/11'",
                      rotulo_periodo(date(2026, 11, 1), AGRUPA_MES) == "nov/26" and rotulo_periodo(hoje, AGRUPA_DIA) == "07/11")

            print("\n--- Exportação CSV (HU18) ---")
            r = servico.gerar(date(2001, 1, 1), date(2001, 12, 31))
            texto = gerar_csv(r, datetime(2026, 11, 7, 14, 30))
            linhas_csv = texto.split("\r\n")
            verificar("cabeçalho repete o período e o agrupamento (filtros da tela)",
                      "Período;01/01/2001 a 31/12/2001 (agrupado por mês)" in linhas_csv)
            verificar("cabeçalho traz a data de geração", "Gerado em;07/11/2026 14:30" in linhas_csv)
            verificar("valores com vírgula decimal, sem milhar: 'Entradas;495,00'", "Entradas;495,00" in linhas_csv)
            verificar("uma linha por mês + total igual ao resumo",
                      sum(1 for l in linhas_csv if l[:4] in {p.rotulo[:4] for p in r.pontos}) == 12
                      and "Total;4;450,00;45,00;495,00;400,00;30,00;370,00;125,00" in linhas_csv)
            verificar("serviços com quantidade, faturamento e ticket médio",
                      any(l.lower().startswith("freios;2;200,00;100,00") for l in linhas_csv))
            verificar("aviso de peça sem custo vai junto", any("1 peça(s) sem custo" in l for l in linhas_csv))
            caminho = os.path.join(tempfile.gettempdir(), "teste_relatorio_camaro.csv")
            RelatorioController.salvar_csv(r, caminho)
            with open(caminho, "rb") as f:
                inicio_arquivo = f.read(3)
            os.remove(caminho)
            verificar("arquivo gravado com BOM UTF-8 (acentos certos no Excel)", inicio_arquivo == b"\xef\xbb\xbf")
            verificar("nome sugerido leva o período",
                      RelatorioController.nome_sugerido(r, "csv") == "relatorio_2001-01-01_a_2001-12-31.csv")
        finally:
            session.rollback()
            limpar()

    with get_session() as s:
        verificar("limpeza: nada de 2001 sobrou",
                  s.scalar(select(func.count()).select_from(Cliente).where(Cliente.cpf == CPF)) == 0
                  and s.scalar(select(func.count()).select_from(Produto).where(Produto.nome.in_([NOME_PX, NOME_PY]))) == 0)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
