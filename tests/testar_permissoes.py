"""
Teste da AUTORIZAÇÃO (RF10): matriz de permissões + guard dos controllers.

Rode da raiz do projeto, com o venv ativo:
    python testar_permissoes.py

Cria dois usuários de teste GRAVADOS (o guard revalida o usuário no banco
por outra conexão), com login começando em "teste-rf10-", e apaga os dois
no fim. Não altera mais nada.

Cobre:
- a matriz (o que dono e mecânico podem);
- TODO método público de TODO controller está protegido (só o de
  autenticação, por onde se entra, fica de fora);
- cada operação restrita: mecânico é recusado, dono passa;
- custo e margem escondidos do mecânico (o dado nem chega à tela);
- revalidação: desativar ou mudar o perfil vale na próxima operação;
- os DTOs não carregam o hash da senha.
"""
import dataclasses
import inspect
from datetime import date

from sqlalchemy import delete

from src.config.database import engine, get_session
from src.controle import (
    agendamento_controller, cliente_controller, movimentacao_estoque_controller,
    ordem_servico_controller, produto_controller, relatorio_controller, usuario_controller, veiculo_controller,
)
from src.controle.agendamento_controller import AgendamentoController
from src.controle.cliente_controller import ClienteController
from src.controle.movimentacao_estoque_controller import MovimentacaoEstoqueController
from src.controle.notificacao_controller import NotificacaoController
from src.controle.ordem_servico_controller import OrdemServicoController
from src.controle.produto_controller import ProdutoController
from src.controle.relatorio_controller import RelatorioController
from src.controle.sessao import UsuarioLogadoDTO, sessao
from src.controle.usuario_controller import UsuarioController, UsuarioDTO
from src.controle.veiculo_controller import VeiculoController
from src.persistencia.models import PerfilUsuario, Produto, Usuario
from src.servico.excecoes import OperacaoNaoPermitidaError
from src.servico.permissoes import Permissao, permissoes_do_perfil
from src.servico.usuario_service import UsuarioService

engine.echo = False
resultados = []
D, M = PerfilUsuario.DONO, PerfilUsuario.MECANICO
SENHA = "senha-de-teste-rf10"
PRODUTO_TESTE = "Produto Permissão RF10"


def verificar(descricao: str, condicao) -> None:
    resultados.append(bool(condicao))
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}")


def recusado(funcao) -> bool:
    try:
        funcao()
    except OperacaoNaoPermitidaError:
        return True
    return False


def permitido(funcao) -> bool:
    try:
        funcao()
    except OperacaoNaoPermitidaError as erro:
        print(f"      (recusado: {erro})")
        return False
    return True


def limpar() -> None:
    with get_session() as s:
        s.execute(delete(Usuario).where(Usuario.login.like("teste-rf10-%")))
        s.execute(delete(Produto).where(Produto.nome == PRODUTO_TESTE))
        s.commit()


def como_dto(u: Usuario) -> UsuarioLogadoDTO:
    return UsuarioLogadoDTO(u.id_usuario, u.nome, u.login, PerfilUsuario(u.perfil))


def entrar(u: UsuarioLogadoDTO) -> None:
    sessao.entrar(u)


