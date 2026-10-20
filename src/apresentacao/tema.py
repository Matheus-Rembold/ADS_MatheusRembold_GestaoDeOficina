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

LARGURA_BARRA_LATERAL = 230


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

    QFrame#barraLateral {{ background: {GRAFITE}; }}
    QLabel#marca {{ color: {LARANJA}; font-size: 22pt; font-weight: 800; }}
    QLabel#marcaSub {{ color: #9AA0A6; font-size: 9pt; }}
    QListWidget#menu {{
        background: {GRAFITE}; border: none; outline: 0; color: #C9CED3;
    }}
    QListWidget#menu::item {{
        padding: 11px 20px; border-left: 3px solid transparent;
    }}
    QListWidget#menu::item:hover:!disabled {{ background: {GRAFITE_CLARO}; }}
    QListWidget#menu::item:selected {{
        background: {GRAFITE_CLARO}; color: white; border-left: 3px solid {LARANJA};
    }}
    QListWidget#menu::item:disabled {{ color: #5F666D; }}

    QLineEdit {{
        background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 6px;
        padding: 7px 10px; selection-background-color: {LARANJA};
    }}
    QLineEdit:focus {{ border: 1px solid {LARANJA}; }}

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
    QPushButton#perigo {{ color: {ERRO}; }}
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
