"""
Janela principal do Camaro: barra lateral de módulos + área de conteúdo.

Cada requisito entregue vira uma página nova (adicionar_modulo). Os módulos
ainda não implementados aparecem desabilitados na barra, para o usuário
ver o que está por vir (visibilidade do estado do sistema, Nielsen).
"""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.apresentacao.telas.clientes_view import ClientesView
from src.apresentacao.tema import LARGURA_BARRA_LATERAL

# Ordem de entrega do cronograma (DVP, seção 3.1). Sai desta lista à medida
# que cada módulo ganha sua tela.
MODULOS_EM_BREVE: List[str] = [
    "Veículos",
    "Produtos",
    "Estoque",
    "Ordens de Serviço",
    "Agendamentos",
    "Notificações",
    "Notas Fiscais",
]


class JanelaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Camaro — Gestão de Oficina Mecânica")
        self.resize(1180, 720)
        self.setMinimumSize(900, 560)

        self._paginas = QStackedWidget()
        self._menu = QListWidget()
        self._menu.setObjectName("menu")
        self._menu.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._menu.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._menu.currentRowChanged.connect(self._trocar_pagina)

        marca = QLabel("CAMARO")
        marca.setObjectName("marca")
        marca_sub = QLabel("Gestão de oficina mecânica")
        marca_sub.setObjectName("marcaSub")

        barra = QFrame()
        barra.setObjectName("barraLateral")
        barra.setFixedWidth(LARGURA_BARRA_LATERAL)
        layout_barra = QVBoxLayout(barra)
        layout_barra.setContentsMargins(0, 24, 0, 16)
        layout_barra.setSpacing(0)
        bloco_marca = QVBoxLayout()
        bloco_marca.setContentsMargins(20, 0, 20, 20)
        bloco_marca.setSpacing(0)
        bloco_marca.addWidget(marca)
        bloco_marca.addWidget(marca_sub)
        layout_barra.addLayout(bloco_marca)
        layout_barra.addWidget(self._menu, 1)

        self.tela_clientes = ClientesView()
        self.adicionar_modulo("Clientes", self.tela_clientes)
        # Rótulo de seção + módulos futuros, todos desabilitados (não clicáveis).
        for texto in ["EM BREVE", *MODULOS_EM_BREVE]:
            item = QListWidgetItem(texto)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._menu.addItem(item)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(barra)
        layout.addWidget(self._paginas, 1)
        self.setCentralWidget(central)

        self._menu.setCurrentRow(0)

    def adicionar_modulo(self, nome: str, pagina: QWidget) -> None:
        """Registra uma página e o item de menu correspondente."""
        self._paginas.addWidget(pagina)
        self._menu.addItem(QListWidgetItem(nome))

    def _trocar_pagina(self, linha: int) -> None:
        if 0 <= linha < self._paginas.count():
            self._paginas.setCurrentIndex(linha)
