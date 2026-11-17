"""
Ícones de traço (estilo Lucide) embutidos como SVG.

Por que embutidos: nada de arquivo solto nem biblioteca nova. O executável
(PyInstaller) já leva o QtSvg, e tudo funciona offline (RNF03).

Os desenhos usam a grade 24x24 do Lucide, com traço de 2 px e pontas
arredondadas. A cor entra como parâmetro: a barra lateral pinta o mesmo ícone
de cinza claro (normal), branco (mouse em cima) e laranja (selecionado).
Os desenhos seguem os ícones do Lucide (licença ISC, https://lucide.dev).
"""
from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_DESENHOS = {
    "clientes": (  # users
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
        '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
    ),
    "veiculos": (  # car
        '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3'
        'c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/>'
        '<circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>'
    ),
    "produtos": (  # package
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73'
        'l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'
    ),
    "estoque": (  # layers
        '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0'
        'l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>'
        '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>'
    ),
    "ordens_servico": (  # wrench
        '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94'
        'l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>'
    ),
    "agendamentos": (  # calendar
        '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/>'
        '<path d="M3 10h18"/>'
    ),
    "notificacoes": (  # bell
        '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>'
    ),
    "relatorios": (  # bar-chart
        '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>'
    ),
    "usuarios": (  # shield-user
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1'
        'c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
        '<circle cx="12" cy="10" r="2.5"/><path d="M8.5 16.5a4 4 0 0 1 7 0"/>'
    ),
    "notas_fiscais": (  # receipt
        '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/>'
        '<path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>'
    ),
    "sair": (  # log-out (porta com seta)
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>'
    ),
}

NOMES = tuple(_DESENHOS)


def svg(nome: str, cor: str) -> str:
    """O SVG completo do ícone, já com a cor do traço."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{cor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f"{_DESENHOS[nome]}</svg>"
    )


def _pixmap(nome: str, cor: str, lado: int) -> QPixmap:
    pixmap = QPixmap(lado, lado)
    pixmap.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg(nome, cor).encode())).render(pintor, QRectF(0, 0, lado, lado))
    pintor.end()
    return pixmap


@lru_cache(maxsize=None)
def icone(nome: str, cor: str, tamanho: int = 18) -> QIcon:
    """
    QIcon do ícone `nome` pintado com `cor`. Leva duas resoluções (1x e 2x):
    o Qt escolhe a nítida em telas com escala de 150%/200%.
    O cache evita redesenhar o SVG a cada passagem do mouse.
    """
    resultado = QIcon()
    for escala in (1, 2):
        resultado.addPixmap(_pixmap(nome, cor, tamanho * escala))
    return resultado
