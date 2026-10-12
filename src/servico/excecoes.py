"""
Exceções de negócio do sistema Camaro.

A Camada de Serviço levanta estas exceções quando uma regra de negócio é
violada. A Camada de Apresentação (telas PyQt6) captura ErroDeNegocio e
mostra a mensagem ao usuário, sem precisar conhecer detalhes de banco.

Hierarquia:
    ErroDeNegocio
    ├── ValidacaoError            (dado ausente ou inválido)
    ├── RegistroDuplicadoError    (ex.: CPF já cadastrado)
    ├── RegistroNaoEncontradoError
    └── OperacaoNaoPermitidaError (ex.: excluir cliente com OS em andamento)
"""
from __future__ import annotations

from typing import List, Union


class ErroDeNegocio(Exception):
    """Classe base: tudo o que a tela pode exibir como mensagem ao usuário."""


class ValidacaoError(ErroDeNegocio):
    """Um ou mais campos ausentes ou inválidos (critério de aceite da HU01)."""

    def __init__(self, erros: Union[str, List[str]]) -> None:
        self.erros: List[str] = [erros] if isinstance(erros, str) else list(erros)
        super().__init__("; ".join(self.erros))


class RegistroDuplicadoError(ErroDeNegocio):
    """Violação de unicidade (ex.: CPF já cadastrado)."""


class RegistroNaoEncontradoError(ErroDeNegocio):
    """O registro pedido não existe (ex.: editar cliente inexistente, HU02)."""


class OperacaoNaoPermitidaError(ErroDeNegocio):
    """A regra de negócio proíbe a operação (ex.: HU03)."""
