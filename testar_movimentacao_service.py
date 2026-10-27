"""
Teste manual do MovimentacaoEstoqueService contra o banco real (RF09 - Estoque).

Rode da raiz do projeto, com o venv ativo:
    python testar_movimentacao_service.py

PRÉ-REQUISITO: rodar uma vez o script migrar_movimentacao_estoque.sql no
pgAdmin (transforma entrada_estoque em movimentacao_estoque). Sem ele o teste
não encontra a tabela.

ATENÇÃO: o Service FAZ commit. Por isso este script cria produtos de teste,
movimenta só esses produtos e, no final (bloco finally), apaga tudo o que criou.
Os produtos do seed (BancoDeDadods.sql) nunca são alterados.
Como o sistema NÃO exclui movimentações, a limpeza deste teste apaga direto
pela sessão (só aqui, por ser um teste).
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from src.config.database import SessionLocal, engine, get_session
from src.persistencia.models import MovimentacaoEstoque, Produto, TipoMovimentacao
from src.servico.excecoes import (
    OperacaoNaoPermitidaError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)
from src.servico.movimentacao_estoque_service import MovimentacaoEstoqueService
from src.servico.produto_service import ProdutoService

# Silencia o SQL impresso pelo echo=True para o resultado ficar legível.
engine.echo = False

NOME_A = "Produto Mov Teste A"
NOME_B = "Produto Mov Teste B"
T = TipoMovimentacao

resultados = []


def verificar(descricao: str, condicao: bool) -> None:
    resultados.append(condicao)
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}")


def esperar_erro(descricao: str, tipo_esperado, funcao) -> None:
    """Executa funcao() e confere se levantou exatamente o erro esperado."""
    try:
        funcao()
    except tipo_esperado as erro:
        verificar(f"{descricao} -> {tipo_esperado.__name__}: {str(erro).splitlines()[0]}", True)
    except Exception as erro:  # erro de outro tipo = bug
        verificar(f"{descricao} -> erro inesperado {type(erro).__name__}: {erro}", False)
    else:
        verificar(f"{descricao} -> deveria ter levantado {tipo_esperado.__name__}", False)


def saldo(session, id_produto: int) -> int:
    session.expire_all()
    return session.get(Produto, id_produto).quantidade


def qtd_movimentacoes(session, id_produto: int) -> int:
    return session.scalar(
        select(func.count()).select_from(MovimentacaoEstoque).where(MovimentacaoEstoque.id_produto == id_produto)
    )


def limpar() -> None:
    """Apaga movimentações e produtos de teste, direto na sessão (só em teste)."""
    with get_session() as s:
        ids = list(s.scalars(select(Produto.id_produto).where(Produto.nome.in_([NOME_A, NOME_B]))))
        if ids:
            s.execute(delete(MovimentacaoEstoque).where(MovimentacaoEstoque.id_produto.in_(ids)))
            s.execute(delete(Produto).where(Produto.id_produto.in_(ids)))
            s.commit()


def main() -> None:
    limpar()  # começo limpo, mesmo se uma rodada anterior falhou
    with get_session() as session:
        produtos = ProdutoService(session)
        servico = MovimentacaoEstoqueService(session)
        try:
            a = produtos.cadastrar(NOME_A, "Testes", "T1", quantidade_minima=5)
            b = produtos.cadastrar(NOME_B)
            id_a, id_b = a.id_produto, b.id_produto
            verificar("produtos de teste nascem com estoque 0", saldo(session, id_a) == 0)
            hoje = date.today()

            print("\n--- Compra (+) ---")
            m = servico.registrar(id_a, T.COMPRA, 10, valor=Decimal("100.50"), fornecedor="  Forn X ")
            verificar("compra gravou quantidade positiva e tipo enum", m.quantidade == 10 and m.tipo is T.COMPRA)
            verificar("saldo do produto subiu para 10", saldo(session, id_a) == 10)
            verificar("valor e fornecedor normalizados", m.valor == Decimal("100.50") and m.fornecedor == "Forn X")
            verificar("data padrão é hoje", m.data_movimentacao == hoje)
            m2 = servico.registrar(id_a, "compra", 2, valor=10, fornecedor="Forn Y")
            verificar("tipo aceito também como texto ('compra') e valor inteiro", m2.tipo is T.COMPRA)
            verificar("saldo 12", saldo(session, id_a) == 12)
            esperar_erro("compra sem fornecedor", ValidacaoError,
                         lambda: servico.registrar(id_a, T.COMPRA, 1, valor=5))
            esperar_erro("compra sem valor", ValidacaoError,
                         lambda: servico.registrar(id_a, T.COMPRA, 1, fornecedor="X"))

            print("\n--- Doação (+) ---")
            servico.registrar(id_a, T.DOACAO, 3)
            verificar("doação sem fornecedor/valor funciona; saldo 15", saldo(session, id_a) == 15)
            d = servico.registrar(id_a, T.DOACAO, 1, fornecedor="Seu João")
            verificar("doação aceita doador (campo fornecedor); saldo 16", d.fornecedor == "Seu João" and saldo(session, id_a) == 16)
            esperar_erro("doação com valor", ValidacaoError,
                         lambda: servico.registrar(id_a, T.DOACAO, 1, valor=10))

            print("\n--- Venda avulsa (−) ---")
            v = servico.registrar(id_a, T.VENDA_AVULSA, 4, valor=Decimal("80"))
            verificar("venda gravou quantidade NEGATIVA (-4)", v.quantidade == -4)
            verificar("saldo caiu para 12", saldo(session, id_a) == 12)
            esperar_erro("venda sem valor recebido", ValidacaoError,
                         lambda: servico.registrar(id_a, T.VENDA_AVULSA, 1))
            esperar_erro("venda com fornecedor", ValidacaoError,
                         lambda: servico.registrar(id_a, T.VENDA_AVULSA, 1, valor=5, fornecedor="X"))

            print("\n--- Devolução ao fornecedor (−) ---")
            dv = servico.registrar(id_a, T.DEVOLUCAO_FORNECEDOR, 2, fornecedor="Forn X")
            verificar("devolução gravou -2 e valor ressarcido é opcional", dv.quantidade == -2 and dv.valor is None)
            verificar("saldo 10", saldo(session, id_a) == 10)
            esperar_erro("devolução sem fornecedor", ValidacaoError,
                         lambda: servico.registrar(id_a, T.DEVOLUCAO_FORNECEDOR, 1))

            print("\n--- Saldo nunca fica negativo ---")
            antes = qtd_movimentacoes(session, id_a)
            esperar_erro("venda maior que o saldo", OperacaoNaoPermitidaError,
                         lambda: servico.registrar(id_a, T.VENDA_AVULSA, 11, valor=1))
            verificar("saldo continua 10 e nada foi gravado",
                      saldo(session, id_a) == 10 and qtd_movimentacoes(session, id_a) == antes)
            servico.registrar(id_a, T.VENDA_AVULSA, 10, valor=1)
            verificar("vender exatamente o saldo é permitido (fica 0)", saldo(session, id_a) == 0)

            print("\n--- Ajuste (+/−) ---")
            aj = servico.registrar(id_a, T.AJUSTE, 7, observacao="Achei peças na prateleira errada")
            verificar("ajuste positivo direto (+7)", aj.quantidade == 7 and saldo(session, id_a) == 7)
            servico.registrar(id_a, T.AJUSTE, -2, observacao="Quebradas")
            verificar("ajuste negativo direto (-2); saldo 5", saldo(session, id_a) == 5)
            esperar_erro("ajuste sem justificativa", ValidacaoError,
                         lambda: servico.registrar(id_a, T.AJUSTE, 1))
            esperar_erro("ajuste zero", ValidacaoError,
                         lambda: servico.registrar(id_a, T.AJUSTE, 0, observacao="x"))
            esperar_erro("ajuste que deixaria saldo negativo", OperacaoNaoPermitidaError,
                         lambda: servico.registrar(id_a, T.AJUSTE, -6, observacao="x"))
            esperar_erro("ajuste com valor", ValidacaoError,
                         lambda: servico.registrar(id_a, T.AJUSTE, 1, observacao="x", valor=3))

            print("\n--- Ajuste pela contagem física ---")
            c = servico.ajustar_para_contagem(id_a, 12, "Inventário de outubro")
            verificar("contou 12 com saldo 5 => ajuste de +7", c.quantidade == 7 and saldo(session, id_a) == 12)
            c = servico.ajustar_para_contagem(id_a, 9, "Faltou peça")
            verificar("contou 9 com saldo 12 => ajuste de -3", c.quantidade == -3 and saldo(session, id_a) == 9)
            c = servico.ajustar_para_contagem(id_a, 0, "Acabou tudo")
            verificar("contou 0 => zera o saldo", saldo(session, id_a) == 0)
            esperar_erro("contagem igual ao saldo", ValidacaoError,
                         lambda: servico.ajustar_para_contagem(id_a, 0, "x"))
            esperar_erro("contagem negativa", ValidacaoError,
                         lambda: servico.ajustar_para_contagem(id_a, -1, "x"))
            esperar_erro("contagem sem justificativa", ValidacaoError,
                         lambda: servico.ajustar_para_contagem(id_a, 3, ""))

            print("\n--- Validações gerais ---")
            esperar_erro("produto não informado", ValidacaoError,
                         lambda: servico.registrar(None, T.COMPRA, 1, valor=1, fornecedor="X"))
            esperar_erro("produto inexistente", RegistroNaoEncontradoError,
                         lambda: servico.registrar(999999, T.COMPRA, 1, valor=1, fornecedor="X"))
            esperar_erro("tipo inválido", ValidacaoError, lambda: servico.registrar(id_b, "sumiu", 1))
            esperar_erro("quantidade zero", ValidacaoError,
                         lambda: servico.registrar(id_b, T.DOACAO, 0))
            esperar_erro("quantidade negativa em tipo não-ajuste", ValidacaoError,
                         lambda: servico.registrar(id_b, T.DOACAO, -3))
            esperar_erro("quantidade decimal", ValidacaoError,
                         lambda: servico.registrar(id_b, T.DOACAO, 1.5))
            esperar_erro("quantidade gigante", ValidacaoError,
                         lambda: servico.registrar(id_b, T.DOACAO, 2_000_000))
            esperar_erro("data futura", ValidacaoError,
                         lambda: servico.registrar(id_b, T.DOACAO, 1, data_movimentacao=hoje + timedelta(days=1)))
            esperar_erro("valor negativo", ValidacaoError,
                         lambda: servico.registrar(id_b, T.COMPRA, 1, valor=-1, fornecedor="X"))
            esperar_erro("valor em texto", ValidacaoError,
                         lambda: servico.registrar(id_b, T.COMPRA, 1, valor="10", fornecedor="X"))
            esperar_erro("observação grande demais", ValidacaoError,
                         lambda: servico.registrar(id_b, T.DOACAO, 1, observacao="x" * 501))
            r = servico.registrar(id_b, T.COMPRA, 1, valor=Decimal("10.005"), fornecedor="X",
                                  data_movimentacao=hoje - timedelta(days=40))
            verificar("valor arredondado para 2 casas (10.005 -> 10.01)", r.valor == Decimal("10.01"))
            verificar("data passada é aceita", r.data_movimentacao == hoje - timedelta(days=40))
            esperar_erro("vários erros de uma vez", ValidacaoError,
                         lambda: servico.registrar(None, "x", 0, valor=-1))

            print("\n--- Consultas ---")
            todas = servico.listar()
            ids_teste = [x for x in todas if x.id_produto in (id_a, id_b)]
            verificar("listar traz as movimentações do seed e as de teste", len(todas) >= 5 + len(ids_teste))
            verificar("ordem: mais recente primeiro",
                      [x.data_movimentacao for x in todas] == sorted((x.data_movimentacao for x in todas), reverse=True))
            vendas = servico.listar(tipo=T.VENDA_AVULSA)
            verificar("filtro por tipo", vendas and all(x.tipo is T.VENDA_AVULSA for x in vendas))
            verificar("busca pelo nome do produto", any(x.id_produto == id_b for x in servico.listar("mov teste b")))
            verificar("busca pelo fornecedor", any(x.fornecedor == "Forn Y" for x in servico.listar("forn y")))
            verificar("busca pela observação", any(x.observacao == "Quebradas" for x in servico.listar("quebradas")))
            verificar("filtro de período exclui o que é mais antigo",
                      all(x.data_movimentacao >= hoje - timedelta(days=30) for x in servico.listar(data_inicio=hoje - timedelta(days=30))))
            verificar("período sem registros volta vazio", servico.listar(data_inicio=hoje + timedelta(days=1)) == [])
            esperar_erro("obter movimentação inexistente", RegistroNaoEncontradoError, lambda: servico.obter(999999))

            print("\n--- Integridade ---")
            soma = session.scalar(select(func.sum(MovimentacaoEstoque.quantidade)).where(MovimentacaoEstoque.id_produto == id_a))
            verificar("soma das movimentações do produto A == saldo dele (começou em 0)", soma == saldo(session, id_a))
            esperar_erro("produto com movimentações não pode ser excluído", OperacaoNaoPermitidaError,
                         lambda: produtos.excluir(id_a))
            verificar("o sistema não tem como editar/excluir movimentação (só registrar e consultar)",
                      not hasattr(servico, "excluir") and not hasattr(servico, "atualizar"))

            print("\n--- Última linha de defesa: CHECK do banco (gravando por fora do Service) ---")
            casos = {
                "compra com quantidade negativa": dict(tipo=T.COMPRA, quantidade=-1, valor=1, fornecedor="X"),
                "venda com quantidade positiva": dict(tipo=T.VENDA_AVULSA, quantidade=1, valor=1),
                "quantidade zero": dict(tipo=T.AJUSTE, quantidade=0, observacao="x"),
                "compra sem fornecedor": dict(tipo=T.COMPRA, quantidade=1, valor=1),
                "compra sem valor": dict(tipo=T.COMPRA, quantidade=1, fornecedor="X"),
                "devolução sem fornecedor": dict(tipo=T.DEVOLUCAO_FORNECEDOR, quantidade=-1),
                "ajuste sem observação": dict(tipo=T.AJUSTE, quantidade=1),
                "valor negativo": dict(tipo=T.DOACAO, quantidade=1, valor=-1),
            }
            for nome, campos in casos.items():
                try:
                    session.add(MovimentacaoEstoque(id_produto=id_b, data_movimentacao=hoje, **campos))
                    session.commit()
                    verificar(f"banco recusou: {nome}", False)
                except IntegrityError:
                    session.rollback()
                    verificar(f"banco recusou: {nome}", True)
            try:
                session.execute(text(
                    "INSERT INTO movimentacao_estoque (id_produto, tipo, quantidade, data_movimentacao) "
                    "VALUES (:p, 'roubo', 1, CURRENT_DATE)"), {"p": id_b})
                session.commit()
                verificar("banco recusou: tipo fora da lista", False)
            except IntegrityError:
                session.rollback()
                verificar("banco recusou: tipo fora da lista", True)

            if engine.dialect.name == "postgresql":
                print("\n--- Trava de concorrência (só PostgreSQL) ---")
                s1, s2 = SessionLocal(), SessionLocal()
                try:
                    s1.get(Produto, id_b, with_for_update=True)  # janela 1 segura a linha
                    s2.execute(text("SET lock_timeout = '500ms'"))
                    esperar_erro("segunda janela espera/recusa enquanto a primeira movimenta o mesmo produto",
                                 OperationalError,
                                 lambda: MovimentacaoEstoqueService(s2).registrar(id_b, T.DOACAO, 1))
                finally:
                    s2.rollback(); s2.close(); s1.rollback(); s1.close()
        finally:
            session.rollback()
            limpar()

    with get_session() as s:
        restou = s.scalar(select(func.count()).select_from(Produto).where(Produto.nome.in_([NOME_A, NOME_B])))
        verificar("limpeza: nenhum produto de teste sobrou", restou == 0)
        sobrou_mov = s.scalar(select(func.count()).select_from(MovimentacaoEstoque).where(MovimentacaoEstoque.observacao.in_(
            ["Achei peças na prateleira errada", "Quebradas", "Inventário de outubro", "Faltou peça", "Acabou tudo"])))
        verificar("limpeza: nenhuma movimentação de teste sobrou", sobrou_mov == 0)
        verificar("seed intacto: continua com as 5 compras originais",
                  s.scalar(select(func.count()).select_from(MovimentacaoEstoque)) == 5)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
