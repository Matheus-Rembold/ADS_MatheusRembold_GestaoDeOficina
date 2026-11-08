"""
Dados de EXEMPLO para ver os relatórios (RF06) e testar as telas à mão.

Rode da raiz do projeto, com o venv ativo:
    python gerar_dados_exemplo.py            # cria 12 meses de movimento
    python gerar_dados_exemplo.py --remover  # apaga TODOS os dados de exemplo

O que é criado (tudo MARCADO, para nunca se misturar com dado real):
- clientes com " (exemplo)" no nome (CPFs válidos, editáveis na tela);
- veículos com placa começando em "EXE";
- produtos com " (exemplo)" no nome; as OS de exemplo usam SÓ esses
  produtos, então o estoque dos produtos reais não é tocado;
- compras com fornecedor "Fornecedor Exemplo", vendas por fora, uma
  devolução ressarcida e uma doação (peça sem custo, para o aviso do lucro);
- ~8 OS por mês nos últimos 12 meses, com tipos de serviço repetidos (e
  algumas grafias diferentes, como "revisão"), mais algumas em orçamento,
  pronto e aguardando pagamento.

Compras, vendas e OS passam pelos PRÓPRIOS SERVIÇOS do sistema (estoque,
custo, preço de venda e baixa seguem as regras de verdade). Só no fim as
datas de criação/entrega são ajustadas para o passado, porque o sistema
sempre grava "agora".

--remover apaga direto pela sessão (só aqui, por ser dado de exemplo).
"""
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, update

from src.config.database import DB_NAME, engine, get_session
from src.persistencia.models import (
    Cliente, MovimentacaoEstoque, OrdemServico, OsProduto, Produto,
    StatusOrdemServico, TipoMovimentacao, Veiculo,
)
from src.servico.movimentacao_estoque_service import MovimentacaoEstoqueService
from src.servico.ordem_servico_service import ItemOS, OrdemServicoService

engine.echo = False

MARCA = " (exemplo)"
FORNECEDOR = "Fornecedor Exemplo"
PREFIXO_PLACA = "EXE"
S, T, D = StatusOrdemServico, TipoMovimentacao, Decimal

CLIENTES = ["Ana Souza", "Bruno Lima", "Carla Mendes", "Diego Rocha", "Elisa Prado",
            "Fábio Teixeira", "Gabriela Nunes", "Hugo Martins", "Isabela Costa", "João Pereira"]
VEICULOS = [("Gol", "Volkswagen"), ("Onix", "Chevrolet"), ("HB20", "Hyundai"), ("Corolla", "Toyota"),
            ("Uno", "Fiat"), ("Civic", "Honda"), ("Ka", "Ford"), ("Sandero", "Renault"),
            ("Strada", "Fiat"), ("Compass", "Jeep")]
# nome, custo unitário da compra, quantidade comprada por mês (reposição do
# que as OS consomem; no 1º mês compra o dobro, como estoque inicial)
PRODUTOS = [("Óleo 5W30 litro", "28.00", 20), ("Filtro de óleo", "22.00", 5), ("Filtro de ar", "35.00", 3),
            ("Pastilha de freio", "95.00", 3), ("Disco de freio", "180.00", 2), ("Amortecedor", "260.00", 2),
            ("Correia dentada", "120.00", 1), ("Vela de ignição", "18.00", 4)]
PECA_DOADA = "Palheta do limpador"  # entra por doação: sem custo registrado
# tipo de serviço, peso (frequência), mão de obra (mín, máx), peças possíveis
SERVICOS = [
    ("Revisão", 22, (120, 250), ["Óleo 5W30 litro", "Filtro de óleo", "Filtro de ar", "Vela de ignição"]),
    ("Troca de óleo", 18, (50, 80), ["Óleo 5W30 litro", "Filtro de óleo"]),
    ("Freios", 14, (90, 200), ["Pastilha de freio", "Disco de freio"]),
    ("Suspensão", 8, (180, 350), ["Amortecedor"]),
    ("Alinhamento e balanceamento", 10, (80, 120), []),
    ("Elétrica", 6, (100, 300), [PECA_DOADA]),
    ("Correia dentada", 5, (200, 320), ["Correia dentada"]),
    ("Embreagem", 3, (400, 650), []),
    ("Arrefecimento", 3, (150, 280), []),
    ("Injeção eletrônica", 3, (180, 300), ["Vela de ignição"]),
    ("Ar-condicionado", 2, (150, 260), []),
    ("Escapamento", 2, (120, 220), []),
]
VARIACOES = {"Revisão": ["revisão", "REVISÃO"], "Freios": ["freios"]}  # grafias que o relatório deve juntar


