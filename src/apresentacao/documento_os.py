"""
OS impressa e em PDF (decidido em 20/11/2026).

O papel é montado UMA vez (HTML num QTextDocument) e serve para as duas
saídas: a impressora (com pré-visualização) e o arquivo PDF. Assim o que se
imprime e o que se salva são sempre iguais. Nenhuma biblioteca nova: tudo do
próprio Qt (QtPrintSupport), funcionando offline (RNF03).

Conteúdo (A4): cabeçalho com os dados da oficina (.env), título conforme a
situação ("ORÇAMENTO" ou "ORDEM DE SERVIÇO"), cliente, veículo, serviço,
problema, peças com preço cobrado, mão de obra, total, linhas de assinatura e
"Documento sem valor fiscal" (a nota fiscal é o RF08). Sem custo nem margem.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QMarginsF, QStandardPaths, QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrintPreviewDialog, QPrinter
from typing import Callable

from PyQt6.QtWidgets import QFileDialog, QMenu, QPushButton, QWidget

from src.apresentacao.componentes import aviso, confirmar, erro_inesperado, formatar_moeda
from src.apresentacao.tema import BORDA, LARANJA, TEXTO, TEXTO_SUAVE
from src.controle.ordem_servico_controller import DocumentoOSDTO, ErroDeNegocio, OrdemServicoController

MARGEM_MM = 15


def _t(texto) -> str:
    """Texto seguro para o HTML (nome com '<', '&' etc. não quebra o documento)."""
    return escape(str(texto)) if texto not in (None, "") else "—"


def _km(valor: Optional[int]) -> str:
    return "—" if valor is None else f"{valor:,} km".replace(",", ".")


def html_documento(doc: DocumentoOSDTO) -> str:
    """O papel em HTML (o subconjunto que o Qt desenha). Função pura: testável sem tela."""
    o, of = doc.os, doc.oficina
    contatos = " · ".join(_t(x) for x in (of.endereco, of.telefone) if x)
    cnpj = f"CNPJ {_t(of.cnpj)}" if of.cnpj else ""
    data = o.criado_em.strftime("%d/%m/%Y")
    entrega = f"<br>Entregue em {o.entregue_em:%d/%m/%Y}" if o.entregue_em else ""
    titulo = f"{doc.titulo} Nº {o.id_ordem_servico}".replace(" ", "&nbsp;")  # nunca quebra a linha

    veiculo = " ".join(x for x in (doc.marca, o.modelo, str(doc.ano) if doc.ano else "") if x)
    linhas_pecas = "".join(
        f"<tr><td>{_t(i.nome_produto)}</td>"
        f"<td align='center'>{i.quantidade}</td>"
        f"<td align='right'>{formatar_moeda(i.preco_unitario)}</td>"
        f"<td align='right'>{formatar_moeda(i.subtotal)}</td></tr>"
        for i in o.itens
    ) or f"<tr><td colspan='4' style='color:{TEXTO_SUAVE}'>Nenhuma peça.</td></tr>"

    rotulo = f"style='color:{TEXTO_SUAVE}; font-size:8pt; font-weight:bold;'"
    return f"""
<html><body style="color:{TEXTO}; font-size:10pt;">
<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="48%" valign="top">
      <span style="font-size:16pt; font-weight:bold; color:{LARANJA};">{_t(of.nome or "Oficina")}</span><br>
      <span style="color:{TEXTO_SUAVE};">{contatos}{"<br>" if contatos and cnpj else ""}{cnpj}</span>
    </td>
    <td width="52%" align="right" valign="top">
      <span style="font-size:14pt; font-weight:bold;">{titulo}</span><br>
      Data: {data}<br>Situação: {_t(o.status.rotulo)}{entrega}
    </td>
  </tr>
</table>
<hr style="border:0; height:1px; background:{BORDA};">

<table width="100%" cellpadding="3" cellspacing="0">
  <tr><td width="18%" {rotulo}>CLIENTE</td>
      <td>{_t(o.nome_cliente)} · CPF {_t(doc.cpf_cliente)} · {_t(doc.contato_cliente)}</td></tr>
  <tr><td {rotulo}>ENDEREÇO</td><td>{_t(doc.endereco_cliente)}</td></tr>
  <tr><td {rotulo}>VEÍCULO</td><td>{_t(veiculo)} · Placa {_t(o.placa)} · {_km(o.quilometragem)}</td></tr>
  <tr><td {rotulo}>SERVIÇO</td><td>{_t(o.tipo_servico)}</td></tr>
  <tr><td {rotulo} valign="top">PROBLEMA</td><td>{_t(o.descricao_problema)}</td></tr>
</table>

<p style="margin-top:14px; margin-bottom:4px;" {rotulo}>PEÇAS</p>
<table width="100%" cellpadding="5" cellspacing="0" border="1"
       style="border-collapse:collapse; border-color:{BORDA};">
  <tr style="background:#F1F3F5; font-weight:bold;">
    <td width="52%">Peça</td><td width="10%" align="center">Qtd</td>
    <td width="19%" align="right">Preço unit.</td><td width="19%" align="right">Subtotal</td>
  </tr>
  {linhas_pecas}
</table>

