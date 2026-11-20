"""
Teste manual do ProdutoService contra o banco real (RF03 - Gerenciar Produtos).

Rode da raiz do projeto, com o venv ativo:
    python testar_produto_service.py

PRÉ-REQUISITO: rodar uma vez o script alterar_produto_nome_unico.sql no pgAdmin
(cria o índice único do nome). Sem ele, só o teste do índice no banco falha.
Para o preço de venda: rodar uma vez o migrar_preco_venda.sql (ou criar o
banco com o BancoDeDadods.sql atualizado).

ATENÇÃO: o Service FAZ commit. Por isso este script cria produtos de teste
e os apaga no final (bloco finally). Os dados do seed (BancoDeDadods.sql)
só são LIDOS, nunca alterados.
"""
from decimal import Decimal

from sqlalchemy import text

from src.config.database import engine, get_session
from src.persistencia.models import Produto
from src.servico.excecoes import (
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)
from src.servico.precificacao import (
    MARKUP_PADRAO,
    calcular_preco_venda,
    margem_sobre_custo,
    preco_sugerido_divergente,
)
from src.servico.produto_service import ProdutoService

# Silencia o SQL impresso pelo echo=True para o resultado ficar legível.
engine.echo = False

NOME_1 = "Produto Teste Alfa"
NOME_2 = "Produto Teste Beta"
NOME_3 = "Produto Teste Gama"

resultados = []


def verificar(descricao: str, condicao: bool) -> None:
    resultados.append(condicao)
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}")


def esperar_erro(descricao: str, tipo_esperado, funcao) -> None:
    """Executa funcao() e confere se levantou exatamente o erro esperado."""
    try:
        funcao()
    except tipo_esperado as erro:
        verificar(f"{descricao} -> {tipo_esperado.__name__}: {erro}", True)
    except Exception as erro:  # erro de outro tipo = bug
        verificar(f"{descricao} -> erro inesperado {type(erro).__name__}: {erro}", False)
    else:
        verificar(f"{descricao} -> deveria ter levantado {tipo_esperado.__name__}", False)


def limpar(servico: ProdutoService) -> None:
    for nome in (NOME_1, NOME_2, NOME_3):
        p = servico.buscar_por_nome(nome)
        if p is not None:
            servico.excluir(p.id_produto)


