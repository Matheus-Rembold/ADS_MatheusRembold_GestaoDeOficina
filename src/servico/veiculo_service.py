"""
Serviço de Veículo (RF02 - Gerenciar Veículos).

Mesma divisão de responsabilidades do ClienteService:

    Repository  -> "o que existe no banco?"
    Service     -> "o que o negócio permite fazer?" (+ commit/rollback)

Regras deste módulo:
- todo veículo pertence a UM cliente que precisa existir;
- placa válida (antiga ABC1234 ou Mercosul ABC1D23) e única;
- veículo com OS em andamento, OS ou agendamentos não pode ser excluído
  (mesma política do cliente: preservar o histórico da oficina);
- o dono de um veículo com histórico não pode ser trocado, senão as OS
  antigas ficariam apontando para um cliente que não é mais o dono.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.persistencia.models import OrdemServico, Veiculo
from src.persistencia.repositories.cliente_repository import ClienteRepository
from src.persistencia.repositories.veiculo_repository import VeiculoRepository
from src.servico.excecoes import (
    OperacaoNaoPermitidaError,
    RegistroDuplicadoError,
    RegistroNaoEncontradoError,
    ValidacaoError,
)
from src.servico.validadores import normalizar_placa, placa_valida

ANO_MINIMO = 1900


class VeiculoService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = VeiculoRepository(session)
        self._repo_clientes = ClienteRepository(session)

    # ------------------------------------------------------------------
    # HU04 - Cadastrar veículo
    # ------------------------------------------------------------------
    def cadastrar(
        self,
        id_cliente: Optional[int],
        modelo: str,
        marca: str,
        placa: str,
        ano: Optional[int] = None,
        motor: Optional[str] = None,
    ) -> Veiculo:
        dados = self._validar_dados(id_cliente, modelo, marca, placa, ano, motor)

        if self._repo.buscar_por_placa(dados["placa"]) is not None:
            raise RegistroDuplicadoError("Já existe um veículo cadastrado com esta placa.")

        veiculo = self._repo.adicionar(Veiculo(**dados))
        self._confirmar()
        return veiculo

    # ------------------------------------------------------------------
    # HU06 - Atualizar veículo
    # ------------------------------------------------------------------
    def atualizar(
        self,
        id_veiculo: int,
        id_cliente: Optional[int],
        modelo: str,
        marca: str,
        placa: str,
        ano: Optional[int] = None,
        motor: Optional[str] = None,
    ) -> Veiculo:
        veiculo = self.obter(id_veiculo)  # regra: só edita quem já existe
        dados = self._validar_dados(id_cliente, modelo, marca, placa, ano, motor)

        # A placa pode repetir apenas se pertencer ao PRÓPRIO veículo editado.
        outro = self._repo.buscar_por_placa(dados["placa"])
        if outro is not None and outro.id_veiculo != veiculo.id_veiculo:
            raise RegistroDuplicadoError("Já existe outro veículo com esta placa.")

        if dados["id_cliente"] != veiculo.id_cliente and self._repo.possui_vinculos(id_veiculo):
            raise OperacaoNaoPermitidaError(
                "Não é possível trocar o cliente: o veículo possui ordens de serviço "
                "ou agendamentos vinculados ao cliente atual."
            )

        for campo, valor in dados.items():
            setattr(veiculo, campo, valor)  # o UPDATE é gerado no commit
        self._confirmar()
        return veiculo

    # ------------------------------------------------------------------
    # HU06 - Excluir veículo
    # ------------------------------------------------------------------
    def excluir(self, id_veiculo: int) -> None:
        veiculo = self.obter(id_veiculo)

        if self._repo.possui_os_em_andamento(id_veiculo):
            raise OperacaoNaoPermitidaError(
                "Não é possível excluir: o veículo possui ordem de serviço em andamento."
            )
        if self._repo.possui_vinculos(id_veiculo):
            raise OperacaoNaoPermitidaError(
                "Não é possível excluir: o veículo possui ordens de serviço ou "
                "agendamentos vinculados, que fazem parte do histórico da oficina."
            )

        self._repo.remover(veiculo)
        self._confirmar()

    # ------------------------------------------------------------------
    # Consultas (não precisam de commit)
    # ------------------------------------------------------------------
    def obter(self, id_veiculo: int) -> Veiculo:
        veiculo = self._repo.buscar_por_id(id_veiculo)
        if veiculo is None:
            raise RegistroNaoEncontradoError(f"Veículo {id_veiculo} não encontrado.")
        return veiculo

    def buscar_por_placa(self, placa: str) -> Optional[Veiculo]:
        return self._repo.buscar_por_placa(normalizar_placa(placa))

    def buscar(self, termo: str) -> List[Veiculo]:
        return self._repo.buscar(termo.strip())

    def listar(self) -> List[Veiculo]:
        return self._repo.listar_todos()

    def listar_por_cliente(self, id_cliente: int) -> List[Veiculo]:
        return self._repo.listar_por_cliente(id_cliente)

    def historico(self, id_veiculo: int) -> List[OrdemServico]:
        """HU05: histórico de serviços do veículo (mais recentes primeiro)."""
        self.obter(id_veiculo)  # levanta RegistroNaoEncontradoError se não existir
        return self._repo.historico_os(id_veiculo)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _validar_dados(
        self,
        id_cliente: Optional[int],
        modelo: Optional[str],
        marca: Optional[str],
        placa: Optional[str],
        ano: Optional[int],
        motor: Optional[str],
    ) -> Dict[str, Any]:
        """
        Valida e normaliza os dados. Acumula TODOS os erros e levanta uma
        única ValidacaoError, para a tela mostrar tudo de uma vez.
        """
        erros: List[str] = []

        if id_cliente is None:
            erros.append("O cliente responsável é obrigatório.")
        elif self._repo_clientes.buscar_por_id(id_cliente) is None:
            erros.append("O cliente selecionado não existe mais.")

        modelo = (modelo or "").strip()
        if not modelo:
            erros.append("O modelo é obrigatório.")
        elif len(modelo) > 100:
            erros.append("O modelo deve ter no máximo 100 caracteres.")

        marca = (marca or "").strip()
        if not marca:
            erros.append("A marca é obrigatória.")
        elif len(marca) > 100:
            erros.append("A marca deve ter no máximo 100 caracteres.")

        placa_norm = normalizar_placa(placa)
        if not placa_norm:
            erros.append("A placa é obrigatória.")
        elif not placa_valida(placa_norm):
            erros.append("A placa é inválida. Use o formato ABC-1234 ou ABC1D23 (Mercosul).")

        ano_maximo = date.today().year + 1  # modelos do próximo ano já são vendidos
        if ano is not None and not (isinstance(ano, int) and ANO_MINIMO <= ano <= ano_maximo):
            erros.append(f"O ano deve ser um número inteiro entre {ANO_MINIMO} e {ano_maximo}.")

        motor = (motor or "").strip() or None
        if motor is not None and len(motor) > 50:
            erros.append("O motor deve ter no máximo 50 caracteres.")

        if erros:
            raise ValidacaoError(erros)

        return {
            "id_cliente": id_cliente,
            "modelo": modelo,
            "marca": marca,
            "placa": placa_norm,  # sempre salva sem hífen, em maiúsculas
            "ano": ano,
            "motor": motor,
        }

    def _confirmar(self) -> None:
        """
        Faz o commit. Se o banco recusar, desfaz tudo (rollback).

        O IntegrityError é a "última linha de defesa": a checagem de placa
        duplicada acima pode falhar numa corrida entre duas janelas, mas a
        constraint UNIQUE do banco nunca falha.
        """
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise RegistroDuplicadoError(
                "O banco de dados recusou a operação por violar uma restrição "
                "de unicidade ou de vínculo."
            ) from exc
        except Exception:
            self._session.rollback()
            raise
