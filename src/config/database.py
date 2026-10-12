"""
Configuração central de conexão com o banco de dados PostgreSQL.

Este módulo concentra a criação da Engine e da Session do SQLAlchemy,
para que nenhuma outra camada do sistema precise saber como a conexão
é montada (Camada de Persistência do DVP, seção 2.1).
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Em produção, estas variáveis vêm do arquivo .env (ver .env.example).
# Nunca deixe credenciais reais commitadas no código.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "camaro_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "masterkey")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# echo=True imprime todo SQL gerado no console — útil durante o
# desenvolvimento, deve ser desligado (False) na versão empacotada.
engine = create_engine(DATABASE_URL, echo=True)

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
