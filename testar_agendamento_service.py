"""
Teste manual do AgendamentoService contra o banco real (RF05 - Agendamentos).

Rode da raiz do projeto, com o venv ativo:
    python testar_agendamento_service.py

PRÉ-REQUISITO: rodar uma vez o script migrar_agendamento.sql no pgAdmin
(ou criar o banco com o BancoDeDadods.sql atualizado).

ATENÇÃO: o Service FAZ commit. Por isso este script cria clientes, veículos,
agendamentos e OS de teste (em datas bem distantes, para não esbarrar nos seus
agendamentos reais) e, no final (bloco finally), apaga tudo o que criou.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from src.config.database import SessionLocal, engine, get_session
from src.persistencia.models import (
    Agendamento, Cliente, OrdemServico, StatusAgendamento, StatusOrdemServico, Veiculo,
)
from src.servico.agendamento_service import AgendamentoService
from src.servico.excecoes import (
    OperacaoNaoPermitidaError, RegistroNaoEncontradoError, ValidacaoError,
)
from src.servico.ordem_servico_service import OrdemServicoService

engine.echo = False

S = StatusAgendamento
CPFS = ["999.999.998-01", "999.999.998-02", "999.999.998-03"]
PLACAS = ["TAG0A01", "TAG0A02", "TAG0A03", "TAG0A04"]
DIA = date.today() + timedelta(days=400)  # bem longe: não esbarra em agendamentos reais


def hora(h: int, m: int = 0, dia: date = DIA) -> datetime:
    return datetime(dia.year, dia.month, dia.day, h, m)


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
    except Exception as erro:
        verificar(f"{descricao} -> erro inesperado {type(erro).__name__}: {erro}", False)
    else:
        verificar(f"{descricao} -> deveria ter levantado {tipo_esperado.__name__}", False)
    return None


def limpar() -> None:
    with get_session() as s:
        ids_c = list(s.scalars(select(Cliente.id_cliente).where(Cliente.cpf.in_(CPFS))))
        if ids_c:
            s.execute(delete(Agendamento).where(Agendamento.id_cliente.in_(ids_c)))
            s.execute(delete(OrdemServico).where(OrdemServico.id_cliente.in_(ids_c)))
            s.execute(delete(Veiculo).where(Veiculo.id_cliente.in_(ids_c)))
            s.execute(delete(Cliente).where(Cliente.id_cliente.in_(ids_c)))
        s.commit()


def main() -> None:
    limpar()
    with get_session() as s0:
        ag_antes = s0.scalar(select(func.count()).select_from(Agendamento))
        os_antes = s0.scalar(select(func.count()).select_from(OrdemServico))

    with get_session() as session:
        servico = AgendamentoService(session)
        try:
            c1 = Cliente(nome="Cliente Agenda Um", cpf=CPFS[0], contato="54999990011")
            c2 = Cliente(nome="Cliente Agenda Dois", cpf=CPFS[1], contato="54999990012")
            c3 = Cliente(nome="Cliente Agenda Tres", cpf=CPFS[2], contato="54999990013")
            session.add_all([c1, c2, c3])
            session.flush()
            v1 = Veiculo(id_cliente=c1.id_cliente, modelo="Modelo A", marca="M", placa=PLACAS[0])
            v1b = Veiculo(id_cliente=c1.id_cliente, modelo="Modelo A2", marca="M", placa=PLACAS[3])
            v2 = Veiculo(id_cliente=c2.id_cliente, modelo="Modelo B", marca="M", placa=PLACAS[1])
            v3 = Veiculo(id_cliente=c3.id_cliente, modelo="Modelo C", marca="M", placa=PLACAS[2])
            session.add_all([v1, v1b, v2, v3])
            session.commit()
            C1, C2, C3 = c1.id_cliente, c2.id_cliente, c3.id_cliente
            V1, V1B, V2, V3 = v1.id_veiculo, v1b.id_veiculo, v2.id_veiculo, v3.id_veiculo

            print("\n--- Validações ---")
            e = esperar_erro("tudo vazio", ValidacaoError, lambda: servico.criar(None, None, "", None, None))
            verificar("   lista os 5 campos obrigatórios", e is not None and len(e.erros) == 5)
            esperar_erro("data no passado", ValidacaoError,
                         lambda: servico.criar(C1, V1, "Revisão", datetime.now() - timedelta(hours=2), 1))
            esperar_erro("duração zero", ValidacaoError, lambda: servico.criar(C1, V1, "Revisão", hora(8), 0))
            esperar_erro("duração negativa", ValidacaoError, lambda: servico.criar(C1, V1, "Revisão", hora(8), -1))
            esperar_erro("duração acima de 12 h", ValidacaoError, lambda: servico.criar(C1, V1, "Revisão", hora(8), 13))
            esperar_erro("duração texto", ValidacaoError, lambda: servico.criar(C1, V1, "Revisão", hora(8), "2h"))
            esperar_erro("data como texto", ValidacaoError, lambda: servico.criar(C1, V1, "Revisão", "2030-01-01", 1))
            esperar_erro("tipo de serviço longo", ValidacaoError, lambda: servico.criar(C1, V1, "x" * 151, hora(8), 1))
            esperar_erro("veículo de outro cliente", ValidacaoError, lambda: servico.criar(C1, V2, "Revisão", hora(8), 1))
            esperar_erro("cliente inexistente", ValidacaoError, lambda: servico.criar(99999999, V1, "Revisão", hora(8), 1))
            esperar_erro("veículo inexistente", ValidacaoError, lambda: servico.criar(C1, 99999999, "Revisão", hora(8), 1))
            verificar("nada foi criado pelas tentativas inválidas",
                      session.scalar(select(func.count()).select_from(Agendamento).where(Agendamento.id_cliente.in_([C1, C2, C3]))) == 0)

            print("\n--- Criar ---")
            a = servico.criar(C1, V1, "  Troca   de óleo ", hora(9), Decimal("2"))  # 09:00-11:00
            verificar("criado como 'agendado'", a.status is S.AGENDADO and a.id_ordem_servico is None)
            verificar("tipo de serviço normalizado", a.tipo_servico == "Troca de óleo")
            verificar("término previsto = início + duração (11:00)", a.termino_previsto == hora(11))
            b = servico.criar(C2, V2, "Freios", hora(9), 1)  # 09:00-10:00
            verificar("segundo serviço no MESMO horário é permitido (limite = 2)", b.status is S.AGENDADO)
            diag = servico.criar(C3, V3, "Diagnóstico", hora(15), Decimal("1.5"))
            verificar("duração 1,5 h gera término 16:30", diag.termino_previsto == hora(16, 30))

            print("\n--- Limite de 2 serviços ao mesmo tempo ---")
            erro = esperar_erro("terceiro serviço sobreposto (09:30-10:30)", OperacaoNaoPermitidaError,
                                lambda: servico.criar(C3, V3, "Alinhamento", hora(9, 30), 1))
            verificar("   mensagem diz que o horário está lotado", erro is not None and "lotado" in str(erro))
            esperar_erro("terceiro serviço exatamente no mesmo horário", OperacaoNaoPermitidaError,
                         lambda: servico.criar(C3, V3, "Alinhamento", hora(9), 1))
            esperar_erro("terceiro começando antes e entrando no horário lotado (08:30-09:30)", OperacaoNaoPermitidaError,
                         lambda: servico.criar(C3, V3, "Alinhamento", hora(8, 30), 1))
            c_ok = servico.criar(C3, V3, "Alinhamento", hora(10), 1)  # só A ocupa 10-11
            verificar("10:00-11:00 tem vaga (B já terminou às 10:00)", c_ok.status is S.AGENDADO)
            servico.cancelar(c_ok.id_agendamento)
            verificar("começar exatamente quando outro termina não conta como conflito",
                      servico.criar(C3, V3, "Alinhamento", hora(11), 1).termino_previsto == hora(12))
            esperar_erro("mesmo veículo sobreposto", OperacaoNaoPermitidaError,
                         lambda: servico.criar(C1, V1, "Outro serviço", hora(10), 1))
            ok_outro_veic = servico.criar(C1, V1B, "Outro carro do mesmo cliente", hora(12), 1)
            verificar("mesmo cliente, outro veículo, horário livre: permitido", ok_outro_veic.status is S.AGENDADO)

            print("\n--- Cancelar libera o horário (HU15) ---")
            b2 = servico.cancelar(b.id_agendamento)
            verificar("agendamento cancelado", b2.status is S.CANCELADO)
            liberou = servico.criar(C3, V3, "Alinhamento", hora(9, 30), 1)
            verificar("agora o horário 09:30 tem vaga", liberou.status is S.AGENDADO)
            esperar_erro("cancelar de novo", OperacaoNaoPermitidaError, lambda: servico.cancelar(b.id_agendamento))
            esperar_erro("cancelar inexistente", RegistroNaoEncontradoError, lambda: servico.cancelar(99999999))
            esperar_erro("editar cancelado", OperacaoNaoPermitidaError,
                         lambda: servico.atualizar(b.id_agendamento, C2, V2, "Freios", hora(14), 1))

            print("\n--- Editar ---")
            a2 = servico.atualizar(a.id_agendamento, C1, V1, "Troca de óleo e filtro", hora(9), Decimal("2"))
            verificar("editar sem mudar horário não conflita consigo mesmo", a2.tipo_servico == "Troca de óleo e filtro")
            a3 = servico.atualizar(a.id_agendamento, C1, V1, "Troca de óleo e filtro", hora(9), Decimal("3"))
            verificar("aumentar a duração para 3 h (término 12:00)", a3.termino_previsto == hora(12))
            # liberou(09:30-10:30) + a(9-12) = 2 ; mover o diagnóstico 'Diagnóstico' (15:00) para 09:45 -> 3 simultâneos
            erro = esperar_erro("mover para horário lotado", OperacaoNaoPermitidaError,
                                lambda: servico.atualizar(ok_outro_veic.id_agendamento, C1, V1B, "Outro carro do mesmo cliente", hora(9, 45), 1))
            verificar("   é o aviso de horário lotado (não o de veículo)", erro is not None and "lotado" in str(erro))
            verificar("   o agendamento continua no horário original", servico.obter(ok_outro_veic.id_agendamento).data_hora == hora(12))
            esperar_erro("mover para horário em que o mesmo veículo já está ocupado", OperacaoNaoPermitidaError,
                         lambda: servico.atualizar(diag.id_agendamento, C3, V3, "Diagnóstico", hora(9, 45), 1))
            diag2 = servico.atualizar(diag.id_agendamento, C3, V3, "Diagnóstico", hora(16), 2)
            verificar("mover para horário livre funciona", diag2.data_hora == hora(16) and diag2.termino_previsto == hora(18))
            esperar_erro("mover para o passado", ValidacaoError,
                         lambda: servico.atualizar(diag.id_agendamento, C3, V3, "Diagnóstico", datetime.now() - timedelta(days=1), 1))
            esperar_erro("trocar para veículo de outro cliente", ValidacaoError,
                         lambda: servico.atualizar(diag.id_agendamento, C3, V1, "Diagnóstico", hora(16), 2))
            esperar_erro("editar inexistente", RegistroNaoEncontradoError,
                         lambda: servico.atualizar(99999999, C1, V1, "x", hora(8), 1))
            # agendamento antigo (passado) continua editável nos outros campos
            velho = Agendamento(id_cliente=C2, id_veiculo=V2, tipo_servico="Antigo", data_hora=datetime.now() - timedelta(days=3),
                                duracao_estimada_horas=Decimal("1"), status=S.AGENDADO)
            session.add(velho)
            session.commit()
            v_ed = servico.atualizar(velho.id_agendamento, C2, V2, "Antigo corrigido", velho.data_hora, 1)
            verificar("agendamento já no passado pode ter outros campos editados (sem mudar o horário)", v_ed.tipo_servico == "Antigo corrigido")

            print("\n--- Converter em OS ---")
            qtd_os = session.scalar(select(func.count()).select_from(OrdemServico).where(OrdemServico.id_cliente == C1))
            esperar_erro("converter sem quilometragem", ValidacaoError, lambda: servico.converter_em_os(a.id_agendamento, None, "Revisão"))
            verificar("   nada mudou: continua agendado e nenhuma OS criada",
                      servico.obter(a.id_agendamento).status is S.AGENDADO
                      and session.scalar(select(func.count()).select_from(OrdemServico).where(OrdemServico.id_cliente == C1)) == qtd_os)
            conv = servico.converter_em_os(a.id_agendamento, 45000, "Troca de óleo agendada")
            verificar("agendamento virou 'concluído' com vínculo da OS", conv.status is S.CONCLUIDO and conv.id_ordem_servico is not None)
            os_ = OrdemServicoService(session).obter(conv.id_ordem_servico)
            verificar("OS criada em orçamento com cliente, veículo e tipo copiados",
                      os_.status is StatusOrdemServico.ORCAMENTO and os_.id_cliente == C1 and os_.id_veiculo == V1
                      and os_.tipo_servico == "Troca de óleo e filtro" and os_.quilometragem == 45000)
            esperar_erro("converter de novo", OperacaoNaoPermitidaError, lambda: servico.converter_em_os(a.id_agendamento, 45000, "x"))
            esperar_erro("converter cancelado", OperacaoNaoPermitidaError, lambda: servico.converter_em_os(b.id_agendamento, 45000, "x"))
            esperar_erro("editar concluído", OperacaoNaoPermitidaError, lambda: servico.atualizar(a.id_agendamento, C1, V1, "x", hora(9), 1))
            esperar_erro("cancelar concluído", OperacaoNaoPermitidaError, lambda: servico.cancelar(a.id_agendamento))
            verificar("conclusão libera a agenda (concluído não ocupa horário)",
                      servico.criar(C2, V2, "Outro", hora(9), 1).status is S.AGENDADO)
            OrdemServicoService(session).excluir(os_.id_ordem_servico)
            session.expire_all()
            apos = servico.obter(a.id_agendamento)
            verificar("excluir a OS (orçamento) mantém o agendamento concluído, sem vínculo", apos.status is S.CONCLUIDO and apos.id_ordem_servico is None)

            print("\n--- Consultas e calendário ---")
            verificar("listar por nome do cliente", {x.id_agendamento for x in servico.listar("Agenda Dois")} >= {b.id_agendamento})
            verificar("listar por placa", all(x.veiculo.placa == PLACAS[1] for x in servico.listar(PLACAS[1].lower())))
            canc = servico.listar("Cliente Agenda", S.CANCELADO)
            verificar("filtro por status cancelado (só cancelados, inclui o cancelado acima)",
                      b.id_agendamento in {x.id_agendamento for x in canc} and all(x.status is S.CANCELADO for x in canc))
            dia_lista = servico.listar("Cliente Agenda", data_inicio=DIA, data_fim=DIA)
            verificar("filtro por data (dia inteiro, inclusive o último)", len(dia_lista) >= 5
                      and all(x.data_hora.date() == DIA for x in dia_lista) and dia_lista == sorted(dia_lista, key=lambda x: (x.data_hora, x.id_agendamento)))
            agenda = servico.agenda_do_dia(DIA)
            verificar("agenda do dia não mostra cancelados", all(x.status is not S.CANCELADO for x in agenda))
            verificar("agenda do dia com cancelados mostra o cancelado",
                      b.id_agendamento in {x.id_agendamento for x in servico.agenda_do_dia(DIA, incluir_cancelados=True)})
            ocupados = servico.dias_ocupados(DIA.year, DIA.month)
            n_ativos = sum(1 for x in servico.agenda_do_dia(DIA) if x.status is S.AGENDADO)
            verificar("dias_ocupados conta só agendamentos ativos do dia", ocupados.get(DIA) == n_ativos)
            verificar("mês sem agendamento de teste não traz o dia", date(2000, 1, 1) not in servico.dias_ocupados(2000, 1))
            grade = {h: (n, itens) for h, n, itens in servico.ocupacao_do_dia(DIA)}
            verificar("grade do dia cobre 07h às 18h no mínimo", all(h in grade for h in range(7, 19)))
            verificar("ocupação nunca passa do limite de 2", all(n <= 2 for n, _ in grade.values()))
            verificar("09h tem 2 vagas ocupadas (conclusão e C3 às 9:30 + o novo de C2)", grade[9][0] == 2)
            verificar("hora sem nada tem ocupação 0", grade[13][0] == 0)
            verificar("ocupacao_no_intervalo (09:30-10:00) = 2", servico.ocupacao_no_intervalo(hora(9, 30), Decimal("0.5")) == 2)
            verificar("ocupacao_no_intervalo (13:00) = 0", servico.ocupacao_no_intervalo(hora(13), 1) == 0)
            verificar("ocupacao_no_intervalo com dados inválidos = None", servico.ocupacao_no_intervalo(None, 1) is None
                      and servico.ocupacao_no_intervalo(hora(9), 0) is None)
            verificar("tipos de serviço sugeridos incluem os usados", "Alinhamento" in servico.listar_tipos_servico())
            esperar_erro("obter inexistente", RegistroNaoEncontradoError, lambda: servico.obter(99999999))

            print("\n--- Última linha de defesa: CHECK/UNIQUE do banco ---")
            def bd(sql: str, **p):
                try:
                    session.execute(text(sql), p)
                    session.commit()
                    return False
                except IntegrityError:
                    session.rollback()
                    return True
            verificar("banco recusa duração zero", bd("UPDATE agendamento SET duracao_estimada_horas=0 WHERE id_agendamento=:i", i=b.id_agendamento))
            verificar("banco recusa status fora da lista", bd("UPDATE agendamento SET status='x' WHERE id_agendamento=:i", i=b.id_agendamento))
            os_t = OrdemServicoService(session).cadastrar(C2, V2, 10, "dup", "Teste")
            ok1 = not bd("UPDATE agendamento SET id_ordem_servico=:o WHERE id_agendamento=:i", o=os_t.id_ordem_servico, i=b.id_agendamento)
            verificar("banco aceita vincular uma OS a um agendamento", ok1)
            verificar("banco recusa a mesma OS ligada a dois agendamentos",
                      bd("UPDATE agendamento SET id_ordem_servico=:o WHERE id_agendamento=:i", o=os_t.id_ordem_servico, i=velho.id_agendamento))
            verificar("banco recusa vínculo com OS inexistente", bd("UPDATE agendamento SET id_ordem_servico=99999999 WHERE id_agendamento=:i", i=velho.id_agendamento))

            if engine.dialect.name == "postgresql":
                print("\n--- Trava da agenda (só PostgreSQL) ---")
                s1, s2 = SessionLocal(), SessionLocal()
                try:
                    s1.execute(text("SELECT pg_advisory_xact_lock(50050)"))  # janela 1 está mexendo na agenda
                    s2.execute(text("SET lock_timeout = '500ms'"))
                    try:
                        AgendamentoService(s2).criar(C2, V2, "Concorrência", hora(13), 1)
                        verificar("segunda janela espera enquanto a primeira mexe na agenda", False)
                    except OperationalError:
                        verificar("segunda janela espera enquanto a primeira mexe na agenda", True)
                finally:
                    s2.rollback(); s2.close(); s1.rollback(); s1.close()
                verificar("nada foi criado pela janela barrada", not servico.listar("Concorrência"))
        finally:
            session.rollback()
            limpar()

    with get_session() as s:
        verificar("limpeza: nada de teste sobrou", s.scalar(select(func.count()).select_from(Cliente).where(Cliente.cpf.in_(CPFS))) == 0)
        verificar("agendamentos que já existiam continuam os mesmos", s.scalar(select(func.count()).select_from(Agendamento)) == ag_antes)
        verificar("OS que já existiam continuam as mesmas", s.scalar(select(func.count()).select_from(OrdemServico)) == os_antes)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")


if __name__ == "__main__":
    main()