def main() -> None:
    limpar()
    print("\n--- Matriz de permissões (um lugar só: servico/permissoes.py) ---")
    verificar("dono tem todas as permissões", permissoes_do_perfil(D) == frozenset(Permissao))
    verificar("mecânico: clientes, veículos, OS, agendamentos, CONSULTA de produtos e notificações",
              permissoes_do_perfil(M) == {Permissao.CLIENTES, Permissao.VEICULOS, Permissao.ORDENS_SERVICO,
                                         Permissao.AGENDAMENTOS, Permissao.PRODUTOS_CONSULTAR,
                                         Permissao.NOTIFICACOES})

    print("\n--- Todo método público de controller está protegido ---")
    sem_guard = []
    # Descobre TODOS os módulos de src/controle (controller novo não escapa do teste)
    import importlib
    import pkgutil
    import src.controle as pacote
    modulos = [importlib.import_module(f"src.controle.{m.name}") for m in pkgutil.iter_modules(pacote.__path__)]
    verificar("controller de notificações (RF07) está entre os verificados",
              any(m.__name__.endswith("notificacao_controller") for m in modulos))
    for modulo in modulos:
        if modulo.__name__.endswith("autenticacao_controller"):
            continue  # o único sem guard, de propósito (é ele que faz o login)
        for _nome, classe in inspect.getmembers(modulo, inspect.isclass):
            if not _nome.endswith("Controller") or classe.__module__ != modulo.__name__:
                continue
            for nome, atributo in vars(classe).items():
                if not nome.startswith("_") and inspect.isfunction(atributo) and not hasattr(atributo, "permissao"):
                    sem_guard.append(f"{classe.__name__}.{nome}")
    verificar(f"nenhum método público sem guard {sem_guard or ''}", not sem_guard)

    print("\n--- DTOs sem o hash da senha ---")
    verificar("UsuarioLogadoDTO não tem senha nem hash",
              not any("senha" in f.name or "hash" in f.name for f in dataclasses.fields(UsuarioLogadoDTO)))
    verificar("UsuarioDTO não tem senha nem hash",
              not any("senha" in f.name or "hash" in f.name for f in dataclasses.fields(UsuarioDTO)))

    with get_session() as s:
        us = UsuarioService(s)
        dono = como_dto(us.cadastrar("Dono Teste", "teste-rf10-dono", SENHA, SENHA, D))
        mec = como_dto(us.cadastrar("Mecânico Teste", "teste-rf10-mec", SENHA, SENHA, M))
    try:
        sessao.sair()
        print("\n--- Sem login ---")
        verificar("sem login, até listar clientes é recusado", recusado(lambda: ClienteController().listar_pagina()))

        print("\n--- Mecânico: o que ele PODE ---")
        entrar(mec)
        hoje = date.today()
        for descricao, funcao in (
            ("listar clientes", lambda: ClienteController().listar_pagina()),
            ("listar veículos", lambda: VeiculoController().listar_pagina()),
            ("listar ordens de serviço", lambda: OrdemServicoController().listar_pagina()),
            ("ver a agenda do dia", lambda: AgendamentoController().agenda_do_dia(hoje)),
            ("consultar produtos", lambda: ProdutoController().listar_pagina()),
            ("ver notificações (RF07)", lambda: NotificacaoController().listar_pagina()),
        ):
            verificar(f"mecânico pode {descricao}", permitido(funcao))

        print("\n--- Mecânico: o que ele NÃO pode (o controller recusa mesmo sem a tela) ---")
        for descricao, funcao in (
            ("cadastrar produto", lambda: ProdutoController().cadastrar(PRODUTO_TESTE)),
            ("editar produto", lambda: ProdutoController().atualizar(1, "X")),
            ("excluir produto", lambda: ProdutoController().excluir(1)),
            ("listar o estoque", lambda: MovimentacaoEstoqueController().listar_pagina()),
            ("registrar movimentação", lambda: MovimentacaoEstoqueController().registrar(1, None, 1)),
            ("gerar relatório", lambda: RelatorioController().gerar(hoje, hoje)),
            ("listar usuários", lambda: UsuarioController().listar()),
            ("criar usuário", lambda: UsuarioController().cadastrar("X", "teste-rf10-x", SENHA, SENHA, D)),
            ("se promover a dono", lambda: UsuarioController().alterar(mec.id_usuario, "Mecânico Teste", D)),
        ):
            verificar(f"mecânico NÃO pode {descricao}", recusado(funcao))

        print("\n--- Mecânico não vê custo nem margem ---")
        pagina = ProdutoController().listar_pagina()
        verificar("produtos: custo, sugerido e margem vazios; preço de venda visível",
                  all(p.valor_unitario is None and p.margem is None and p.preco_sugerido is None for p in pagina.itens)
                  and any(p.preco_venda is not None for p in pagina.itens))
        verificar("OS: lista de peças sem custo",
                  all(p.valor_unitario is None for p in OrdemServicoController().listar_produtos()))
        itens = [i for o in OrdemServicoController().listar_pagina().itens for i in o.itens]
        verificar("OS: peças gravadas sem custo", all(i.custo_unitario is None for i in itens))

        print("\n--- Dono: as mesmas operações passam ---")
        entrar(dono)
        for descricao, funcao in (
            ("listar o estoque", lambda: MovimentacaoEstoqueController().listar_pagina()),
            ("gerar relatório", lambda: RelatorioController().gerar(hoje, hoje)),
            ("listar usuários", lambda: UsuarioController().listar()),
            ("cadastrar e excluir produto",
             lambda: ProdutoController().excluir(ProdutoController().cadastrar(PRODUTO_TESTE).id_produto)),
        ):
            verificar(f"dono pode {descricao}", permitido(funcao))
        verificar("dono vê o custo dos produtos",
                  any(p.valor_unitario is not None for p in ProdutoController().listar_pagina().itens))

        print("\n--- Revalidação no banco a cada operação ---")
        entrar(mec)
        with get_session() as s:
            UsuarioService(s).alterar(mec.id_usuario, "Mecânico Teste", D, dono.id_usuario)
        verificar("promovido a dono: já pode gerar relatório (vale o perfil ATUAL)",
                  permitido(lambda: RelatorioController().gerar(hoje, hoje)))
        with get_session() as s:
            UsuarioService(s).alterar(mec.id_usuario, "Mecânico Teste", M, dono.id_usuario)
        sessao.entrar(UsuarioLogadoDTO(mec.id_usuario, mec.nome, mec.login, D))  # sessão antiga dizendo "dono"
        erro = None
        try:
            RelatorioController().gerar(hoje, hoje)
        except OperacaoNaoPermitidaError as e:
            erro = e
        verificar("rebaixado com a sessão antiga: recusado com 'Suas permissões mudaram'",
                  erro is not None and "permissões mudaram" in str(erro))
        entrar(mec)
        with get_session() as s:
            UsuarioService(s).definir_ativo(mec.id_usuario, False, dono.id_usuario)
        erro = None
        try:
            ClienteController().listar_pagina()
        except OperacaoNaoPermitidaError as e:
            erro = e
        verificar("desativado: a próxima ação é recusada ('foi desativado')", erro is not None and "desativado" in str(erro))

        print("\n--- Sair ---")
        sessao.sair()
        verificar("depois de sair não há usuário na sessão e nada é permitido",
                  sessao.usuario is None and not sessao.pode(Permissao.CLIENTES))
        sessao.entrar_sistema()
        verificar("sessão interna (diagnóstico/testes) tem perfil de dono e não existe no banco",
                  sessao.usuario.sistema and sessao.pode(Permissao.USUARIOS))
        sessao.sair()
    finally:
        sessao.sair()
        limpar()

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
