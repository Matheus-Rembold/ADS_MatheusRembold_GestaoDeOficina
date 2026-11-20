"""
Teste do AutenticacaoService e da segurança de senha (RF10) no PostgreSQL real.

Rode da raiz do projeto, com o venv ativo:
    python testar_autenticacao_service.py

ISOLAMENTO TOTAL: tudo roda dentro de UMA transação que é desfeita no fim
(join_transaction_mode="create_savepoint": cada commit do serviço vira um
savepoint). O teste chega a apagar os usuários para simular o primeiro
acesso, e no fim o banco volta exatamente como estava. Funciona com ou sem
usuários cadastrados.

O bloqueio por tempo usa um RELÓGIO FALSO injetado no serviço: o teste
"avança" 5 minutos sem esperar.
"""
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.config.database import engine
from src.persistencia.models import PerfilUsuario, Usuario
from src.servico.autenticacao_service import BLOQUEIO_MINUTOS, MAX_TENTATIVAS, AutenticacaoService
from src.servico.excecoes import (
    CredenciaisInvalidasError,
    OperacaoNaoPermitidaError,
    UsuarioBloqueadoError,
    ValidacaoError,
)
from src.servico.seguranca_senha import CUSTO_BCRYPT, gerar_hash, problemas_da_senha, senha_confere
from src.servico.usuario_service import UsuarioService

engine.echo = False
resultados = []
SENHA_DONO = "Oficina#Camaro2026"
SENHA_MEC = "chave-de-roda-15"


def verificar(descricao: str, condicao) -> None:
    resultados.append(bool(condicao))
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}")


def esperar_erro(descricao, tipo, funcao):
    try:
        funcao()
    except tipo as erro:
        verificar(f"{descricao} -> {tipo.__name__}: {str(erro).splitlines()[0]}", True)
        return erro
    except Exception as erro:  # noqa: BLE001
        verificar(f"{descricao} -> erro inesperado {type(erro).__name__}: {erro}", False)
    else:
        verificar(f"{descricao} -> deveria ter levantado {tipo.__name__}", False)
    return None


class RelogioFalso:
    def __init__(self) -> None:
        self.agora = datetime(2026, 11, 15, 9, 0, 0)

    def __call__(self) -> datetime:
        return self.agora

    def avancar(self, **delta) -> None:
        self.agora += timedelta(**delta)


