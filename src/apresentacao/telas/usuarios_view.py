"""
Tela de Usuários (RF10) — só aparece para o dono.

Mesmo padrão das outras telas de cadastro (Nielsen):
- botões de ação no topo, ao lado do "+ Novo"; desabilitados sem seleção;
- "Desativar" vira "Ativar" conforme a situação do usuário selecionado
  (visibilidade do estado do sistema);
- a coluna Situação diz em texto se o usuário está ativo, inativo ou
  bloqueado (não depende só da cor); o usuário logado aparece com "(você)";
- desativar pede confirmação, com "Cancelar" como padrão (prevenção de erros).
Não existe excluir: só desativar (preserva o histórico e o último dono).
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.apresentacao.componentes import aviso, confirmar, erro_inesperado, preenchendo_tabela
from src.apresentacao.tema import ERRO, TEXTO_SUAVE
from src.apresentacao.telas.usuario_dialog import EDITAR, NOVO, SENHA, UsuarioDialog
from src.controle.usuario_controller import ErroDeNegocio, UsuarioController, UsuarioDTO

COLUNAS = ["Nome", "Usuário", "Perfil", "Situação", "Último acesso"]
COL_NOME, COL_LOGIN, COL_PERFIL, COL_SITUACAO, COL_ACESSO = range(5)


class UsuariosView(QWidget):
    def __init__(self, controller: Optional[UsuarioController] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagina")
        self._controller = controller or UsuarioController()
        self._dtos: List[UsuarioDTO] = []
        self._timer_feedback = QTimer(self, singleShot=True, interval=5000)
        self._montar_interface()
        self._atualizar_botoes()

    def _montar_interface(self) -> None:
        titulo = QLabel("Usuários")
        titulo.setObjectName("titulo")
        subtitulo = QLabel("Quem pode entrar no sistema e com qual perfil")
        subtitulo.setObjectName("subtitulo")
        bloco = QVBoxLayout()
        bloco.setSpacing(2)
        bloco.addWidget(titulo)
        bloco.addWidget(subtitulo)

        self._btn_senha = QPushButton("Redefinir senha")
        self._btn_ativo = QPushButton("Desativar")
        self._btn_editar = QPushButton("Editar")
        self._btn_novo = QPushButton("+  Novo usuário")
        self._btn_novo.setObjectName("primario")
        cabecalho = QHBoxLayout()
        cabecalho.addLayout(bloco)
        cabecalho.addStretch(1)
        for botao in (self._btn_senha, self._btn_ativo, self._btn_editar):
            cabecalho.addWidget(botao, alignment=Qt.AlignmentFlag.AlignVCenter)
        cabecalho.addSpacing(12)  # afasta as ações do botão primário
        cabecalho.addWidget(self._btn_novo, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._tabela = QTableWidget(0, len(COLUNAS))
        self._tabela.setHorizontalHeaderLabels(COLUNAS)
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.setShowGrid(False)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.verticalHeader().setDefaultSectionSize(40)
        cab = self._tabela.horizontalHeader()
        cab.setHighlightSections(False)
        cab.setSectionResizeMode(COL_NOME, QHeaderView.ResizeMode.Stretch)
        for c in (COL_LOGIN, COL_PERFIL, COL_SITUACAO, COL_ACESSO):
            cab.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        self._lbl_total = QLabel()
        self._lbl_total.setObjectName("rodape")
        self._lbl_feedback = QLabel()
        self._lbl_feedback.setObjectName("feedbackOk")
        rodape = QHBoxLayout()
        rodape.addWidget(self._lbl_total)
        rodape.addSpacing(16)
        rodape.addWidget(self._lbl_feedback, stretch=1)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(14)
        raiz.addLayout(cabecalho)
        raiz.addWidget(self._tabela, stretch=1)
        raiz.addLayout(rodape)

        self._btn_novo.clicked.connect(self._novo)
        self._btn_editar.clicked.connect(self._editar)
        self._btn_senha.clicked.connect(self._redefinir_senha)
        self._btn_ativo.clicked.connect(self._alternar_ativo)
        self._tabela.itemSelectionChanged.connect(self._atualizar_botoes)
        self._tabela.itemDoubleClicked.connect(lambda _i: self._editar())
        self._timer_feedback.timeout.connect(lambda: self._lbl_feedback.setText(""))

    # ------------------------------------------------------------------
    def showEvent(self, evento) -> None:  # noqa: N802
        super().showEvent(evento)
        self.recarregar()

    def recarregar(self, selecionar: Optional[int] = None) -> None:
        if selecionar is None and self._selecionado():
            selecionar = self._selecionado().id_usuario
        try:
            self._dtos = self._controller.listar()
        except ErroDeNegocio as exc:
            aviso(self, "Acesso negado", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            erro_inesperado(self, exc, "Não foi possível carregar os usuários.")
            return
        with preenchendo_tabela(self._tabela):
            self._preencher(selecionar)

    def _preencher(self, selecionar: Optional[int]) -> None:
        self._tabela.setRowCount(len(self._dtos))
        linha_sel = -1
        for linha, u in enumerate(self._dtos):
            situacao = "Bloqueado" if u.bloqueado else ("Ativo" if u.ativo else "Inativo")
            acesso = u.ultimo_login_em.strftime("%d/%m/%Y %H:%M") if u.ultimo_login_em else "—"
            valores = [u.nome + ("  (você)" if u.eh_voce else ""), u.login, u.perfil_rotulo, situacao, acesso]
            for coluna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if not u.ativo:
                    item.setForeground(QBrush(QColor(TEXTO_SUAVE)))
                elif coluna == COL_SITUACAO and u.bloqueado:
                    item.setForeground(QBrush(QColor(ERRO)))
                self._tabela.setItem(linha, coluna, item)
            if u.id_usuario == selecionar:
                linha_sel = linha
        if linha_sel >= 0:
            self._tabela.selectRow(linha_sel)
        ativos = sum(1 for u in self._dtos if u.ativo)
        self._lbl_total.setText(f"{len(self._dtos)} usuário(s)  •  {ativos} ativo(s)")
        self._atualizar_botoes()

    def _selecionado(self) -> Optional[UsuarioDTO]:
        linha = self._tabela.currentRow()
        if linha < 0 or not self._tabela.selectedItems() or linha >= len(self._dtos):
            return None
        return self._dtos[linha]

    def _atualizar_botoes(self) -> None:
        u = self._selecionado()
        for botao in (self._btn_editar, self._btn_senha, self._btn_ativo):
            botao.setEnabled(u is not None)
        self._btn_ativo.setText("Ativar" if u is not None and not u.ativo else "Desativar")
        if u is not None and u.eh_voce:
            self._btn_ativo.setEnabled(False)  # prevenção: ninguém se desativa
            self._btn_ativo.setToolTip("Você não pode desativar o seu próprio usuário.")
        else:
            self._btn_ativo.setToolTip("")

    def _feedback(self, texto: str) -> None:
        self._lbl_feedback.setText(texto)
        self._timer_feedback.start()

    # ------------------------------------------------------------------
    def _novo(self) -> None:
        d = UsuarioDialog(self._controller, NOVO, parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self.recarregar(d.resultado.id_usuario)
            self._feedback(f"Usuário “{d.resultado.login}” criado.")

    def _editar(self) -> None:
        u = self._selecionado()
        if u is None:
            return
        d = UsuarioDialog(self._controller, EDITAR, u, parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self.recarregar(u.id_usuario)
            self._feedback(f"Usuário “{u.login}” atualizado.")

    def _redefinir_senha(self) -> None:
        u = self._selecionado()
        if u is None:
            return
        d = UsuarioDialog(self._controller, SENHA, u, parent=self)
        if d.exec() == QDialog.DialogCode.Accepted and d.resultado:
            self.recarregar(u.id_usuario)
            self._feedback(f"Senha de “{u.login}” redefinida.")

    def _alternar_ativo(self) -> None:
        u = self._selecionado()
        if u is None:
            return
        if u.ativo and not confirmar(
            self, "Desativar usuário",
            f"Desativar “{u.nome}”? Ele não conseguirá mais entrar no sistema.\n"
            "Você pode reativá-lo depois.", rotulo_confirmar="Desativar",
        ):
            return
        try:
            self._controller.definir_ativo(u.id_usuario, not u.ativo)
        except ErroDeNegocio as exc:
            aviso(self, "Operação não permitida", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            erro_inesperado(self, exc, "Não foi possível alterar o usuário.")
            return
        self.recarregar(u.id_usuario)
        self._feedback(f"Usuário “{u.login}” {'desativado' if u.ativo else 'ativado'}.")
