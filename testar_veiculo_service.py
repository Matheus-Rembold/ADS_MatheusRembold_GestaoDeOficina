"""
Teste manual do VeiculoService contra o banco real (RF02 - HU04/HU05/HU06).

Rode da raiz do projeto, com o venv ativo:
    python testar_veiculo_service.py

ATENÇÃO: o Service FAZ commit. Por isso este script cria um cliente e
veículos de teste e os apaga no final (bloco finally). Os dados do seed
(BancoDeDadods.sql) só são LIDOS, nunca alterados.
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
from src.servico.veiculo_service import VeiculoService

# Silencia o SQL impresso pelo echo=True para o resultado ficar legível.
engine.echo = False

CPF_A = "529.982.247-25"
CPF_B = "111.444.777-35"
PLACA_1 = "TST1A23"   # Mercosul
PLACA_2 = "TST1234"   # padrão antigo

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


def limpar(clientes: ClienteService, veiculos: VeiculoService) -> None:
    for placa in (PLACA_1, PLACA_2):
        v = veiculos.buscar_por_placa(placa)
        if v is not None:
            veiculos.excluir(v.id_veiculo)
    for cpf in (CPF_A, CPF_B):
        c = clientes.buscar_por_cpf(cpf)
        if c is not None:
            clientes.excluir(c.id_cliente)


def main() -> None:
    with get_session() as session:
        clientes = ClienteService(session)
        servico = VeiculoService(session)
        limpar(clientes, servico)  # começo limpo, mesmo se uma rodada anterior falhou
        try:
            ana = clientes.cadastrar("Ana Teste", CPF_A, "(54) 90000-0001")
            bruno = clientes.cadastrar("Bruno Teste", CPF_B, "(54) 90000-0002")

            print("\n--- HU04: cadastrar ---")
            v1 = servico.cadastrar(ana.id_cliente, "  Onix ", "Chevrolet", "tst-1a23", ano=2020, motor="1.0")
            verificar(f"cadastro válido gerou id {v1.id_veiculo}", v1.id_veiculo is not None)
            verificar("placa normalizada (maiúscula, sem hífen)", v1.placa == PLACA_1)
            verificar("modelo sem espaços sobrando", v1.modelo == "Onix")

            v2 = servico.cadastrar(bruno.id_cliente, "Gol", "Volkswagen", "TST-1234")
            verificar("ano e motor são opcionais", v2.ano is None and v2.motor is None)
            verificar("placa no padrão antigo aceita", v2.placa == PLACA_2)

            esperar_erro("placa repetida (mesmo com outra formatação)", RegistroDuplicadoError,
                         lambda: servico.cadastrar(ana.id_cliente, "Outro", "Marca", "tst 1a23"))
            esperar_erro("campos obrigatórios ausentes", ValidacaoError,
                         lambda: servico.cadastrar(None, "", "", ""))
            esperar_erro("placa em formato inválido", ValidacaoError,
                         lambda: servico.cadastrar(ana.id_cliente, "X", "Y", "ABC-12"))
            esperar_erro("ano absurdo", ValidacaoError,
                         lambda: servico.cadastrar(ana.id_cliente, "X", "Y", "ZZZ9Z99", ano=1800))
            esperar_erro("cliente inexistente", ValidacaoError,
                         lambda: servico.cadastrar(999999, "X", "Y", "ZZZ9Z99"))

            print("\n--- HU06: atualizar ---")
            v1 = servico.atualizar(v1.id_veiculo, ana.id_cliente, "Onix Plus", "Chevrolet", "TST1A23", ano=2021)
            verificar("editar sem mudar a placa funciona (não conflita consigo mesmo)",
                      v1.modelo == "Onix Plus" and v1.ano == 2021)
            esperar_erro("atualizar para a placa de outro veículo", RegistroDuplicadoError,
                         lambda: servico.atualizar(v1.id_veiculo, ana.id_cliente, "X", "Y", PLACA_2))
            esperar_erro("atualizar veículo inexistente", RegistroNaoEncontradoError,
                         lambda: servico.atualizar(999999, ana.id_cliente, "X", "Y", "ZZZ9Z99"))
            v1 = servico.atualizar(v1.id_veiculo, bruno.id_cliente, "Onix Plus", "Chevrolet", "TST1A23")
            verificar("veículo sem histórico pode trocar de dono", v1.id_cliente == bruno.id_cliente)

            print("\n--- Consultas ---")
            verificar("buscar_por_placa encontra", servico.buscar_por_placa("tst-1a23") is not None)
            verificar("buscar por nome do cliente", any(v.id_veiculo == v1.id_veiculo for v in servico.buscar("bruno")))
            verificar("buscar por modelo parcial", any(v.id_veiculo == v1.id_veiculo for v in servico.buscar("plus")))
            verificar("listar_por_cliente traz os 2 veículos do Bruno",
                      len(servico.listar_por_cliente(bruno.id_cliente)) == 2)

            print("\n--- HU05: histórico (seed) ---")
            camaro = servico.buscar_por_placa("CAM1A19")
            hist = servico.historico(camaro.id_veiculo)
            verificar("Camaro SS do seed tem 1 OS no histórico", len(hist) == 1 and hist[0].status == "pronto")
            verificar("veículo novo tem histórico vazio", servico.historico(v1.id_veiculo) == [])
            esperar_erro("histórico de veículo inexistente", RegistroNaoEncontradoError,
                         lambda: servico.historico(999999))
            esperar_erro("trocar dono de veículo com histórico", OperacaoNaoPermitidaError,
                         lambda: servico.atualizar(camaro.id_veiculo, ana.id_cliente, camaro.modelo,
                                                   camaro.marca, camaro.placa))
            session.rollback()  # descarta a alteração em memória que falhou

            print("\n--- HU06: excluir ---")
            gol = servico.buscar_por_placa("GOL2B45")
            esperar_erro("veículo com OS em andamento", OperacaoNaoPermitidaError,
                         lambda: servico.excluir(gol.id_veiculo))
            esperar_erro("veículo com OS no histórico", OperacaoNaoPermitidaError,
                         lambda: servico.excluir(camaro.id_veiculo))
            onix_seed = servico.buscar_por_placa("ABC1D23")
            esperar_erro("veículo só com agendamento", OperacaoNaoPermitidaError,
                         lambda: servico.excluir(onix_seed.id_veiculo))
            esperar_erro("veículo inexistente", RegistroNaoEncontradoError,
                         lambda: servico.excluir(999999))
            servico.excluir(v2.id_veiculo)
            verificar("veículo sem vínculos foi excluído", servico.buscar_por_placa(PLACA_2) is None)

            print("\n--- Integridade com RF01 ---")
            esperar_erro("excluir cliente que tem veículo", OperacaoNaoPermitidaError,
                         lambda: clientes.excluir(bruno.id_cliente))
        finally:
            session.rollback()
            limpar(clientes, servico)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