def cpf_valido(base: int) -> str:
    numeros = [int(c) for c in f"{base:09d}"]
    for tamanho in (9, 10):
        soma = sum(n * (tamanho + 1 - i) for i, n in enumerate(numeros[:tamanho]))
        digito = (soma * 10) % 11
        numeros.append(0 if digito == 10 else digito)
    t = "".join(map(str, numeros))
    return f"{t[:3]}.{t[3:6]}.{t[6:9]}-{t[9:]}"


def remover() -> None:
    with get_session() as s:
        ids_c = list(s.scalars(select(Cliente.id_cliente).where(Cliente.nome.like(f"%{MARCA}"))))
        ids_p = list(s.scalars(select(Produto.id_produto).where(Produto.nome.like(f"%{MARCA}"))))
        ids_os = list(s.scalars(select(OrdemServico.id_ordem_servico).where(
            OrdemServico.id_cliente.in_(ids_c)))) if ids_c else []
        if ids_os:
            s.execute(delete(OsProduto).where(OsProduto.id_ordem_servico.in_(ids_os)))
            s.execute(delete(OrdemServico).where(OrdemServico.id_ordem_servico.in_(ids_os)))
        if ids_p:
            s.execute(delete(MovimentacaoEstoque).where(MovimentacaoEstoque.id_produto.in_(ids_p)))
            s.execute(delete(Produto).where(Produto.id_produto.in_(ids_p)))
        if ids_c:
            s.execute(delete(Veiculo).where(Veiculo.id_cliente.in_(ids_c)))
            s.execute(delete(Cliente).where(Cliente.id_cliente.in_(ids_c)))
        s.commit()
    print(f"Removidos do banco '{DB_NAME}': {len(ids_os)} OS, {len(ids_p)} produtos e {len(ids_c)} clientes de exemplo.")