def main() -> None:
    with get_session() as session:
        servico = ProdutoService(session)
        limpar(servico)  # começo limpo, mesmo se uma rodada anterior falhou
        try:
            print("\n--- Cadastrar ---")
            a = servico.cadastrar("  Produto   Teste  Alfa ", " Testes ", " T1 ", quantidade_minima=5)
            verificar(f"cadastro válido gerou id {a.id_produto}", a.id_produto is not None)
            verificar("nome normalizado (espaços sobrando removidos)", a.nome == NOME_1)
            verificar("produto novo nasce com estoque 0 (o estoque entra pelo RF09)", a.quantidade == 0)
            verificar("categoria e prateleira sem espaços", a.categoria == "Testes" and a.prateleira == "T1")
            verificar("estoque 0 < mínimo 5 => estoque_baixo", a.estoque_baixo is True)

            b = servico.cadastrar(NOME_2)
            verificar("só o nome é obrigatório (mínimo padrão 0)", b.quantidade_minima == 0 and b.categoria is None)

            esperar_erro("nome repetido", RegistroDuplicadoError,
                         lambda: servico.cadastrar(NOME_1))
            esperar_erro("nome repetido com outras maiúsculas e espaços", RegistroDuplicadoError,
                         lambda: servico.cadastrar("  produto teste ALFA "))
            esperar_erro("nome repetido de produto do seed", RegistroDuplicadoError,
                         lambda: servico.cadastrar("FILTRO DE ÓLEO"))
            esperar_erro("nome ausente", ValidacaoError, lambda: servico.cadastrar("   "))
            esperar_erro("mínimo negativo", ValidacaoError,
                         lambda: servico.cadastrar("Outro", quantidade_minima=-1))
            esperar_erro("mínimo não inteiro", ValidacaoError,
                         lambda: servico.cadastrar("Outro", quantidade_minima=2.5))
            esperar_erro("nome grande demais", ValidacaoError,
                         lambda: servico.cadastrar("x" * 151))

            print("\n--- Atualizar ---")
            a.quantidade = 7  # simula uma entrada de estoque do RF09
            session.commit()
            a = servico.atualizar(a.id_produto, "Produto Teste Alfa 2", "Testes", "T2", quantidade_minima=3)
            verificar("nome, prateleira e mínimo atualizados",
                      a.nome == "Produto Teste Alfa 2" and a.prateleira == "T2" and a.quantidade_minima == 3)
            verificar("atualizar NÃO altera a quantidade em estoque", a.quantidade == 7)
            verificar("estoque 7 >= mínimo 3 => sem alerta", a.estoque_baixo is False)
            a = servico.atualizar(a.id_produto, NOME_1, "Testes", "T2", quantidade_minima=3)
            verificar("editar sem mudar o nome funciona (não conflita consigo mesmo)", a.nome == NOME_1)
            esperar_erro("atualizar para o nome de outro produto", RegistroDuplicadoError,
                         lambda: servico.atualizar(a.id_produto, NOME_2.upper()))
            esperar_erro("atualizar produto inexistente", RegistroNaoEncontradoError,
                         lambda: servico.atualizar(999999, "X"))

            print("\n--- Consultas ---")
            verificar("buscar_por_nome encontra (sem diferenciar maiúsculas)",
                      servico.buscar_por_nome("produto teste alfa") is not None)
            verificar("buscar por categoria", any(p.id_produto == a.id_produto for p in servico.buscar("testes")))
            verificar("buscar por prateleira", any(p.id_produto == a.id_produto for p in servico.buscar("t2")))
            verificar("listar traz os produtos do seed e os de teste", len(servico.listar()) >= 8)
            pastilha = servico.buscar_por_nome("Pastilha de Freio Dianteira")
            verificar("pastilha do seed está com estoque baixo (2 < 6)", pastilha.estoque_baixo is True)

            print("\n--- Precificação (regra central em precificacao.py) ---")
            verificar("markup padrão é 20%", MARKUP_PADRAO == Decimal("0.20"))
            verificar("custo 50,00 -> preço 60,00", calcular_preco_venda(Decimal("50")) == Decimal("60.00"))
            verificar("arredonda para centavos: 3,3333 x 1,2 = 3,99996 -> 4,00",
                      calcular_preco_venda(Decimal("3.3333")) == Decimal("4.00"))
            verificar("sem custo -> sem preço", calcular_preco_venda(None) is None)
            verificar("margem sobre o custo: 60 sobre 50 = 0,20",
                      margem_sobre_custo(Decimal("60"), Decimal("50")) == Decimal("0.2"))
            verificar("margem negativa: 40 sobre 50 = -0,20",
                      margem_sobre_custo(Decimal("40"), Decimal("50")) == Decimal("-0.2"))
            verificar("margem sem custo ou com custo zero -> None",
                      margem_sobre_custo(Decimal("10"), None) is None
                      and margem_sobre_custo(Decimal("10"), Decimal("0")) is None)
            verificar("markup 20% = margem de 16,67% sobre a venda (pergunta da banca)",
                      ((Decimal("60") - Decimal("50")) / Decimal("60")).quantize(Decimal("0.0001")) == Decimal("0.1667"))
            verificar("seed: preço inicial = custo x 1,20 (pastilha 40 -> 48,00), automático",
                      pastilha.preco_venda == Decimal("48.00") and pastilha.preco_venda_manual is False)

            print("\n--- Preço de venda no cadastro ---")
            g = servico.cadastrar(NOME_3)
            verificar("produto novo (sem custo) no automático nasce sem preço",
                      g.preco_venda is None and g.preco_venda_manual is False)
            servico.excluir(g.id_produto)
            g = servico.cadastrar(NOME_3, preco_venda_manual=False, preco_venda=99)
            verificar("no automático o preço enviado é ignorado", g.preco_venda is None)
            esperar_erro("manual sem preço", ValidacaoError,
                         lambda: servico.atualizar(g.id_produto, NOME_3, preco_venda_manual=True))
            esperar_erro("manual com preço em texto", ValidacaoError,
                         lambda: servico.atualizar(g.id_produto, NOME_3, preco_venda_manual=True, preco_venda="10"))
            esperar_erro("manual com preço negativo", ValidacaoError,
                         lambda: servico.atualizar(g.id_produto, NOME_3, preco_venda_manual=True, preco_venda=-1))
            esperar_erro("manual com preço acima do limite", ValidacaoError,
                         lambda: servico.atualizar(g.id_produto, NOME_3, preco_venda_manual=True, preco_venda=10**9))
            g = servico.atualizar(g.id_produto, NOME_3, preco_venda_manual=True, preco_venda=Decimal("15.555"))
            verificar("produto sem custo aceita preço manual (arredondado: 15,555 -> 15,56)",
                      g.preco_venda == Decimal("15.56") and g.preco_venda_manual is True)
            verificar("sem custo não há preço sugerido para comparar", preco_sugerido_divergente(g) is None)

            g.valor_unitario = Decimal("50")  # simula uma compra do RF09
            session.commit()
            verificar("custo 50 e preço manual 15,56: sugere 60,00",
                      preco_sugerido_divergente(g) == Decimal("60.00"))
            g = servico.atualizar(g.id_produto, NOME_3, preco_venda_manual=False)
            verificar("voltar ao automático recalcula na hora: 50 x 1,2 = 60,00",
                      g.preco_venda == Decimal("60.00") and g.preco_venda_manual is False)
            verificar("automático não gera aviso de sugestão", preco_sugerido_divergente(g) is None)
            g = servico.atualizar(g.id_produto, NOME_3, "Testes", quantidade_minima=1,
                                  preco_venda_manual=True, preco_venda=Decimal("75"))
            verificar("preço manual 75,00 gravado junto com os outros campos",
                      g.preco_venda == Decimal("75.00") and g.preco_venda_manual and g.categoria == "Testes")
            verificar("margem efetiva 75 sobre 50 = 50%",
                      margem_sobre_custo(g.preco_venda, g.valor_unitario) == Decimal("0.5"))
            g = servico.atualizar(g.id_produto, NOME_3, "Testes", "P9", quantidade_minima=1,
                                  preco_venda_manual=True, preco_venda=Decimal("75"))
            verificar("editar outro campo mantém o preço manual", g.preco_venda == Decimal("75.00") and g.prateleira == "P9")
            verificar("o custo não muda pelo cadastro", g.valor_unitario == Decimal("50"))

            print("\n--- Preço de venda: CHECK do banco ---")
            for descricao, sql in (
                ("banco recusa preço de venda negativo (ck_produto_preco_venda)",
                 "UPDATE produto SET preco_venda = -1 WHERE id_produto = :i"),
                ("banco recusa preço manual vazio (ck_produto_preco_manual)",
                 "UPDATE produto SET preco_venda = NULL, preco_venda_manual = TRUE WHERE id_produto = :i"),
            ):
                try:
                    session.execute(text(sql), {"i": g.id_produto})
                    session.commit()
                    verificar(descricao, False)
                except Exception:
                    session.rollback()
                    verificar(descricao, True)

            print("\n--- Excluir ---")
            oleo = servico.buscar_por_nome("Óleo de Motor 5W30 (litro)")
            esperar_erro("produto usado em OS", OperacaoNaoPermitidaError,
                         lambda: servico.excluir(oleo.id_produto))
            esperar_erro("produto só com entradas de estoque", OperacaoNaoPermitidaError,
                         lambda: servico.excluir(pastilha.id_produto))
            esperar_erro("produto inexistente", RegistroNaoEncontradoError,
                         lambda: servico.excluir(999999))
            servico.excluir(b.id_produto)
            verificar("produto sem vínculos foi excluído", servico.buscar_por_nome(NOME_2) is None)

            print("\n--- Última linha de defesa: o índice único do banco ---")
            try:
                session.add(Produto(nome=NOME_1.upper(), quantidade=0, quantidade_minima=0))
                session.commit()
                verificar("banco recusou nome duplicado (uq_produto_nome)", False)
            except Exception:
                session.rollback()
                verificar("banco recusou nome duplicado (uq_produto_nome)", True)
        finally:
            session.rollback()
            limpar(servico)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
