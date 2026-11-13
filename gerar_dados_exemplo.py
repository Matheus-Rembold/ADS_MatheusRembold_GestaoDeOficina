"""
Dados de EXEMPLO para testar as telas à mão e ver os relatórios (RF06).

Rode da raiz do projeto, com o venv ativo, num banco recém-criado pelo
BancoDeDadods.sql:
    python gerar_dados_exemplo.py            # cria 24 meses de movimento (~1 a 2 min)
    python gerar_dados_exemplo.py --remover  # apaga TODOS os dados de exemplo

O que é criado (tudo MARCADO, para nunca se misturar com dado real):
- 50 clientes com " (exemplo)" no nome e 70 veículos (alguns clientes com 2 carros);
- 30 produtos com " (exemplo)" no nome, alguns com preço de venda manual
  (um deles abaixo do custo) e alguns terminando com estoque baixo;
- 24 meses de compras (reposição pelo consumo), doações, vendas por fora,
  devoluções ressarcidas e ajustes de inventário;
- cerca de 1.100 OS em todas as situações: entregues, aguardando pagamento,
  orçamentos não aprovados e, nos últimos dias, em andamento e prontas;
- agendamentos: passados (concluídos e ligados à OS, ou cancelados) e nas
  próximas 2 semanas, incluindo um horário LOTADO (limite de 2 simultâneos).

Clientes, veículos, compras, OS e agendamentos futuros passam pelos PRÓPRIOS
SERVIÇOS do sistema: CPF, placa, estoque, custo, preço de venda e limite da
agenda seguem as regras de verdade, e tudo pode ser editado nas telas. Só no
fim as datas são ajustadas para o passado, porque o sistema sempre grava
"agora". As OS de exemplo usam só produtos de exemplo, então o estoque dos
produtos reais (seed) não muda.
"""
import random
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, update

from src.config.database import DB_NAME, engine, get_session
from src.persistencia.models import (
    Agendamento, Cliente, MovimentacaoEstoque, OrdemServico, OsProduto, Produto,
    StatusAgendamento, StatusOrdemServico, TipoMovimentacao, Veiculo,
)
from src.servico.agendamento_service import AgendamentoService
from src.servico.cliente_service import ClienteService
from src.servico.excecoes import ErroDeNegocio
from src.servico.movimentacao_estoque_service import MovimentacaoEstoqueService
from src.servico.ordem_servico_service import ItemOS, OrdemServicoService
from src.servico.produto_service import ProdutoService
from src.servico.veiculo_service import VeiculoService

engine.echo = False

MARCA = " (exemplo)"
FORNECEDORES = ["Distribuidora Exemplo Sul", "Auto Peças Exemplo", "Lubrificantes Exemplo"]
S, T, D = StatusOrdemServico, TipoMovimentacao, Decimal
MESES = 24
OS_POR_MES = (38, 52)

NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabriela", "Hugo", "Isabela", "João",
         "Karina", "Lucas", "Mariana", "Nelson", "Olívia", "Paulo", "Queila", "Rafael", "Sabrina", "Tiago",
         "Úrsula", "Vinícius", "Wagner", "Yasmin", "Zeca"]
SOBRENOMES = ["Souza", "Lima", "Mendes", "Rocha", "Prado", "Teixeira", "Nunes", "Martins", "Costa", "Pereira"]
VEICULOS = [("Gol", "Volkswagen"), ("Onix", "Chevrolet"), ("HB20", "Hyundai"), ("Corolla", "Toyota"),
            ("Uno", "Fiat"), ("Civic", "Honda"), ("Ka", "Ford"), ("Sandero", "Renault"), ("Strada", "Fiat"),
            ("Compass", "Jeep"), ("Polo", "Volkswagen"), ("Kwid", "Renault"), ("Hilux", "Toyota"),
            ("S10", "Chevrolet"), ("Argo", "Fiat"), ("Creta", "Hyundai")]
RUAS = ["Rua Independência", "Av. Brasil", "Rua Paissandu", "Rua Moron", "Av. Sete de Setembro",
        "Rua Bento Gonçalves", "Rua Uruguai", "Av. Presidente Vargas"]

