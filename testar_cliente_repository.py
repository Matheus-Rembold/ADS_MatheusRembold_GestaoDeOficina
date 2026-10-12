"""
Teste manual do ClienteRepository contra o banco real.

Rode da raiz do projeto, com o venv ativo:
    python testar_cliente_repository.py

O script NUNCA faz commit: tudo o que ele insere é desfeito no rollback
final, então seus dados de teste continuam intactos.
"""
from src.config.database import get_session
from src.persistencia.models import Cliente
from src.persistencia.repositories.cliente_repository import ClienteRepository


def main() -> None:
    with get_session() as session:
        repo = ClienteRepository(session)

        print("\n=== 1. adicionar() ===")
        novo = Cliente(
            nome="Cliente Teste",
            cpf="999.999.999-99",
            contato="(54) 90000-0000",
        )
        repo.adicionar(novo)
        print(f"Inserido com id gerado pelo banco: {novo.id_cliente}")

        print("\n=== 2. buscar_por_cpf() ===")
        print(repo.buscar_por_cpf("999.999.999-99"))

        print("\n=== 3. buscar_por_nome() (busca parcial) ===")
        print(repo.buscar_por_nome("rembold"))

        print("\n=== 4. listar_todos() com selectinload ===")
        for c in repo.listar_todos():
            print(f"{c.nome}: {len(c.veiculos)} veículo(s)")

        print("\n=== 5. Regras de negócio de apoio ===")
        # Seed: João da Silva (id 2) tem a OS 2 em andamento.
        print(f"João (id 2) possui OS em andamento? {repo.possui_os_em_andamento(2)}")
        # Seed: Fernanda Lima (id 5) não tem nada vinculado.
        print(f"Fernanda (id 5) possui vínculos? {repo.possui_vinculos(5)}")
        print(f"Osvaldo (id 1) possui vínculos? {repo.possui_vinculos(1)}")

        print("\n=== 6. Atualização automática (unit of work) ===")
        novo.nome = "Cliente Teste Alterado"
        session.flush()  # o SQLAlchemy gera o UPDATE sozinho
        print(repo.buscar_por_id(novo.id_cliente))

        print("\n=== 7. remover() ===")
        repo.remover(novo)
        print(f"Depois de remover: {repo.buscar_por_cpf('999.999.999-99')}")

        # Sem commit: descartamos tudo o que foi feito acima.
        session.rollback()
        print("\nRollback feito: o banco ficou como estava.")


if __name__ == "__main__":
    main()
