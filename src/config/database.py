"""
Configuração central de conexão com o banco de dados PostgreSQL.

Este módulo concentra a criação da Engine e da Session do SQLAlchemy,
para que nenhuma outra camada do sistema precise saber como a conexão
é montada (Camada de Persistência do DVP, seção 2.1).
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from src.config.ambiente import carregar_env, variavel_booleana

# As variáveis vêm do arquivo .env (ver .env.example), lido da raiz do projeto
# ou da pasta do Camaro.exe. NUNCA há senha escrita no código.
carregar_env()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "camaro_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# URL.create monta a conexão com segurança: uma senha com @, : ou / não
# quebra a URL (com f-string, quebraria).
DATABASE_URL = URL.create(
    "postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME,
)

# DB_ECHO=true no .env imprime todo o SQL no console (útil para depurar).
# Padrão desligado: no executável não há console.
engine = create_engine(DATABASE_URL, echo=variavel_booleana("DB_ECHO", False))

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Classe base que todos os models SQLAlchemy vão herdar."""
    pass


def get_session():
    """
    Retorna uma nova sessão de banco de dados.

    Uso recomendado (garante que a sessão é sempre fechada):

        with get_session() as session:
            ... consultas ...
    """
    return SessionLocal()
