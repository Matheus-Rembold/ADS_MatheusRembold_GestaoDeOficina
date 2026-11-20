"""
Teste do RF07 (Notificações pelo WhatsApp) contra o PostgreSQL real.

Rode da raiz do projeto, com o venv ativo:
    python -m tests.testar_notificacao_service

PRÉ-REQUISITO: banco/migracoes/07_migrar_notificacao.sql rodado (ou banco criado pelo
banco/BancoDeDados.sql atualizado).

O teste cria clientes, veículos, OS e agendamentos próprios (CPFs e placas
de teste, datas bem no futuro) e apaga tudo no fim (bloco finally). Os
números de notificações são comparados antes/depois, nunca pelo total do banco.
"""
from datetime import date, datetime, timedelta
from urllib.parse import unquote

from sqlalchemy import delete, select

from src.config.database import engine, get_session
from src.controle.sessao import sessao
from src.integracao.whatsapp import ProvedorWaMe, formatar_celular, normalizar_celular
from src.persistencia.models import (
    Agendamento, Cliente, Notificacao, OrdemServico, StatusEnvio, StatusOrdemServico,
    TipoNotificacao, Veiculo,
)
from src.servico import notificacao_service as ns
from src.servico.agendamento_service import AgendamentoService
from src.servico.cliente_service import ClienteService
from src.servico.excecoes import (
    OperacaoNaoPermitidaError, RegistroNaoEncontradoError, ValidacaoError,
)
from src.servico.notificacao_service import (
    CANCELADAS, ENVIADAS, MOTIVO_SEM_ACEITE, PARA_ENVIAR, PROXIMAS, NotificacaoService,
    data_lembrete, data_pos_venda, mensagem_lembrete,
)
from src.servico.ordem_servico_service import OrdemServicoService

engine.echo = False

CPFS = ["999.999.971-98", "999.999.972-79", "999.999.973-50"]  # válidos (dígitos verificadores)
PLACAS = ["TNT0A01", "TNT0A02", "TNT0A03"]
DIA = date.today() + timedelta(days=500)  # agenda bem longe dos dados reais

resultados = []


def verificar(descricao: str, condicao: bool) -> None:
    resultados.append(condicao)
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}")


def esperar_erro(descricao: str, tipo_esperado, funcao):
    try:
        funcao()
    except tipo_esperado as erro:
        verificar(f"{descricao} -> {tipo_esperado.__name__}: {str(erro).splitlines()[0]}", True)
        return erro
    except Exception as erro:  # noqa: BLE001
        verificar(f"{descricao} -> erro inesperado {type(erro).__name__}: {erro}", False)
    else:
        verificar(f"{descricao} -> deveria ter levantado {tipo_esperado.__name__}", False)
    return None


def limpar() -> None:
    with get_session() as s:
        ids_c = list(s.scalars(select(Cliente.id_cliente).where(Cliente.cpf.in_(CPFS))))
        if ids_c:
            ids_os = select(OrdemServico.id_ordem_servico).where(OrdemServico.id_cliente.in_(ids_c))
            s.execute(delete(Notificacao).where(Notificacao.id_ordem_servico.in_(ids_os)))
            s.execute(delete(Agendamento).where(Agendamento.id_cliente.in_(ids_c)))  # CASCADE nos lembretes
            s.execute(delete(OrdemServico).where(OrdemServico.id_cliente.in_(ids_c)))
            s.execute(delete(Veiculo).where(Veiculo.id_cliente.in_(ids_c)))
            s.execute(delete(Cliente).where(Cliente.id_cliente.in_(ids_c)))
        s.commit()


class Relogio:
    """Relógio controlado pelo teste."""

    def __init__(self, agora: datetime) -> None:
        self.agora = agora

    def __call__(self) -> datetime:
        return self.agora


def notif(s, **filtro) -> Notificacao:
    s.expire_all()
    return s.scalars(select(Notificacao).filter_by(**filtro)).one()


