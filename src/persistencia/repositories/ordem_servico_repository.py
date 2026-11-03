"""
Repository de Ordem de Serviço (RF04).

Mesmo padrão dos outros repositories: a Session vem de fora e nenhum método
faz commit (só flush); o commit é do serviço.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from src.persistencia.models import (
    Cliente,
    OrdemServico,
    OsProduto,
    Produto,
    StatusOrdemServico,
    Veiculo,
)


class OrdemServicoRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def adicionar(self, os_: OrdemServico) -> OrdemServico:
        self._session.add(os_)
        self._session.flush()
        return os_

    def remover(self, os_: OrdemServico) -> None:
        self._session.delete(os_)
        self._session.flush()

    def flush(self) -> None:
        self._session.flush()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def _base(self):
        # joinedload nos "para um" e selectinload nas peças: evita N+1
        return select(OrdemServico).options(
            joinedload(OrdemServico.cliente),
            joinedload(OrdemServico.veiculo),
            selectinload(OrdemServico.os_produtos).joinedload(OsProduto.produto),
        )

    def buscar_por_id(self, id_os: int, travar: bool = False) -> Optional[OrdemServico]:
        """Com travar=True a linha da OS fica bloqueada (FOR UPDATE) até o fim da transação."""
        stmt = self._base().where(OrdemServico.id_ordem_servico == id_os)
        if travar:
            # FOR UPDATE não combina com o outer join: trava só a tabela da OS
            stmt = stmt.with_for_update(of=OrdemServico).execution_options(populate_existing=True)
        return self._session.scalars(stmt).unique().first()

    def listar(
        self, termo: str = "", status: Optional[StatusOrdemServico] = None
    ) -> List[OrdemServico]:
        stmt = (
            self._base()
            .join(OrdemServico.cliente)
            .join(OrdemServico.veiculo)
        )
        if termo:
            like = [
                Cliente.nome.icontains(termo, autoescape=True),
                Veiculo.placa.icontains(termo, autoescape=True),
                Veiculo.modelo.icontains(termo, autoescape=True),
                OrdemServico.tipo_servico.icontains(termo, autoescape=True),
                OrdemServico.descricao_problema.icontains(termo, autoescape=True),
            ]
            if termo.isdigit():
                like.append(OrdemServico.id_ordem_servico == int(termo))
            stmt = stmt.where(or_(*like))
        if status is not None:
            stmt = stmt.where(OrdemServico.status == status)
        stmt = stmt.order_by(OrdemServico.criado_em.desc(), OrdemServico.id_ordem_servico.desc())
        return list(self._session.scalars(stmt).unique().all())

    def listar_por_veiculo(self, id_veiculo: int) -> List[OrdemServico]:
        stmt = (
            self._base()
            .where(OrdemServico.id_veiculo == id_veiculo)
            .order_by(OrdemServico.criado_em.desc(), OrdemServico.id_ordem_servico.desc())
        )
        return list(self._session.scalars(stmt).unique().all())

    def ultima_quilometragem(
        self, id_veiculo: int, ignorar_os: Optional[int] = None
    ) -> Optional[int]:
        """Maior quilometragem já registrada em OS deste veículo."""
        stmt = select(func.max(OrdemServico.quilometragem)).where(
            OrdemServico.id_veiculo == id_veiculo
        )
        if ignorar_os is not None:
            stmt = stmt.where(OrdemServico.id_ordem_servico != ignorar_os)
        return self._session.scalar(stmt)

    def listar_tipos_servico(self) -> List[str]:
        """Tipos de serviço já usados em OS e agendamentos (sugestões da tela)."""
        from src.persistencia.models import Agendamento

        de_os = select(OrdemServico.tipo_servico).where(OrdemServico.tipo_servico.is_not(None))
        de_ag = select(Agendamento.tipo_servico).where(Agendamento.tipo_servico.is_not(None))
        valores = self._session.scalars(de_os.union(de_ag)).all()
        return sorted({v.strip() for v in valores if v and v.strip()}, key=str.lower)

    def buscar_produtos_com_trava(self, ids: Sequence[int]) -> dict:
        """Trava os produtos (FOR UPDATE) SEMPRE em ordem de id, evitando deadlock."""
        if not ids:
            return {}
        stmt = (
            select(Produto)
            .where(Produto.id_produto.in_(sorted(set(ids))))
            .order_by(Produto.id_produto)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {p.id_produto: p for p in self._session.scalars(stmt).all()}

    def buscar_cliente(self, id_cliente: int) -> Optional[Cliente]:
        return self._session.get(Cliente, id_cliente)

    def buscar_veiculo(self, id_veiculo: int) -> Optional[Veiculo]:
        return self._session.get(Veiculo, id_veiculo)

    def listar_veiculos_do_cliente(self, id_cliente: int) -> List[Veiculo]:
        stmt = select(Veiculo).where(Veiculo.id_cliente == id_cliente).order_by(Veiculo.placa)
        return list(self._session.scalars(stmt).all())

    def listar_produtos(self) -> List[Produto]:
        return list(self._session.scalars(select(Produto).order_by(func.lower(Produto.nome))).all())
