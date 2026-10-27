"""
Serviço de Movimentação de Estoque (RF09 - Gerenciar Estoque).

Camada de Serviço (DVP, seção 2.1): concentra as REGRAS DE NEGÓCIO e é a
dona da transação.

Regras deste módulo:
- movimentações são só REGISTRADAS e CONSULTADAS (sem editar nem excluir);
  um erro se corrige com um ajuste;
- cada tipo tem regras próprias de sinal, valor, fornecedor e observação
  (ver tabela no model MovimentacaoEstoque);
- registrar a movimentação e atualizar a quantidade do produto acontecem na
  MESMA transação: ou grava os dois ou nenhum;
- o saldo do produto nunca pode ficar negativo;
- o produto precisa já existir (RF03): o estoque nunca cria produto.

Convenção do parâmetro `quantidade` em registrar():
- compra, doação, devolução e venda: sempre um número POSITIVO (a quantidade
  que o usuário digita); o sinal é aplicado pelo serviço conforme o tipo;
- ajuste: já é o DELTA com sinal (+3 ou -2), diferente de zero. Na tela, o
  ajuste usa ajustar_para_contagem(), que calcula o delta a partir da
  quantidade contada.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Union

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.persistencia.models import MovimentacaoEstoque, Produto, TipoMovimentacao
from src.persistencia.repositories.movimentacao_estoque_repository import (
    MovimentacaoEstoqueRepository,
)
from src.servico.excecoes import (
    OperacaoNaoPermitidaError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)

QUANTIDADE_MAXIMA = 1_000_000
VALOR_MAXIMO = Decimal("99999999.99")  # limite do NUMERIC(10,2)
OBSERVACAO_MAXIMA = 500

Numero = Union[int, float, Decimal]

# Quais campos cada tipo usa: "obrigatorio", "opcional" ou "nao_usa".
_REGRAS = {
    TipoMovimentacao.COMPRA:               {"valor": "obrigatorio", "fornecedor": "obrigatorio"},
    TipoMovimentacao.DOACAO:               {"valor": "nao_usa",     "fornecedor": "opcional"},
    TipoMovimentacao.DEVOLUCAO_FORNECEDOR: {"valor": "opcional",    "fornecedor": "obrigatorio"},
    TipoMovimentacao.VENDA_AVULSA:         {"valor": "obrigatorio", "fornecedor": "nao_usa"},
    TipoMovimentacao.AJUSTE:               {"valor": "nao_usa",     "fornecedor": "nao_usa"},
}
_ROTULO_FORNECEDOR = {
    TipoMovimentacao.DOACAO: "doador",
}


class MovimentacaoEstoqueService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = MovimentacaoEstoqueRepository(session)

    # ------------------------------------------------------------------
    # Registrar movimentação
    # ------------------------------------------------------------------
    def registrar(
        self,
        id_produto: Optional[int],
        tipo: Union[TipoMovimentacao, str, None],
        quantidade: Optional[int],
        data_movimentacao: Optional[date] = None,
        valor: Optional[Numero] = None,
        fornecedor: Optional[str] = None,
        observacao: Optional[str] = None,
    ) -> MovimentacaoEstoque:
        erros: List[str] = []

        if id_produto is None:
            erros.append("O produto é obrigatório.")
        tipo_enum = self._validar_tipo(tipo, erros)
        delta = self._validar_quantidade(tipo_enum, quantidade, erros)
        campos = self._validar_campos(
            tipo_enum, data_movimentacao, valor, fornecedor, observacao, erros
        )
        if erros:
            raise ValidacaoError(erros)

        produto = self._obter_produto_travado(id_produto)
        return self._gravar(produto, tipo_enum, delta, campos)

    # ------------------------------------------------------------------
    # Ajuste pela contagem física
    # ------------------------------------------------------------------
    def ajustar_para_contagem(
        self,
        id_produto: Optional[int],
        quantidade_contada: Optional[int],
        observacao: Optional[str],
        data_movimentacao: Optional[date] = None,
    ) -> MovimentacaoEstoque:
        """
        Iguala o saldo do sistema à contagem física. O usuário informa
        quanto CONTOU e o serviço calcula a diferença (delta) e registra um
        ajuste com ela.
        """
        erros: List[str] = []

        if id_produto is None:
            erros.append("O produto é obrigatório.")
        if not self._eh_inteiro(quantidade_contada) or not (0 <= quantidade_contada <= QUANTIDADE_MAXIMA):
            erros.append(f"A quantidade contada deve ser um número inteiro entre 0 e {QUANTIDADE_MAXIMA}.")
        campos = self._validar_campos(
            TipoMovimentacao.AJUSTE, data_movimentacao, None, None, observacao, erros
        )
        if erros:
            raise ValidacaoError(erros)

        produto = self._obter_produto_travado(id_produto)
        delta = quantidade_contada - produto.quantidade
        if delta == 0:
            mensagem = (
                f"A contagem é igual ao saldo do sistema ({produto.quantidade}): "
                "nenhum ajuste é necessário."
            )
            self._session.rollback()  # libera a trava do produto
            raise ValidacaoError(mensagem)
        return self._gravar(produto, TipoMovimentacao.AJUSTE, delta, campos)

    # ------------------------------------------------------------------
    # Consultas (não precisam de commit)
    # ------------------------------------------------------------------
    def obter(self, id_movimentacao: int) -> MovimentacaoEstoque:
        movimentacao = self._repo.buscar_por_id(id_movimentacao)
        if movimentacao is None:
            raise RegistroNaoEncontradoError(f"Movimentação {id_movimentacao} não encontrada.")
        return movimentacao

    def listar(
        self,
        termo: str = "",
        tipo: Optional[TipoMovimentacao] = None,
        data_inicio: Optional[date] = None,
        data_fim: Optional[date] = None,
    ) -> List[MovimentacaoEstoque]:
        return self._repo.listar((termo or "").strip(), tipo, data_inicio, data_fim)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    @staticmethod
    def _eh_inteiro(valor: object) -> bool:
        return isinstance(valor, int) and not isinstance(valor, bool)

    @staticmethod
    def _validar_tipo(tipo: Union[TipoMovimentacao, str, None], erros: List[str]) -> Optional[TipoMovimentacao]:
        if isinstance(tipo, TipoMovimentacao):
            return tipo
        try:
            return TipoMovimentacao(tipo)
        except ValueError:
            erros.append("O tipo de movimentação é obrigatório e deve ser válido.")
            return None

    def _validar_quantidade(
        self, tipo: Optional[TipoMovimentacao], quantidade: Optional[int], erros: List[str]
    ) -> int:
        """Devolve o DELTA com sinal (0 se inválido; os erros vão para a lista)."""
        if not self._eh_inteiro(quantidade):
            erros.append("A quantidade deve ser um número inteiro.")
            return 0
        if abs(quantidade) > QUANTIDADE_MAXIMA:
            erros.append(f"A quantidade deve ser de no máximo {QUANTIDADE_MAXIMA}.")
            return 0
        if tipo is TipoMovimentacao.AJUSTE:
            if quantidade == 0:
                erros.append("O ajuste não pode ser zero.")
            return quantidade
        if quantidade <= 0:
            erros.append("A quantidade deve ser maior que zero.")
            return 0
        return quantidade * tipo.sinal if tipo is not None else 0

    def _validar_campos(
        self,
        tipo: Optional[TipoMovimentacao],
        data_movimentacao: Union[date, datetime, None],
        valor: Optional[Numero],
        fornecedor: Optional[str],
        observacao: Optional[str],
        erros: List[str],
    ) -> dict:
        # --- data ---
        if data_movimentacao is None:
            data_movimentacao = date.today()
        elif isinstance(data_movimentacao, datetime):
            data_movimentacao = data_movimentacao.date()
        elif not isinstance(data_movimentacao, date):
            erros.append("A data é inválida.")
            data_movimentacao = date.today()
        if data_movimentacao > date.today():
            erros.append("A data da movimentação não pode ser futura.")

        fornecedor = (fornecedor or "").strip() or None
        observacao = (observacao or "").strip() or None
        valor_final: Optional[Decimal] = None

        if tipo is not None:
            regras = _REGRAS[tipo]
            nome_forn = _ROTULO_FORNECEDOR.get(tipo, "fornecedor")

            # --- valor ---
            if valor is not None:
                if regras["valor"] == "nao_usa":
                    erros.append(f"{tipo.rotulo} não possui valor.")
                else:
                    valor_final = self._normalizar_valor(valor, erros)
            elif regras["valor"] == "obrigatorio":
                erros.append("O valor é obrigatório para " + tipo.rotulo.lower() + ".")

            # --- fornecedor ---
            if fornecedor is not None and regras["fornecedor"] == "nao_usa":
                erros.append(f"{tipo.rotulo} não possui fornecedor.")
            elif fornecedor is None and regras["fornecedor"] == "obrigatorio":
                erros.append(f"O {nome_forn} é obrigatório para " + tipo.rotulo.lower() + ".")
            if fornecedor is not None and len(fornecedor) > 150:
                erros.append(f"O {nome_forn} deve ter no máximo 150 caracteres.")

            # --- observação ---
            if tipo is TipoMovimentacao.AJUSTE and observacao is None:
                erros.append("A justificativa é obrigatória no ajuste de estoque.")
        if observacao is not None and len(observacao) > OBSERVACAO_MAXIMA:
            erros.append(f"A observação deve ter no máximo {OBSERVACAO_MAXIMA} caracteres.")

        return {
            "data_movimentacao": data_movimentacao,
            "valor": valor_final,
            "fornecedor": fornecedor,
            "observacao": observacao,
        }

    @staticmethod
    def _normalizar_valor(valor: Numero, erros: List[str]) -> Optional[Decimal]:
        if isinstance(valor, bool) or not isinstance(valor, (int, float, Decimal)):
            erros.append("O valor deve ser numérico.")
            return None
        try:
            decimal = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:  # noqa: BLE001  (NaN, infinito...)
            erros.append("O valor deve ser numérico.")
            return None
        if decimal < 0 or decimal > VALOR_MAXIMO:
            erros.append("O valor deve estar entre 0,00 e 99.999.999,99.")
            return None
        return decimal

    def _obter_produto_travado(self, id_produto: int) -> Produto:
        produto = self._repo.buscar_produto_com_trava(id_produto)
        if produto is None:
            raise RegistroNaoEncontradoError(f"Produto {id_produto} não encontrado.")
        return produto

    def _gravar(
        self,
        produto: Produto,
        tipo: TipoMovimentacao,
        delta: int,
        campos: dict,
    ) -> MovimentacaoEstoque:
        """Registra a movimentação E atualiza o saldo na mesma transação."""
        novo_saldo = produto.quantidade + delta
        if novo_saldo < 0:
            mensagem = (
                f"Saldo insuficiente: o produto “{produto.nome}” tem {produto.quantidade} "
                f"em estoque e esta movimentação retira {abs(delta)}."
            )
            self._session.rollback()  # libera a trava do produto
            raise OperacaoNaoPermitidaError(mensagem)

        movimentacao = self._repo.adicionar(
            MovimentacaoEstoque(
                id_produto=produto.id_produto,
                tipo=tipo,
                quantidade=delta,
                **campos,
            )
        )
        produto.quantidade = novo_saldo  # o UPDATE sai junto no commit
        self._confirmar()
        return movimentacao

    def _confirmar(self) -> None:
        """
        Faz o commit. Se o banco recusar, desfaz tudo (rollback), inclusive a
        atualização do saldo. Os CHECK do banco são a "última linha de defesa"
        das regras por tipo.
        """
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise OperacaoNaoPermitidaError(
                "O banco de dados recusou a movimentação por violar uma regra de "
                "integridade (por exemplo, saldo negativo)."
            ) from exc
        except Exception:
            self._session.rollback()
            raise
