"""
Serviço de Ordem de Serviço (RF04).

Camada de Serviço (DVP, seção 2.1): concentra as REGRAS DE NEGÓCIO e é a
dona da transação.

Regras principais
-----------------
- Obrigatórios: cliente, veículo (que pertença ao cliente), quilometragem
  (inteiro >= 0), descrição do problema e tipo de serviço.
- Peças: cada produto aparece uma vez por OS; quantidade inteira > 0.
- Preço da peça: vem do PREÇO DE VENDA do produto (custo + markup, ver
  src/servico/precificacao.py). A tela já o pré-preenche e o usuário pode
  alterá-lo (desconto, caso especial). Se o preço vier vazio, o serviço usa o
  preço já gravado no item (edição) ou o preço de venda do produto; sem
  nenhum dos dois, é erro de validação. O preço e o custo (último valor pago)
  são COPIADOS para os_produto: mudar o produto depois não altera OS antigas.
- Preço abaixo do custo NÃO bloqueia: é só um aviso (pecas_abaixo_do_custo).
- Valor total = soma(quantidade x preço) + mão de obra (calculado, não guardado).
- Estoque: "orçamento" NÃO consome. Ao passar a "andamento" as peças saem do
  estoque; se faltar saldo, a mudança é bloqueada e as peças são listadas.
  Peças alteradas enquanto está em andamento ajustam o estoque na hora; voltar
  a "orçamento" devolve tudo. A baixa NÃO gera movimentação de estoque (RF09):
  o consumo fica registrado em os_produto.
- Fórmula única: para cada produto, delta = consumo_depois - consumo_antes,
  onde "consumo" só conta se a OS está fora de orçamento. Produtos são
  travados (FOR UPDATE) em ordem de id e o saldo nunca fica negativo.
- Ciclo de vida: orcamento <-> andamento <-> pronto <-> aguardando_pagamento
  -> entregue. A partir de "pronto" a OS fica travada (só o status muda).
  Voltar de status é bloqueado se a OS já tem nota fiscal (RF08).
- Só é possível excluir OS em orçamento.
- Quilometragem menor que a da última OS do veículo NÃO bloqueia: é só um
  aviso (aviso_quilometragem), a tela pede confirmação.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Sequence, Union

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.persistencia.models import OrdemServico, OsProduto, StatusOrdemServico
from src.persistencia.models.ordem_servico import TRANSICOES_DE_VOLTA
from src.persistencia.repositories.ordem_servico_repository import OrdemServicoRepository
from src.servico.excecoes import (
    OperacaoNaoPermitidaError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)

QUILOMETRAGEM_MAXIMA = 10_000_000
QUANTIDADE_MAXIMA = 1_000_000
VALOR_MAXIMO = Decimal("99999999.99")  # limite do NUMERIC(10,2)
DESCRICAO_MAXIMA = 2000
TIPO_SERVICO_MAXIMO = 150

Numero = Union[int, float, Decimal]


@dataclass(frozen=True)
class ItemOS:
    """Uma peça da OS, como a tela informa."""

    id_produto: int
    quantidade: int
    preco_unitario: Optional[Numero] = None  # vazio = usar o preço de venda do produto


class OrdemServicoService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = OrdemServicoRepository(session)

    # ------------------------------------------------------------------
    # Cadastrar
    # ------------------------------------------------------------------
    def cadastrar(
        self,
        id_cliente: Optional[int],
        id_veiculo: Optional[int],
        quilometragem: Optional[int],
        descricao_problema: Optional[str],
        tipo_servico: Optional[str],
        valor_mao_de_obra: Optional[Numero] = None,
        itens: Sequence[ItemOS] = (),
        status: Union[StatusOrdemServico, str] = StatusOrdemServico.ORCAMENTO,
        confirmar: bool = True,
    ) -> OrdemServico:
        """
        confirmar=False deixa a transação ABERTA (só flush): quem chamou fecha com
        commit/rollback. Usado pelo RF05 para criar a OS e marcar o agendamento
        como concluído na MESMA transação.
        """
        erros: List[str] = []
        status_enum = self._validar_status_inicial(status, erros)
        dados = self._validar_dados(
            id_cliente, id_veiculo, quilometragem, descricao_problema,
            tipo_servico, valor_mao_de_obra, itens, erros,
        )
        if erros:
            raise ValidacaoError(erros)
        self._validar_cliente_e_veiculo(id_cliente, id_veiculo)

        os_ = OrdemServico(
            id_cliente=id_cliente,
            id_veiculo=id_veiculo,
            quilometragem=dados["quilometragem"],
            descricao_problema=dados["descricao"],
            tipo_servico=dados["tipo_servico"],
            valor_mao_de_obra=dados["mao_de_obra"],
            status=status_enum,
        )
        produtos = self._travar_produtos([i.id_produto for i in dados["itens"]])
        dados["itens"] = self._resolver_precos(dados["itens"], produtos, {})
        for item in dados["itens"]:
            os_.os_produtos.append(
                OsProduto(
                    id_produto=item.id_produto,
                    quantidade_utilizada=item.quantidade,
                    preco_unitario=item.preco_unitario,
                    custo_unitario=produtos[item.id_produto].valor_unitario,
                )
            )
        if status_enum.consome_estoque:
            self._baixar_estoque({i.id_produto: i.quantidade for i in dados["itens"]}, produtos)
        self._repo.adicionar(os_)
        if not confirmar:
            return os_
        self._confirmar()
        return self._recarregar(os_.id_ordem_servico)

    # ------------------------------------------------------------------
    # Atualizar (somente orçamento e andamento)
    # ------------------------------------------------------------------
    def atualizar(
        self,
        id_os: int,
        id_cliente: Optional[int],
        id_veiculo: Optional[int],
        quilometragem: Optional[int],
        descricao_problema: Optional[str],
        tipo_servico: Optional[str],
        valor_mao_de_obra: Optional[Numero] = None,
        itens: Sequence[ItemOS] = (),
    ) -> OrdemServico:
        erros: List[str] = []
        dados = self._validar_dados(
            id_cliente, id_veiculo, quilometragem, descricao_problema,
            tipo_servico, valor_mao_de_obra, itens, erros,
        )
        if erros:
            raise ValidacaoError(erros)

        os_ = self._obter_travada(id_os)
        if not os_.status.editavel:
            self._recusar(
                f"A OS {id_os} está “{os_.status.rotulo}” e não pode mais ser editada. "
                "Só o status pode ser alterado."
            )
        try:
            self._validar_cliente_e_veiculo(id_cliente, id_veiculo)
        except Exception:
            self._session.rollback()
            raise

        antigos: Dict[int, OsProduto] = {i.id_produto: i for i in os_.os_produtos}
        ids_novos = {i.id_produto for i in dados["itens"]}
        produtos = self._travar_produtos(list(set(antigos) | ids_novos))
        # Peça que já estava na OS mantém o preço gravado se a tela não mandar outro.
        gravados = {p: linha.preco_unitario for p, linha in antigos.items()}
        novos = {i.id_produto: i for i in self._resolver_precos(dados["itens"], produtos, gravados)}

        deltas: Dict[int, int] = {}
        for id_produto in set(antigos) | set(novos):
            antes = antigos[id_produto].quantidade_utilizada if id_produto in antigos else 0
            depois = novos[id_produto].quantidade if id_produto in novos else 0
            if depois != antes:
                deltas[id_produto] = depois - antes

        for id_produto, linha in list(antigos.items()):
            if id_produto not in novos:
                os_.os_produtos.remove(linha)  # delete-orphan apaga a linha
        for id_produto, item in novos.items():
            if id_produto in antigos:
                antigos[id_produto].quantidade_utilizada = item.quantidade
                antigos[id_produto].preco_unitario = item.preco_unitario
            else:
                os_.os_produtos.append(
                    OsProduto(
                        id_produto=id_produto,
                        quantidade_utilizada=item.quantidade,
                        preco_unitario=item.preco_unitario,
                        custo_unitario=produtos[id_produto].valor_unitario,
                    )
                )

        os_.id_cliente = id_cliente
        os_.id_veiculo = id_veiculo
        os_.quilometragem = dados["quilometragem"]
        os_.descricao_problema = dados["descricao"]
        os_.tipo_servico = dados["tipo_servico"]
        os_.valor_mao_de_obra = dados["mao_de_obra"]
        os_.atualizado_em = datetime.now()

        if os_.status.consome_estoque and deltas:
            self._ajustar_estoque(deltas, produtos)
        self._repo.flush()
        self._confirmar()
        return self._recarregar(id_os)

    # ------------------------------------------------------------------
    # Mudar de status
    # ------------------------------------------------------------------
    def alterar_status(
        self, id_os: int, novo_status: Union[StatusOrdemServico, str]
    ) -> OrdemServico:
        try:
            novo = StatusOrdemServico(novo_status)
        except ValueError:
            raise ValidacaoError("O status informado é inválido.") from None

        os_ = self._obter_travada(id_os)
        atual = os_.status
        if novo not in atual.proximos:
            self._recusar(
                f"Não é possível passar a OS {id_os} de “{atual.rotulo}” para “{novo.rotulo}”."
            )
        if (atual, novo) in TRANSICOES_DE_VOLTA and os_.id_nota_fiscal is not None:
            self._recusar(
                f"A OS {id_os} já possui nota fiscal e não pode voltar para “{novo.rotulo}”."
            )

        itens = {i.id_produto: i.quantidade_utilizada for i in os_.os_produtos}
        if atual.consome_estoque != novo.consome_estoque and itens:
            produtos = self._travar_produtos(list(itens))
            if novo.consome_estoque:
                self._baixar_estoque(itens, produtos)
            else:
                self._ajustar_estoque({p: -q for p, q in itens.items()}, produtos)

        os_.status = novo
        os_.entregue_em = datetime.now() if novo is StatusOrdemServico.ENTREGUE else None
        os_.atualizado_em = datetime.now()
        self._repo.flush()
        self._confirmar()
        return self._recarregar(id_os)

    # ------------------------------------------------------------------
    # Excluir (somente orçamento)
    # ------------------------------------------------------------------
    def excluir(self, id_os: int) -> None:
        os_ = self._obter_travada(id_os)
        if os_.status is not StatusOrdemServico.ORCAMENTO:
            self._recusar(
                f"Só é possível excluir OS em orçamento; a OS {id_os} está “{os_.status.rotulo}”."
            )
        self._repo.remover(os_)
        self._confirmar()

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def obter(self, id_os: int) -> OrdemServico:
        os_ = self._repo.buscar_por_id(id_os)
        if os_ is None:
            raise RegistroNaoEncontradoError(f"Ordem de serviço {id_os} não encontrada.")
        return os_

    def listar(
        self, termo: str = "", status: Optional[StatusOrdemServico] = None
    ) -> List[OrdemServico]:
        return self._repo.listar((termo or "").strip(), status)

    def listar_por_veiculo(self, id_veiculo: int) -> List[OrdemServico]:
        return self._repo.listar_por_veiculo(id_veiculo)

    def listar_tipos_servico(self) -> List[str]:
        return self._repo.listar_tipos_servico()

    def aviso_quilometragem(
        self, id_veiculo: Optional[int], quilometragem: Optional[int], id_os: Optional[int] = None
    ) -> Optional[str]:
        """Texto de aviso se a km for menor que a da última OS do veículo (não bloqueia)."""
        if id_veiculo is None or not self._eh_inteiro(quilometragem):
            return None
        anterior = self._repo.ultima_quilometragem(id_veiculo, ignorar_os=id_os)
        if anterior is not None and quilometragem < anterior:
            return (
                f"A quilometragem informada ({quilometragem:,} km) é menor que a da última OS "
                f"deste veículo ({anterior:,} km).".replace(",", ".")
            )
        return None

    def pecas_abaixo_do_custo(
        self, itens: Sequence[ItemOS], id_os: Optional[int] = None
    ) -> List[str]:
        """
        Nomes das peças cujo preço ficaria ABAIXO DO CUSTO (não bloqueia: a tela
        pede confirmação). O custo comparado é o mesmo que será gravado: o já
        copiado na OS, para peças que já estavam nela, ou o custo atual do produto.
        """
        ids = [i.id_produto for i in itens if self._eh_inteiro(i.id_produto)]
        produtos = self._repo.buscar_produtos(ids)
        linhas = {}
        if id_os is not None:
            os_ = self._repo.buscar_por_id(id_os)
            if os_ is not None:
                linhas = {l.id_produto: l for l in os_.os_produtos}
        nomes = []
        for item in itens:
            produto = produtos.get(item.id_produto)
            if produto is None:
                continue
            linha = linhas.get(item.id_produto)
            custo = linha.custo_unitario if linha is not None else produto.valor_unitario
            if item.preco_unitario is not None:
                preco = self._normalizar_valor(item.preco_unitario)
            else:
                preco = linha.preco_unitario if linha is not None else produto.preco_venda
            if custo is not None and preco is not None and preco < custo:
                nomes.append(produto.nome)
        return sorted(nomes, key=str.lower)

    @staticmethod
    def transicoes_permitidas(os_: OrdemServico) -> List[StatusOrdemServico]:
        """Status para onde a OS pode ir agora, na ordem do ciclo de vida."""
        ordem = list(StatusOrdemServico)
        permitidos = []
        for destino in os_.status.proximos:
            if (os_.status, destino) in TRANSICOES_DE_VOLTA and os_.id_nota_fiscal is not None:
                continue
            permitidos.append(destino)
        return sorted(permitidos, key=ordem.index)

    # ------------------------------------------------------------------
    # Internos: validação
    # ------------------------------------------------------------------
    @staticmethod
    def _eh_inteiro(valor: object) -> bool:
        return isinstance(valor, int) and not isinstance(valor, bool)

    @staticmethod
    def _validar_status_inicial(status, erros: List[str]) -> StatusOrdemServico:
        try:
            enum = StatusOrdemServico(status)
        except ValueError:
            erros.append("O status inicial é inválido.")
            return StatusOrdemServico.ORCAMENTO
        if enum not in (StatusOrdemServico.ORCAMENTO, StatusOrdemServico.ANDAMENTO):
            erros.append("Uma OS nova só pode começar como orçamento ou em andamento.")
        return enum

    def _validar_dados(
        self, id_cliente, id_veiculo, quilometragem, descricao, tipo_servico,
        valor_mao_de_obra, itens, erros: List[str],
    ) -> dict:
        if id_cliente is None:
            erros.append("O cliente é obrigatório.")
        if id_veiculo is None:
            erros.append("O veículo é obrigatório.")

        if not self._eh_inteiro(quilometragem) or not (0 <= quilometragem <= QUILOMETRAGEM_MAXIMA):
            erros.append(
                f"A quilometragem é obrigatória e deve ser um inteiro entre 0 e {QUILOMETRAGEM_MAXIMA}."
            )
            quilometragem = None

        descricao = (descricao or "").strip()
        if not descricao:
            erros.append("A descrição do problema é obrigatória.")
        elif len(descricao) > DESCRICAO_MAXIMA:
            erros.append(f"A descrição deve ter no máximo {DESCRICAO_MAXIMA} caracteres.")

        tipo_servico = " ".join((tipo_servico or "").split())
        if not tipo_servico:
            erros.append("O tipo de serviço é obrigatório.")
        elif len(tipo_servico) > TIPO_SERVICO_MAXIMO:
            erros.append(f"O tipo de serviço deve ter no máximo {TIPO_SERVICO_MAXIMO} caracteres.")

        mao_de_obra = Decimal("0.00")
        if valor_mao_de_obra is not None:
            valor = self._normalizar_valor(valor_mao_de_obra)
            if valor is None:
                erros.append("O valor da mão de obra deve estar entre 0,00 e 99.999.999,99.")
            else:
                mao_de_obra = valor

        itens_ok: List[ItemOS] = []
        vistos = set()
        for n, item in enumerate(itens or (), start=1):
            if not self._eh_inteiro(item.id_produto):
                erros.append(f"Peça {n}: produto inválido.")
                continue
            if item.id_produto in vistos:
                erros.append(f"Peça {n}: o produto está repetido; some as quantidades em uma linha só.")
                continue
            vistos.add(item.id_produto)
            if not self._eh_inteiro(item.quantidade) or not (0 < item.quantidade <= QUANTIDADE_MAXIMA):
                erros.append(f"Peça {n}: a quantidade deve ser um inteiro entre 1 e {QUANTIDADE_MAXIMA}.")
                continue
            if item.preco_unitario is None:  # resolvido depois, com o produto travado
                itens_ok.append(ItemOS(item.id_produto, item.quantidade, None))
                continue
            preco = self._normalizar_valor(item.preco_unitario)
            if preco is None:
                erros.append(f"Peça {n}: o preço deve estar entre 0,00 e 99.999.999,99.")
                continue
            itens_ok.append(ItemOS(item.id_produto, item.quantidade, preco))

        return {
            "quilometragem": quilometragem,
            "descricao": descricao,
            "tipo_servico": tipo_servico,
            "mao_de_obra": mao_de_obra,
            "itens": itens_ok,
        }

    @staticmethod
    def _normalizar_valor(valor: Numero) -> Optional[Decimal]:
        if isinstance(valor, bool) or not isinstance(valor, (int, float, Decimal)):
            return None
        try:
            decimal = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:  # noqa: BLE001  (NaN, infinito...)
            return None
        if decimal < 0 or decimal > VALOR_MAXIMO:
            return None
        return decimal

    def _validar_cliente_e_veiculo(self, id_cliente: int, id_veiculo: int) -> None:
        if self._repo.buscar_cliente(id_cliente) is None:
            raise ValidacaoError("O cliente informado não existe.")
        veiculo = self._repo.buscar_veiculo(id_veiculo)
        if veiculo is None:
            raise ValidacaoError("O veículo informado não existe.")
        if veiculo.id_cliente != id_cliente:
            raise ValidacaoError("O veículo informado não pertence ao cliente escolhido.")

    # ------------------------------------------------------------------
    # Internos: acesso e estoque
    # ------------------------------------------------------------------
    def _obter_travada(self, id_os: int) -> OrdemServico:
        os_ = self._repo.buscar_por_id(id_os, travar=True)
        if os_ is None:
            self._session.rollback()
            raise RegistroNaoEncontradoError(f"Ordem de serviço {id_os} não encontrada.")
        return os_

    def _recarregar(self, id_os: int) -> OrdemServico:
        return self.obter(id_os)

    def _recusar(self, mensagem: str) -> None:
        """Libera as travas e recusa a operação."""
        self._session.rollback()
        raise OperacaoNaoPermitidaError(mensagem)

    def _travar_produtos(self, ids: Sequence[int]) -> dict:
        produtos = self._repo.buscar_produtos_com_trava(ids)
        faltando = sorted(set(ids) - set(produtos))
        if faltando:
            self._session.rollback()
            raise ValidacaoError(
                "Produto(s) inexistente(s): " + ", ".join(str(i) for i in faltando) + "."
            )
        return produtos

    def _resolver_precos(
        self, itens: Sequence[ItemOS], produtos: dict, gravados: Dict[int, Decimal]
    ) -> List[ItemOS]:
        """
        Preenche o preço das peças que vieram sem preço: primeiro o já gravado na
        OS (edição), depois o preço de venda do produto. Sem nenhum dos dois, a
        operação é recusada e nada é gravado.
        """
        finais: List[ItemOS] = []
        erros: List[str] = []
        for item in itens:
            preco = item.preco_unitario
            if preco is None:
                preco = gravados.get(item.id_produto)
            if preco is None:
                preco = produtos[item.id_produto].preco_venda
            if preco is None:
                erros.append(
                    f"“{produtos[item.id_produto].nome}”: informe o preço; o produto ainda "
                    "não tem preço de venda (registre uma compra ou defina o preço no cadastro)."
                )
                continue
            finais.append(ItemOS(item.id_produto, item.quantidade, preco))
        if erros:
            self._session.rollback()  # libera as travas
            raise ValidacaoError(erros)
        return finais

    def _baixar_estoque(self, quantidades: Dict[int, int], produtos: dict) -> None:
        self._ajustar_estoque(quantidades, produtos, sinal=-1)

    def _ajustar_estoque(self, deltas: Dict[int, int], produtos: dict, sinal: int = -1) -> None:
        """
        Aplica os deltas de CONSUMO ao saldo: consumo positivo diminui o saldo,
        negativo devolve. Se algum produto ficar negativo, nada é gravado e a
        mensagem lista todas as peças com saldo insuficiente.
        """
        faltas = []
        for id_produto, delta in sorted(deltas.items()):
            produto = produtos[id_produto]
            novo = produto.quantidade + sinal * delta
            if novo < 0:
                faltas.append(
                    f"“{produto.nome}”: {delta} a retirar, em estoque {produto.quantidade}"
                )
        if faltas:
            self._session.rollback()
            raise OperacaoNaoPermitidaError(
                "Estoque insuficiente para: " + "; ".join(faltas) + "."
            )
        for id_produto, delta in deltas.items():
            produtos[id_produto].quantidade += sinal * delta

    def _confirmar(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise OperacaoNaoPermitidaError(
                "O banco de dados recusou a operação por violar uma regra de integridade."
            ) from exc
        except Exception:
            self._session.rollback()
            raise
