"""
Janela principal do Camaro: barra lateral de módulos + área de conteúdo.

RF10 (login e perfis): os módulos são registrados numa lista
(rótulo, permissão, tela, grupo, ícone) e só entram no menu os que o perfil
logado pode usar. As telas proibidas nem são criadas (não basta esconder o
item). É a primeira das duas camadas de autorização; a segunda é o guard dos
controllers (src/controle/sessao.py), que recusa a operação de qualquer jeito.

Barra lateral (redesenhada em 16/11/2026):
- Grupos por assunto (Gestalt, proximidade): OPERAÇÃO, CADASTROS, GESTÃO e
  EM BREVE. Grupo sem nenhum item visível para o perfil não ganha título.
- Itens de 44 px com ícone (lei de Fitts; reconhecimento em vez de
  memorização, Nielsen). Selo laranja com as mensagens para enviar (RF07).
- Um item marcado por vez (controlado em ir_para); a página é trocada pelo WIDGET da tela,
  nunca pela posição, para não quebrar quando o perfil esconde itens.
- Só o menu rola; a marca e o rodapé (usuário + Sair) ficam sempre à vista.
- Teclado: Tab percorre os itens (contorno laranja) e Espaço abre o módulo.

O rodapé mostra quem está logado e o botão "Sair". Sair destrói esta janela
inteira (quem cuida disso é o main.py): nenhuma tela, busca ou dado do
usuário anterior fica em memória para o próximo.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.apresentacao.componentes import BotaoComIcone, BotaoMenu, iniciais
from src.apresentacao.telas.agendamentos_view import AgendamentosView
from src.apresentacao.telas.clientes_view import ClientesView
from src.apresentacao.telas.movimentacoes_view import MovimentacoesView
from src.apresentacao.telas.notificacoes_view import NotificacoesView
from src.apresentacao.telas.ordens_servico_view import OrdensServicoView
from src.apresentacao.telas.produtos_view import ProdutosView
from src.apresentacao.telas.relatorios_view import RelatoriosView
from src.apresentacao.telas.usuarios_view import UsuariosView
from src.apresentacao.telas.veiculos_view import VeiculosView
from src.apresentacao.tema import LARGURA_BARRA_LATERAL
from src.controle.sessao import Permissao, sessao

log = logging.getLogger(__name__)

CADASTROS, OPERACAO, GESTAO, EM_BREVE = "CADASTROS", "OPERAÇÃO", "GESTÃO", "EM BREVE"
GRUPOS = (OPERACAO, CADASTROS, GESTAO)  # ordem na barra (o dia a dia primeiro); EM BREVE vem por último

# (rótulo, permissão necessária, atributo da janela, como criar a tela, grupo, ícone)
MODULOS: List[Tuple[str, Permissao, str, Callable[[], QWidget], str, str]] = [
    ("Clientes", Permissao.CLIENTES, "tela_clientes", ClientesView, CADASTROS, "clientes"),
    ("Veículos", Permissao.VEICULOS, "tela_veiculos", VeiculosView, CADASTROS, "veiculos"),
    ("Produtos", Permissao.PRODUTOS_CONSULTAR, "tela_produtos", ProdutosView, CADASTROS, "produtos"),
    ("Ordens de Serviço", Permissao.ORDENS_SERVICO, "tela_os", OrdensServicoView, OPERACAO, "ordens_servico"),
    ("Agendamentos", Permissao.AGENDAMENTOS, "tela_agendamentos", AgendamentosView, OPERACAO, "agendamentos"),
    ("Estoque", Permissao.ESTOQUE, "tela_estoque", MovimentacoesView, OPERACAO, "estoque"),
    ("Notificações", Permissao.NOTIFICACOES, "tela_notificacoes", NotificacoesView, GESTAO, "notificacoes"),
    ("Relatórios", Permissao.RELATORIOS, "tela_relatorios", RelatoriosView, GESTAO, "relatorios"),
    ("Usuários", Permissao.USUARIOS, "tela_usuarios", UsuariosView, GESTAO, "usuarios"),
]

# Ordem de entrega do cronograma. Sai desta lista quando o módulo ganha tela.
# A permissão vazia (None) aparece para todos. (rótulo, permissão, ícone)
MODULOS_EM_BREVE: List[Tuple[str, Optional[Permissao], str]] = [
    ("Notas Fiscais", Permissao.NOTA_FISCAL, "notas_fiscais"),
]


def _divisor() -> QFrame:
    """Linha de 1 px entre a marca, o menu e o rodapé."""
    linha = QFrame()
    linha.setObjectName("divisorBarra")
    linha.setFixedHeight(1)
    return linha


class JanelaPrincipal(QMainWindow):
    saiu = pyqtSignal()    # o usuário clicou em "Sair": o main.py volta ao login
    fechou = pyqtSignal()  # o usuário fechou a janela: o programa encerra

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Camaro — Gestão de Oficina Mecânica")
        self.resize(1180, 720)
        self.setMinimumSize(1024, 640)  # a área de conteúdo não fica espremida
        self.saindo = False  # distingue "Sair" (volta ao login) de fechar a janela (encerra)

        self._paginas = QStackedWidget()
        # Um item marcado por vez é garantido em ir_para(), e NÃO por um QButtonGroup:
        # com grupo (exclusivo ou não) o Qt trata os botões como rádio e tira os itens
        # não marcados da ordem do Tab (só daria para navegar com as setas).
        self._botoes: Dict[QWidget, BotaoMenu] = {}  # tela -> item do menu
        self.titulos_grupo: List[str] = []            # títulos que apareceram (para os testes)
        self.botoes_em_breve: List[BotaoMenu] = []

        barra = QFrame()
        barra.setObjectName("barraLateral")
        barra.setFixedWidth(LARGURA_BARRA_LATERAL)
        layout_barra = QVBoxLayout(barra)
        layout_barra.setContentsMargins(0, 0, 0, 0)
        layout_barra.setSpacing(0)
        layout_barra.addLayout(self._montar_marca())
        layout_barra.addWidget(_divisor())
        layout_barra.addWidget(self._montar_menu(), 1)  # só o menu rola
        layout_barra.addWidget(_divisor())
        layout_barra.addLayout(self._rodape_usuario())

        # RF07: aviso ao entrar quando há mensagens para enviar (pode ser fechado)
        self.aviso_notificacoes = self._montar_aviso_notificacoes()
        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(0, 0, 0, 0)
        conteudo.setSpacing(0)
        conteudo.addWidget(self.aviso_notificacoes)
        conteudo.addWidget(self._paginas, 1)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(barra)
        layout.addLayout(conteudo, 1)
        self.setCentralWidget(central)

        if self.tela_notificacoes is not None:
            self.tela_notificacoes.contagem_mudou.connect(self._contagem_notificacoes_mudou)
            self._contagem_notificacoes_mudou(self._contar_notificacoes(), mostrar_aviso=True)

        # Ordem do Tab explícita: itens na ordem do menu e depois o Sair. Sem isso o
        # Qt segue a ordem em que os widgets entraram na janela, e a lista do menu
        # (encaixada na área de rolagem) fica fora de ordem.
        itens = [self._botoes[self._paginas.widget(i)] for i in range(self._paginas.count())]
        for anterior, proximo in zip(itens, itens[1:] + [self.botao_sair]):
            QWidget.setTabOrder(anterior, proximo)

        if self._paginas.count():
            self.ir_para(self._paginas.widget(0))

    # ------------------------------------------------------------------
    # Barra lateral
    # ------------------------------------------------------------------
    def _montar_marca(self) -> QVBoxLayout:
        marca = QLabel("CAMARO")
        marca.setObjectName("marca")
        marca_sub = QLabel("Gestão de oficina mecânica")
        marca_sub.setObjectName("marcaSub")
        # Marca centralizada na barra: lê como logotipo, não como mais um item do menu
        for rotulo in (marca, marca_sub):
            rotulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        bloco = QVBoxLayout()
        bloco.setContentsMargins(20, 28, 20, 24)
        bloco.setSpacing(2)
        bloco.addWidget(marca)
        bloco.addWidget(marca_sub)
        return bloco

    def _montar_menu(self) -> QScrollArea:
        """Grupos e itens permitidos ao perfil logado (as outras telas nem são criadas)."""
        conteudo = QWidget()
        conteudo.setObjectName("conteudoMenu")
        lista = QVBoxLayout(conteudo)
        lista.setContentsMargins(0, 8, 0, 16)
        lista.setSpacing(0)

        visiveis: Dict[str, list] = {grupo: [] for grupo in GRUPOS}
        for rotulo, permissao, atributo, criar, grupo, nome_icone in MODULOS:
            if sessao.pode(permissao):
                visiveis[grupo].append((rotulo, atributo, criar, nome_icone))
            else:
                setattr(self, atributo, None)

        for grupo in GRUPOS:
            if not visiveis[grupo]:
                continue  # sem título de grupo vazio
            lista.addWidget(self._titulo_grupo(grupo))
            for rotulo, atributo, criar, nome_icone in visiveis[grupo]:
                tela = criar()
                setattr(self, atributo, tela)
                lista.addWidget(self.adicionar_modulo(rotulo, tela, nome_icone))

        em_breve = [(r, i) for r, p, i in MODULOS_EM_BREVE if p is None or sessao.pode(p)]
        if em_breve:
            lista.addWidget(self._titulo_grupo(EM_BREVE))
            for rotulo, nome_icone in em_breve:
                botao = BotaoMenu(rotulo, nome_icone, em_breve=True)
                self.botoes_em_breve.append(botao)
                lista.addWidget(botao)
        lista.addStretch(1)

        rolagem = QScrollArea()
        rolagem.setObjectName("rolagemMenu")
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rolagem.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        rolagem.setWidget(conteudo)
        self.rolagem_menu = rolagem
        return rolagem

    def _titulo_grupo(self, texto: str) -> QLabel:
        titulo = QLabel(texto)
        titulo.setObjectName("grupoMenu")
        fonte = QFont(titulo.font())
        fonte.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)  # o QSS do Qt não tem letter-spacing
        titulo.setFont(fonte)
        self.titulos_grupo.append(texto)
        return titulo

    def _rodape_usuario(self) -> QVBoxLayout:
        """Avatar com as iniciais, nome, perfil e o botão Sair."""
        usuario = sessao.usuario
        self.avatar = QLabel(iniciais(usuario.nome if usuario else ""))
        self.avatar.setObjectName("avatar")
        self.avatar.setFixedSize(36, 36)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nome = QLabel(usuario.nome if usuario else "—")
        nome.setObjectName("usuarioNome")
        nome.setWordWrap(True)
        perfil = QLabel(usuario.perfil_rotulo if usuario else "")
        perfil.setObjectName("usuarioPerfil")
        textos = QVBoxLayout()
        textos.setSpacing(0)
        textos.addWidget(nome)
        textos.addWidget(perfil)
        linha_usuario = QHBoxLayout()
        linha_usuario.setSpacing(12)
        linha_usuario.addWidget(self.avatar)
        linha_usuario.addLayout(textos, 1)

        self.botao_sair = BotaoComIcone("  Sair", "sair")
        self.botao_sair.setObjectName("sairBarra")
        self.botao_sair.setToolTip("Encerrar a sessão e voltar à tela de login")
        self.botao_sair.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_sair.clicked.connect(self._sair)

        bloco = QVBoxLayout()
        bloco.setContentsMargins(20, 16, 20, 16)
        bloco.setSpacing(12)
        bloco.addLayout(linha_usuario)
        bloco.addWidget(self.botao_sair)
        return bloco

    def adicionar_modulo(self, nome: str, pagina: QWidget, nome_icone: str = "clientes") -> BotaoMenu:
        """Registra uma página e cria o item de menu dela (quem chama põe o item na lista)."""
        self._paginas.addWidget(pagina)
        botao = BotaoMenu(nome, nome_icone)
        self._botoes[pagina] = botao
        botao.clicked.connect(lambda _marcado=False, tela=pagina: self.ir_para(tela))
        return botao

    def ir_para(self, tela: QWidget) -> None:
        """Mostra a tela e marca o item dela no menu (pela referência, não pela posição)."""
        if tela in self._botoes:
            self._paginas.setCurrentWidget(tela)
            for outra, botao in self._botoes.items():
                botao.setChecked(outra is tela)  # clicar no item atual não o desmarca

    def botao_do_modulo(self, rotulo: str) -> Optional[BotaoMenu]:
        return next((b for b in self._botoes.values() if b.rotulo == rotulo), None)

    def modulos_visiveis(self) -> List[str]:
        return [self._botoes[self._paginas.widget(i)].rotulo for i in range(self._paginas.count())]

    # ------------------------------------------------------------------
    # RF07: selo de Notificações no menu + aviso ao entrar
    # ------------------------------------------------------------------
    def _montar_aviso_notificacoes(self) -> QFrame:
        faixa = QFrame()
        faixa.setObjectName("faixaAviso")
        self._lbl_aviso_notificacoes = QLabel()
        self._lbl_aviso_notificacoes.setObjectName("faixaAvisoTexto")
        ver = QPushButton("Ver notificações")
        ver.setObjectName("primario")
        ver.clicked.connect(self._ir_para_notificacoes)
        fechar = QPushButton("✕")
        fechar.setObjectName("faixaAvisoFechar")
        fechar.setToolTip("Fechar este aviso")
        fechar.clicked.connect(faixa.hide)
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(32, 10, 20, 10)
        linha.addWidget(self._lbl_aviso_notificacoes, 1)
        linha.addWidget(ver)
        linha.addWidget(fechar)
        faixa.hide()
        return faixa

    def _contar_notificacoes(self) -> int:
        try:
            return self.tela_notificacoes.contar_para_enviar()
        except Exception:  # noqa: BLE001  (o aviso é só um extra: não impede a janela de abrir)
            log.exception("Não foi possível contar as notificações")
            return 0

    def atualizar_badge_notificacoes(self, quantidade: int) -> None:
        """Selo laranja no item Notificações (0 esconde; acima de 99 mostra '99+')."""
        if self.tela_notificacoes is not None:
            self._botoes[self.tela_notificacoes].definir_selo(quantidade)

    def _contagem_notificacoes_mudou(self, quantidade: int, mostrar_aviso: bool = False) -> None:
        self.atualizar_badge_notificacoes(quantidade)
        if quantidade == 0:
            self.aviso_notificacoes.hide()
        elif mostrar_aviso:
            plural = "mensagens" if quantidade > 1 else "mensagem"
            self._lbl_aviso_notificacoes.setText(
                f"Você tem {quantidade} {plural} de WhatsApp para enviar hoje "
                "(pós-venda e lembretes de agendamento).")
            self.aviso_notificacoes.show()

    def _ir_para_notificacoes(self) -> None:
        self.aviso_notificacoes.hide()
        if self.tela_notificacoes is not None:
            self.ir_para(self.tela_notificacoes)

    # ------------------------------------------------------------------
    def _sair(self) -> None:
        self.saindo = True
        self.saiu.emit()

    def closeEvent(self, evento) -> None:  # noqa: N802 (nome imposto pelo Qt)
        super().closeEvent(evento)
        if not self.saindo:
            self.fechou.emit()
