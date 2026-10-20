"""
Histórico de serviços de um veículo (RF02 - HU05). Janela somente leitura.
"""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt
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
)

from src.controle.veiculo_controller import OrdemServicoHistoricoDTO, VeiculoDTO

# Nomes de status como aparecem no DVP (RF04).
ROTULOS_STATUS = {
    "orcamento": "Somente orçamento",
    "andamento": "Em andamento",
    "pronto": "Pronto",
    "aguardando_pagamento": "Aguardando pagamento",
}

COLUNAS = ["OS", "Data", "Status", "Km", "Problema"]


class VeiculoHistoricoDialog(QDialog):
    def __init__(
        self,
        veiculo: VeiculoDTO,
        historico: List[OrdemServicoHistoricoDTO],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Histórico — {veiculo.placa}")
        self.setModal(True)
        self.setMinimumSize(720, 420)

        titulo = QLabel(f"{veiculo.marca} {veiculo.modelo} — {veiculo.placa}")
        titulo.setObjectName("titulo")
        subtitulo = QLabel(f"Cliente: {veiculo.nome_cliente}")
        subtitulo.setObjectName("subtitulo")

        tabela = QTableWidget(len(historico), len(COLUNAS))
        tabela.setHorizontalHeaderLabels(COLUNAS)
        tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabela.setAlternatingRowColors(True)
        tabela.setShowGrid(False)
        tabela.verticalHeader().setVisible(False)
        tabela.verticalHeader().setDefaultSectionSize(40)
        cab = tabela.horizontalHeader()
        cab.setHighlightSections(False)
        cab.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for coluna in range(4):
            cab.setSectionResizeMode(coluna, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        for linha, o in enumerate(historico):
            valores = [
                f"#{o.id_ordem_servico}",
                o.criado_em.strftime("%d/%m/%Y"),
                ROTULOS_STATUS.get(o.status, o.status),
                "—" if o.quilometragem is None else f"{o.quilometragem:,}".replace(",", "."),
                o.descricao_problema or "—",
            ]
            for coluna, valor in enumerate(valores):
                tabela.setItem(linha, coluna, QTableWidgetItem(valor))

        vazio = QLabel("Este veículo ainda não possui ordens de serviço.")
        vazio.setObjectName("vazio")
        vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tabela.setVisible(bool(historico))
        vazio.setVisible(not historico)

        total = QLabel(
            "1 ordem de serviço" if len(historico) == 1 else f"{len(historico)} ordens de serviço"
        )
        total.setObjectName("rodape")
        fechar = QPushButton("Fechar")
        fechar.setDefault(True)
        fechar.clicked.connect(self.accept)

        rodape = QHBoxLayout()
        rodape.addWidget(total)
        rodape.addStretch(1)
        rodape.addWidget(fechar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addWidget(tabela, stretch=1)
        layout.addWidget(vazio, stretch=1)
        layout.addLayout(rodape)
