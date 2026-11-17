"""
Tema visual do sistema (RNF01 e RNF02).

TODAS as cores ficam aqui, em constantes. As telas nunca escrevem uma cor
diretamente, então trocar a identidade visual é editar só este arquivo.

ATENÇÃO (RNF02): esta paleta (grafite + laranja) é PROVISÓRIA. Para seguir
a identidade visual real da oficina, troque os valores das constantes
abaixo pelas cores dela.
"""

# --- Paleta -------------------------------------------------------------
GRAFITE = "#1F2327"          # barra lateral
GRAFITE_CLARO = "#2B3036"    # item selecionado / hover da barra lateral
LARANJA = "#E8590C"          # cor de destaque (botão principal, seleção)
LARANJA_ESCURO = "#C94A08"   # hover do botão principal
LARANJA_SUAVE = "#FFE8D6"    # linha selecionada na tabela
FUNDO = "#F3F4F6"            # fundo das páginas
SUPERFICIE = "#FFFFFF"       # tabelas, campos, cartões
TEXTO = "#212529"
TEXTO_SUAVE = "#6B7280"
BORDA = "#D9DDE3"
ERRO = "#C92A2A"
ERRO_FUNDO = "#FFF0F0"
ERRO_BORDA = "#F5B7B7"
SUCESSO = "#2B8A3E"

# --- Situações da OS (RF04): coluna "Situação" e cartões da tela de OS ---
COR_OS_ORCAMENTO = "#868E96"
COR_OS_ANDAMENTO = "#1C7ED6"
COR_OS_PRONTO = "#E67700"
COR_OS_AGUARDANDO = ERRO
COR_OS_ENTREGUE = SUCESSO

# --- Barra lateral (sobre o GRAFITE) -----------------------------------
TEXTO_BARRA = "#C9CED3"              # itens do menu e ícones no estado normal
TEXTO_BARRA_SUAVE = "#9AA0A6"        # subtítulo da marca, perfil do usuário, títulos de grupo
TEXTO_BARRA_DESABILITADO = "#5F666D"  # módulos "em breve"
DIVISOR_BARRA = "#3A4047"            # linhas divisórias e borda do botão Sair
TEXTO_BARRA_ATIVO = "white"          # item com o mouse em cima ou selecionado

# --- Gráficos (RF06) ----------------------------------------------------
# Entradas x Saídas: laranja x grafite médio. Validado em 07/11/2026 (OKLab +
# simulação de daltonismo, Machado 2009): diferença ΔE de 22,9 normal,
# 13,7 protanopia, 19,6 deuteranopia e 27,3 tritanopia (meta >= 8); contraste
# com o fundo branco >= 3:1 (WCAG 1.4.11). Se trocar estas cores, revalide.
COR_ENTRADAS = LARANJA
COR_SAIDAS = TEXTO_SUAVE
COR_SERIE_UNICA = LARANJA      # ranking de serviços (uma série só)
COR_GRADE = "#E9ECEF"          # linhas de grade: discretas, não competem com os dados

LARGURA_BARRA_LATERAL = 264
ALTURA_ITEM_MENU = 44   # alvo grande, clique fácil (lei de Fitts)
TAMANHO_ICONE_MENU = 18


