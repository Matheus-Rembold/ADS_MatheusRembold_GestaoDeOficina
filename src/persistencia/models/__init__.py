from src.persistencia.models.cliente import Cliente
from src.persistencia.models.veiculo import Veiculo
from src.persistencia.models.produto import Produto
from src.persistencia.models.nota_fiscal import NotaFiscal
from src.persistencia.models.ordem_servico import OrdemServico, StatusOrdemServico
from src.persistencia.models.os_produto import OsProduto
from src.persistencia.models.agendamento import Agendamento, StatusAgendamento
from src.persistencia.models.movimentacao_estoque import MovimentacaoEstoque, TipoMovimentacao
from src.persistencia.models.notificacao import Notificacao

__all__ = [
    "Cliente",
    "Veiculo",
    "Produto",
    "NotaFiscal",
    "OrdemServico",
    "StatusOrdemServico",
    "OsProduto",
    "Agendamento",
    "StatusAgendamento",
    "MovimentacaoEstoque",
    "TipoMovimentacao",
    "Notificacao",
]