# nome, categoria, custo base, consumo médio por mês, quantidade mínima
PRODUTOS = [
    ("Óleo 5W30 litro", "Fluidos", "28.00", 60, 20), ("Óleo 15W40 litro", "Fluidos", "22.00", 30, 10),
    ("Fluido de freio DOT4", "Fluidos", "32.00", 6, 3), ("Aditivo de radiador", "Fluidos", "25.00", 6, 3),
    ("Filtro de óleo", "Filtros", "22.00", 18, 6), ("Filtro de ar", "Filtros", "35.00", 10, 4),
    ("Filtro de combustível", "Filtros", "29.00", 6, 3), ("Filtro de cabine", "Filtros", "31.00", 6, 3),
    ("Pastilha de freio dianteira", "Freios", "95.00", 8, 4), ("Pastilha de freio traseira", "Freios", "85.00", 4, 2),
    ("Disco de freio", "Freios", "180.00", 4, 2), ("Lona de freio", "Freios", "70.00", 2, 2),
    ("Amortecedor dianteiro", "Suspensão", "260.00", 4, 2), ("Amortecedor traseiro", "Suspensão", "230.00", 2, 2),
    ("Bieleta", "Suspensão", "65.00", 3, 2), ("Pivô de suspensão", "Suspensão", "80.00", 2, 2),
    ("Correia dentada", "Motor", "120.00", 3, 2), ("Kit embreagem", "Motor", "650.00", 1, 1),
    ("Vela de ignição", "Motor", "18.00", 16, 8), ("Cabo de vela (jogo)", "Motor", "95.00", 2, 1),
    ("Bomba d'água", "Arrefecimento", "210.00", 1, 1), ("Válvula termostática", "Arrefecimento", "75.00", 1, 1),
    ("Bateria 60Ah", "Elétrica", "420.00", 3, 2), ("Lâmpada H4", "Elétrica", "25.00", 8, 4),
    ("Alternador recondicionado", "Elétrica", "550.00", 1, 1), ("Gás do ar-condicionado", "Ar-condicionado", "90.00", 2, 2),
    ("Filtro secador do ar", "Ar-condicionado", "140.00", 1, 1), ("Silencioso traseiro", "Escapamento", "240.00", 1, 1),
    ("Abraçadeira de escapamento", "Escapamento", "12.00", 4, 4),
]
PECA_DOADA = ("Palheta do limpador", "Acessórios")  # entra só por doação: sem custo registrado
ACABAM_BAIXOS = {"Pastilha de freio traseira", "Lâmpada H4"}  # sem reposição no último mês
MANUAIS = {  # preço de venda definido à mão: fator sobre o custo da 1ª compra
    "Bateria 60Ah": D("1.45"),            # margem maior que a padrão
    "Óleo 15W40 litro": D("0.90"),        # abaixo do custo: a tela destaca margem negativa
    "Kit embreagem": D("1.30"),
}

# tipo de serviço, peso (frequência), mão de obra (mín, máx), peças possíveis
SERVICOS = [
    ("Revisão", 22, (150, 280), ["Óleo 5W30 litro", "Filtro de óleo", "Filtro de ar", "Filtro de cabine", "Vela de ignição"]),
    ("Troca de óleo", 20, (50, 90), ["Óleo 5W30 litro", "Óleo 15W40 litro", "Filtro de óleo"]),
    ("Freios", 14, (90, 220), ["Pastilha de freio dianteira", "Pastilha de freio traseira", "Disco de freio",
                               "Fluido de freio DOT4", "Lona de freio"]),
    ("Suspensão", 8, (180, 380), ["Amortecedor dianteiro", "Amortecedor traseiro", "Bieleta", "Pivô de suspensão"]),
    ("Alinhamento e balanceamento", 12, (80, 130), []),
    ("Elétrica", 7, (100, 300), ["Bateria 60Ah", "Lâmpada H4", "Alternador recondicionado", PECA_DOADA[0]]),
    ("Correia dentada", 4, (220, 340), ["Correia dentada", "Bomba d'água"]),
    ("Embreagem", 2, (450, 700), ["Kit embreagem"]),
    ("Arrefecimento", 3, (150, 280), ["Aditivo de radiador", "Válvula termostática", "Bomba d'água"]),
    ("Injeção eletrônica", 4, (180, 320), ["Vela de ignição", "Filtro de combustível", "Cabo de vela (jogo)"]),
    ("Ar-condicionado", 3, (150, 260), ["Gás do ar-condicionado", "Filtro secador do ar", "Filtro de cabine"]),
    ("Escapamento", 2, (120, 220), ["Silencioso traseiro", "Abraçadeira de escapamento"]),
    ("Diagnóstico", 3, (80, 150), []),
]
# grafias diferentes que o relatório deve juntar (RF06)
VARIACOES = {"Revisão": ["revisão", "REVISÃO"], "Freios": ["freios"], "Troca de óleo": ["troca de óleo"]}