def estilo_global() -> str:
    """Folha de estilo (QSS) aplicada em toda a aplicação."""
    return f"""
    * {{
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        font-size: 10pt;
    }}
    QMainWindow, QDialog {{ background: {FUNDO}; }}
    QWidget#pagina {{ background: {FUNDO}; }}

    QLabel {{ color: {TEXTO}; background: transparent; }}
    QLabel#titulo {{ font-size: 18pt; font-weight: 600; }}
    QLabel#subtitulo {{ color: {TEXTO_SUAVE}; }}
    QLabel#vazio {{ color: {TEXTO_SUAVE}; font-size: 11pt; }}
    QLabel#rodape {{ color: {TEXTO_SUAVE}; }}
    QLabel#feedbackOk {{ color: {SUCESSO}; font-weight: 600; }}
    QLabel#erroForm {{
        background: {ERRO_FUNDO}; color: {ERRO};
        border: 1px solid {ERRO_BORDA}; border-radius: 6px; padding: 8px 10px;
    }}
    /* Margem sobre o custo / preço abaixo do custo: o texto já diz o problema,
       a cor só reforça (Nielsen: visibilidade do estado do sistema). */
    QLabel#margem {{ font-weight: 600; }}
    QLabel#margem[negativa="true"], QLabel#subtitulo[alerta="true"] {{ color: {ERRO}; font-weight: 600; }}
    QLineEdit:read-only {{ background: #F1F3F5; color: {TEXTO_SUAVE}; }}

    /* Login e configuração inicial (RF10) */
    QLabel#marcaLogin {{ color: {LARANJA}; font-size: 26pt; font-weight: 800; }}
    QLabel#subtituloLogin {{ color: {TEXTO_SUAVE}; }}
    QLabel#avisoBloqueio {{
        background: #FFF4E6; color: {LARANJA_ESCURO};
        border: 1px solid #FFD8A8; border-radius: 6px; padding: 8px 10px; font-weight: 600;
    }}
    /* Rodapé da barra lateral: quem está logado + Sair */
    QLabel#usuarioNome {{ color: {TEXTO_BARRA_ATIVO}; font-weight: 700; }}
    QLabel#usuarioPerfil {{ color: {TEXTO_BARRA_SUAVE}; font-size: 9pt; }}
    QLabel#avatar {{
        background: {LARANJA}; color: white; border-radius: 18px;
        font-size: 10pt; font-weight: 700;
    }}
    /* Sair: botão "fantasma" (transparente, borda sutil) */
    QPushButton#sairBarra {{
        background: transparent; color: {TEXTO_BARRA}; border: 1px solid {DIVISOR_BARRA};
        border-radius: 6px; padding: 8px 12px;
    }}
    QPushButton#sairBarra:hover {{ background: {GRAFITE_CLARO}; color: {TEXTO_BARRA_ATIVO}; }}
    QPushButton#sairBarra {{ outline: none; }}
    QPushButton#sairBarra[focoTeclado="true"] {{ border: 1px solid {LARANJA}; }}

    /* Relatórios (RF06): cartões de resumo e área dos gráficos */
    QFrame#cartao, QFrame#painelGrafico {{
        background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 8px;
    }}
    QLabel#cartaoTitulo {{ color: {TEXTO_SUAVE}; font-weight: 600; }}
    QLabel#cartaoValor {{ font-size: 16pt; font-weight: 700; }}
    QLabel#cartaoValor[negativa="true"] {{ color: {ERRO}; }}
    QLabel#cartaoDetalhe {{ color: {TEXTO_SUAVE}; font-size: 9pt; }}
    QLabel#cartaoDetalhe[alerta="true"] {{ color: {ERRO}; font-weight: 600; }}
    /* Tela de OS: cartões de situação (clicáveis: filtram a lista) */
    QFrame#cartaoSituacao {{
        background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 8px;
    }}
    QFrame#cartaoSituacao:hover {{ border: 1px solid {LARANJA}; }}
    QFrame#cartaoSituacao[ativo="true"] {{ border: 2px solid {LARANJA}; background: #FFF8F3; }}
    QLabel#cartaoSituacaoTitulo {{ color: {TEXTO_SUAVE}; font-size: 8pt; font-weight: 700; }}
    QLabel#cartaoSituacaoValor {{ font-size: 18pt; font-weight: 700; }}
    QLabel#cartaoSituacaoValor[situacao="andamento"] {{ color: {COR_OS_ANDAMENTO}; }}
    QLabel#cartaoSituacaoValor[situacao="pronto"] {{ color: {COR_OS_PRONTO}; }}
    QLabel#cartaoSituacaoValor[situacao="aguardando_pagamento"] {{ color: {COR_OS_AGUARDANDO}; }}
    QLabel#cartaoSituacaoDetalhe {{ color: {TEXTO_SUAVE}; font-size: 9pt; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{
        background: transparent; color: {TEXTO_SUAVE}; padding: 8px 14px;
        border-bottom: 2px solid transparent; font-weight: 600;
    }}
    QTabBar::tab:selected {{ color: {TEXTO}; border-bottom: 2px solid {LARANJA}; }}

    QFrame#barraLateral {{ background: {GRAFITE}; }}
    /* RF07: faixa de aviso no topo do conteúdo (mensagens para enviar) */
    QFrame#faixaAviso {{ background: {LARANJA_SUAVE}; border-bottom: 1px solid #F7C9A6; }}
    QLabel#faixaAvisoTexto {{ color: {TEXTO}; font-weight: 600; }}
    QPushButton#faixaAvisoFechar {{
        background: transparent; border: none; color: {TEXTO_SUAVE}; padding: 4px 8px;
    }}
    QPushButton#faixaAvisoFechar:hover {{ color: {TEXTO}; }}
    QLabel#marca {{ color: {LARANJA}; font-size: 22pt; font-weight: 800; }}
    QLabel#marcaSub {{ color: {TEXTO_BARRA_SUAVE}; font-size: 9pt; }}
    QFrame#divisorBarra {{ background: {DIVISOR_BARRA}; border: none; }}

    /* Menu: só ele rola (a marca e o rodapé ficam fixos) */
    QScrollArea#rolagemMenu, QWidget#conteudoMenu {{ background: {GRAFITE}; border: none; }}
    QScrollArea#rolagemMenu QScrollBar:vertical {{ background: {GRAFITE}; width: 8px; margin: 0; }}
    QScrollArea#rolagemMenu QScrollBar::handle:vertical {{
        background: {TEXTO_BARRA_DESABILITADO}; border-radius: 4px; min-height: 24px;
    }}
    QScrollArea#rolagemMenu QScrollBar::add-line:vertical,
    QScrollArea#rolagemMenu QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollArea#rolagemMenu QScrollBar::add-page:vertical,
    QScrollArea#rolagemMenu QScrollBar::sub-page:vertical {{ background: none; }}

    /* Título de grupo: não é clicável e não parece item desabilitado
       (menor, maiúsculo, espaçado; o espaçamento entre letras vem da fonte) */
    QLabel#grupoMenu {{
        color: {TEXTO_BARRA_SUAVE}; font-size: 8pt; font-weight: 700;
        padding: 16px 20px 4px 20px;
    }}

    /* Item do menu (BotaoMenu). Borda esquerda de 3 px reservada: no item
       selecionado ela fica laranja, sem o texto "pular" de lugar. */
    QPushButton#itemMenu {{
        background: transparent; color: {TEXTO_BARRA}; border: none;
        border-left: 3px solid transparent; border-radius: 0;
        padding: 0 20px 0 17px; text-align: left; font-size: 10.5pt; font-weight: 500;
    }}
    QPushButton#itemMenu:hover {{ background: {GRAFITE_CLARO}; color: {TEXTO_BARRA_ATIVO}; }}
    QPushButton#itemMenu:checked {{
        background: {GRAFITE_CLARO}; color: {TEXTO_BARRA_ATIVO}; font-weight: 600;
        border-left: 3px solid {LARANJA};
    }}
    /* Foco pelo TECLADO (Tab): contorno laranja de 1 px. A propriedade focoTeclado
       só liga quando o foco veio do Tab (como o :focus-visible da web): o foco que o
       Qt dá sozinho ao abrir a janela ou o clique do mouse não desenham contorno. */
    QPushButton#itemMenu {{ outline: none; }}
    QPushButton#itemMenu[focoTeclado="true"] {{ border: 1px solid {LARANJA}; border-left: 3px solid transparent; }}
    QPushButton#itemMenu[focoTeclado="true"]:checked {{ border: 1px solid {LARANJA}; border-left: 3px solid {LARANJA}; }}
    QPushButton#itemMenu[emBreve="true"], QPushButton#itemMenu[emBreve="true"]:hover {{
        background: transparent; color: {TEXTO_BARRA_DESABILITADO};
    }}
    /* Selo (pill) de quantidade, ex.: mensagens para enviar */
    QLabel#seloMenu {{
        background: {LARANJA}; color: white; font-size: 8.5pt; font-weight: 700;
        border-radius: 9px; padding: 0 7px;
    }}

    QLineEdit, QPlainTextEdit, QDateEdit, QTimeEdit, QDoubleSpinBox {{
        background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 6px;
        padding: 7px 10px; selection-background-color: {LARANJA};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QDateEdit:focus, QTimeEdit:focus, QDoubleSpinBox:focus {{
        border: 1px solid {LARANJA};
    }}
    QLineEdit:disabled, QPlainTextEdit:disabled {{ color: #868E96; background: #F1F3F5; }}

    QComboBox {{
        background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 6px;
        padding: 7px 10px;
    }}
    QComboBox:focus {{ border: 1px solid {LARANJA}; }}
    QComboBox QAbstractItemView {{
        background: {SUPERFICIE}; border: 1px solid {BORDA};
        selection-background-color: {LARANJA_SUAVE}; selection-color: {TEXTO}; outline: 0;
    }}

    QPushButton {{
        background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 6px;
        padding: 8px 18px; font-weight: 600;
    }}
    QPushButton:hover {{ background: #EDEFF2; }}
    QPushButton:disabled {{ color: #A0A6AE; background: #F1F3F5; }}
    QPushButton#primario {{
        background: {LARANJA}; border: 1px solid {LARANJA}; color: white;
    }}
    QPushButton#primario:hover {{ background: {LARANJA_ESCURO}; }}
    /* Desabilitado tem de PARECER desabilitado (Nielsen: visibilidade do estado) */
    QPushButton#primario:disabled {{ background: #F1F3F5; border: 1px solid {BORDA}; color: #A0A6AE; }}
    QPushButton#perigo {{ color: {ERRO}; }}
    QPushButton#perigo:disabled {{ color: #A0A6AE; }}
    QPushButton#perigo:hover:!disabled {{ background: {ERRO_FUNDO}; }}

    QTableWidget {{
        background: {SUPERFICIE}; alternate-background-color: #FAFAFB;
        border: 1px solid {BORDA}; border-radius: 8px; gridline-color: transparent;
        selection-background-color: {LARANJA_SUAVE}; selection-color: {TEXTO};
        outline: 0;
    }}
    QTableWidget::item {{ padding: 6px 8px; }}
    QHeaderView::section {{
        background: #F1F3F5; color: {TEXTO_SUAVE}; border: none;
        border-bottom: 1px solid {BORDA}; padding: 9px 8px; font-weight: 600;
    }}
    """
