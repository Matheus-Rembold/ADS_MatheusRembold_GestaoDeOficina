"""
Ponto de entrada do sistema Camaro.

Desenvolvimento (raiz do projeto, venv ativo):
    python -m src.main
    python -m src.main --verificar     # autodiagnóstico, sem abrir janela

Executável (PyInstaller, RNF07):
    Camaro.exe
    Camaro.exe --verificar             # resultado em %LOCALAPPDATA%\\Camaro\\camaro.log

O .env fica na raiz do projeto (desenvolvimento) ou ao lado do Camaro.exe.

Fluxo (RF10): banco disponível -> sem nenhum usuário? configuração inicial
(cria o dono) -> login -> janela principal. "Sair" destrói a janela e volta
ao login; fechar a janela, ou cancelar o login, encerra o programa.
"""
import logging
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from src.config.ambiente import (
    ARQUIVO_ENV,
    ARQUIVO_LOG,
    EMPACOTADO,
    configurar_log,
)

configurar_log()  # antes de tudo: qualquer erro daqui em diante vai para o arquivo

from src.apresentacao.janela_principal import JanelaPrincipal  # noqa: E402
from src.apresentacao.telas.configuracao_inicial_dialog import ConfiguracaoInicialDialog  # noqa: E402
from src.apresentacao.telas.login_dialog import LoginDialog  # noqa: E402
from src.controle.autenticacao_controller import AutenticacaoController  # noqa: E402
from src.controle.sessao import sessao  # noqa: E402
from src.apresentacao.tema import estilo_global  # noqa: E402
from src.config.database import DB_HOST, DB_NAME, DB_PORT, engine  # noqa: E402

logger = logging.getLogger("camaro")


def banco_disponivel() -> bool:
    """Abre e fecha uma conexão só para saber se o PostgreSQL responde."""
    try:
        with engine.connect():
            return True
    except Exception:  # inclui OperationalError e o UnicodeDecodeError do Windows em português
        logger.exception("Não foi possível conectar ao banco de dados")
        return False


def _tratar_excecao(tipo, valor, rastro) -> None:
    """
    Erro não tratado (ex.: dentro de um clique de botão). Sem este gancho, o
    PyQt6 FECHA o programa na hora; com ele, o erro vai para o log e o usuário
    vê uma mensagem, e o sistema continua aberto.
    """
    logger.critical("Erro não tratado:\n%s", "".join(traceback.format_exception(tipo, valor, rastro)))
    if QApplication.instance() is not None:
        QMessageBox.critical(
            None, "Camaro — erro inesperado",
            f"Ocorreu um erro inesperado e a operação não foi concluída.\n\n{valor}\n\n"
            f"Detalhes registrados em:\n{ARQUIVO_LOG}",
        )


def _criar_app() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName("Camaro")
    app.setStyleSheet(estilo_global())
    return app


def verificar() -> int:
    """
    Autodiagnóstico do executável (Camaro.exe --verificar): testa o que mais
    costuma quebrar no empacotamento (banco, telas, gráficos e PDF) sem abrir
    janela. O resultado vai para o log; o código de saída é 0 (ok) ou 1.
    """
    from src.apresentacao.relatorio_pdf import salvar_pdf
    from src.controle.relatorio_controller import RelatorioController, ULTIMOS_12_MESES

    app = _criar_app()
    resultados = []

    def passo(nome, funcao):
        try:
            detalhe = funcao()
            resultados.append(True)
            logger.info("[OK] %s%s", nome, f" ({detalhe})" if detalhe else "")
        except Exception:  # noqa: BLE001
            resultados.append(False)
            logger.exception("[FALHOU] %s", nome)

    logger.info("=== Verificação do Camaro (%s) ===", "executável" if EMPACOTADO else "desenvolvimento")
    passo("arquivo .env encontrado", lambda: str(ARQUIVO_ENV) if ARQUIVO_ENV.exists() else 1 / 0)
    passo("conexão com o PostgreSQL", lambda: f"{DB_HOST}:{DB_PORT}/{DB_NAME}" if banco_disponivel() else 1 / 0)
    if not resultados[-1]:
        # Sem banco, as telas abririam caixas de erro esperando um clique que
        # nunca vem (a verificação travaria). Encerra aqui com falha.
        logger.error("Sem conexão com o banco: os passos seguintes foram pulados.")
        logger.info("=== Resultado: HÁ FALHAS (confira o .env em %s) ===", ARQUIVO_ENV)
        app.quit()
        return 1

    def tabela_de_usuarios():
        configurar = AutenticacaoController().precisa_configuracao_inicial()
        return "nenhum usuário ainda: o sistema vai pedir a configuração inicial" if configurar else "usuários cadastrados"

    passo("tabela de usuários (login)", tabela_de_usuarios)

    def bcrypt_funciona():
        import bcrypt  # extensão compilada: é o que mais pode faltar no executável
        h = bcrypt.hashpw(b"verificacao", bcrypt.gensalt(4))
        if not bcrypt.checkpw(b"verificacao", h):
            raise RuntimeError("bcrypt não confere")
        return f"bcrypt {bcrypt.__version__}"

    passo("hash de senha (bcrypt)", bcrypt_funciona)

    # Sessão interna de diagnóstico (perfil dono, só em memória): sem ela as
    # telas seriam recusadas pelo guard, porque aqui ninguém faz login.
    sessao.entrar_sistema()

    def abrir_telas():
        janela = JanelaPrincipal()
        for i in range(janela._paginas.count()):
            janela._paginas.setCurrentIndex(i)
            janela._paginas.currentWidget().show()
            app.processEvents()
        return f"{janela._paginas.count()} telas"

    passo("todas as telas abrem", abrir_telas)

    def relatorio_e_exportacao():
        controller = RelatorioController()
        relatorio = controller.gerar(*controller.datas_do_periodo(ULTIMOS_12_MESES))
        pasta = Path(tempfile.gettempdir())
        pdf, csv = pasta / "camaro_verificacao.pdf", pasta / "camaro_verificacao.csv"
        salvar_pdf(relatorio, str(pdf))
        controller.salvar_csv(relatorio, str(csv))
        tamanhos = pdf.stat().st_size, csv.stat().st_size
        pdf.unlink()
        csv.unlink()
        if min(tamanhos) == 0:
            raise RuntimeError("arquivo exportado vazio")
        return f"{relatorio.resumo.qtd_os} OS no período; PDF {tamanhos[0] // 1024} KB"

    passo("relatório, gráficos e exportação PDF/CSV", relatorio_e_exportacao)

    def ordem_servico_em_pdf():
        """OS impressa/PDF: confere que o QtPrintSupport veio no pacote (só lê o banco)."""
        from src.apresentacao.documento_os import gerar_pdf
        from src.controle.ordem_servico_controller import OrdemServicoController
        controller = OrdemServicoController()
        pagina = controller.listar_pagina()
        if not pagina.itens:
            return "nenhuma OS cadastrada ainda (nada a imprimir)"
        documento = controller.documento(pagina.itens[0].id_ordem_servico)
        pdf = Path(tempfile.gettempdir()) / "camaro_verificacao_os.pdf"
        gerar_pdf(documento, str(pdf))
        tamanho = pdf.stat().st_size
        pdf.unlink()
        if tamanho == 0:
            raise RuntimeError("PDF da OS vazio")
        return f"OS nº {documento.os.id_ordem_servico}; PDF {tamanho // 1024} KB"

    passo("ordem de serviço em PDF", ordem_servico_em_pdf)

    ok = all(resultados)
    logger.info("=== Resultado: %d/%d passos ok — %s ===", sum(resultados), len(resultados),
                "TUDO CERTO" if ok else "HÁ FALHAS")
    app.quit()
    return 0 if ok else 1


