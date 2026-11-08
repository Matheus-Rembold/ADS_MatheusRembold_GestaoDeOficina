"""
Controller de Relatórios (RF06) - Camada de Controle (DVP, seção 2.1).

Mesmo papel dos outros controllers: abre/fecha a Session, chama o serviço e
devolve objetos imutáveis para a tela.

Por que não há DTOs novos aqui? O RelatorioService já devolve dataclasses
frozen SEM nenhum objeto ORM (relatório não é tabela). Copiá-las campo a
campo para "outros" DTOs iguais seria só cerimônia; o controller reexporta
os tipos e a tela continua importando apenas desta camada.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Optional, Tuple

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.servico.exportacao_relatorio import CODIFICACAO, gerar_csv
from src.servico.relatorio_service import (  # noqa: F401  (reexportados para a tela)
    AGRUPA_DIA,
    AGRUPA_MES,
    PERIODOS,
    PERSONALIZADO,
    ULTIMOS_12_MESES,
    PontoFinanceiro,
    Relatorio,
    RelatorioService,
    ResumoFinanceiro,
    ServicoRanking,
    periodo_predefinido,
)

# Reexportadas de propósito: a tela importa as exceções DAQUI.
from src.servico.excecoes import ErroDeNegocio, ValidacaoError  # noqa: F401

__all__ = [
    "AGRUPA_DIA", "AGRUPA_MES", "ErroDeNegocio", "PERIODOS", "PERSONALIZADO",
    "PontoFinanceiro", "Relatorio", "RelatorioController", "ResumoFinanceiro",
    "ServicoRanking", "ULTIMOS_12_MESES", "ValidacaoError",
]


class RelatorioController:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def gerar(self, inicio: Optional[date], fim: Optional[date]) -> Relatorio:
        with self._session_factory() as session:
            return RelatorioService(session).gerar(inicio, fim)

    @staticmethod
    def datas_do_periodo(nome: str, hoje: Optional[date] = None) -> Tuple[date, date]:
        return periodo_predefinido(nome, hoje)

    @staticmethod
    def salvar_csv(relatorio: Relatorio, caminho: str, gerado_em: Optional[datetime] = None) -> None:
        """Grava o CSV do relatório que está na tela (mesmos números, mesmos filtros)."""
        with open(caminho, "w", encoding=CODIFICACAO, newline="") as arquivo:
            arquivo.write(gerar_csv(relatorio, gerado_em))

    @staticmethod
    def nome_sugerido(relatorio: Relatorio, extensao: str) -> str:
        return f"relatorio_{relatorio.inicio:%Y-%m-%d}_a_{relatorio.fim:%Y-%m-%d}.{extensao}"
