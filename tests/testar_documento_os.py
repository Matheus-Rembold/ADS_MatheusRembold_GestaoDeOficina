"""
Teste da OS impressa / em PDF (decidido em 20/11/2026).

Rode da raiz do projeto, com o venv ativo:
    python testar_documento_os.py

Só LÊ o banco (uma OS do seed). O resto usa um documento montado aqui, sem
banco: o HTML do papel é uma função pura. O PDF é gravado numa pasta
temporária e apagado no fim.
"""
import os
import sys
import tempfile
from datetime import datetime
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from src.apresentacao.documento_os import gerar_pdf, html_documento  # noqa: E402
from src.controle.ordem_servico_controller import (  # noqa: E402
    DocumentoOSDTO, ItemOSDTO, OrdemServicoController, OrdemServicoDTO,
    RegistroNaoEncontradoError, StatusOrdemServico as S,
)
from src.controle.sessao import sessao  # noqa: E402
from src.servico.oficina import DadosOficina  # noqa: E402

resultados = []


def verificar(descricao: str, condicao: bool) -> None:
    resultados.append(bool(condicao))
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}")


def documento(status=S.ANDAMENTO, oficina=DadosOficina(nome="Rembold Motors"), nome="José <Teste> & Filhos",
              placa="ABC1D23") -> DocumentoOSDTO:
    item = ItemOSDTO(1, "Pastilha de freio", 2, Decimal("120.00"), Decimal("77.77"), Decimal("240.00"))
    o = OrdemServicoDTO(
        id_ordem_servico=1035, id_cliente=1, nome_cliente=nome, id_veiculo=1, placa=placa, modelo="Strada",
        quilometragem=85300, descricao_problema="Barulho ao frear", tipo_servico="Freios",
        valor_mao_de_obra=Decimal("150.00"), valor_pecas=Decimal("240.00"), valor_total=Decimal("390.00"),
        status=status, possui_nota_fiscal=False, criado_em=datetime(2026, 11, 7, 9, 30), entregue_em=None,
        itens=(item,), transicoes=(),
    )
    return DocumentoOSDTO(o, "123.456.789-09", "(54) 99999-1234", None, "Fiat", 2020, oficina,
                          datetime(2026, 11, 20, 10, 0))


def main() -> None:
    print("\n1) Conteúdo do documento (sem banco)")
    h = html_documento(documento())
    verificar("título 'ORDEM DE SERVIÇO Nº 1035' (sem quebra de linha)", "ORDEM&nbsp;DE&nbsp;SERVIÇO&nbsp;Nº&nbsp;1035" in h)
    h_orc = html_documento(documento(S.ORCAMENTO))
    verificar("em orçamento o título é 'ORÇAMENTO Nº 1035'", "ORÇAMENTO&nbsp;Nº&nbsp;1035" in h_orc
              and "ORDEM&nbsp;DE" not in h_orc)
    verificar("nome com '<' e '&' é escapado (não quebra o HTML)", "José &lt;Teste&gt; &amp; Filhos" in h)
    verificar("peça, quantidade, preço e subtotal", "Pastilha de freio" in h and "R$ 120,00" in h and "R$ 240,00" in h)
    verificar("mão de obra e total", "R$ 150,00" in h and "R$ 390,00" in h)
    verificar("custo da peça NÃO aparece (o papel vai para o cliente)", "77,77" not in h)
    verificar("veículo, placa e km", "Fiat Strada 2020" in h and "ABC1D23" in h and "85.300 km" in h)
    verificar("'Documento sem valor fiscal' no rodapé", "Documento sem valor fiscal" in h)
    verificar("linhas de assinatura", "Assinatura do cliente" in h and "Responsável pela oficina" in h)
    verificar("endereço do cliente vazio vira '—'", "ENDEREÇO</td><td>—" in h)
    verificar("só o nome da oficina: sem CNPJ nem telefone", "CNPJ" not in h)
    h_cheio = html_documento(documento(oficina=DadosOficina("Rembold Motors", "Rua A, 1", "(54) 3300-0000", "00.000.000/0001-00")))
    verificar("com os dados no .env: endereço, telefone e CNPJ no cabeçalho",
              "Rua A, 1" in h_cheio and "(54) 3300-0000" in h_cheio and "CNPJ 00.000.000/0001-00" in h_cheio)
    verificar("veículo sem placa mostra 'sem placa'", "Placa sem placa" in html_documento(documento(placa="sem placa")))

    print("\n2) Nome do arquivo")
    verificar("OS: 'OS_1035_Jose_Teste_Filhos.pdf' (sem acento, espaço nem símbolo)",
              documento().nome_arquivo == "OS_1035_Jose_Teste_Filhos.pdf")
    verificar("orçamento: começa com 'Orcamento_1035_'",
              documento(S.ORCAMENTO).nome_arquivo.startswith("Orcamento_1035_"))

    print("\n3) PDF")
    with tempfile.TemporaryDirectory() as pasta:
        caminho = os.path.join(pasta, documento().nome_arquivo)
        gerar_pdf(documento(), caminho)
        with open(caminho, "rb") as f:
            inicio = f.read(5)
        verificar(f"PDF gerado ({os.path.getsize(caminho)} bytes, cabeçalho %PDF)",
                  inicio == b"%PDF-" and os.path.getsize(caminho) > 5000)

    print("\n4) Controller (só lê uma OS do seed)")
    sessao.entrar_sistema()
    c = OrdemServicoController()
    primeira = c.listar_pagina().itens[-1]
    d = c.documento(primeira.id_ordem_servico)
    verificar("documento traz OS, CPF e contato do cliente", d.os.id_ordem_servico == primeira.id_ordem_servico
              and len(d.cpf_cliente) == 14 and bool(d.contato_cliente))
    verificar("totais iguais aos da lista", d.os.valor_total == primeira.valor_total)
    try:
        c.documento(-1)
        verificar("OS inexistente -> RegistroNaoEncontradoError", False)
    except RegistroNaoEncontradoError:
        verificar("OS inexistente -> RegistroNaoEncontradoError", True)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} verificações passaram.")
    raise SystemExit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
