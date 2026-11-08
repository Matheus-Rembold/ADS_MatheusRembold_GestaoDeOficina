"""
Serviço de Relatórios (RF06 - Gerar Relatórios e Gráficos).

Regras (decididas com o Matheus em 07/11/2026, ver CLAUDE.md seção 5):

- ENTRADAS (ganhos) = OS ENTREGUES no período, pela data entregue_em
  (peças + mão de obra), + VENDAS POR FORA (venda_avulsa.valor).
  É regime de CAIXA: só conta o que tem data comprovada. "Pronto" e
  "aguardando pagamento" não têm data própria no banco.
- A RECEBER = OS em "aguardando pagamento" (cartão à parte, sem filtro de data).
- SAÍDAS (gastos) = compras − ressarcimentos de devolução, pela data da
  movimentação.
- LUCRO BRUTO DAS OS = receita das OS − CMV (custo das peças usadas nessas
  OS; regime de competência). Peça sem custo entra como zero e é contada.
- SERVIÇOS MAIS PRESTADOS = mesma regra das OS (entregue + entregue_em),
  por quantidade de OS; top 10 + "Outros". A soma do faturamento do ranking
  é igual à receita das OS (as duas partes da tela batem).
- Período fechado [início, fim]; até 62 dias agrupa por DIA, acima por MÊS.
  Dias/meses sem movimento aparecem com ZERO (o gráfico não "pula" meses).

Os resultados são dataclasses IMUTÁVEIS (frozen) sem nenhum objeto ORM: já
são DTOs prontos, por isso o controller os repassa sem recopiar campo a campo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.persistencia.models import TipoMovimentacao
from src.persistencia.repositories.relatorio_repository import RelatorioRepository
from src.servico.excecoes import ValidacaoError

LIMITE_DIARIO = 62  # períodos de até 62 dias são agrupados por dia
TOP_SERVICOS = 10
ROTULO_SEM_TIPO = "Não informado"
ROTULO_OUTROS = "Outros"

AGRUPA_DIA = "dia"
AGRUPA_MES = "mes"

_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
_ZERO = Decimal("0.00")
_CENTAVO = Decimal("0.01")

# --- períodos prontos do filtro -------------------------------------------
ULTIMOS_12_MESES = "Últimos 12 meses"
ESTE_MES = "Este mês"
MES_PASSADO = "Mês passado"
ESTE_ANO = "Este ano"
ANO_PASSADO = "Ano passado"
PERSONALIZADO = "Personalizado"
PERIODOS = [ULTIMOS_12_MESES, ESTE_MES, MES_PASSADO, ESTE_ANO, ANO_PASSADO, PERSONALIZADO]


def _dinheiro(valor) -> Decimal:
    return Decimal(valor or 0).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def _primeiro_dia_mes(d: date, meses_atras: int = 0) -> date:
    total = d.year * 12 + (d.month - 1) - meses_atras
    return date(total // 12, total % 12 + 1, 1)


def periodo_predefinido(nome: str, hoje: Optional[date] = None) -> Tuple[date, date]:
    """Datas (início, fim) de um período pronto do filtro. 'Este mês/ano' vão até hoje."""
    hoje = hoje or date.today()
    if nome == ULTIMOS_12_MESES:
        return _primeiro_dia_mes(hoje, 11), hoje
    if nome == ESTE_MES:
        return _primeiro_dia_mes(hoje), hoje
    if nome == MES_PASSADO:
        inicio = _primeiro_dia_mes(hoje, 1)
        return inicio, _primeiro_dia_mes(hoje) - timedelta(days=1)
    if nome == ESTE_ANO:
        return date(hoje.year, 1, 1), hoje
    if nome == ANO_PASSADO:
        return date(hoje.year - 1, 1, 1), date(hoje.year - 1, 12, 31)
    raise ValidacaoError(f"Período desconhecido: {nome}.")


def rotulo_periodo(inicio: date, agrupamento: str) -> str:
    """'07/11' (por dia) ou 'nov/26' (por mês)."""
    if agrupamento == AGRUPA_DIA:
        return inicio.strftime("%d/%m")
    return f"{_MESES[inicio.month - 1]}/{inicio.strftime('%y')}"


# --- resultados (DTOs imutáveis) ---------------------------------------------
@dataclass(frozen=True)
class PontoFinanceiro:
    """Um dia ou mês do gráfico de entradas x saídas."""

    inicio: date
    rotulo: str
    receita_os: Decimal
    vendas_avulsas: Decimal
    compras: Decimal
    ressarcimentos: Decimal
    qtd_os: int

    @property
    def entradas(self) -> Decimal:
        return self.receita_os + self.vendas_avulsas

    @property
    def saidas(self) -> Decimal:
        return self.compras - self.ressarcimentos

    @property
    def saldo(self) -> Decimal:
        return self.entradas - self.saidas


@dataclass(frozen=True)
class ResumoFinanceiro:
    """Totais do período (os cartões da tela)."""

    receita_os: Decimal
    vendas_avulsas: Decimal
    compras: Decimal
    ressarcimentos: Decimal
    custo_pecas: Decimal  # CMV das OS entregues
    qtd_os: int
    qtd_vendas: int
    qtd_compras: int
    pecas_sem_custo: int
    a_receber: Decimal
    qtd_a_receber: int

    @property
    def entradas(self) -> Decimal:
        return self.receita_os + self.vendas_avulsas

    @property
    def saidas(self) -> Decimal:
        return self.compras - self.ressarcimentos

    @property
    def saldo(self) -> Decimal:
        return self.entradas - self.saidas

    @property
    def lucro_bruto_os(self) -> Decimal:
        return self.receita_os - self.custo_pecas


@dataclass(frozen=True)
class ServicoRanking:
    tipo: str
    quantidade: int
    faturamento: Decimal

    @property
    def ticket_medio(self) -> Decimal:
        if not self.quantidade:
            return _ZERO
        return (self.faturamento / self.quantidade).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Relatorio:
    inicio: date
    fim: date
    agrupamento: str  # AGRUPA_DIA ou AGRUPA_MES
    pontos: Tuple[PontoFinanceiro, ...]
    resumo: ResumoFinanceiro
    servicos: Tuple[ServicoRanking, ...]

    @property
    def descricao_periodo(self) -> str:
        agrup = "por dia" if self.agrupamento == AGRUPA_DIA else "por mês"
        return f"{self.inicio:%d/%m/%Y} a {self.fim:%d/%m/%Y} (agrupado {agrup})"

    @property
    def vazio(self) -> bool:
        r = self.resumo
        return not (r.qtd_os or r.qtd_vendas or r.qtd_compras or r.ressarcimentos)


# --- serviço -------------------------------------------------------------------
class RelatorioService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = RelatorioRepository(session)

    def gerar(self, inicio: Optional[date], fim: Optional[date]) -> Relatorio:
        inicio, fim = self._validar_periodo(inicio, fim)
        agrupamento = AGRUPA_DIA if (fim - inicio).days + 1 <= LIMITE_DIARIO else AGRUPA_MES
        unidade = "day" if agrupamento == AGRUPA_DIA else "month"

        # Intervalo meio-aberto [início, fim + 1 dia): uma OS entregue às 23:59
        # do último dia entra; a da 00:00 do dia seguinte não.
        ini_dt = datetime.combine(inicio, datetime.min.time())
        fim_exclusivo = fim + timedelta(days=1)
        fim_dt = datetime.combine(fim_exclusivo, datetime.min.time())

        os_linhas = self._repo.receita_os_por_periodo(ini_dt, fim_dt, unidade)
        mov_linhas = self._repo.movimentacoes_por_periodo(inicio, fim_exclusivo, unidade)
        ranking = self._repo.ranking_servicos(ini_dt, fim_dt)
        qtd_receber, total_receber = self._repo.a_receber()

        pontos = self._montar_pontos(inicio, fim, agrupamento, os_linhas, mov_linhas)
        resumo = self._montar_resumo(os_linhas, mov_linhas, qtd_receber, total_receber)
        servicos = self._montar_ranking(ranking)
        return Relatorio(inicio, fim, agrupamento, pontos, resumo, servicos)

    # ------------------------------------------------------------------
    @staticmethod
    def _validar_periodo(inicio, fim) -> Tuple[date, date]:
        erros: List[str] = []
        if not isinstance(inicio, date):
            erros.append("Informe a data inicial do período.")
        if not isinstance(fim, date):
            erros.append("Informe a data final do período.")
        if erros:
            raise ValidacaoError(erros)
        # datetime também é date: normaliza para data pura
        inicio = inicio.date() if isinstance(inicio, datetime) else inicio
        fim = fim.date() if isinstance(fim, datetime) else fim
        if inicio > fim:
            raise ValidacaoError("A data inicial não pode ser depois da data final.")
        return inicio, fim

    @staticmethod
    def _inicios(inicio: date, fim: date, agrupamento: str) -> List[date]:
        """Todos os dias (ou primeiros dias de mês) do período, inclusive os vazios."""
        if agrupamento == AGRUPA_DIA:
            return [inicio + timedelta(days=i) for i in range((fim - inicio).days + 1)]
        atual, ultimo, lista = _primeiro_dia_mes(inicio), _primeiro_dia_mes(fim), []
        while atual <= ultimo:
            lista.append(atual)
            atual = _primeiro_dia_mes(atual, -1)
        return lista

    def _montar_pontos(self, inicio, fim, agrupamento, os_linhas, mov_linhas):
        os_por = {linha[0].date(): linha for linha in os_linhas}
        mov_por: Dict[Tuple[date, TipoMovimentacao], Decimal] = {
            (linha[0].date(), TipoMovimentacao(linha[1])): linha[3] for linha in mov_linhas
        }
        pontos = []
        for dia in self._inicios(inicio, fim, agrupamento):
            os_ = os_por.get(dia)
            pontos.append(
                PontoFinanceiro(
                    inicio=dia,
                    rotulo=rotulo_periodo(dia, agrupamento),
                    receita_os=_dinheiro(os_[2] + os_[3]) if os_ else _ZERO,
                    vendas_avulsas=_dinheiro(mov_por.get((dia, TipoMovimentacao.VENDA_AVULSA))),
                    compras=_dinheiro(mov_por.get((dia, TipoMovimentacao.COMPRA))),
                    ressarcimentos=_dinheiro(
                        mov_por.get((dia, TipoMovimentacao.DEVOLUCAO_FORNECEDOR))
                    ),
                    qtd_os=int(os_[1]) if os_ else 0,
                )
            )
        return tuple(pontos)

    @staticmethod
    def _montar_resumo(os_linhas, mov_linhas, qtd_receber, total_receber) -> ResumoFinanceiro:
        def soma_mov(tipo, indice):
            return sum(
                (linha[indice] for linha in mov_linhas if TipoMovimentacao(linha[1]) is tipo), 0
            )

        return ResumoFinanceiro(
            receita_os=_dinheiro(sum((l[2] + l[3] for l in os_linhas), 0)),
            vendas_avulsas=_dinheiro(soma_mov(TipoMovimentacao.VENDA_AVULSA, 3)),
            compras=_dinheiro(soma_mov(TipoMovimentacao.COMPRA, 3)),
            ressarcimentos=_dinheiro(soma_mov(TipoMovimentacao.DEVOLUCAO_FORNECEDOR, 3)),
            custo_pecas=_dinheiro(sum((l[4] for l in os_linhas), 0)),
            qtd_os=int(sum((l[1] for l in os_linhas), 0)),
            qtd_vendas=int(soma_mov(TipoMovimentacao.VENDA_AVULSA, 2)),
            qtd_compras=int(soma_mov(TipoMovimentacao.COMPRA, 2)),
            pecas_sem_custo=int(sum((l[5] for l in os_linhas), 0)),
            a_receber=_dinheiro(total_receber),
            qtd_a_receber=int(qtd_receber),
        )

    @staticmethod
    def _montar_ranking(linhas) -> Tuple[ServicoRanking, ...]:
        itens = [
            ServicoRanking(tipo or ROTULO_SEM_TIPO, int(qtd), _dinheiro(fat))
            for tipo, qtd, fat in linhas
        ]
        # Mesma ordem do SQL, garantida aqui também (regra testável sem depender do banco).
        itens.sort(key=lambda s: (-s.quantidade, -s.faturamento, s.tipo.lower()))
        if len(itens) <= TOP_SERVICOS:
            return tuple(itens)
        resto = itens[TOP_SERVICOS:]  # 10 primeiros + "Outros" com a soma do resto
        outros = ServicoRanking(
            ROTULO_OUTROS,
            sum(s.quantidade for s in resto),
            _dinheiro(sum((s.faturamento for s in resto), 0)),
        )
        return tuple(itens[:TOP_SERVICOS]) + (outros,)