<table width="100%" cellpadding="4" cellspacing="0" style="margin-top:8px;">
  <tr><td width="62%"></td><td width="19%" align="right">Peças</td>
      <td width="19%" align="right">{formatar_moeda(o.valor_pecas)}</td></tr>
  <tr><td></td><td align="right">Mão de obra</td>
      <td align="right">{formatar_moeda(o.valor_mao_de_obra)}</td></tr>
  <tr><td></td><td align="right" style="font-size:12pt; font-weight:bold;">TOTAL</td>
      <td align="right" style="font-size:12pt; font-weight:bold;">{formatar_moeda(o.valor_total)}</td></tr>
</table>

<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:56px;">
  <tr>
    <td width="45%" align="center">______________________________<br>Assinatura do cliente</td>
    <td width="10%"></td>
    <td width="45%" align="center">______________________________<br>Responsável pela oficina</td>
  </tr>
</table>

<p style="margin-top:28px; color:{TEXTO_SUAVE}; font-size:8pt;" align="center">
  Documento sem valor fiscal · gerado em {doc.gerado_em:%d/%m/%Y às %H:%M}
</p>
</body></html>
"""


def _documento_qt(doc: DocumentoOSDTO) -> QTextDocument:
    texto = QTextDocument()
    texto.setDefaultFont(QFont("Segoe UI", 10))
    texto.setHtml(html_documento(doc))
    return texto


def _impressora(modo=QPrinter.PrinterMode.HighResolution) -> QPrinter:
    impressora = QPrinter(modo)
    impressora.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    impressora.setPageMargins(QMarginsF(MARGEM_MM, MARGEM_MM, MARGEM_MM, MARGEM_MM), QPageLayout.Unit.Millimeter)
    return impressora


def gerar_pdf(doc: DocumentoOSDTO, caminho: str) -> None:
    """Grava o PDF da OS em `caminho` (usado pela tela e pelos testes)."""
    impressora = _impressora()
    impressora.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    impressora.setOutputFileName(caminho)
    impressora.setDocName(doc.nome_arquivo)
    _documento_qt(doc).print(impressora)


def visualizar_e_imprimir(parent: QWidget, doc: DocumentoOSDTO) -> None:
    """Pré-visualização com o botão de imprimir do próprio Qt (Nielsen: confira antes de gastar papel)."""
    impressora = _impressora()
    impressora.setDocName(doc.nome_arquivo)
    texto = _documento_qt(doc)
    previa = QPrintPreviewDialog(impressora, parent)
    previa.setWindowTitle(f"{doc.titulo.capitalize()} nº {doc.os.id_ordem_servico} — visualizar e imprimir")
    previa.resize(900, 800)
    previa.paintRequested.connect(texto.print)
    previa.exec()


def salvar_pdf(parent: QWidget, doc: DocumentoOSDTO) -> Optional[str]:
    """Pergunta onde salvar (sugere Documentos/<nome>.pdf), grava e oferece abrir. Devolve o caminho."""
    pasta = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or str(Path.home())
    caminho, _filtro = QFileDialog.getSaveFileName(
        parent, "Salvar como PDF", str(Path(pasta) / doc.nome_arquivo), "PDF (*.pdf)")
    if not caminho:
        return None  # cancelou
    if not caminho.lower().endswith(".pdf"):
        caminho += ".pdf"
    try:
        gerar_pdf(doc, caminho)
    except Exception as erro:  # noqa: BLE001
        erro_inesperado(parent, erro, "Não foi possível salvar o PDF.")
        return None
    if confirmar(parent, "PDF salvo", f"O PDF foi salvo em:\n{caminho}\n\nDeseja abri-lo agora?",
                 rotulo_confirmar="Abrir PDF", rotulo_cancelar="Fechar"):
        QDesktopServices.openUrl(QUrl.fromLocalFile(caminho))
    return caminho


class BotaoImprimir(QPushButton):
    """
    "Imprimir ▾" com duas opções: Visualizar e imprimir / Salvar como PDF.
    `id_os()` diz qual OS imprimir (a selecionada na lista ou a aberta na janela).
    O documento é lido do banco na hora: sai sempre como a OS está SALVA.
    """

    def __init__(self, controller: OrdemServicoController, id_os: Callable[[], Optional[int]],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__("Imprimir  ▾", parent)
        self._controller = controller
        self._id_os = id_os
        self.setToolTip("Imprimir ou salvar em PDF a ordem de serviço, como está salva")
        self.clicked.connect(self._abrir_menu)
        self.acao = None  # última opção escolhida (para os testes)

    def _abrir_menu(self) -> None:
        menu = QMenu(self)
        imprimir = menu.addAction("Visualizar e imprimir…")
        pdf = menu.addAction("Salvar como PDF…")
        escolhida = menu.exec(self.mapToGlobal(self.rect().bottomLeft()))
        if escolhida is imprimir:
            self.executar("imprimir")
        elif escolhida is pdf:
            self.executar("pdf")

    def executar(self, acao: str) -> Optional[DocumentoOSDTO]:
        self.acao = acao
        id_os = self._id_os()
        if id_os is None:
            return None
        try:
            doc = self._controller.documento(id_os)  # leitura fresca
        except ErroDeNegocio as erro:
            aviso(self, "Não foi possível imprimir", str(erro))
            return None
        except Exception as erro:  # noqa: BLE001
            erro_inesperado(self, erro, "Não foi possível montar o documento da OS.")
            return None
        if acao == "pdf":
            salvar_pdf(self.window(), doc)
        else:
            visualizar_e_imprimir(self.window(), doc)
        return doc