def main() -> int:
    sys.excepthook = _tratar_excecao
    if "--verificar" in sys.argv:
        return verificar()

    app = _criar_app()
    logger.info("Camaro iniciado em %s (%s)", datetime.now().strftime("%d/%m/%Y %H:%M"),
                "executável" if EMPACOTADO else "desenvolvimento")

    if not ARQUIVO_ENV.exists():
        QMessageBox.critical(
            None,
            "Camaro — configuração não encontrada",
            "O arquivo de configuração .env não foi encontrado.\n\n"
            f"Ele deve ficar em:\n{ARQUIVO_ENV}\n\n"
            "Copie o arquivo .env.example (que vem junto com o sistema) para esse local "
            "com o nome .env e preencha os dados de acesso ao PostgreSQL.",
        )
        return 1

    if not banco_disponivel():
        QMessageBox.critical(
            None,
            "Camaro — banco de dados indisponível",
            "Não foi possível conectar ao PostgreSQL.\n\n"
            "Confira se o serviço do PostgreSQL está em execução e se os dados do "
            f"arquivo .env (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD) estão corretos.\n\n"
            f"Arquivo .env esperado em:\n{ARQUIVO_ENV}\n\nDetalhes no log:\n{ARQUIVO_LOG}",
        )
        return 1

    aplicacao = Aplicacao(app)
    if not aplicacao.iniciar():
        return 0  # cancelou a configuração inicial ou o login
    return app.exec()


class Aplicacao:
    """Liga login e janela principal: entrar, sair e voltar ao login."""

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._auth = AutenticacaoController()
        self._janela = None
        self._ultimo_login = ""
        # Quem encerra o programa é o fechamento da janela principal (closeEvent),
        # não "a última janela fechou": no "Sair" a janela some antes do login abrir.
        app.setQuitOnLastWindowClosed(False)

    def iniciar(self) -> bool:
        if self._auth.precisa_configuracao_inicial():
            dialogo = ConfiguracaoInicialDialog(self._auth)
            if dialogo.exec() != QDialog.DialogCode.Accepted:
                return False
            self._ultimo_login = dialogo.resultado.login
        elif not self._pedir_login():
            return False
        self._abrir_janela()
        return True

    def _pedir_login(self) -> bool:
        dialogo = LoginDialog(self._auth, self._ultimo_login)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return False
        self._ultimo_login = dialogo.resultado.login
        return True

    def _abrir_janela(self) -> None:
        self._janela = JanelaPrincipal()
        self._janela.saiu.connect(self._sair)
        self._janela.fechou.connect(self._app.quit)
        self._janela.show()

    def _sair(self) -> None:
        """Destrói a janela inteira: nada do usuário anterior fica em memória."""
        janela, self._janela = self._janela, None
        janela.hide()
        janela.deleteLater()
        self._auth.sair()
        logger.info("Sessão encerrada (Sair)")
        if self._pedir_login():
            self._abrir_janela()
        else:
            self._app.quit()


if __name__ == "__main__":
    sys.exit(main())