def cpf_valido(base: int) -> str:
    numeros = [int(c) for c in f"{base:09d}"]
    for tamanho in (9, 10):
        soma = sum(n * (tamanho + 1 - i) for i, n in enumerate(numeros[:tamanho]))
        digito = (soma * 10) % 11
        numeros.append(0 if digito == 10 else digito)
    t = "".join(map(str, numeros))
    return f"{t[:3]}.{t[3:6]}.{t[6:9]}-{t[9:]}"


def placa_exemplo(n: int) -> str:
    """Placa Mercosul válida e única, começando com EXE (ex.: EXE3D07)."""
    return f"EXE{n % 10}{chr(65 + n % 26)}{n:02d}"


def mes_seguinte(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def dia_util(rnd, inicio: date, fim: date) -> date:
    """Dia útil (segunda a sábado) entre inicio e fim."""
    for _ in range(20):
        d = inicio + timedelta(days=rnd.randint(0, (fim - inicio).days))
        if d.weekday() < 6:
            return d
    return inicio


def remover() -> None:
    with get_session() as s:
        ids_c = list(s.scalars(select(Cliente.id_cliente).where(Cliente.nome.like(f"%{MARCA}"))))
        ids_p = list(s.scalars(select(Produto.id_produto).where(Produto.nome.like(f"%{MARCA}"))))
        ids_os = list(s.scalars(select(OrdemServico.id_ordem_servico).where(
            OrdemServico.id_cliente.in_(ids_c)))) if ids_c else []
        if ids_c:
            s.execute(delete(Agendamento).where(Agendamento.id_cliente.in_(ids_c)))
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
    print(f"Removidos do banco '{DB_NAME}': {len(ids_os)} OS, {len(ids_p)} produtos e "
          f"{len(ids_c)} clientes de exemplo (com veículos, movimentações e agendamentos).")


def gerar() -> None:
    rnd = random.Random(2026)  # sempre os mesmos dados (reprodutível)
    hoje = date.today()
    agora = datetime.now()
    inicio = date(hoje.year, hoje.month, 1)
    for _ in range(MESES - 1):
        inicio = date(inicio.year - (inicio.month == 1), (inicio.month - 2) % 12 + 1, 1)
    t0 = time.perf_counter()

    with get_session() as s:
        if s.scalar(select(func.count()).select_from(Cliente).where(Cliente.nome.like(f"%{MARCA}"))):
            print("Já existem dados de exemplo. Rode com --remover antes de gerar de novo.")
            return
        clientes_srv, veiculos_srv = ClienteService(s), VeiculoService(s)
        produtos_srv, movs, oss = ProdutoService(s), MovimentacaoEstoqueService(s), OrdemServicoService(s)

        # --- clientes e veículos (pelas regras do sistema) ---
        clientes, veiculos = [], []  # veiculos: (id_cliente, id_veiculo)
        for n in range(50):
            nome = f"{NOMES[n % len(NOMES)]} {SOBRENOMES[(n * 7) % len(SOBRENOMES)]}{MARCA}"
            c = clientes_srv.cadastrar(nome, cpf_valido(900_000_100 + n), f"(54) 99{n:03d}-{1000 + n * 37 % 9000:04d}",
                                       idade=rnd.randint(19, 78),
                                       endereco=f"{rnd.choice(RUAS)}, {rnd.randint(10, 2500)} - Passo Fundo")
            clientes.append(c.id_cliente)
        for n in range(70):
            dono = clientes[n] if n < 50 else rnd.choice(clientes)
            modelo, marca = VEICULOS[n % len(VEICULOS)]
            v = veiculos_srv.cadastrar(dono, modelo, marca, placa_exemplo(n), ano=rnd.randint(2008, 2025),
                                       motor=rnd.choice(["1.0", "1.4", "1.6", "2.0", "2.8 diesel"]))
            veiculos.append((dono, v.id_veiculo))

        # --- produtos ---
        produtos, info_prod = {}, {}
        for nome, categoria, custo, consumo, minimo in PRODUTOS:
            p = produtos_srv.cadastrar(nome + MARCA, categoria, f"E{rnd.randint(1, 9)}", quantidade_minima=minimo)
            produtos[nome] = p.id_produto
            info_prod[nome] = (D(custo), consumo, minimo, categoria)
        p = produtos_srv.cadastrar(PECA_DOADA[0] + MARCA, PECA_DOADA[1], "E9", quantidade_minima=2)
        produtos[PECA_DOADA[0]] = p.id_produto
        print(f"  cadastros prontos: {len(clientes)} clientes, {len(veiculos)} veículos, {len(produtos)} produtos")

        km = {v: rnd.randint(20_000, 120_000) for _c, v in veiculos}
        tipos = [t for t, peso, *_ in SERVICOS for _ in range(peso)]
        info_serv = {t: (mo, pecas) for t, _p, mo, pecas in SERVICOS}
        datas_os = {}       # id_os -> (criada, entregue ou None)
        agend_passados = []  # (id_cliente, id_veiculo, tipo, data_hora, duracao, status, id_os)
        mes, indice_mes, puladas = inicio, 0, 0

        while mes <= hoje:
            ultimo = min(mes_seguinte(mes) - timedelta(days=1), hoje)
            ultimo_mes = mes_seguinte(mes) > hoje
            inflacao = D("1") + D("0.006") * indice_mes  # custos sobem um pouco ao longo do tempo

            # --- compras: repõe o estoque pelo consumo (estoque inicial no 1º mês) ---
            for nome, (custo, consumo, minimo, _cat) in info_prod.items():
                if ultimo_mes and nome in ACABAM_BAIXOS:
                    continue
                atual = s.get(Produto, produtos[nome], populate_existing=True).quantidade
                # consumo do mês + mínimo + 3 de segurança (peça de baixo giro varia muito de um mês para outro)
                alvo = int(consumo * (2.5 if indice_mes == 0 else 2.0)) + minimo + 3
                if atual < alvo:
                    qtd = alvo - atual
                    valor = (custo * inflacao * D(str(round(rnd.uniform(0.95, 1.07), 3))) * qtd).quantize(D("0.01"))
                    dia = mes + timedelta(days=rnd.randint(0, min(3, (ultimo - mes).days)))
                    movs.registrar(produtos[nome], T.COMPRA, qtd, dia, valor, rnd.choice(FORNECEDORES))
            movs.registrar(produtos[PECA_DOADA[0]], T.DOACAO, 3, mes, fornecedor="Cliente antigo")
            if indice_mes == 0:  # preços de venda definidos à mão (depois da 1ª compra)
                for nome, fator in MANUAIS.items():
                    p = s.get(Produto, produtos[nome], populate_existing=True)
                    produtos_srv.atualizar(p.id_produto, p.nome, p.categoria, p.prateleira, p.quantidade_minima,
                                           True, (p.valor_unitario * fator).quantize(D("0.01")))

            # --- OS do mês, em ordem de data (a quilometragem cresce) ---
            plano = sorted(
                (datetime.combine(dia_util(rnd, mes, ultimo), datetime.min.time())
                 + timedelta(hours=rnd.randint(8, 16), minutes=rnd.choice([0, 15, 30, 45])))
                for _ in range(rnd.randint(*OS_POR_MES))
            )
            for criada in plano:
                criada = min(criada, agora - timedelta(minutes=5))
                tipo = rnd.choice(tipos)
                (mo_min, mo_max), pecas = info_serv[tipo]
                grafia = rnd.choice([tipo] * 5 + VARIACOES.get(tipo, []))
                itens = []
                for nome in (rnd.sample(pecas, k=min(len(pecas), rnd.randint(1, 3))) if pecas else []):
                    qtd = 4 if nome.startswith("Óleo") else rnd.randint(1, 2)
                    preco = D("35.00") if nome == PECA_DOADA[0] else None  # sem preço de venda: digita
                    if preco is None and rnd.random() < 0.07:  # desconto pontual
                        p = s.get(Produto, produtos[nome])
                        preco = (p.preco_venda * D("0.9")).quantize(D("0.01")) if p.preco_venda else None
                    itens.append(ItemOS(produtos[nome], qtd, preco))
                id_cliente, id_veiculo = rnd.choice(veiculos)
                km[id_veiculo] += rnd.randint(1_500, 8_000)
                mao = D(rnd.randrange(mo_min, mo_max + 1, 10))

                dias_atras = (agora - criada).days
                sorteio = rnd.random()
                if sorteio < 0.05:
                    destino = S.ORCAMENTO          # orçamento que o cliente não aprovou
                elif dias_atras <= 3:
                    destino = rnd.choice([S.ANDAMENTO, S.ANDAMENTO, S.PRONTO, S.AGUARDANDO_PAGAMENTO])
                elif dias_atras <= 10:
                    destino = rnd.choice([S.ENTREGUE, S.ENTREGUE, S.PRONTO, S.AGUARDANDO_PAGAMENTO])
                else:
                    destino = S.AGUARDANDO_PAGAMENTO if sorteio > 0.985 else S.ENTREGUE  # poucos inadimplentes
                try:
                    os_ = oss.cadastrar(id_cliente, id_veiculo, km[id_veiculo], "Serviço de exemplo", grafia, mao,
                                        itens, status=S.ORCAMENTO if destino is S.ORCAMENTO else S.ANDAMENTO)
                except ErroDeNegocio:
                    puladas += 1  # o sistema recusou (ex.: estoque acabou), como faria na tela
                    continue
                for passo in (S.PRONTO, S.AGUARDANDO_PAGAMENTO, S.ENTREGUE):
                    if destino in (S.ORCAMENTO, S.ANDAMENTO):
                        break
                    oss.alterar_status(os_.id_ordem_servico, passo)
                    if passo is destino:
                        break
                entregue = None
                if destino is S.ENTREGUE:
                    entregue = min(criada + timedelta(days=rnd.randint(0, 4), hours=rnd.randint(2, 8)), agora)
                datas_os[os_.id_ordem_servico] = (criada, entregue)
                if destino is not S.ORCAMENTO and rnd.random() < 0.3:  # veio por agendamento
                    marcado = (criada - timedelta(days=rnd.randint(1, 6))).replace(minute=0)
                    agend_passados.append((id_cliente, id_veiculo, tipo, marcado, D(rnd.choice(["1", "1.5", "2", "3"])),
                                           StatusAgendamento.CONCLUIDO, os_.id_ordem_servico))
                elif rnd.random() < 0.04:  # cliente desmarcou
                    agend_passados.append((id_cliente, id_veiculo, tipo, criada.replace(minute=0), D("1"),
                                           StatusAgendamento.CANCELADO, None))

            # --- vendas por fora, devoluções e inventário ---
            for _ in range(rnd.randint(1, 4)):
                nome = rnd.choice(["Óleo 5W30 litro", "Filtro de ar", "Vela de ignição", "Lâmpada H4", "Aditivo de radiador"])
                p = s.get(Produto, produtos[nome], populate_existing=True)
                if p.quantidade >= 2 and p.preco_venda:
                    movs.registrar(p.id_produto, T.VENDA_AVULSA, 2, dia_util(rnd, mes, ultimo), p.preco_venda * 2)
            if indice_mes % 4 == 2:
                nome = rnd.choice(["Amortecedor dianteiro", "Disco de freio", "Bateria 60Ah"])
                p = s.get(Produto, produtos[nome], populate_existing=True)
                if p.quantidade >= 1:
                    movs.registrar(p.id_produto, T.DEVOLUCAO_FORNECEDOR, 1, ultimo,
                                   (p.valor_unitario or D("0")).quantize(D("0.01")), rnd.choice(FORNECEDORES),
                                   "Peça com defeito de fábrica (exemplo)")
            if indice_mes % 3 == 1:
                nome = rnd.choice(list(info_prod))
                p = s.get(Produto, produtos[nome], populate_existing=True)
                contada = max(0, p.quantidade + rnd.choice([-2, -1, 1]))
                if contada != p.quantidade:
                    movs.ajustar_para_contagem(p.id_produto, contada, "Inventário trimestral (exemplo)", ultimo)

            print(f"  {mes:%m/%Y}: {len(plano)} OS planejadas ({time.perf_counter() - t0:.0f} s)")
            mes, indice_mes = mes_seguinte(mes), indice_mes + 1

        # --- inventário final: algumas peças terminam ABAIXO do mínimo (alerta da tela de Produtos) ---
        for nome in sorted(ACABAM_BAIXOS):
            p = s.get(Produto, produtos[nome], populate_existing=True)
            contada = max(0, p.quantidade_minima - 1)
            if contada < p.quantidade:
                movs.ajustar_para_contagem(p.id_produto, contada, "Inventário: peças avariadas (exemplo)", hoje)

        # --- datas no passado (o sistema sempre grava "agora") ---
        for id_os, (criada, entregue) in datas_os.items():
            s.execute(update(OrdemServico).where(OrdemServico.id_ordem_servico == id_os).values(
                criado_em=criada, atualizado_em=entregue or criada, entregue_em=entregue))
        # agendamentos passados: gravados direto (o serviço não aceita data passada)
        for id_cliente, id_veiculo, tipo, quando, duracao, status, id_os in agend_passados:
            s.add(Agendamento(id_cliente=id_cliente, id_veiculo=id_veiculo, tipo_servico=tipo, data_hora=quando,
                              duracao_estimada_horas=duracao, status=status, id_ordem_servico=id_os))
        s.commit()

        # --- agendamentos futuros (pelo serviço: valida o limite de 2 simultâneos) ---
        agenda = AgendamentoService(s)
        criados = recusados = 0
        amanha = hoje + timedelta(days=1)
        for d in range(14):
            dia = amanha + timedelta(days=d)
            if dia.weekday() == 6:
                continue
            for _ in range(rnd.randint(2, 6)):
                id_cliente, id_veiculo = rnd.choice(veiculos)
                quando = datetime.combine(dia, datetime.min.time()) + timedelta(hours=rnd.randint(8, 16))
                try:
                    agenda.criar(id_cliente, id_veiculo, rnd.choice(tipos), quando, D(rnd.choice(["1", "1.5", "2", "3"])))
                    criados += 1
                except ErroDeNegocio:
                    recusados += 1
        # um horário LOTADO de propósito: 2 serviços às 10h, depois de amanhã
        lotado = datetime.combine(amanha + timedelta(days=1), datetime.min.time()) + timedelta(hours=10)
        for _ in range(3):
            id_cliente, id_veiculo = rnd.choice(veiculos)
            try:
                agenda.criar(id_cliente, id_veiculo, "Revisão", lotado, D("2"))
                criados += 1
            except ErroDeNegocio:
                recusados += 1

        total = len(datas_os)
        entregues = sum(1 for _c, e in datas_os.values() if e)
        print(f"\nBanco '{DB_NAME}': 50 clientes, 70 veículos, {len(produtos)} produtos e {total} OS de exemplo "
              f"({entregues} entregues) de {inicio:%m/%Y} a {hoje:%m/%Y}.")
        print(f"Agendamentos: {len(agend_passados)} passados, {criados} futuros "
              f"({recusados} recusados pelo limite da agenda, como na tela). OS recusadas por estoque: {puladas}.")
        print(f"Tempo: {time.perf_counter() - t0:.0f} s. Para apagar tudo: python gerar_dados_exemplo.py --remover")


if __name__ == "__main__":
    if "--remover" in sys.argv:
        remover()
    else:
        gerar()
