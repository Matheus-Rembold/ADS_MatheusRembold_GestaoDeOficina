# -*- mode: python ; coding: utf-8 -*-
"""
Receita do executável do Camaro (PyInstaller, RNF07 - Windows nativo).

Gerar (raiz do projeto, venv ativo):
    pyinstaller camaro.spec --noconfirm --clean

Resultado (pacote de entrega, 20/11/2026):
    dist/Camaro/   Camaro.exe + _internal/ + BancoDeDados.sql + .env.example + LEIA-ME.txt
    dist/Camaro.zip   a mesma pasta compactada, pronta para enviar
Para testar aqui, copie o seu .env para dist/Camaro/ (ao lado do Camaro.exe);
ele NUNCA entra no .zip.

Decisões:
- ONEDIR (pasta), não onefile: abre mais rápido (o onefile descompacta tudo
  numa pasta temporária a cada abertura) e gera menos alarme falso de antivírus.
- console=False: é um sistema de janelas; erros vão para
  %LOCALAPPDATA%\\Camaro\\camaro.log (ver src/config/ambiente.py).
- O .env NÃO entra no pacote (tem a senha do banco); só o .env.example vai junto,
  ao lado do Camaro.exe, como modelo para quem instala.
- hiddenimports: o SQLAlchemy carrega o dialeto do PostgreSQL pelo nome
  ("postgresql+psycopg2"), que o PyInstaller não enxerga sozinho.
"""

a = Analysis(
    ["src/main.py"],
    pathex=[SPECPATH],  # raiz do projeto: os imports são "from src. ..."
    datas=[],
    hiddenimports=[
        "sqlalchemy.dialects.postgresql.psycopg2",
        "PyQt6.QtCharts",
        "PyQt6.QtPrintSupport",  # OS impressa / PDF (documento_os.py)
        "PyQt6.QtSvg",  # ícones da barra lateral (SVG embutido em icones.py)
    ],
    excludes=[
        # bibliotecas que o Camaro não usa: o pacote fica menor
        "tkinter",
        "unittest",
        "pydoc",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtMultimedia",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNetwork",
        "PyQt6.Qt3DCore",
    ],
    noarchive=False,
)
# DLLs grandes que o Camaro não usa (~25 MB a menos). Conferido com
# "Camaro.exe --verificar", que abre todas as telas e exporta o PDF:
# - opengl32sw.dll: OpenGL por software (reserva para apps 3D/QML);
# - Qt6Pdf.dll / qpdf.dll: LEITURA de PDF. Para GERAR usamos o QPdfWriter (QtGui).
SEM_USO = {"opengl32sw.dll", "qt6pdf.dll", "qpdf.dll"}
a.binaries = [b for b in a.binaries if b[0].replace("\\", "/").split("/")[-1].lower() not in SEM_USO]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Camaro",
    console=False,
    upx=False,  # UPX comprime, mas costuma disparar antivírus e quebrar DLLs do Qt
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="Camaro",
    upx=False,
)

# ---------------------------------------------------------------------------
# Pacote de entrega: arquivos de instalação ao lado do Camaro.exe + Camaro.zip
# ---------------------------------------------------------------------------
import shutil
import zipfile
from pathlib import Path

RAIZ = Path(SPECPATH)
PASTA = Path(DISTPATH) / "Camaro"
JUNTO = {
    RAIZ / "banco" / "BancoDeDados.sql": "BancoDeDados.sql",
    RAIZ / ".env.example": ".env.example",
    RAIZ / "docs" / "LEIA-ME-instalacao.txt": "LEIA-ME.txt",
}
for origem, nome in JUNTO.items():
    shutil.copy2(origem, PASTA / nome)

ZIP = Path(DISTPATH) / "Camaro.zip"
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as pacote:
    for arquivo in sorted(PASTA.rglob("*")):
        if arquivo.is_file() and arquivo.name.lower() != ".env":  # a senha nunca vai junto
            pacote.write(arquivo, Path("Camaro") / arquivo.relative_to(PASTA))
print(f"Pacote de entrega: {ZIP} ({ZIP.stat().st_size / 1_048_576:.1f} MB)")

