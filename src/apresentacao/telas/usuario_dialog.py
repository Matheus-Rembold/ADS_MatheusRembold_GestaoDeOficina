"""
Diálogo de usuário (RF10), em três modos:
- NOVO: nome, usuário, perfil, senha inicial e confirmação;
- EDITAR: nome e perfil (o usuário/login não muda: é a identidade);
- SENHA: redefinir a senha (também desbloqueia quem errou 5 vezes).

Erros na própria janela, sem perder o que foi digitado.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.apresentacao.componentes import caixa_mostrar_senha, campo_senha
from src.controle.usuario_controller import (
    SENHA_MINIMA,
    ErroDeNegocio,
    PerfilUsuario,
    UsuarioController,
    UsuarioDTO,
    ValidacaoError,
)

logger = logging.getLogger(__name__)

NOVO, EDITAR, SENHA = "novo", "editar", "senha"


class UsuarioDialog(QDialog):
    def __init__(self, controller: UsuarioController, modo: str = NOVO,
                 usuario: Optional[UsuarioDTO] = None, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._modo = modo
        self._usuario = usuario
        self.resultado: Optional[UsuarioDTO] = None

        titulos = {NOVO: "Novo usuário", EDITAR: "Editar usuário", SENHA: "Redefinir senha"}
        self.setWindowTitle(titulos[modo])
        self.setModal(True)
        self.setMinimumWidth(440)

        self._nome = QLineEdit(usuario.nome if usuario else "")
        self._nome.setMaxLength(100)
        self._login = QLineEdit(usuario.login if usuario else "")
        self._login.setMaxLength(30)
        self._login.setPlaceholderText("Ex.: joao")
        self._perfil = QComboBox()
        for perfil in PerfilUsuario:
            self._perfil.addItem(perfil.rotulo, perfil)
        self._perfil.setCurrentIndex(self._perfil.findData(usuario.perfil if usuario else PerfilUsuario.MECANICO))
        self._senha = campo_senha(f"mínimo {SENHA_MINIMA} caracteres")
        self._confirmacao = campo_senha("digite a senha de novo")

        formulario = QFormLayout()
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        formulario.setVerticalSpacing(10)
        dica_texto = ""
        if modo == SENHA:
            formulario.addRow("Usuário", QLabel(f"{usuario.nome} ({usuario.login})"))
            dica_texto = "A nova senha também desbloqueia o usuário, se ele errou a senha muitas vezes."
        else:
            formulario.addRow("Nome *", self._nome)
            if modo == NOVO:
                formulario.addRow("Usuário *", self._login)
            else:
                formulario.addRow("Usuário", QLabel(usuario.login))
            formulario.addRow("Perfil *", self._perfil)
            if modo == EDITAR and usuario.eh_voce:
                self._perfil.setEnabled(False)  # prevenção: ninguém muda o próprio perfil
                dica_texto = "Você não pode alterar o seu próprio perfil."
        if modo in (NOVO, SENHA):
            formulario.addRow("Senha *", self._senha)
            formulario.addRow("Confirmar *", self._confirmacao)
            formulario.addRow("", caixa_mostrar_senha(self._senha, self._confirmacao))
        if modo == NOVO:
            dica_texto = (f"Administrador: acesso total. Funcionário: Clientes, Veículos, Ordens de Serviço, "
                          f"Agendamentos, Notificações e consulta de Produtos (sem custos). "
                          f"Senha com pelo menos {SENHA_MINIMA} caracteres.")

        dica = QLabel(dica_texto)
        dica.setObjectName("subtitulo")
        dica.setWordWrap(True)
        dica.setVisible(bool(dica_texto))

        self._erro = QLabel()
        self._erro.setObjectName("erroForm")
        self._erro.setWordWrap(True)
        self._erro.hide()

        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        salvar = QPushButton("Salvar")
        salvar.setObjectName("primario")
        salvar.setDefault(True)
        salvar.clicked.connect(self._salvar)
        botoes = QHBoxLayout()
        botoes.addStretch()
        botoes.addWidget(cancelar)
        botoes.addWidget(salvar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(formulario)
        layout.addWidget(dica)
        layout.addWidget(self._erro)
        layout.addLayout(botoes)
        (self._senha if modo == SENHA else self._nome).setFocus()

    def _salvar(self) -> None:
        self._erro.hide()
        try:
            if self._modo == NOVO:
                self.resultado = self._controller.cadastrar(
                    self._nome.text(), self._login.text(), self._senha.text(),
                    self._confirmacao.text(), self._perfil.currentData(),
                )
            elif self._modo == EDITAR:
                self.resultado = self._controller.alterar(
                    self._usuario.id_usuario, self._nome.text(), self._perfil.currentData()
                )
            else:
                self.resultado = self._controller.redefinir_senha(
                    self._usuario.id_usuario, self._senha.text(), self._confirmacao.text()
                )
        except ValidacaoError as exc:
            self._mostrar("\n".join(f"• {e}" for e in exc.erros))
        except ErroDeNegocio as exc:
            self._mostrar(str(exc))
        except Exception:
            logger.exception("Falha inesperada ao salvar usuário")
            self._mostrar("Não foi possível salvar. Verifique a conexão com o banco de dados.")
        else:
            self.accept()

    def _mostrar(self, texto: str) -> None:
        self._erro.setText(texto)
        self._erro.show()
