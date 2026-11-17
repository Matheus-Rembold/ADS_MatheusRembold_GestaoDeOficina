"""
Tela de login (RF10).

Decisões de usabilidade e segurança:
- Enter envia; o foco começa no usuário (ou na senha, se o usuário já veio
  preenchido); "Mostrar senha" ajuda a corrigir digitação (Nielsen:
  prevenção de erros).
- O erro aparece DENTRO da janela, sem fechá-la, e a senha é limpa para
  digitar de novo (Nielsen: ajudar a se recuperar de erros).
- A mensagem de falha é sempre a mesma ("Usuário ou senha inválidos"): não
  revela se o usuário existe.
- Bloqueado: mostra o tempo restante, contando de 1 em 1 segundo, e só
  libera o botão quando o tempo acaba (visibilidade do estado do sistema).
- Fechar ou clicar em "Sair" encerra o programa (quem chama decide).
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.apresentacao.componentes import caixa_mostrar_senha, campo_senha
from src.controle.autenticacao_controller import (
    AutenticacaoController,
    CredenciaisInvalidasError,
    ErroDeNegocio,
    UsuarioBloqueadoError,
)
from src.controle.sessao import UsuarioLogadoDTO

logger = logging.getLogger(__name__)


class LoginDialog(QDialog):
    def __init__(self, controller: AutenticacaoController, login_inicial: str = "", parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.resultado: Optional[UsuarioLogadoDTO] = None
        self._segundos_bloqueio = 0
        self._login_bloqueado = ""

        self.setWindowTitle("Camaro — Entrar")
        self.setModal(True)
        self.setMinimumWidth(380)

        marca = QLabel("CAMARO")
        marca.setObjectName("marcaLogin")
        marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("Gestão de oficina mecânica")
        sub.setObjectName("subtituloLogin")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._login = QLineEdit(login_inicial)
        self._login.setMaxLength(30)
        self._login.setPlaceholderText("seu usuário")
        self._senha = campo_senha("sua senha")
        mostrar = caixa_mostrar_senha(self._senha)

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Usuário", self._login)
        formulario.addRow("Senha", self._senha)
        formulario.addRow("", mostrar)

        self._erro = QLabel()
        self._erro.setObjectName("erroForm")
        self._erro.setWordWrap(True)
        self._erro.hide()

        self._botao_sair = QPushButton("Sair")
        self._botao_sair.clicked.connect(self.reject)
        self._botao_entrar = QPushButton("Entrar")
        self._botao_entrar.setObjectName("primario")
        self._botao_entrar.setDefault(True)  # Enter entra
        self._botao_entrar.clicked.connect(self._entrar)
        botoes = QHBoxLayout()
        botoes.addStretch()
        botoes.addWidget(self._botao_sair)
        botoes.addWidget(self._botao_entrar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(12)
        layout.addWidget(marca)
        layout.addWidget(sub)
        layout.addSpacing(8)
        layout.addLayout(formulario)
        layout.addWidget(self._erro)
        layout.addLayout(botoes)

        self._timer = QTimer(self, interval=1000)
        self._timer.timeout.connect(self._contar_bloqueio)
        self._login.textChanged.connect(self._ao_mudar_login)
        (self._senha if login_inicial else self._login).setFocus()

    # ------------------------------------------------------------------
    def _entrar(self) -> None:
        if not self._login.text().strip() or not self._senha.text():
            self._mostrar("Informe o usuário e a senha.")
            return
        try:
            self.resultado = self._controller.entrar(self._login.text(), self._senha.text())
        except UsuarioBloqueadoError as exc:
            self._iniciar_bloqueio(exc.segundos_restantes)
        except CredenciaisInvalidasError as exc:
            self._mostrar(str(exc))
            self._senha.clear()
            self._senha.setFocus()
        except ErroDeNegocio as exc:
            self._mostrar(str(exc))
        except Exception:
            logger.exception("Falha inesperada no login")
            self._mostrar("Não foi possível entrar. Verifique a conexão com o banco de dados.")
        else:
            self.accept()

    def _mostrar(self, texto: str, bloqueio: bool = False) -> None:
        self._erro.setObjectName("avisoBloqueio" if bloqueio else "erroForm")
        self._erro.style().unpolish(self._erro)
        self._erro.style().polish(self._erro)
        self._erro.setText(texto)
        self._erro.setVisible(bool(texto))

    # --- bloqueio com contagem regressiva ---
    def _iniciar_bloqueio(self, segundos: int) -> None:
        self._segundos_bloqueio = segundos
        self._login_bloqueado = self._login.text().strip().lower()
        self._senha.clear()
        self._contar_bloqueio(primeira=True)
        self._timer.start()

    def _contar_bloqueio(self, primeira: bool = False) -> None:
        if not primeira:
            self._segundos_bloqueio -= 1
        if self._segundos_bloqueio <= 0:
            self._timer.stop()
            self._botao_entrar.setEnabled(True)
            self._mostrar("Bloqueio encerrado. Você já pode tentar de novo.", bloqueio=True)
            self._senha.setFocus()
            return
        minutos, segundos = divmod(self._segundos_bloqueio, 60)
        tempo = f"{minutos} min {segundos:02d} s" if minutos else f"{segundos} s"
        self._mostrar(f"Muitas tentativas sem sucesso. Tente novamente em {tempo}.", bloqueio=True)
        self._botao_entrar.setEnabled(False)

    def _ao_mudar_login(self, texto: str) -> None:
        """O bloqueio é do usuário: trocando de usuário, o botão volta a funcionar."""
        if self._timer.isActive():
            outro = texto.strip().lower() != self._login_bloqueado
            self._botao_entrar.setEnabled(outro)