def testar_funcoes_puras() -> None:
    print("\n1) Funções puras (celular, link, datas, mensagem)")
    verificar("'(54) 99999-1234' -> 5554999991234", normalizar_celular("(54) 99999-1234") == "5554999991234")
    verificar("'+55 54 99999-1234' -> 5554999991234", normalizar_celular("+55 54 99999-1234") == "5554999991234")
    verificar("'054 99999 1234' -> 5554999991234", normalizar_celular("054 99999 1234") == "5554999991234")
    verificar("fixo '(54) 3333-1234' -> None", normalizar_celular("(54) 3333-1234") is None)
    verificar("sem DDD '99999-1234' -> None", normalizar_celular("99999-1234") is None)
    verificar("DDD inválido '(05) 99999-1234' -> None", normalizar_celular("(05) 99999-1234") is None)
    verificar("vazio/None -> None", normalizar_celular("") is None and normalizar_celular(None) is None)
    verificar("formatar 5554999991234 -> (54) 99999-1234", formatar_celular("5554999991234") == "(54) 99999-1234")
    texto = "Olá, João! Tudo bem?\nOS nº 12 & peças"
    link = ProvedorWaMe().preparar("5554999991234", texto)
    verificar("link começa com https://wa.me/5554999991234?text=", link.startswith("https://wa.me/5554999991234?text="))
    verificar("texto do link codificado (sem espaço, \\n, &) e reversível",
              " " not in link and "\n" not in link and "&" not in link
              and unquote(link.split("text=")[1]) == texto)
    verificar("pós-venda = entrega + 7 dias", data_pos_venda(datetime(2026, 11, 10, 15, 0)) == date(2026, 11, 17))
    hoje = date(2026, 11, 15)
    verificar("lembrete = véspera", data_lembrete(datetime(2026, 11, 20, 8), hoje) == date(2026, 11, 19))
    verificar("lembrete de amanhã = hoje", data_lembrete(datetime(2026, 11, 16, 8), hoje) == hoje)
    verificar("lembrete de hoje = hoje", data_lembrete(datetime(2026, 11, 15, 18), hoje) == hoje)
    from types import SimpleNamespace as N
    os_sem_placa = N(id_ordem_servico=7, tipo_servico="Revisão", cliente=N(nome="Ana Souza"),
                     veiculo=N(modelo="Trator", placa=None))
    m = ns.mensagem_pos_venda(os_sem_placa)
    verificar("veículo sem placa: mensagem diz só o modelo, sem '(None)'",
              "seu Trator saiu daqui" in m and "None" not in m)


