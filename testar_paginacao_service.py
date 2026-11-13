"""
Teste da paginação das listagens (09/11/2026) contra o banco real.

Rode da raiz do projeto, com o venv ativo:
    python testar_paginacao_service.py

Só LÊ o banco. Em vez de depender de quantos registros existem, compara
cada listagem paginada com a listagem COMPLETA (sem paginação) do próprio
serviço:
- juntando todas as páginas, tem que dar exatamente a lista completa, na
  mesma ordem, sem nenhum registro faltando ou repetido entre páginas;
- os totais do rodapé (valor das OS, estoque baixo, compras/vendas) têm que
  bater com a soma feita em Python sobre a lista completa;
- busca e filtros valem para todas as páginas.
Para ter várias páginas, os testes usam páginas pequenas (por_pagina=7).
"""
from decimal import Decimal

from src.config.database import engine, get_session
from src.persistencia.models import StatusOrdemServico, TipoMovimentacao
from src.servico.cliente_service import ClienteService
from src.servico.movimentacao_estoque_service import MovimentacaoEstoqueService
from src.servico.ordem_servico_service import OrdemServicoService
from src.servico.paginacao import POR_PAGINA, Pagina, montar_pagina, normalizar_pagina
from src.servico.produto_service import ProdutoService
from src.servico.veiculo_service import VeiculoService

engine.echo = False
resultados = []


def verificar(descricao: str, condicao: bool) -> None:
    resultados.append(bool(condicao))
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}")


def todas_as_paginas(listar, por_pagina=7):
    """Percorre página por página até a última e devolve (itens, primeira página, nº de páginas)."""
    primeira = listar(1, por_pagina)
    itens = list(primeira.itens)
    for numero in range(2, primeira.total_paginas + 1):
        pagina = listar(numero, por_pagina)
        verificar_silencioso = pagina.pagina == numero and len(pagina.itens) <= por_pagina
        if not verificar_silencioso:
            return None, primeira, numero
        itens.extend(pagina.itens)
    return itens, primeira, primeira.total_paginas


def conferir(nome, listar, completa, chave):
    itens, primeira, paginas = todas_as_paginas(listar)
    ids_paginados = [chave(x) for x in (itens or [])]
    ids_completos = [chave(x) for x in completa]
    verificar(f"{nome}: total da página = tamanho da lista completa ({len(completa)})",
              primeira.total == len(completa))
    verificar(f"{nome}: {paginas} página(s) de 7 juntas = lista completa, mesma ordem",
              itens is not None and ids_paginados == ids_completos)
    verificar(f"{nome}: nenhum registro repetido entre páginas", len(set(ids_paginados)) == len(ids_paginados))
    return primeira