class CapturaLog(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.mensagens = []

    def emit(self, registro) -> None:
        self.mensagens.append(registro.getMessage())


def foto_usuarios():
    """Retrato da tabela usuario (para provar que o teste não deixou rastro)."""
    with Session(engine) as s:
        return [tuple(r) for r in s.execute(select(
            Usuario.id_usuario, Usuario.login, Usuario.senha_hash, Usuario.ativo,
            Usuario.tentativas_falhas, Usuario.bloqueado_ate, Usuario.ultimo_login_em,
        ).order_by(Usuario.id_usuario)).all()]


def main() -> None:
    antes = foto_usuarios()
    conexao = engine.connect()
    transacao = conexao.begin()
    s = Session(bind=conexao, join_transaction_mode="create_savepoint")
    relogio = RelogioFalso()
    auth = AutenticacaoService(s, relogio=relogio)
    log = CapturaLog()
    logging.getLogger("src").addHandler(log)
    logging.getLogger("src").setLevel(logging.INFO)
    try:
        print("\n--- Política de senha (NIST SP 800-63B + limite do bcrypt) ---")
        verificar("7 caracteres: curta", problemas_da_senha("1234567"))
        verificar("8 caracteres: aceita (sem exigir maiúscula ou símbolo)", problemas_da_senha("abcdefgh") == [])
        verificar("só espaços: recusada", problemas_da_senha("        "))
        verificar("igual ao usuário (sem diferenciar maiúsculas): recusada",
                  problemas_da_senha("Osvaldo123", "osvaldo123"))
        verificar("64 letras simples: aceita", problemas_da_senha("a" * 64) == [])
        verificar("65 caracteres: recusada", problemas_da_senha("a" * 65))
        verificar("37 letras com acento = 74 bytes (> 72 do bcrypt): recusada", problemas_da_senha("á" * 37))
        verificar("vazia: recusada", problemas_da_senha(""))

        print("\n--- Hash (nunca a senha em texto) ---")
        h1, h2 = gerar_hash(SENHA_DONO), gerar_hash(SENHA_DONO)
        verificar(f"hash bcrypt de 60 caracteres, custo {CUSTO_BCRYPT} ($2b${CUSTO_BCRYPT}$...)",
                  len(h1) == 60 and h1.startswith(f"$2b${CUSTO_BCRYPT}$"))
        verificar("hash nunca contém a senha", SENHA_DONO not in h1)
        verificar("mesma senha, hashes diferentes (sal aleatório)", h1 != h2)
        verificar("a senha confere com os dois hashes", senha_confere(SENHA_DONO, h1) and senha_confere(SENHA_DONO, h2))
        verificar("senha errada não confere", not senha_confere("outra-senha", h1))
        verificar("senha de 80 bytes não estoura o bcrypt: só não confere", senha_confere("ç" * 40, h1) is False)
        verificar("sem hash (login inexistente): não confere", senha_confere(SENHA_DONO, None) is False)

        print("\n--- Primeiro acesso (tabela vazia nesta transação) ---")
        s.execute(delete(Usuario))
        s.commit()
        verificar("sem usuários: precisa da configuração inicial", auth.precisa_configuracao_inicial())
        e = esperar_erro("tudo vazio", ValidacaoError, lambda: auth.criar_primeiro_usuario("", "", "", ""))
        verificar("   lista nome, usuário e senha", e is not None and len(e.erros) >= 3)
        esperar_erro("senha curta", ValidacaoError, lambda: auth.criar_primeiro_usuario("Osvaldo", "osvaldo", "123", "123"))
        esperar_erro("confirmação diferente", ValidacaoError,
                     lambda: auth.criar_primeiro_usuario("Osvaldo", "osvaldo", SENHA_DONO, SENHA_DONO + "x"))
        esperar_erro("usuário com acento/espaço", ValidacaoError,
                     lambda: auth.criar_primeiro_usuario("Osvaldo", "osvaldo r", SENHA_DONO, SENHA_DONO))
        dono = auth.criar_primeiro_usuario("  Osvaldo   Rembold ", "  OSVALDO ", SENHA_DONO, SENHA_DONO)
        verificar("primeiro usuário criado como DONO", dono.perfil is PerfilUsuario.DONO and dono.ativo)
        verificar("usuário gravado em minúsculas e nome sem espaços sobrando",
                  dono.login == "osvaldo" and dono.nome == "Osvaldo Rembold")
        verificar("o banco guarda o hash, não a senha", dono.senha_hash != SENHA_DONO and dono.senha_hash.startswith("$2b$"))
        verificar("agora não precisa mais de configuração inicial", not auth.precisa_configuracao_inicial())
        esperar_erro("criar 'primeiro usuário' de novo", OperacaoNaoPermitidaError,
                     lambda: auth.criar_primeiro_usuario("Outro", "outro", SENHA_DONO, SENHA_DONO))

        print("\n--- Login ---")
        u = auth.autenticar("OSVALDO", SENHA_DONO)
        verificar("login certo (sem diferenciar maiúsculas) entra", u.id_usuario == dono.id_usuario)
        verificar("registra o último acesso (pelo relógio)", u.ultimo_login_em == relogio.agora)
        e1 = esperar_erro("senha errada", CredenciaisInvalidasError, lambda: auth.autenticar("osvaldo", "errada!!"))
        e2 = esperar_erro("usuário inexistente", CredenciaisInvalidasError, lambda: auth.autenticar("ninguem", SENHA_DONO))
        verificar("   as duas mensagens são idênticas ('Usuário ou senha inválidos.')",
                  e1 is not None and e2 is not None and str(e1) == str(e2) == "Usuário ou senha inválidos.")
        esperar_erro("login e senha vazios", CredenciaisInvalidasError, lambda: auth.autenticar("", ""))

        def medir(login, senha, vezes=3):
            t = time.perf_counter()
            for _ in range(vezes):
                try:
                    auth.autenticar(login, senha)
                except Exception:  # noqa: BLE001
                    pass
            return (time.perf_counter() - t) / vezes

        auth.autenticar("osvaldo", SENHA_DONO)  # zera o contador antes de medir
        t_inexistente = medir("ninguem-aqui", "qualquer-coisa")
        t_errada = medir("osvaldo", "senha-errada")
        auth.autenticar("osvaldo", SENHA_DONO)
        verificar(f"tempo igual para inexistente ({t_inexistente*1000:.0f} ms) e senha errada ({t_errada*1000:.0f} ms)",
                  0.5 < t_inexistente / t_errada < 2.0)

        print(f"\n--- Bloqueio: {MAX_TENTATIVAS} falhas, {BLOQUEIO_MINUTOS} minutos (relógio falso) ---")
        for _ in range(MAX_TENTATIVAS - 1):
            try:
                auth.autenticar("osvaldo", "errada!!")
            except CredenciaisInvalidasError:
                pass
        s.expire_all()
        verificar(f"{MAX_TENTATIVAS - 1} falhas ficam gravadas no banco",
                  s.get(Usuario, dono.id_usuario).tentativas_falhas == MAX_TENTATIVAS - 1)
        auth.autenticar("osvaldo", SENHA_DONO)
        s.expire_all()
        verificar("login certo zera o contador", s.get(Usuario, dono.id_usuario).tentativas_falhas == 0)
        for _ in range(MAX_TENTATIVAS - 1):
            try:
                auth.autenticar("osvaldo", "errada!!")
            except CredenciaisInvalidasError:
                pass
        e = esperar_erro(f"{MAX_TENTATIVAS}ª falha seguida bloqueia", UsuarioBloqueadoError,
                         lambda: auth.autenticar("osvaldo", "errada!!"))
        verificar(f"   bloqueio de {BLOQUEIO_MINUTOS} min", e is not None and e.segundos_restantes == BLOQUEIO_MINUTOS * 60)
        esperar_erro("bloqueado: nem a senha CERTA entra", UsuarioBloqueadoError, lambda: auth.autenticar("osvaldo", SENHA_DONO))
        relogio.avancar(minutes=4)
        e = esperar_erro("4 min depois: ainda bloqueado", UsuarioBloqueadoError, lambda: auth.autenticar("osvaldo", SENHA_DONO))
        verificar("   faltam 60 s", e is not None and e.segundos_restantes == 60)
        verificar("   a mensagem mostra o tempo restante ('1 min 00 s')", e is not None and "1 min 00 s" in str(e))
        relogio.avancar(minutes=1, seconds=1)
        u = auth.autenticar("osvaldo", SENHA_DONO)
        s.expire_all()
        verificar("passado o tempo, a senha certa entra e o bloqueio some",
                  u is not None and s.get(Usuario, dono.id_usuario).bloqueado_ate is None)
        try:
            auth.autenticar("osvaldo", "errada!!")
        except CredenciaisInvalidasError:
            pass
        s.expire_all()
        verificar("depois do bloqueio, o contador recomeça do zero", s.get(Usuario, dono.id_usuario).tentativas_falhas == 1)
        auth.autenticar("osvaldo", SENHA_DONO)

        print("\n--- Usuário inativo ---")
        mec = UsuarioService(s).cadastrar("João Mecânico", "joao", SENHA_MEC, SENHA_MEC, PerfilUsuario.MECANICO)
        verificar("mecânico ativo entra", auth.autenticar("joao", SENHA_MEC).perfil is PerfilUsuario.MECANICO)
        UsuarioService(s).definir_ativo(mec.id_usuario, False, dono.id_usuario)
        e = esperar_erro("inativo com a senha certa não entra", CredenciaisInvalidasError,
                         lambda: auth.autenticar("joao", SENHA_MEC))
        verificar("   mesma mensagem genérica (não revela que existe)", e is not None and str(e) == "Usuário ou senha inválidos.")
        verificar("usuario_vigente devolve None para inativo e o usuário para ativo",
                  auth.usuario_vigente(mec.id_usuario) is None and auth.usuario_vigente(dono.id_usuario) is not None)

        print("\n--- Log ---")
        verificar("o log registra os logins", any("Login: osvaldo" in m for m in log.mensagens))
        verificar("NENHUMA mensagem de log contém uma senha",
                  not any(senha in m for m in log.mensagens for senha in (SENHA_DONO, SENHA_MEC, "errada!!")))
    finally:
        logging.getLogger("src").removeHandler(log)
        s.close()
        transacao.rollback()  # desfaz TUDO: o banco volta exatamente como estava
        conexao.close()

    verificar("transação desfeita: a tabela de usuários está idêntica ao que era antes do teste",
              foto_usuarios() == antes)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