def gerar() -> None:
    rnd = random.Random(2026)  # sempre os mesmos dados (reprodutível)
    hoje = date.today()
    agora = datetime.now()
    inicio = date(hoje.year - 1, hoje.month, 1) + timedelta(days=31)
    inicio = date(inicio.year, inicio.month, 1)  # 1º dia do mês, 11 meses atrás

    with get_session() as s:
        if s.scalar(select(func.count()).select_from(Cliente).where(Cliente.nome.like(f"%{MARCA}"))):
            print("Já existem dados de exemplo. Rode com --remover antes de gerar de novo.")
            return

        clientes, veiculos = [], []
        for n, nome in enumerate(CLIENTES):
            c = Cliente(nome=nome + MARCA, cpf=cpf_valido(900_000_100 + n), contato=f"5499900{n:04d}")
            s.add(c)
            s.flush()
            modelo, marca = VEICULOS[n]
            v = Veiculo(id_cliente=c.id_cliente, modelo=modelo, marca=marca, ano=2012 + n,
                        placa=f"{PREFIXO_PLACA}{n}A{n:02d}")
            s.add(v)
            s.flush()
            clientes.append(c.id_cliente)
            veiculos.append(v.id_veiculo)
        produtos = {}
        for nome, _custo, _qtd in PRODUTOS + [(PECA_DOADA, None, 0)]:
            p = Produto(nome=nome + MARCA, categoria="Exemplo", prateleira="EX", quantidade=0, quantidade_minima=3)
            s.add(p)
            s.flush()
            produtos[nome] = p.id_produto
        s.commit()

        movs = MovimentacaoEstoqueService(s)
        oss = OrdemServicoService(s)
        km = {v: 30_000 + 7_000 * i for i, v in enumerate(veiculos)}
        datas_os = {}  # id_os -> (criada, entregue ou None)
        tipos = [t for t, peso, *_ in SERVICOS for _ in range(peso)]
        info = {t: (mo, pecas) for t, _p, mo, pecas in SERVICOS}

        mes = inicio
        while mes <= hoje:
            ultimo_dia = (date(mes.year + mes.month // 12, mes.month % 12 + 1, 1) - timedelta(days=1))
            ultimo_dia = min(ultimo_dia, hoje)

            # --- compras do mês (custo varia um pouco: o preço de venda acompanha) ---
            for nome, custo, qtd in PRODUTOS:
                qtd = qtd * 2 if mes == inicio else qtd
                variacao = D(str(round(rnd.uniform(0.95, 1.08), 3)))
                valor = (D(custo) * qtd * variacao).quantize(D("0.01"))
                dia = mes + timedelta(days=rnd.randint(0, min(4, (ultimo_dia - mes).days)))
                movs.registrar(produtos[nome], T.COMPRA, qtd, dia, valor, FORNECEDOR)
            movs.registrar(produtos[PECA_DOADA], T.DOACAO, 4, mes, fornecedor="Cliente antigo")

            # --- OS do mês ---
            for _ in range(rnd.randint(9, 13)):
                dia = mes + timedelta(days=rnd.randint(0, (ultimo_dia - mes).days))
                criada = min(agora, datetime.combine(dia, datetime.min.time()) + timedelta(hours=rnd.randint(8, 11)))
                tipo = rnd.choice(tipos)
                (mo_min, mo_max), pecas = info[tipo]
                grafia = rnd.choice([tipo] * 4 + VARIACOES.get(tipo, []))
                itens = []
                for nome in rnd.sample(pecas, k=min(len(pecas), rnd.randint(1, 2))) if pecas else []:
                    qtd = 4 if nome.startswith("Óleo") else rnd.randint(1, 2)
                    preco = D("35.00") if nome == PECA_DOADA else None  # sem preço de venda: digita
                    itens.append(ItemOS(produtos[nome], qtd, preco))
                v = rnd.randrange(len(veiculos))
                km[veiculos[v]] += rnd.randint(2_000, 6_000)
                mao = D(rnd.randrange(mo_min, mo_max + 1, 10))
                try:
                    os_ = oss.cadastrar(clientes[v], veiculos[v], km[veiculos[v]], "Serviço de exemplo",
                                        grafia, mao, itens, status=S.ANDAMENTO)
                except Exception as erro:  # noqa: BLE001  (ex.: estoque acabou no mês)
                    # normal: o sistema recusou por falta de estoque, como faria na tela
                    print(f"  (uma OS de exemplo não foi criada, o sistema recusou: {str(erro).splitlines()[0]})")
                    continue
                entregue = criada + timedelta(days=rnd.randint(0, 3), hours=rnd.randint(5, 8))
                recente = entregue > agora
                destino = rnd.choices([S.ENTREGUE, S.AGUARDANDO_PAGAMENTO, S.PRONTO],
                                      weights=[90, 6, 4])[0] if not recente else S.PRONTO
                for passo in (S.PRONTO, S.AGUARDANDO_PAGAMENTO, S.ENTREGUE):
                    oss.alterar_status(os_.id_ordem_servico, passo)
                    if passo is destino:
                        break
                datas_os[os_.id_ordem_servico] = (criada, entregue if destino is S.ENTREGUE else None)

            # --- vendas por fora e uma devolução ---
            for _ in range(rnd.randint(0, 2)):
                nome = rnd.choice(["Óleo 5W30 litro", "Filtro de ar", "Vela de ignição"])
                p = s.get(Produto, produtos[nome])
                s.refresh(p)
                if p.quantidade >= 2 and p.preco_venda:
                    dia = mes + timedelta(days=rnd.randint(0, (ultimo_dia - mes).days))
                    movs.registrar(p.id_produto, T.VENDA_AVULSA, 2, dia, p.preco_venda * 2)
            if mes.month in (3, 9):
                p = s.get(Produto, produtos["Amortecedor"])
                s.refresh(p)
                if p.quantidade >= 1:
                    movs.registrar(p.id_produto, T.DEVOLUCAO_FORNECEDOR, 1, ultimo_dia,
                                   D("250.00"), FORNECEDOR, "Peça com defeito (exemplo)")
            mes = date(mes.year + mes.month // 12, mes.month % 12 + 1, 1)

        # Algumas OS recentes em orçamento (não consomem estoque nem entram no relatório).
        for i in range(2):
            oss.cadastrar(clientes[i], veiculos[i], km[veiculos[i]] + 100, "Orçamento de exemplo", "Embreagem",
                          D("500"), [], status=S.ORCAMENTO)

        # Datas no passado (o sistema sempre grava "agora").
        for id_os, (criada, entregue) in datas_os.items():
            s.execute(update(OrdemServico).where(OrdemServico.id_ordem_servico == id_os).values(
                criado_em=criada, atualizado_em=entregue or criada, entregue_em=entregue))
        s.commit()

        total = len(datas_os)
        entregues = sum(1 for _c, e in datas_os.values() if e)
        print(f"Banco '{DB_NAME}': {len(clientes)} clientes, {len(produtos)} produtos e {total} OS de exemplo "
              f"({entregues} entregues) de {inicio:%m/%Y} a {hoje:%m/%Y}.")
        print("Para apagar tudo depois: python gerar_dados_exemplo.py --remover")


if __name__ == "__main__":
    if "--remover" in sys.argv:
        remover()
    else:
        gerar()
