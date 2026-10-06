"""
Ponto de entrada do sistema Camaro.

Por enquanto só inicializa a aplicação Qt com uma janela vazia,
para validar que o ambiente está configurado corretamente antes
de começar a implementar as telas de fato (RF01 - Gerenciar Clientes).
"""
import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Camaro - Sistema de Gerenciamento de Oficina")
        self.resize(1024, 768)
        self.setCentralWidget(QLabel("Camaro em construção - ambiente OK"))

.
def main():
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
