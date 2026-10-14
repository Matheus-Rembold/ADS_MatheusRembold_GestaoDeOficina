"""
Ponto de entrada do sistema Camaro.

Execute da raiz do projeto, com o venv ativo:
    python -m src.main
"""
import logging
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from src.apresentacao.janela_principal import JanelaPrincipal
from src.apresentacao.tema import estilo_global
from src.config.database import engine

logger = logging.getLogger(__name__)


def banco_disponivel() -> bool:
    """Abre e fecha uma conexão só para saber se o PostgreSQL responde."""
    try:
        with engine.connect():
            return True
    except Exception:  # inclui OperationalError e o UnicodeDecodeError do Windows em português
        logger.exception("Não foi possível conectar ao banco de dados")
        return False


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Camaro")
    app.setStyleSheet(estilo_global())

    if not banco_disponivel():
        QMessageBox.critical(
            None,
            "Camaro — banco de dados indisponível",
            "Não foi possível conectar ao PostgreSQL.\n\n"
            "Confira se o serviço do PostgreSQL está em execução e se os dados do "
            "arquivo .env (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD) estão corretos.",
        )
        return 1

    janela = JanelaPrincipal()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
