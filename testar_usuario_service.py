"""
Teste do UsuarioService (RF10, tela de Usuários) no PostgreSQL real.

Rode da raiz do projeto, com o venv ativo:
    python testar_usuario_service.py

Mesmo isolamento do testar_autenticacao_service.py: tudo numa transação
desfeita no fim (o banco volta exatamente como estava).
"""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.config.database import engine
from src.persistencia.models import PerfilUsuario, Usuario
from src.servico.autenticacao_service import MAX_TENTATIVAS, AutenticacaoService
from src.servico.excecoes import (
    CredenciaisInvalidasError,
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    UsuarioBloqueadoError,
    ValidacaoError,
)
from src.servico.usuario_service import UsuarioService

engine.echo = False
resultados = []
D, M = PerfilUsuario.DONO, PerfilUsuario.MECANICO
SENHA = "senha-boa-123"


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


def foto_usuarios():
    with Session(engine) as s:
        return [tuple(r) for r in s.execute(select(
            Usuario.id_usuario, Usuario.login, Usuario.senha_hash, Usuario.perfil, Usuario.ativo,
        ).order_by(Usuario.id_usuario)).all()]


def main() -> None:
    antes = foto_usuarios()
    conexao = engine.connect()
    transacao = conexao.begin()
    s = Session(bind=conexao, join_transaction_mode="create_savepoint")
    us, auth = UsuarioService(s), AutenticacaoService(s)
    try:
        s.execute(delete(Usuario))
        s.commit()
        dono = auth.criar_primeiro_usuario("Osvaldo", "osvaldo", SENHA, SENHA)
        A = dono.id_usuario

        print("\n--- Cadastrar ---")
        joao = us.cadastrar("João", "Joao.Silva", SENHA, SENHA, "mecanico")
        verificar("mecânico cadastrado, login em minúsculas", joao.perfil is M and joao.login == "joao.silva")
        verificar("hash, não a senha", joao.senha_hash != SENHA and joao.senha_hash.startswith("$2b$"))
        esperar_erro("login repetido com outras maiúsculas", RegistroDuplicadoError,
                     lambda: us.cadastrar("Outro", "JOAO.SILVA", SENHA, SENHA, M))
        esperar_erro("login curto (2 letras)", ValidacaoError, lambda: us.cadastrar("X", "jo", SENHA, SENHA, M))
        esperar_erro("login com acento", ValidacaoError, lambda: us.cadastrar("X", "joão", SENHA, SENHA, M))
        esperar_erro("perfil inválido", ValidacaoError, lambda: us.cadastrar("X", "xavier", SENHA, SENHA, "chefe"))
        esperar_erro("senha curta", ValidacaoError, lambda: us.cadastrar("X", "xavier", "123", "123", M))
        esperar_erro("senha igual ao login", ValidacaoError, lambda: us.cadastrar("X", "xavier99", "xavier99", "xavier99", M))
        esperar_erro("confirmação diferente", ValidacaoError, lambda: us.cadastrar("X", "xavier", SENHA, SENHA + "!", M))
        verificar("listar traz os 2 usuários", {u.login for u in us.listar()} == {"osvaldo", "joao.silva"})

        print("\n--- Perfil e nome ---")
        joao = us.alterar(joao.id_usuario, "João da Silva", D, A)
        verificar("dono promove mecânico a dono e muda o nome", joao.perfil is D and joao.nome == "João da Silva")
        esperar_erro("dono não altera o PRÓPRIO perfil", OperacaoNaoPermitidaError, lambda: us.alterar(A, "Osvaldo", M, A))
        joao = us.alterar(joao.id_usuario, "João da Silva", M, A)
        verificar("com 2 donos, um rebaixa o outro", joao.perfil is M)
        esperar_erro("rebaixar o ÚLTIMO dono ativo (pedido por outro)", OperacaoNaoPermitidaError,
                     lambda: us.alterar(A, "Osvaldo", M, joao.id_usuario))
        verificar("mudar só o nome do próprio usuário é permitido", us.alterar(A, "Osvaldo Rembold", D, A).nome == "Osvaldo Rembold")
        esperar_erro("nome vazio", ValidacaoError, lambda: us.alterar(A, " ", D, A))

        print("\n--- Ativar e desativar ---")
        esperar_erro("dono não desativa a si mesmo", OperacaoNaoPermitidaError, lambda: us.definir_ativo(A, False, A))
        esperar_erro("ninguém desativa o ÚLTIMO dono ativo", OperacaoNaoPermitidaError,
                     lambda: us.definir_ativo(A, False, joao.id_usuario))
        maria = us.cadastrar("Maria", "maria", SENHA, SENHA, D)
        us.definir_ativo(A, False, maria.id_usuario)
        s.expire_all()
        verificar("com outro dono ativo, um dono pode ser desativado", s.get(Usuario, A).ativo is False)
        esperar_erro("agora a Maria é a última dona ativa", OperacaoNaoPermitidaError,
                     lambda: us.definir_ativo(maria.id_usuario, False, joao.id_usuario))
        esperar_erro("dono desativado não entra", CredenciaisInvalidasError, lambda: auth.autenticar("osvaldo", SENHA))
        us.definir_ativo(A, True, maria.id_usuario)
        verificar("reativado volta a entrar", auth.autenticar("osvaldo", SENHA).id_usuario == A)
        us.definir_ativo(joao.id_usuario, False, A)
        verificar("mecânico desativado pelo dono", us.obter(joao.id_usuario).ativo is False)

        print("\n--- Redefinir senha (e desbloquear) ---")
        us.definir_ativo(joao.id_usuario, True, A)
        for _ in range(MAX_TENTATIVAS):
            try:
                auth.autenticar("joao.silva", "chute-errado")
            except (CredenciaisInvalidasError, UsuarioBloqueadoError):
                pass
        esperar_erro("mecânico bloqueado por errar a senha", UsuarioBloqueadoError, lambda: auth.autenticar("joao.silva", SENHA))
        esperar_erro("nova senha curta", ValidacaoError, lambda: us.redefinir_senha(joao.id_usuario, "curta", "curta"))
        us.redefinir_senha(joao.id_usuario, "nova-senha-456", "nova-senha-456")
        verificar("redefinir a senha desbloqueia e a nova senha entra",
                  auth.autenticar("joao.silva", "nova-senha-456").id_usuario == joao.id_usuario)
        esperar_erro("a senha antiga não entra mais", CredenciaisInvalidasError, lambda: auth.autenticar("joao.silva", SENHA))
        esperar_erro("usuário inexistente", RegistroNaoEncontradoError, lambda: us.redefinir_senha(999999, SENHA, SENHA))
        esperar_erro("ativar usuário inexistente", RegistroNaoEncontradoError, lambda: us.definir_ativo(999999, True, A))

        print("\n--- Última linha de defesa: o banco ---")
        for descricao, campo in (
            ("banco recusa perfil fora da lista", dict(perfil="chefe")),
            ("banco recusa login com maiúscula", dict(login="Maiusculo")),
        ):
            try:
                with s.begin_nested():
                    s.execute(Usuario.__table__.insert().values(
                        nome="X", login=campo.get("login", "xyz"), senha_hash="x" * 60, perfil=campo.get("perfil", "dono")))
                verificar(descricao, False)
            except Exception:  # noqa: BLE001
                verificar(descricao, True)
        try:
            with s.begin_nested():
                s.execute(Usuario.__table__.insert().values(nome="X", login="maria", senha_hash="x" * 60, perfil="dono"))
            verificar("banco recusa login repetido (uq_usuario_login)", False)
        except Exception:  # noqa: BLE001
            verificar("banco recusa login repetido (uq_usuario_login)", True)
    finally:
        s.close()
        transacao.rollback()
        conexao.close()

    verificar("transação desfeita: tabela de usuários idêntica ao que era antes", foto_usuarios() == antes)
    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
