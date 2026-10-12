from src.persistencia.models.cliente import Cliente
from src.persistencia.models.veiculo import Veiculo
from src.persistencia.models.produto import Produto
from src.persistencia.models.nota_fiscal import NotaFiscal
from src.persistencia.models.ordem_servico import OrdemServico
from src.persistencia.models.os_produto import OsProduto
from src.persistencia.models.agendamento import Agendamento
from src.persistencia.models.entrada_estoque import EntradaEstoque
from src.persistencia.models.notificacao import Notificacao

__all__ = [
    "Cliente",
    "Veiculo",
    "Produto",
    "NotaFiscal",
    "OrdemServico",
    "OsProduto",
    "Agendamento",
    "EntradaEstoque",
    "Notificacao",
]