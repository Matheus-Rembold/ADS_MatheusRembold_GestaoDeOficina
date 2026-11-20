"""
Configuração inicial (RF10): aparece só quando NÃO existe nenhum usuário.

Cria o primeiro usuário, que é sempre o DONO, e já entra com ele. Nenhuma
senha vem pronta no código ou no banco: quem instala define a sua.
Erros aparecem na própria janela, sem perder o que foi digitado.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
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
    SENHA_MINIMA,
    AutenticacaoController,
    ErroDeNegocio,
    ValidacaoError,
)
from src.controle.sessao import UsuarioLogadoDTO

logger = logging.getLogger(__name__)


class ConfiguracaoInicialDialog(QDialog):
    def __init__(self, controller: AutenticacaoController, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.resultado: Optional[UsuarioLogadoDTO] = None

        self.setWindowTitle("Camaro — Configuração inicial")
        self.setModal(True)
        self.setMinimumWidth(460)

        titulo = QLabel("Bem-vindo ao Camaro!")
        titulo.setObjectName("titulo")
        explicacao = QLabel(
            "Este é o primeiro acesso. Crie o usuário administrador da oficina: ele terá acesso "
            "total e poderá cadastrar os funcionários depois, na tela Usuários."
        )
        explicacao.setObjectName("subtitulo")
        explicacao.setWordWrap(True)

        self._nome = QLineEdit()
        self._nome.setMaxLength(100)
        self._nome.setPlaceholderText("Ex.: Osvaldo Rembold")
        self._login = QLineEdit()
        self._login.setMaxLength(30)
        self._login.setPlaceholderText("Ex.: osvaldo")
        self._senha = campo_senha(f"mínimo {SENHA_MINIMA} caracteres")
        self._confirmacao = campo_senha("digite a senha de novo")

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        formulario.setVerticalSpacing(10)
        formulario.addRow("Nome *", self._nome)
        formulario.addRow("Usuário *", self._login)
        formulario.addRow("Senha *", self._senha)
        formulario.addRow("Confirmar *", self._confirmacao)
        formulario.addRow("", caixa_mostrar_senha(self._senha, self._confirmacao))

        dica = QLabel(
            f"Usuário: letras sem acento, números, ponto, hífen ou sublinhado. "
            f"Senha: pelo menos {SENHA_MINIMA} caracteres, diferente do usuário. "
            "Uma frase fácil de lembrar é melhor que uma senha curta e complicada."
        )
        dica.setObjectName("subtitulo")
        dica.setWordWrap(True)

        self._erro = QLabel()
        self._erro.setObjectName("erroForm")
        self._erro.setWordWrap(True)
        self._erro.hide()

        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        self._criar = QPushButton("Criar e entrar")
        self._criar.setObjectName("primario")
        self._criar.setDefault(True)
        self._criar.clicked.connect(self._salvar)
        botoes = QHBoxLayout()
        botoes.addStretch()
        botoes.addWidget(cancelar)
        botoes.addWidget(self._criar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)
        layout.addWidget(titulo)
        layout.addWidget(explicacao)
        layout.addLayout(formulario)
        layout.addWidget(dica)
        layout.addWidget(self._erro)
        layout.addLayout(botoes)
        self._nome.setFocus()

    def _salvar(self) -> None:
        self._erro.hide()
        try:
            self.resultado = self._controller.criar_primeiro_usuario(
                self._nome.text(), self._login.text(), self._senha.text(), self._confirmacao.text()
            )
        except ValidacaoError as exc:
            self._mostrar("\n".join(f"• {e}" for e in exc.erros))
        except ErroDeNegocio as exc:
            self._mostrar(str(exc))
        except Exception:
            logger.exception("Falha inesperada na configuração inicial")
            self._mostrar("Não foi possível criar o usuário. Verifique a conexão com o banco de dados.")
        else:
            self.accept()

    def _mostrar(self, texto: str) -> None:
        self._erro.setText(texto)
        self._erro.show()
