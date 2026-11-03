"""
Teste manual do OrdemServicoService contra o banco real (RF04 - Ordens de Serviço).

Rode da raiz do projeto, com o venv ativo:
    python testar_os_service.py

PRÉ-REQUISITO: rodar uma vez o script migrar_ordem_servico.sql no pgAdmin
(ou criar o banco com o BancoDeDadods.sql atualizado).

ATENÇÃO: o Service FAZ commit. Por isso este script cria cliente, veículos,
produtos, nota fiscal e OS de teste, usa só esses dados e, no final (bloco
finally), apaga tudo o que criou. Os dados do seed nunca são alterados.
Como o sistema não exclui OS fora de orçamento, a limpeza deste teste apaga
direto pela sessão (só aqui, por ser um teste).
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from src.config.database import SessionLocal, engine, get_session
from src.persistencia.models import (
    Cliente, MovimentacaoEstoque, NotaFiscal, OrdemServico, OsProduto, Produto,
    StatusOrdemServico, TipoMovimentacao, Veiculo,
)
from src.servico.excecoes import (
    OperacaoNaoPermitidaError, RegistroNaoEncontradoError, ValidacaoError,
)
from src.servico.movimentacao_estoque_service import MovimentacaoEstoqueService
from src.servico.ordem_servico_service import ItemOS, OrdemServicoService

engine.echo = False

S = StatusOrdemServico
CPF_1, CPF_2 = "999.999.999-01", "999.999.999-02"
PLACA_1, PLACA_2 = "TST0A01", "TST0A02"
NOME_PA, NOME_PB, NOME_PC = "Peça OS Teste A", "Peça OS Teste B", "Peça OS Teste C"
TIPO = "Teste Freios"

resultados = []


def verificar(descricao: str, condicao: bool) -> None:
    resultados.append(condicao)
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}")


def esperar_erro(descricao: str, tipo_esperado, funcao):
    try:
        funcao()
    except tipo_esperado as erro:
        verificar(f"{descricao} -> {tipo_esperado.__name__}: {str(erro).splitlines()[0]}", True)
        return erro
    except Exception as erro:  # erro de outro tipo = bug
        verificar(f"{descricao} -> erro inesperado {type(erro).__name__}: {erro}", False)
    else:
        verificar(f"{descricao} -> deveria ter levantado {tipo_esperado.__name__}", False)
    return None


def limpar() -> None:
    """Apaga tudo o que o teste criou, direto na sessão (só em teste)."""
    with get_session() as s:
        ids_p = list(s.scalars(select(Produto.id_produto).where(Produto.nome.in_([NOME_PA, NOME_PB, NOME_PC]))))
        ids_c = list(s.scalars(select(Cliente.id_cliente).where(Cliente.cpf.in_([CPF_1, CPF_2]))))
        ids_os = list(s.scalars(select(OrdemServico.id_ordem_servico).where(OrdemServico.id_cliente.in_(ids_c)))) if ids_c else []
        nfs = list(s.scalars(select(OrdemServico.id_nota_fiscal).where(
            OrdemServico.id_ordem_servico.in_(ids_os), OrdemServico.id_nota_fiscal.is_not(None)))) if ids_os else []
        if ids_os:
            s.execute(delete(OsProduto).where(OsProduto.id_ordem_servico.in_(ids_os)))
            s.execute(delete(OrdemServico).where(OrdemServico.id_ordem_servico.in_(ids_os)))
        if nfs:
            s.execute(delete(NotaFiscal).where(NotaFiscal.id_nota_fiscal.in_(nfs)))
        if ids_p:
            s.execute(delete(OsProduto).where(OsProduto.id_produto.in_(ids_p)))
            s.execute(delete(MovimentacaoEstoque).where(MovimentacaoEstoque.id_produto.in_(ids_p)))
            s.execute(delete(Produto).where(Produto.id_produto.in_(ids_p)))
        if ids_c:
            s.execute(delete(Veiculo).where(Veiculo.id_cliente.in_(ids_c)))
            s.execute(delete(Cliente).where(Cliente.id_cliente.in_(ids_c)))
        s.commit()


def saldo(session, id_produto: int) -> int:
    session.expire_all()
    return session.get(Produto, id_produto).quantidade


def vu(session, id_produto: int):
    session.expire_all()
    return session.get(Produto, id_produto).valor_unitario


def main() -> None:
    limpar()
    with get_session() as s0:
        os_antes = s0.scalar(select(func.count()).select_from(OrdemServico))
        saldos_antes = {p.id_produto: p.quantidade for p in s0.scalars(select(Produto))}
        itens_antes = s0.scalar(select(func.count()).select_from(OsProduto))

    with get_session() as session:
        servico = OrdemServicoService(session)
        movs = MovimentacaoEstoqueService(session)
        try:
            c1 = Cliente(nome="Cliente OS Teste Um", cpf=CPF_1, contato="54999990001")
            c2 = Cliente(nome="Cliente OS Teste Dois", cpf=CPF_2, contato="54999990002")
            session.add_all([c1, c2])
            session.flush()
            v1 = Veiculo(id_cliente=c1.id_cliente, modelo="Modelo Teste", marca="Marca", placa=PLACA_1)
            v2 = Veiculo(id_cliente=c2.id_cliente, modelo="Outro Teste", marca="Marca", placa=PLACA_2)
            pa = Produto(nome=NOME_PA, quantidade=0)
            pb = Produto(nome=NOME_PB, quantidade=0)
            pc = Produto(nome=NOME_PC, quantidade=3)
            session.add_all([v1, v2, pa, pb, pc])
            session.commit()
            C1, C2, V1, V2 = c1.id_cliente, c2.id_cliente, v1.id_veiculo, v2.id_veiculo
            PA, PB, PC = pa.id_produto, pb.id_produto, pc.id_produto

            print("\n--- RF09: compra atualiza o valor unitário do produto ---")
            hoje = date.today()
            verificar("produto nunca comprado tem valor_unitario vazio", vu(session, PA) is None)
            movs.registrar(PA, TipoMovimentacao.COMPRA, 10, hoje - timedelta(days=10), Decimal("200.00"), "Forn")
            verificar("compra de 10 por R$ 200 -> R$ 20,00 por unidade", vu(session, PA) == Decimal("20"))
            movs.registrar(PA, TipoMovimentacao.COMPRA, 10, hoje - timedelta(days=60), Decimal("50.00"), "Forn")
            verificar("compra mais ANTIGA não sobrescreve a mais recente", vu(session, PA) == Decimal("20"))
            movs.registrar(PB, TipoMovimentacao.COMPRA, 3, hoje, Decimal("10.00"), "Forn")
            verificar("compra de 3 por R$ 10 -> 3,3333 por unidade (4 casas)", vu(session, PB) == Decimal("3.3333"))
            movs.registrar(PB, TipoMovimentacao.COMPRA, 2, hoje, Decimal("20.00"), "Forn")
            verificar("compra mais nova (mesma data, registrada depois) vira o valor", vu(session, PB) == Decimal("10"))
            movs.registrar(PB, TipoMovimentacao.DOACAO, 5, hoje)
            movs.registrar(PB, TipoMovimentacao.VENDA_AVULSA, 1, hoje, Decimal("999.00"))
            verificar("doação e venda avulsa NÃO mudam o valor unitário", vu(session, PB) == Decimal("10"))
            verificar("saldos: A=20, B=9 (3+2+5-1), C=3", (saldo(session, PA), saldo(session, PB), saldo(session, PC)) == (20, 9, 3))
            # deixa A=10 e B=5 para facilitar as contas
            movs.ajustar_para_contagem(PA, 10, "acerto do teste")
            movs.ajustar_para_contagem(PB, 5, "acerto do teste")
            verificar("saldos de partida: A=10, B=5, C=3 (C nunca comprado)", (saldo(session, PA), saldo(session, PB), saldo(session, PC)) == (10, 5, 3))
            verificar("C sem compra: valor_unitario vazio", vu(session, PC) is None)

            print("\n--- Validações ---")
            ok = dict(id_cliente=C1, id_veiculo=V1, quilometragem=50000, descricao_problema="Barulho nos freios", tipo_servico=TIPO)
            e = esperar_erro("tudo vazio", ValidacaoError, lambda: servico.cadastrar(None, None, None, "", ""))
            verificar("   lista todos os 5 campos obrigatórios", e is not None and len(e.erros) >= 5)
            esperar_erro("quilometragem negativa", ValidacaoError, lambda: servico.cadastrar(**{**ok, "quilometragem": -1}))
            esperar_erro("quilometragem texto", ValidacaoError, lambda: servico.cadastrar(**{**ok, "quilometragem": "abc"}))
            esperar_erro("quilometragem booleana", ValidacaoError, lambda: servico.cadastrar(**{**ok, "quilometragem": True}))
            esperar_erro("descrição só com espaços", ValidacaoError, lambda: servico.cadastrar(**{**ok, "descricao_problema": "   "}))
            esperar_erro("tipo de serviço vazio", ValidacaoError, lambda: servico.cadastrar(**{**ok, "tipo_servico": " "}))
            esperar_erro("tipo de serviço muito longo", ValidacaoError, lambda: servico.cadastrar(**{**ok, "tipo_servico": "x" * 151}))
            esperar_erro("veículo de outro cliente", ValidacaoError, lambda: servico.cadastrar(**{**ok, "id_veiculo": V2}))
            esperar_erro("cliente inexistente", ValidacaoError, lambda: servico.cadastrar(**{**ok, "id_cliente": 99999999}))
            esperar_erro("veículo inexistente", ValidacaoError, lambda: servico.cadastrar(**{**ok, "id_veiculo": 99999999}))
            esperar_erro("mão de obra negativa", ValidacaoError, lambda: servico.cadastrar(**ok, valor_mao_de_obra=-1))
            esperar_erro("mão de obra acima do limite", ValidacaoError, lambda: servico.cadastrar(**ok, valor_mao_de_obra=10**9))
            esperar_erro("mão de obra texto", ValidacaoError, lambda: servico.cadastrar(**ok, valor_mao_de_obra="abc"))
            esperar_erro("peça repetida", ValidacaoError,
                         lambda: servico.cadastrar(**ok, itens=[ItemOS(PA, 1, 10), ItemOS(PA, 2, 10)]))
            esperar_erro("quantidade zero", ValidacaoError, lambda: servico.cadastrar(**ok, itens=[ItemOS(PA, 0, 10)]))
            esperar_erro("quantidade decimal", ValidacaoError, lambda: servico.cadastrar(**ok, itens=[ItemOS(PA, 1.5, 10)]))
            esperar_erro("preço vazio", ValidacaoError, lambda: servico.cadastrar(**ok, itens=[ItemOS(PA, 1, None)]))
            esperar_erro("preço negativo", ValidacaoError, lambda: servico.cadastrar(**ok, itens=[ItemOS(PA, 1, -5)]))
            esperar_erro("produto inexistente", ValidacaoError, lambda: servico.cadastrar(**ok, itens=[ItemOS(99999999, 1, 5)]))
            esperar_erro("status inicial 'pronto'", ValidacaoError, lambda: servico.cadastrar(**ok, status="pronto"))
            esperar_erro("status inicial inválido", ValidacaoError, lambda: servico.cadastrar(**ok, status="xyz"))
            verificar("nenhuma OS foi criada pelas tentativas inválidas",
                      session.scalar(select(func.count()).select_from(OrdemServico).where(OrdemServico.id_cliente == C1)) == 0)
            verificar("estoque intacto após as tentativas inválidas", (saldo(session, PA), saldo(session, PB), saldo(session, PC)) == (10, 5, 3))

            print("\n--- Orçamento: cria sem mexer no estoque ---")
            os1 = servico.cadastrar(C1, V1, 50000, "  Barulho nos freios ", "  Teste   Freios ",
                                    Decimal("100"), [ItemOS(PA, 2, Decimal("35.00")), ItemOS(PB, 1, 18.5)])
            ID1 = os1.id_ordem_servico
            verificar("nasce como orçamento", os1.status is S.ORCAMENTO and os1.entregue_em is None)
            verificar("textos normalizados (trim e espaços internos)", os1.descricao_problema == "Barulho nos freios" and os1.tipo_servico == TIPO)
            verificar("valor_pecas = 2x35 + 18,50 = 88,50", os1.valor_pecas == Decimal("88.50"))
            verificar("valor_total = peças + mão de obra = 188,50", os1.valor_total == Decimal("188.50"))
            verificar("estoque NÃO mudou em orçamento", (saldo(session, PA), saldo(session, PB)) == (10, 5))
            linhas = {i.id_produto: i for i in os1.os_produtos}
            verificar("custo gravado na linha = último valor pago (A=20, B=10)",
                      linhas[PA].custo_unitario == Decimal("20") and linhas[PB].custo_unitario == Decimal("10"))
            verificar("não cria movimentação de estoque", session.scalar(select(func.count()).select_from(MovimentacaoEstoque).where(
                MovimentacaoEstoque.observacao.is_(None), MovimentacaoEstoque.id_produto == PA, MovimentacaoEstoque.quantidade < 0)) == 0)

            print("\n--- Aviso de quilometragem (não bloqueia) ---")
            verificar("sem OS anterior no veículo... a própria OS é ignorada", servico.aviso_quilometragem(V1, 10, ID1) is None)
            verificar("km menor que a última OS gera aviso", "menor" in (servico.aviso_quilometragem(V1, 40000) or ""))
            verificar("km igual/maior não avisa", servico.aviso_quilometragem(V1, 50000) is None and servico.aviso_quilometragem(V1, 60000) is None)
            os_km = servico.cadastrar(C1, V1, 40000, "km menor ainda salva", "Revisão")
            verificar("cadastro com km menor FUNCIONA (só aviso)", os_km.quilometragem == 40000)
            servico.excluir(os_km.id_ordem_servico)

            print("\n--- Orçamento -> Andamento baixa o estoque ---")
            os1 = servico.alterar_status(ID1, S.ANDAMENTO)
            verificar("status andamento", os1.status is S.ANDAMENTO)
            verificar("estoque baixou: A=8, B=4", (saldo(session, PA), saldo(session, PB)) == (8, 4))

            print("\n--- Transições inválidas ---")
            esperar_erro("andamento -> aguardando_pagamento", OperacaoNaoPermitidaError, lambda: servico.alterar_status(ID1, S.AGUARDANDO_PAGAMENTO))
            esperar_erro("andamento -> entregue", OperacaoNaoPermitidaError, lambda: servico.alterar_status(ID1, S.ENTREGUE))
            esperar_erro("andamento -> andamento", OperacaoNaoPermitidaError, lambda: servico.alterar_status(ID1, S.ANDAMENTO))
            esperar_erro("status inexistente", ValidacaoError, lambda: servico.alterar_status(ID1, "voando"))
            esperar_erro("OS inexistente", RegistroNaoEncontradoError, lambda: servico.alterar_status(99999999, S.ANDAMENTO))
            verificar("estoque continua A=8, B=4", (saldo(session, PA), saldo(session, PB)) == (8, 4))
            verificar("transições permitidas em andamento: orçamento e pronto",
                      servico.transicoes_permitidas(servico.obter(ID1)) == [S.ORCAMENTO, S.PRONTO])

            print("\n--- Editar em andamento ajusta o estoque na hora ---")
            os1 = servico.atualizar(ID1, C1, V1, 50000, "Barulho nos freios", TIPO, Decimal("120"),
                                    [ItemOS(PA, 5, Decimal("40")), ItemOS(PC, 1, Decimal("70"))])  # A 2->5, B removido, C novo
            verificar("A: 8 - 3 = 5 | B devolvido: 4 + 1 = 5 | C: 3 - 1 = 2", (saldo(session, PA), saldo(session, PB), saldo(session, PC)) == (5, 5, 2))
            verificar("total recalculado: 5x40 + 1x70 + 120 = 390", os1.valor_total == Decimal("390.00"))
            linhas = {i.id_produto: i for i in os1.os_produtos}
            verificar("peças da OS: A e C (B saiu)", set(linhas) == {PA, PC})
            verificar("peça sem compra: custo vazio", linhas[PC].custo_unitario is None)
            movs.registrar(PA, TipoMovimentacao.COMPRA, 1, hoje, Decimal("30.00"), "Forn")  # valor_unitario de A muda p/ 30
            os1 = servico.atualizar(ID1, C1, V1, 50000, "Barulho nos freios", TIPO, Decimal("120"),
                                    [ItemOS(PA, 4, Decimal("41")), ItemOS(PC, 1, Decimal("70"))])
            linhas = {i.id_produto: i for i in os1.os_produtos}
            verificar("custo gravado é cópia do momento: A continua 20 mesmo após nova compra a 30", linhas[PA].custo_unitario == Decimal("20"))
            verificar("preço atualizado e estoque devolveu 1 (A: 5+1(compra)+1)", linhas[PA].preco_unitario == Decimal("41.00") and saldo(session, PA) == 7)

            print("\n--- Estoque insuficiente bloqueia e lista as peças ---")
            antes = (saldo(session, PA), saldo(session, PB), saldo(session, PC))
            erro = esperar_erro("aumentar A e C além do saldo", OperacaoNaoPermitidaError,
                                lambda: servico.atualizar(ID1, C1, V1, 50000, "Barulho nos freios", TIPO, 0,
                                                          [ItemOS(PA, 40, 1), ItemOS(PC, 30, 1)]))
            verificar("   mensagem lista as DUAS peças", erro is not None and NOME_PA in str(erro) and NOME_PC in str(erro))
            verificar("   nada foi gravado (estoque e peças iguais)",
                      (saldo(session, PA), saldo(session, PB), saldo(session, PC)) == antes
                      and {i.id_produto: i.quantidade_utilizada for i in servico.obter(ID1).os_produtos} == {PA: 4, PC: 1})

            print("\n--- Andamento -> Orçamento devolve tudo ---")
            os1 = servico.alterar_status(ID1, S.ORCAMENTO)
            verificar("estoque devolvido: A=11, B=5, C=3", (saldo(session, PA), saldo(session, PB), saldo(session, PC)) == (11, 5, 3))
            os1 = servico.atualizar(ID1, C1, V1, 50000, "Barulho nos freios", TIPO, 0, [ItemOS(PA, 9, 10)])
            verificar("editar em orçamento (mesmo pedindo 9) não mexe no estoque", saldo(session, PA) == 11)
            erro = esperar_erro("orçamento -> andamento sem saldo (A=11, pede 12)", OperacaoNaoPermitidaError,
                                lambda: (servico.atualizar(ID1, C1, V1, 50000, "Barulho nos freios", TIPO, 0, [ItemOS(PA, 12, 10)]),
                                         servico.alterar_status(ID1, S.ANDAMENTO)))
            verificar("   continua orçamento e estoque intacto", servico.obter(ID1).status is S.ORCAMENTO and saldo(session, PA) == 11)
            servico.atualizar(ID1, C1, V1, 50000, "Barulho nos freios", TIPO, 0, [ItemOS(PA, 3, 10)])

            print("\n--- Exclusão: só orçamento ---")
            os_x = servico.cadastrar(C1, V1, 50000, "Para excluir", TIPO, itens=[ItemOS(PB, 1, 5)])
            servico.excluir(os_x.id_ordem_servico)
            verificar("orçamento excluído (OS e peças)", session.get(OrdemServico, os_x.id_ordem_servico) is None
                      and session.scalar(select(func.count()).select_from(OsProduto).where(OsProduto.id_ordem_servico == os_x.id_ordem_servico)) == 0)
            esperar_erro("excluir OS inexistente", RegistroNaoEncontradoError, lambda: servico.excluir(99999999))

            print("\n--- Criar já em andamento ---")
            antes = (saldo(session, PA), saldo(session, PB), saldo(session, PC))
            qtd_os = session.scalar(select(func.count()).select_from(OrdemServico).where(OrdemServico.id_cliente == C2))
            esperar_erro("em andamento sem saldo", OperacaoNaoPermitidaError,
                         lambda: servico.cadastrar(C2, V2, 1000, "Sem saldo", TIPO, itens=[ItemOS(PC, 4, 1)], status=S.ANDAMENTO))
            verificar("   OS não foi criada e estoque intacto",
                      session.scalar(select(func.count()).select_from(OrdemServico).where(OrdemServico.id_cliente == C2)) == qtd_os
                      and (saldo(session, PA), saldo(session, PB), saldo(session, PC)) == antes)
            os2 = servico.cadastrar(C2, V2, 1000, "Em andamento direto", "Elétrica", Decimal("50"),
                                    [ItemOS(PC, 2, 100)], status="andamento")
            ID2 = os2.id_ordem_servico
            verificar("criada em andamento e baixou o estoque (C: 3 -> 1)", os2.status is S.ANDAMENTO and saldo(session, PC) == 1)

            print("\n--- Pronto trava a OS; entregue é o fim ---")
            os2 = servico.alterar_status(ID2, S.PRONTO)
            esperar_erro("editar OS pronta", OperacaoNaoPermitidaError,
                         lambda: servico.atualizar(ID2, C2, V2, 1000, "x", "Elétrica", 0, [ItemOS(PC, 1, 1)]))
            esperar_erro("excluir OS pronta", OperacaoNaoPermitidaError, lambda: servico.excluir(ID2))
            esperar_erro("pronto -> orcamento direto", OperacaoNaoPermitidaError, lambda: servico.alterar_status(ID2, S.ORCAMENTO))
            verificar("estoque da OS pronta continua baixado (C=1)", saldo(session, PC) == 1)
            os2 = servico.alterar_status(ID2, S.AGUARDANDO_PAGAMENTO)
            os2 = servico.alterar_status(ID2, S.PRONTO)       # voltar é permitido sem nota
            os2 = servico.alterar_status(ID2, S.ANDAMENTO)
            os2 = servico.alterar_status(ID2, S.PRONTO)
            os2 = servico.alterar_status(ID2, S.AGUARDANDO_PAGAMENTO)
            verificar("ainda sem entregue_em antes da entrega", os2.entregue_em is None)
            os2 = servico.alterar_status(ID2, S.ENTREGUE)
            verificar("entregue grava entregue_em", os2.status is S.ENTREGUE and os2.entregue_em is not None)
            for destino in (S.AGUARDANDO_PAGAMENTO, S.PRONTO, S.ANDAMENTO, S.ORCAMENTO):
                esperar_erro(f"entregue -> {destino.value}", OperacaoNaoPermitidaError, lambda d=destino: servico.alterar_status(ID2, d))
            verificar("entregue não tem próximos passos", servico.transicoes_permitidas(servico.obter(ID2)) == [])
            verificar("estoque da OS entregue continua baixado (C=1)", saldo(session, PC) == 1)

            print("\n--- Nota fiscal impede voltar de status ---")
            os3 = servico.cadastrar(C1, V1, 51000, "Com nota", TIPO, itens=[ItemOS(PB, 1, 20)], status=S.ANDAMENTO)
            ID3 = os3.id_ordem_servico
            servico.alterar_status(ID3, S.PRONTO)
            nf = NotaFiscal(status="pendente")
            session.add(nf)
            session.flush()
            session.get(OrdemServico, ID3).id_nota_fiscal = nf.id_nota_fiscal
            session.commit()
            esperar_erro("pronto -> andamento com nota fiscal", OperacaoNaoPermitidaError, lambda: servico.alterar_status(ID3, S.ANDAMENTO))
            verificar("transições permitidas com nota: só aguardando pagamento",
                      servico.transicoes_permitidas(servico.obter(ID3)) == [S.AGUARDANDO_PAGAMENTO])
            servico.alterar_status(ID3, S.AGUARDANDO_PAGAMENTO)
            esperar_erro("aguardando -> pronto com nota fiscal", OperacaoNaoPermitidaError, lambda: servico.alterar_status(ID3, S.PRONTO))
            servico.alterar_status(ID3, S.ENTREGUE)

            print("\n--- Consultas ---")
            esperar_erro("obter OS inexistente", RegistroNaoEncontradoError, lambda: servico.obter(99999999))
            verificar("listar por nome do cliente", {o.id_ordem_servico for o in servico.listar("Cliente OS Teste Dois")} == {ID2})
            verificar("listar por placa", {o.id_ordem_servico for o in servico.listar(PLACA_1.lower())} >= {ID1, ID3})
            verificar("listar por nº da OS", [o.id_ordem_servico for o in servico.listar(str(ID2))][:1] == [ID2])
            verificar("filtro por status", {o.id_ordem_servico for o in servico.listar("Cliente OS Teste", S.ENTREGUE)} == {ID2, ID3})
            verificar("filtro orçamento", {o.id_ordem_servico for o in servico.listar("Cliente OS Teste", S.ORCAMENTO)} == {ID1})
            verificar("busca com % e _ é literal (não curinga)", servico.listar("%") == [] and servico.listar("_") == [])
            verificar("histórico por veículo (mais recente primeiro)", [o.id_ordem_servico for o in servico.listar_por_veiculo(V1)] == [ID3, ID1])
            verificar("tipos de serviço sugeridos incluem o do teste", TIPO in servico.listar_tipos_servico())

            print("\n--- Última linha de defesa: CHECK/UNIQUE do banco ---")
            def bd(sql: str, **p):
                try:
                    session.execute(text(sql), p)
                    session.commit()
                    return False
                except IntegrityError:
                    session.rollback()
                    return True
            verificar("banco recusa status fora da lista", bd("UPDATE ordem_servico SET status='roubado' WHERE id_ordem_servico=:i", i=ID1))
            verificar("banco recusa 'entregue' sem entregue_em", bd("UPDATE ordem_servico SET status='entregue', entregue_em=NULL WHERE id_ordem_servico=:i", i=ID1))
            verificar("banco recusa entregue_em fora de 'entregue'", bd("UPDATE ordem_servico SET entregue_em=NOW() WHERE id_ordem_servico=:i", i=ID1))
            verificar("banco recusa mão de obra negativa", bd("UPDATE ordem_servico SET valor_mao_de_obra=-1 WHERE id_ordem_servico=:i", i=ID1))
            verificar("banco recusa preço negativo na peça", bd("UPDATE os_produto SET preco_unitario=-1 WHERE id_ordem_servico=:i", i=ID1))
            verificar("banco recusa custo negativo na peça", bd("UPDATE os_produto SET custo_unitario=-1 WHERE id_ordem_servico=:i", i=ID1))
            verificar("banco recusa valor_unitario negativo no produto", bd("UPDATE produto SET valor_unitario=-1 WHERE id_produto=:i", i=PA))
            verificar("banco recusa peça repetida na OS", bd(
                "INSERT INTO os_produto (id_ordem_servico, id_produto, quantidade_utilizada, preco_unitario) VALUES (:o, :p, 1, 1)", o=ID1, p=PA))

            if engine.dialect.name == "postgresql":
                print("\n--- Trava de concorrência (só PostgreSQL) ---")
                os4 = servico.cadastrar(C2, V2, 2000, "Concorrência", TIPO, itens=[ItemOS(PB, 1, 5)])
                s1, s2 = SessionLocal(), SessionLocal()
                try:
                    s1.get(Produto, PB, with_for_update=True)  # janela 1 segura o produto
                    s2.execute(text("SET lock_timeout = '500ms'"))
                    try:
                        OrdemServicoService(s2).alterar_status(os4.id_ordem_servico, S.ANDAMENTO)
                        verificar("segunda janela espera/recusa enquanto a primeira trava o produto", False)
                    except OperationalError:
                        verificar("segunda janela espera/recusa enquanto a primeira trava o produto", True)
                finally:
                    s2.rollback(); s2.close(); s1.rollback(); s1.close()
                verificar("a OS da janela barrada continua em orçamento", servico.obter(os4.id_ordem_servico).status is S.ORCAMENTO)
        finally:
            session.rollback()
            limpar()

    with get_session() as s:
        verificar("limpeza: nada de teste sobrou", s.scalar(select(func.count()).select_from(Produto).where(
            Produto.nome.in_([NOME_PA, NOME_PB, NOME_PC]))) == 0 and s.scalar(select(func.count()).select_from(Cliente).where(
            Cliente.cpf.in_([CPF_1, CPF_2]))) == 0)
        verificar("OS que já existiam continuam as mesmas", s.scalar(select(func.count()).select_from(OrdemServico)) == os_antes
                  and s.scalar(select(func.count()).select_from(OsProduto)) == itens_antes)
        verificar("saldos dos produtos que já existiam não foram alterados",
                  {p.id_produto: p.quantidade for p in s.scalars(select(Produto))} == saldos_antes)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
