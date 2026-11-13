"""
Ambiente de execução: onde estão os arquivos do sistema e o .env, e o log.

Funciona igual em desenvolvimento (python -m src.main) e no executável do
PyInstaller (RNF07: Windows nativo):

- PASTA_DO_SISTEMA: raiz do projeto em desenvolvimento; a pasta do
  Camaro.exe quando empacotado. O .env fica sempre AQUI, fora do pacote,
  porque tem a senha do banco e muda de computador para computador.
- PASTA_DE_DADOS: %LOCALAPPDATA%\\Camaro (o log fica aí). Não usamos a pasta
  do .exe para gravar, porque em "Arquivos de Programas" o Windows não
  deixa um usuário comum escrever.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

EMPACOTADO = bool(getattr(sys, "frozen", False))

PASTA_DO_SISTEMA = (
    Path(sys.executable).resolve().parent if EMPACOTADO
    else Path(__file__).resolve().parents[2]  # src/config/ambiente.py -> raiz do projeto
)
PASTA_DE_DADOS = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Camaro"
ARQUIVO_ENV = PASTA_DO_SISTEMA / ".env"
ARQUIVO_LOG = PASTA_DE_DADOS / "camaro.log"


def carregar_env() -> bool:
    """
    Lê o .env da pasta do sistema. override=False: uma variável já definida no
    ambiente vale mais que o arquivo (os testes usam DB_NAME=... assim).
    Devolve se o arquivo existia.
    """
    return load_dotenv(ARQUIVO_ENV, override=False)


def configurar_log() -> None:
    """Log em arquivo (até 3 arquivos de 1 MB). No .exe não existe console para ver erros."""
    PASTA_DE_DADOS.mkdir(parents=True, exist_ok=True)
    arquivo = RotatingFileHandler(ARQUIVO_LOG, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(arquivo)
    if not EMPACOTADO:
        raiz.addHandler(logging.StreamHandler())


def variavel_booleana(nome: str, padrao: bool = False) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes", "on")