def main() -> None:
    sessao.entrar_sistema()
    limpar()
    testar_funcoes_puras()
    ns_nome_antigo = ns.os.environ.pop("OFICINA_NOME", None)
    try:
        with get_session() as s:
            c1 = Cliente(nome="joão notificação teste", cpf=CPFS[0], contato="(54) 99999-0101")
            c2 = Cliente(nome="Maria Sem Mensagem", cpf=CPFS[1], contato="54999990102", aceita_mensagens=False)
            c3 = Cliente(nome="Pedro Telefone Fixo", cpf=CPFS[2], contato="(54) 3333-0103")
            s.add_all([c1, c2, c3])
            s.flush()
            v1 = Veiculo(id_cliente=c1.id_cliente, modelo="Gol", marca="VW", placa=PLACAS[0])
            v2 = Veiculo(id_cliente=c2.id_cliente, modelo="Uno", marca="Fiat", placa=PLACAS[1])
            v3 = Veiculo(id_cliente=c3.id_cliente, modelo="Ka", marca="Ford", placa=PLACAS[2])
            s.add_all([v1, v2, v3])
            s.commit()
            ids = dict(c1=c1.id_cliente, c2=c2.id_cliente, c3=c3.id_cliente,
                       v1=v1.id_veiculo, v2=v2.id_veiculo, v3=v3.id_veiculo)

        # --------------------------------------------------------------
        print("\n2) Pós-venda criada ao entregar a OS")
        with get_session() as s:
            servico_os = OrdemServicoService(s)

            def os_entregue(id_c, id_v):
                o = servico_os.cadastrar(id_c, id_v, 1000, "Barulho", "Troca de óleo")
                for st in ("andamento", "pronto", "aguardando_pagamento"):
                    servico_os.alterar_status(o.id_ordem_servico, st)
                verificar("antes de entregar: sem notificação",
                          s.scalars(select(Notificacao).filter_by(id_ordem_servico=o.id_ordem_servico)).first() is None)
                servico_os.alterar_status(o.id_ordem_servico, "entregue")
                return o.id_ordem_servico

            os1 = os_entregue(ids["c1"], ids["v1"])
            n1 = notif(s, id_ordem_servico=os1)
            entregue = s.get(OrdemServico, os1).entregue_em
            verificar("tipo pós-venda, pendente", n1.tipo is TipoNotificacao.POS_VENDA and n1.status_envio is StatusEnvio.PENDENTE)
            verificar("prevista = entrega + 7 dias", n1.data_envio_prevista == entregue.date() + timedelta(days=7))
            verificar("sem agendamento e sem motivo", n1.id_agendamento is None and n1.motivo_cancelamento is None)

            os2 = os_entregue(ids["c2"], ids["v2"])
            n2 = notif(s, id_ordem_servico=os2)
            verificar("cliente que não aceita: nasce cancelada com o motivo",
                      n2.status_envio is StatusEnvio.CANCELADO and n2.motivo_cancelamento == MOTIVO_SEM_ACEITE)
            os3 = os_entregue(ids["c3"], ids["v3"])
            id_n1, id_n2, id_n3 = n1.id_notificacao, n2.id_notificacao, notif(s, id_ordem_servico=os3).id_notificacao

        # --------------------------------------------------------------
        print("\n3) Abas, atraso e impedimentos (relógio controlado)")
        hoje = date.today()
        with get_session() as s:
            agora7 = Relogio(datetime.combine(hoje + timedelta(days=7), datetime.min.time()).replace(hour=9))
            serv7 = NotificacaoService(s, relogio=agora7)
            serv_hoje = NotificacaoService(s)
            p_hoje = serv_hoje.listar_pagina(PROXIMAS, "notificação teste")
            verificar("hoje: pós-venda do João em 'Próximas'", any(n.id_notificacao == id_n1 for n in p_hoje.itens))
            verificar("hoje: não está em 'Para enviar'",
                      all(n.id_notificacao != id_n1 for n in serv_hoje.listar_pagina(PARA_ENVIAR, "notificação teste").itens))
            p7 = serv7.listar_pagina(PARA_ENVIAR, "notificação teste")
            verificar("daqui a 7 dias: em 'Para enviar'", [n.id_notificacao for n in p7.itens] == [id_n1])
            verificar("resumo conta por aba (busca pelo nome)", p7.resumo[PARA_ENVIAR] == 1 and p7.resumo[PROXIMAS] == 0)
            verificar("busca pela placa encontra", serv7.listar_pagina(PARA_ENVIAR, PLACAS[0].lower()).total == 1)
            verificar("'Canceladas' tem a da Maria", any(n.id_notificacao == id_n2 for n in serv7.listar_pagina(CANCELADAS, "Maria Sem").itens))
            n = serv7.obter(id_n1)
            verificar("não atrasada no dia previsto", not serv7.atrasada(n, agora7().date()))
            verificar("atrasada um dia depois", serv7.atrasada(n, agora7().date() + timedelta(days=1)))
            antes = serv7.contar_para_enviar()
            agora9 = Relogio(agora7.agora + timedelta(days=2))
            verificar("atrasada continua em 'Para enviar' (não expira)",
                      NotificacaoService(s, relogio=agora9).listar_pagina(PARA_ENVIAR, "notificação teste").total == 1)
            verificar("contar_para_enviar inclui a do João", antes >= 1)
            verificar("impedimento: nenhum para o João", serv7.impedimento(n) is None)
            verificar("impedimento: telefone fixo do Pedro",
                      "celular válido" in (serv7.impedimento(serv7.obter(id_n3)) or ""))
            verificar("impedimento: Maria cancelada", serv7.impedimento(serv7.obter(id_n2)) is not None)
            esperar_erro("aba inválida", ValidacaoError, lambda: serv7.listar_pagina("xyz"))

            # ----------------------------------------------------------
            print("\n4) Mensagem e link")
            msg = serv7.mensagem_padrao(n)
            verificar("mensagem cita primeiro nome capitalizado, veículo, placa e OS",
                      msg.startswith("Olá, João!") and "Gol (TNT0A01)" in msg and f"OS nº {os1}" in msg
                      and "troca de óleo" in msg)
            verificar("sem OFICINA_NOME: 'Aqui é da oficina.'", "Aqui é da oficina." in msg)
            ns.os.environ["OFICINA_NOME"] = "Camaro Motors"
            verificar("com OFICINA_NOME: 'Aqui é da oficina Camaro Motors.'",
                      "Aqui é da oficina Camaro Motors." in serv7.mensagem_padrao(n))
            ns.os.environ.pop("OFICINA_NOME")
            env = serv7.preparar_envio(id_n1)
            verificar("preparar_envio: número internacional", env.numero == "5554999990101")
            verificar("preparar_envio: link wa.me com a mensagem", env.endereco.startswith("https://wa.me/5554999990101?text=")
                      and unquote(env.endereco.split("text=")[1]) == msg)
            env2 = serv7.preparar_envio(id_n1, "  Texto editado pela oficina  ")
            verificar("mensagem editada vale (sem espaços nas pontas)", env2.mensagem == "Texto editado pela oficina")
            esperar_erro("mensagem vazia", ValidacaoError, lambda: serv7.preparar_envio(id_n1, "   "))
            esperar_erro("mensagem gigante", ValidacaoError, lambda: serv7.preparar_envio(id_n1, "x" * 2001))
            esperar_erro("preparar com telefone fixo", OperacaoNaoPermitidaError, lambda: serv7.preparar_envio(id_n3))
            esperar_erro("preparar de cliente que recusou", OperacaoNaoPermitidaError, lambda: serv7.preparar_envio(id_n2))
            esperar_erro("notificação inexistente", RegistroNaoEncontradoError, lambda: serv7.preparar_envio(-1))
            verificar("preparar não grava nada", serv7.obter(id_n1).status_envio is StatusEnvio.PENDENTE)

            # ----------------------------------------------------------
            print("\n5) Confirmar envio e cancelar")
            r = serv7.confirmar_envio(id_n1, env2.mensagem)
            verificar("enviada, com data e texto gravados",
                      r.status_envio is StatusEnvio.ENVIADO and r.data_envio_real == agora7.agora
                      and r.mensagem == "Texto editado pela oficina")
            verificar("texto() devolve o enviado", serv7.texto(r) == "Texto editado pela oficina")
            verificar("aparece em 'Enviadas'", serv7.listar_pagina(ENVIADAS, "notificação teste").total == 1)
            esperar_erro("confirmar de novo", OperacaoNaoPermitidaError, lambda: serv7.confirmar_envio(id_n1, "x"))
            esperar_erro("cancelar enviada", OperacaoNaoPermitidaError, lambda: serv7.cancelar(id_n1))
            esperar_erro("motivo longo demais", ValidacaoError, lambda: serv7.cancelar(id_n3, "x" * 151))
            c = serv7.cancelar(id_n3)
            verificar("cancelar sem motivo usa o padrão", c.status_envio is StatusEnvio.CANCELADO
                      and c.motivo_cancelamento == ns.MOTIVO_PADRAO)

        # --------------------------------------------------------------
        print("\n6) Lembrete de agendamento")
        with get_session() as s:
            ag_srv = AgendamentoService(s)
            a1 = ag_srv.criar(ids["c1"], ids["v1"], "Revisão", datetime.combine(DIA, datetime.min.time()).replace(hour=8), 1)
            l1 = notif(s, id_agendamento=a1.id_agendamento)
            verificar("lembrete criado na véspera, pendente",
                      l1.tipo is TipoNotificacao.LEMBRETE_AGENDAMENTO and l1.status_envio is StatusEnvio.PENDENTE
                      and l1.data_envio_prevista == DIA - timedelta(days=1) and l1.id_ordem_servico is None)
            novo = datetime.combine(DIA + timedelta(days=3), datetime.min.time()).replace(hour=10)
            ag_srv.atualizar(a1.id_agendamento, ids["c1"], ids["v1"], "Revisão", novo, 1)
            verificar("mudar o horário remarca o lembrete",
                      notif(s, id_agendamento=a1.id_agendamento).data_envio_prevista == novo.date() - timedelta(days=1))
            serv = NotificacaoService(s, relogio=Relogio(novo - timedelta(days=1)))
            m = serv.mensagem_padrao(notif(s, id_agendamento=a1.id_agendamento))
            verificar("mensagem do lembrete diz 'amanhã', hora e placa",
                      "amanhã" in m and "às 10:00" in m and "TNT0A01" in m and "revisão" in m)
            verificar("lembrete para depois de amanhã usa 'na/no <dia>'",
                      " na " in mensagem_lembrete(s.get(Agendamento, a1.id_agendamento), novo.date() - timedelta(days=5))
                      or " no " in mensagem_lembrete(s.get(Agendamento, a1.id_agendamento), novo.date() - timedelta(days=5)))
            depois = NotificacaoService(s, relogio=Relogio(novo + timedelta(hours=1)))
            verificar("horário já passou: não pode enviar (impedimento)",
                      "já passou" in (depois.impedimento(notif(s, id_agendamento=a1.id_agendamento)) or ""))

            ag_srv.cancelar(a1.id_agendamento)
            l1 = notif(s, id_agendamento=a1.id_agendamento)
            verificar("cancelar agendamento cancela o lembrete",
                      l1.status_envio is StatusEnvio.CANCELADO and l1.motivo_cancelamento == ns.MOTIVO_AGENDAMENTO_CANCELADO)

            a2 = ag_srv.criar(ids["c1"], ids["v1"], "Alinhamento", datetime.combine(DIA, datetime.min.time()).replace(hour=14), 1)
            ag_srv.converter_em_os(a2.id_agendamento, 1200, "Puxando")
            l2 = notif(s, id_agendamento=a2.id_agendamento)
            verificar("converter em OS cancela o lembrete",
                      l2.status_envio is StatusEnvio.CANCELADO and l2.motivo_cancelamento == ns.MOTIVO_AGENDAMENTO_CONVERTIDO)

            a3 = ag_srv.criar(ids["c2"], ids["v2"], "Freios", datetime.combine(DIA, datetime.min.time()).replace(hour=16), 1)
            l3 = notif(s, id_agendamento=a3.id_agendamento)
            verificar("lembrete de quem não aceita nasce cancelado", l3.status_envio is StatusEnvio.CANCELADO
                      and l3.motivo_cancelamento == MOTIVO_SEM_ACEITE)
            id_a3 = a3.id_agendamento

        # --------------------------------------------------------------
        print("\n7) Aceite do cliente (LGPD)")
        with get_session() as s:
            cs = ClienteService(s)
            c2 = s.get(Cliente, ids["c2"])
            cs.atualizar(ids["c2"], c2.nome, c2.cpf, c2.contato, None, None, True)
            verificar("voltar a aceitar reativa o lembrete futuro",
                      notif(s, id_agendamento=id_a3).status_envio is StatusEnvio.PENDENTE)
            verificar("e reativa a pós-venda cancelada por recusa",
                      notif(s, id_ordem_servico=os2).status_envio is StatusEnvio.PENDENTE)
            cs.atualizar(ids["c2"], c2.nome, c2.cpf, c2.contato, None, None, False)
            verificar("recusar cancela as pendentes do cliente",
                      notif(s, id_agendamento=id_a3).status_envio is StatusEnvio.CANCELADO
                      and notif(s, id_ordem_servico=os2).motivo_cancelamento == MOTIVO_SEM_ACEITE)
            verificar("aceite gravado no cliente", s.get(Cliente, ids["c2"]).aceita_mensagens is False)
            c1 = s.get(Cliente, ids["c1"])
            verificar("recusar não mexe em notificação já enviada do João",
                      cs.atualizar(ids["c1"], c1.nome, c1.cpf, c1.contato, None, None, False) is not None
                      and notif(s, id_ordem_servico=os1).status_envio is StatusEnvio.ENVIADO)

        # --------------------------------------------------------------
        print("\n8) Banco: constraints do RF07")
        with engine.connect() as con:
            from sqlalchemy import text
            from sqlalchemy.exc import IntegrityError
            for desc, sql in [
                ("pós-venda sem OS", "INSERT INTO notificacao (tipo) VALUES ('pos_venda')"),
                ("lembrete com OS", f"INSERT INTO notificacao (tipo, id_ordem_servico) VALUES ('lembrete_agendamento', {os3})"),
                ("tipo inválido", f"INSERT INTO notificacao (tipo, id_ordem_servico) VALUES ('sms', {os3})"),
                ("status inválido", f"INSERT INTO notificacao (status_envio, id_ordem_servico) VALUES ('lida', {os3})"),
                ("duas notificações para a mesma OS", f"INSERT INTO notificacao (id_ordem_servico) VALUES ({os3})"),
            ]:
                tr = con.begin()
                try:
                    con.execute(text(sql))
                    verificar(f"banco recusa {desc}", False)
                except IntegrityError:
                    verificar(f"banco recusa {desc}", True)
                finally:
                    tr.rollback()
            tr = con.begin()
            con.execute(text(f"DELETE FROM agendamento WHERE id_agendamento = {id_a3}"))
            sobrou = con.execute(text(f"SELECT count(*) FROM notificacao WHERE id_agendamento = {id_a3}")).scalar()
            verificar("apagar agendamento apaga o lembrete (ON DELETE CASCADE)", sobrou == 0)
            tr.rollback()
    finally:
        limpar()
        if ns_nome_antigo is not None:
            ns.os.environ["OFICINA_NOME"] = ns_nome_antigo
        with get_session() as s:
            resto = s.scalars(select(Cliente).where(Cliente.cpf.in_(CPFS))).first()
            verificar("limpeza: nada do teste ficou no banco", resto is None)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")
    raise SystemExit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
