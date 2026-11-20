"""
Dados da oficina, lidos do .env (todos opcionais).

    OFICINA_NOME, OFICINA_ENDERECO, OFICINA_TELEFONE, OFICINA_CNPJ

Usados nas mensagens do WhatsApp (RF07) e no cabeçalho da OS impressa/PDF.
O que não estiver preenchido simplesmente não aparece. Ficam no .env, e não
no banco, porque são da instalação (uma oficina por instalação) e podem ser
ajustados sem tela nova.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _ler(variavel: str) -> str:
    return " ".join((os.getenv(variavel) or "").split())


@dataclass(frozen=True)
class DadosOficina:
    nome: str = ""
    endereco: str = ""
    telefone: str = ""
    cnpj: str = ""


def dados_da_oficina() -> DadosOficina:
    return DadosOficina(
        nome=_ler("OFICINA_NOME"),
        endereco=_ler("OFICINA_ENDERECO"),
        telefone=_ler("OFICINA_TELEFONE"),
        cnpj=_ler("OFICINA_CNPJ"),
    )
