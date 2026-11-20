"""
Script rápido para validar que todos os models e relacionamentos
foram montados sem erro, sem precisar abrir a interface PyQt6.

Rode da raiz do projeto:
    python testar_models.py
"""
from src.config.database import get_session
from src.persistencia.models import Cliente, Produto


def main():
    with get_session() as session:
        # Testa consulta simples
        cliente = session.query(Cliente).first()
        if cliente is None:
            print("Nenhum cliente encontrado - confira se o seed foi executado.")
            return

        print(f"Cliente encontrado: {cliente}")

        # Testa a navegação por relationship() - isso dispara um JOIN
        # automático por trás das cenas (lazy loading).
        print(f"Veículos deste cliente: {cliente.veiculos}")

        # Testa a propriedade calculada no model Produto
        produtos_com_estoque_baixo = [
            p for p in session.query(Produto).all() if p.estoque_baixo
        ]
        print(f"Produtos com estoque baixo: {produtos_com_estoque_baixo}")


if __name__ == "__main__":
    main()