def main() -> None:
    print("\n--- Regras da paginação ---")
    verificar("tamanho padrão da página é 50", POR_PAGINA == 50)
    verificar("página pedida além da última vira a última (2 páginas, pediu 9 -> 2)",
              normalizar_pagina(9, total=60, por_pagina=50) == 2)
    verificar("página zero, negativa, texto ou booleana vira 1",
              [normalizar_pagina(x, 100) for x in (0, -3, "2", True, None)] == [1, 1, 1, 1, 1])
    verificar("lista vazia: página 1", normalizar_pagina(5, total=0) == 1)
    p = Pagina(tuple(range(10)), total=110, pagina=3, por_pagina=50)
    verificar("Pagina: 3 de 3, itens 101 a 110, tem anterior e não tem próxima",
              (p.total_paginas, p.primeiro, p.ultimo, p.tem_anterior, p.tem_proxima) == (3, 101, 110, True, False))
    vazia = Pagina((), total=0, pagina=1)
    verificar("Pagina vazia: 1 página, mostrando 0–0", (vazia.total_paginas, vazia.primeiro, vazia.ultimo) == (1, 0, 0))
    chamadas = []
    montar_pagina(0, 1, lambda l, d: chamadas.append((l, d)) or [])
    verificar("total zero nem chega a buscar no banco", chamadas == [])
    pagina = montar_pagina(120, 3, lambda l, d: list(range(d, d + min(l, 120 - d))), por_pagina=50)
    verificar("montar_pagina pede LIMIT 50 OFFSET 100 na página 3", pagina.itens == tuple(range(100, 120)))
    verificar("por_pagina inválido volta ao padrão (50)", montar_pagina(10, 1, lambda l, d: [], por_pagina=0).por_pagina == 50)

    with get_session() as s:
        print("\n--- Ordens de serviço ---")
        oss = OrdemServicoService(s)
        completa = oss.listar()
        primeira = conferir("OS", lambda n, t: oss.listar_pagina("", None, n, t), completa, lambda o: o.id_ordem_servico)
        verificar("OS: total do rodapé (todas as OS) = soma de valor_total da lista completa",
                  primeira.resumo["valor_total"] == sum((o.valor_total for o in completa), Decimal("0")))
        for status in (StatusOrdemServico.ENTREGUE, StatusOrdemServico.ORCAMENTO):
            filtrada = oss.listar("", status)
            p = conferir(f"OS {status.value}", lambda n, t, st=status: oss.listar_pagina("", st, n, t),
                         filtrada, lambda o: o.id_ordem_servico)
            verificar(f"OS {status.value}: total do rodapé respeita o filtro",
                      p.resumo["valor_total"] == sum((o.valor_total for o in filtrada), Decimal("0")))
        if completa:
            termo = completa[0].cliente.nome[:5]
            conferir(f"OS busca '{termo}'", lambda n, t: oss.listar_pagina(termo, None, n, t),
                     oss.listar(termo), lambda o: o.id_ordem_servico)
        nada = oss.listar_pagina("zzz-nao-existe-zzz", None, 4)
        verificar("OS: busca sem resultado = página 1 vazia, total R$ 0",
                  (nada.total, nada.pagina, nada.itens, nada.resumo["valor_total"]) == (0, 1, (), 0))
        ultima = oss.listar_pagina("", None, 10_000)
        verificar("OS: página 10.000 devolve a última página válida", ultima.pagina == ultima.total_paginas)

        print("\n--- Clientes ---")
        cs = ClienteService(s)
        completa = cs.listar()
        conferir("clientes", lambda n, t: cs.listar_pagina("", n, t), completa, lambda c: c.id_cliente)
        if completa:
            alvo = completa[-1]
            achado = cs.listar_pagina(alvo.cpf.replace(".", "").replace("-", ""), 1)
            verificar("clientes: 11 dígitos buscam pelo CPF exato (1 resultado)",
                      achado.total == 1 and achado.itens[0].id_cliente == alvo.id_cliente)
            verificar("clientes: a página traz os veículos (para a coluna 'Veículos')",
                      all(isinstance(c.veiculos, list) for c in cs.listar_pagina("", 1).itens))
            conferir("clientes busca por nome", lambda n, t: cs.listar_pagina("a", n, t),
                     cs.buscar_por_nome("a"), lambda c: c.id_cliente)

        print("\n--- Veículos ---")
        vs = VeiculoService(s)
        conferir("veículos", lambda n, t: vs.listar_pagina("", n, t), vs.listar(), lambda v: v.id_veiculo)
        conferir("veículos busca 'a'", lambda n, t: vs.listar_pagina("a", n, t), vs.buscar("a"), lambda v: v.id_veiculo)

        print("\n--- Produtos ---")
        ps = ProdutoService(s)
        completa = ps.listar()
        primeira = conferir("produtos", lambda n, t: ps.listar_pagina("", n, t), completa, lambda p: p.id_produto)
        verificar("produtos: 'estoque baixo' do rodapé conta TODOS os produtos, não só a página",
                  primeira.resumo["estoque_baixo"] == sum(1 for p in completa if p.estoque_baixo))
        conferir("produtos busca 'filtro'", lambda n, t: ps.listar_pagina("filtro", n, t),
                 ps.buscar("filtro"), lambda p: p.id_produto)

        print("\n--- Estoque (movimentações) ---")
        ms = MovimentacaoEstoqueService(s)
        completa = ms.listar()
        primeira = conferir("movimentações", lambda n, t: ms.listar_pagina("", None, None, None, n, t),
                            completa, lambda m: m.id_movimentacao_estoque)
        for tipo in (TipoMovimentacao.COMPRA, TipoMovimentacao.VENDA_AVULSA):
            soma = sum((m.valor for m in completa if m.tipo is tipo and m.valor is not None), Decimal("0"))
            verificar(f"movimentações: soma de {tipo.value} do rodapé = soma da lista completa",
                      primeira.resumo.get(tipo, Decimal("0")) == soma)
        conferir("movimentações só compras",
                 lambda n, t: ms.listar_pagina("", TipoMovimentacao.COMPRA, None, None, n, t),
                 ms.listar("", TipoMovimentacao.COMPRA), lambda m: m.id_movimentacao_estoque)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
