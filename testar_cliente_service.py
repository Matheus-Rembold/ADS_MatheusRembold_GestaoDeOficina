"""
Teste manual do ClienteService contra o banco real (RF01 - HU01/HU02/HU03).

Rode da raiz do projeto, com o venv ativo:
    python testar_cliente_service.py

ATENÇÃO: diferente do teste do repository, o Service FAZ commit. Por isso
este script cria clientes de teste e os apaga no final (bloco finally).
Os CPFs usados abaixo são válidos pelo algoritmo oficial (os do seed são
fictícios e seriam recusados pela validação).
"""
from src.config.database import engine, get_session
from src.servico.cliente_service import ClienteService
from src.servico.excecoes import (
    ErroDeNegocio,
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)

# Silencia o SQL impresso pelo echo=True para o resultado ficar legível.
# Comente esta linha se quiser ver o SQL de cada operação.
engine.echo = False

CPF_A = "529.982.247-25"
CPF_B = "111.444.777-35"

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


def limpar(servico: ClienteService) -> None:
    for cpf in (CPF_A, CPF_B):
        cliente = servico.buscar_por_cpf(cpf)
        if cliente is not None:
            servico.excluir(cliente.id_cliente)


def main() -> None:
    with get_session() as session:
        servico = ClienteService(session)
        limpar(servico)  # garante um começo limpo, mesmo se uma rodada anterior falhou
        try:
            print("\n--- HU01: cadastrar ---")
            a = servico.cadastrar("  Ana Teste ", CPF_A, "(54) 90000-0001", idade=30)
            verificar(f"cadastro válido gerou id {a.id_cliente} e nome sem espaços", a.nome == "Ana Teste")
            verificar("CPF salvo formatado", a.cpf == CPF_A)

            b = servico.cadastrar("Bruno Teste", "11144477735", "(54) 90000-0002")
            verificar("CPF sem pontuação foi aceito e formatado", b.cpf == CPF_B)

            esperar_erro("CPF repetido", RegistroDuplicadoError,
                         lambda: servico.cadastrar("Outro", CPF_A, "(54) 90000-0003"))
            esperar_erro("nome, CPF e contato ausentes", ValidacaoError,
                         lambda: servico.cadastrar("", "", ""))
            esperar_erro("CPF inválido", ValidacaoError,
                         lambda: servico.cadastrar("Fulano", "123.456.789-00", "(54) 9"))
            esperar_erro("idade absurda", ValidacaoError,
                         lambda: servico.cadastrar("Fulano", CPF_A, "(54) 9", idade=200))

            print("\n--- HU02: atualizar ---")
            a = servico.atualizar(a.id_cliente, "Ana Teste Silva", CPF_A, "(54) 90000-0001", idade=31)
            verificar("nome e idade atualizados", a.nome == "Ana Teste Silva" and a.idade == 31)
            esperar_erro("atualizar para o CPF de outro cliente", RegistroDuplicadoError,
                         lambda: servico.atualizar(a.id_cliente, "Ana", CPF_B, "(54) 9"))
            esperar_erro("atualizar cliente inexistente", RegistroNaoEncontradoError,
                         lambda: servico.atualizar(999999, "X", CPF_A, "(54) 9"))

            print("\n--- Consultas ---")
            verificar("buscar_por_cpf encontra", servico.buscar_por_cpf("529.982.247-25") is not None)
            verificar("buscar_por_nome parcial", any(c.id_cliente == a.id_cliente for c in servico.buscar_por_nome("silva")))

            print("\n--- HU03: excluir ---")
            # Seed: João (id 2) tem OS em andamento; Osvaldo (id 1) tem veículos e OS.
            esperar_erro("cliente com OS em andamento", OperacaoNaoPermitidaError,
                         lambda: servico.excluir(2))
            esperar_erro("cliente com veículos/histórico", OperacaoNaoPermitidaError,
                         lambda: servico.excluir(1))
            esperar_erro("cliente inexistente", RegistroNaoEncontradoError,
                         lambda: servico.excluir(999999))
            servico.excluir(b.id_cliente)
            verificar("cliente sem vínculos foi excluído", servico.buscar_por_cpf(CPF_B) is None)
        finally:
            limpar(servico)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
