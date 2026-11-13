# Revisão do DVP — Camaro (versão 1.6 → 1.7)

Leitura feita em 08/11/2026 do `DVP_MatheusRembold_TrabalhoFinal_V.Final.docx`, comparando com o sistema implementado.

**Como usar:** cada bloco cinza é o texto pronto para colar na célula ou no parágrafo indicado no Word. Uma linha do bloco = um parágrafo (ou um item de lista) no Word. Onde o DVP atual já está certo, a seção aparece como **"sem alteração"**.

Legenda: 🔴 diverge do sistema (corrigir) · 🟡 desatualizado/incompleto · 🟢 só revisão de texto · ❓ precisa de decisão sua

---

## 0. Decisões que precisam de você antes de colar

| # | Ponto | Problema | Minha recomendação |
|---|---|---|---|
| ✅1 | **RNF05** ("senhas de acesso devem ser armazenadas com criptografia") | O sistema ainda não tem login. | **Decidido (08/11):** haverá uma tela de login com um único administrador e a senha guardada como hash. O RNF05 fica mantido e ganha mais precisão; texto na seção 1.3.1. O RF10/HU27 do login está na seção 1.4, para colar **depois** que a tela existir. |
| ❓2 | **RF08 / modelo lógico**: uma nota fiscal para **uma** OS ou para **várias**? | O DVP diz "selecionar a(s) ordem(ns)" e "NOTA_FISCAL (1)—(N) ORDEM_SERVICO". O banco tem `ordem_servico.id_nota_fiscal UNIQUE`, ou seja, **uma nota por OS**. | **Uma nota por OS** (1:1), como o banco já está. É o caso comum numa oficina, mais simples de emitir e de cancelar. Os textos abaixo já seguem isso. |
| ❓3 | **Cronograma (3.1)** | As datas do DVP já passaram para vários RFs (RF05 previsto para 26/10 e entregue em 03/11, por exemplo). | Você tinha decidido **não alterar**. Mantive assim. Se a banca perguntar, a resposta é "o cronograma é o planejado; o histórico do Git mostra o realizado". |

---

## 1. Seções a alterar

### Capa e histórico de alterações 🟡

**Histórico de alterações**: acrescentar estas linhas na tabela (ajuste a data para o dia em que colar):

```
1.7 | Atualização de RF01, RF03, RF04, RF05, RF06 e RF09 e das histórias de usuário conforme a implementação; preço de venda com markup de 20% | Matheus Rembold | 08/11/2026
1.8 | Atualização dos requisitos não funcionais, da arquitetura, das ferramentas e do modelo lógico do banco de dados | Matheus Rembold | 08/11/2026
```

---

### 1.2.1 Identificação do Domínio 🟡

O primeiro e o último parágrafo continuam iguais. Substituir a **lista de funcionalidades** por:

```
Gestão de Clientes: cadastro, atualização e exclusão de clientes, contendo nome, idade, CPF, contato e endereço. O CPF é o identificador único do cliente. Cada cliente pode possuir um ou mais veículos vinculados;
Gestão de Veículos: cadastro, atualização e exclusão de veículos, contendo modelo, marca, ano, motor e placa. Cada veículo pertence a um único cliente e possui histórico de ordens de serviço;
Gestão de Produtos: cadastro, atualização e exclusão de produtos, contendo nome, categoria, prateleira e quantidade mínima, além do custo (último valor pago) e do preço de venda, calculado automaticamente com margem de 20% sobre o custo ou definido manualmente;
Gestão de Estoque: registro e consulta das movimentações de estoque (compra, doação, devolução ao fornecedor, venda fora de ordem de serviço e ajuste por contagem física), com atualização automática da quantidade e do custo dos produtos;
Geração de Ordens de Serviço: criação de ordens de serviço para cada veículo, com peças, mão de obra e controle de situação (somente orçamento, em andamento, pronto, aguardando pagamento e entregue);
Agendamentos: módulo para agendamento de serviços, contendo cliente, veículo, serviço, horário e duração estimada, com limite de dois serviços simultâneos e conversão do agendamento em ordem de serviço;
Emissão de Nota Fiscal: módulo dedicado para emissão de notas fiscais eletrônicas (NF-e/NFS-e) referentes a ordens de serviço entregues, com integração a API externa de emissão.
```

Na lista de diferenciais, trocar o último item por:

```
Geração de gráficos e relatórios com ganhos, gastos e serviços mais prestados em um mês, ano ou período selecionado, com exportação em PDF e CSV.
```

🟢 Na tabela de stakeholders: "Joao" → "João".

---

### RF01 Gerenciar Clientes 🔴

O DVP diz que só se impede a exclusão com OS "em andamento". O sistema impede também quando o cliente tem veículos, OS ou agendamentos (para preservar o histórico).

**Célula "Problema / Necessidades Identificadas + Fluxo Esperado"**: só o Fluxo muda:

```
Fluxo Esperado:
O sistema deve permitir o cadastro de clientes com nome, idade, CPF, contato e endereço.
O CPF é obrigatório, deve ser válido (dígitos verificadores) e não pode se repetir: ele é o identificador único do cliente. O contato é obrigatório, mas pode se repetir (por exemplo, familiares com o mesmo telefone).
O sistema deve permitir a atualização e a exclusão de clientes já cadastrados.
Cada cliente deve poder ter um ou mais veículos vinculados ao seu cadastro.
O sistema deve impedir a exclusão de um cliente que possua veículos, ordens de serviço ou agendamentos vinculados, preservando o histórico de atendimentos.
```

---

### RF02 Gerenciar Veículos 🟡

Último item do Fluxo Esperado: acrescentar uma linha:

```
O sistema deve impedir a exclusão de um veículo que possua ordens de serviço ou agendamentos vinculados.
```

---

### RF03 Gerenciar Produto 🔴

O DVP diz que o produto tem "quantidade disponível" digitada. No sistema a quantidade **não é digitada**: ela vem do estoque (RF09) e das OS. Falta também o preço de venda (orientação da professora).

```
Problema /Necessidades Identificadas:
A oficina não possui controle adequado das peças e produtos disponíveis, o que gera dificuldade para saber a disponibilidade de itens no momento da execução de um serviço e para definir o preço cobrado por cada peça.
Fluxo Esperado:
O sistema deve permitir o cadastro, a atualização e a exclusão de produtos.
Cada produto deve possuir nome (único), categoria, prateleira e quantidade mínima.
A quantidade em estoque não é digitada no cadastro: o produto começa com zero e a quantidade é alterada pelas movimentações de estoque (RF09) e pelas ordens de serviço (RF04).
O sistema deve exibir o custo do produto (valor pago por unidade na compra mais recente), sem permitir sua edição no cadastro.
O sistema deve calcular o preço de venda do produto aplicando uma margem de 20% sobre o custo (markup), recalculando-o a cada nova compra. O usuário pode definir o preço de venda manualmente; nesse caso, novas compras não o alteram e o sistema apenas informa o novo valor sugerido.
O sistema deve exibir a margem efetiva (preço de venda em relação ao custo), destacando quando o preço estiver abaixo do custo.
O sistema deve alertar quando a quantidade de um produto estiver abaixo do mínimo definido.
O sistema deve impedir a exclusão de produtos já utilizados em ordens de serviço ou com movimentações de estoque registradas.
```

> **Para a banca (markup × margem):** custo × 1,20 é um **markup** de 20% (sobre o custo). A margem sobre o preço de venda fica em 16,67% (20 ÷ 120). Por isso o sistema diz "margem sobre o custo".

---

### RF04 Gerenciar Ordens de Serviço 🔴

O DVP tem 4 situações e não fala de preço, mão de obra nem estoque. O sistema tem 5 situações, com regras de estoque e de trava.

```
Problema /Necessidades Identificadas:
É necessário registrar e acompanhar o andamento dos serviços prestados a cada veículo, controlando sua situação desde o orçamento até a entrega, além das peças utilizadas e do valor cobrado.
Fluxo Esperado:
O sistema deve permitir a criação de uma ordem de serviço vinculada a um cliente e a um veículo desse cliente, com tipo de serviço, descrição do problema e quilometragem do veículo.
A ordem de serviço deve possuir as situações: somente orçamento, em andamento, pronto, aguardando pagamento e entregue. A situação "entregue" é a final e registra a data de entrega.
O sistema deve permitir associar produtos do estoque à ordem de serviço. O preço de cada peça vem preenchido com o preço de venda do produto (RF03) e pode ser alterado pelo usuário; preço abaixo do custo gera um aviso, sem bloquear.
O valor total da ordem de serviço é a soma das peças (quantidade × preço) mais o valor da mão de obra, que é um valor único por ordem de serviço.
Em "somente orçamento" o estoque não é alterado. As peças saem do estoque quando a ordem passa para "em andamento", desde que haja quantidade suficiente.
A partir de "pronto" a ordem de serviço não pode mais ser editada; apenas a situação pode ser alterada. Apenas ordens em "somente orçamento" podem ser excluídas.
O sistema deve permitir a consulta do histórico de ordens de serviço por cliente e por veículo.
```

---

### RF05 Gerenciar Agendamentos 🟡

O DVP diz "**pode** permitir até dois serviços". A regra implementada é um limite, e considera a duração do serviço.

```
Fluxo Esperado:
O sistema deve permitir o agendamento de serviços vinculados a um cliente, um veículo e um tipo de serviço, informando data, horário e duração estimada.
O sistema deve exibir um calendário com os dias que possuem agendamentos e a ocupação de cada horário do dia.
O sistema deve permitir no máximo dois serviços simultâneos, considerando a duração estimada de cada um; um terceiro agendamento no mesmo intervalo deve ser bloqueado.
O sistema deve informar o tempo estimado para o serviço ficar pronto (duração estimada).
O sistema deve permitir a edição e o cancelamento de agendamentos; o cancelamento libera o horário.
O sistema deve permitir converter um agendamento em ordem de serviço quando o cliente comparecer.
```

---

### RF06 Gerar Relatórios e Gráficos 🟡

```
Fluxo Esperado:
O sistema deve gerar gráficos de ganhos (entradas) e gastos (saídas) por mês, ou por dia em períodos de até dois meses.
Os ganhos correspondem às ordens de serviço entregues no período, pela data de entrega, somadas às vendas de peças fora de ordem de serviço. Os gastos correspondem às compras de estoque, descontados os valores ressarcidos em devoluções.
O sistema deve exibir também o lucro bruto das ordens de serviço (receita menos o custo das peças utilizadas) e o valor a receber das ordens aguardando pagamento.
O sistema deve exibir os serviços mais prestados em um mês, ano ou período selecionado.
O sistema deve permitir a exportação dos relatórios gerados em PDF e CSV.
```

---

### RF07 Enviar Notificações Automáticas 🟢

Sem alteração por enquanto. Ainda não foi implementado; revisar depois da implementação.

---

### RF08 Emitir Nota Fiscal 🔴 (depende da decisão ❓2)

Duas trocas no Fluxo Esperado:

```
O sistema deve disponibilizar uma página dedicada para emissão de notas fiscais, listando as ordens de serviço entregues que ainda não possuem nota fiscal.
O usuário deve selecionar manualmente a ordem de serviço para a qual deseja emitir a nota fiscal (uma nota fiscal por ordem de serviço).
```

Acrescentar como último item:

```
Após a emissão da nota fiscal, a ordem de serviço não pode mais voltar de situação.
```

---

### RF09 Gerenciar Estoque 🔴

O DVP só prevê "entradas". O sistema registra 5 tipos de movimentação.

```
Problema /Necessidades Identificadas:
A oficina não possui registro das movimentações de produtos (compras, doações, devoluções a fornecedores, vendas fora de ordem de serviço e acertos de contagem), dificultando o controle de custos e a reposição adequada do estoque.
Fluxo Esperado:
O sistema deve permitir registrar movimentações de estoque dos tipos: compra, doação, devolução ao fornecedor, venda fora de ordem de serviço e ajuste por contagem física.
Cada tipo possui campos próprios: a compra exige valor pago e fornecedor; a devolução exige fornecedor; a venda exige o valor recebido (preenchido com o preço de venda × quantidade); o ajuste exige justificativa.
Ao registrar uma movimentação, o sistema deve atualizar automaticamente a quantidade do produto, sem permitir saldo negativo.
Uma compra atualiza o custo do produto (valor pago por unidade na compra mais recente) e, se o preço de venda estiver no modo automático, também o preço de venda (RF03).
No ajuste, o usuário informa a quantidade contada na prateleira e o sistema calcula a diferença.
O produto deve estar previamente cadastrado (RF03).
Movimentações apenas são registradas e consultadas: não podem ser editadas nem excluídas; um erro é corrigido com um ajuste.
O consumo de peças nas ordens de serviço é registrado na própria ordem (RF04) e não é uma movimentação de estoque.
O sistema deve manter o histórico de movimentações, com filtro por produto, fornecedor, tipo e período.
```

> **Pergunta prevista da banca:** "por que o RF09 não controla todas as saídas?" Resposta: as saídas por serviço já ficam registradas na OS, com peça, quantidade, preço e custo. Duplicar isso como movimentação criaria duas fontes para o mesmo fato. Os tipos de saída do RF09 (venda por fora, devolução, ajuste) cobrem as saídas que **não** passam por uma OS.

---

### 1.3.1 Requisitos Não Funcionais

**RNF04** 🟡 (deixar verificável):

```
Os dados pessoais dos clientes (nome, CPF, contato e endereço) devem ser armazenados apenas no banco de dados local da oficina, protegido por senha, e só devem ser enviados a serviços externos quando necessário à funcionalidade (por exemplo, o telefone para a mensagem via WhatsApp), em conformidade com a LGPD.
```

**RNF05** 🟡 (o login vai existir; o texto fica mais preciso):

```
O acesso ao sistema deve exigir usuário e senha. A senha deve ser armazenada apenas na forma de hash criptográfico com salt, nunca em texto puro. As credenciais de acesso ao banco de dados não devem ser armazenadas no código-fonte: devem ficar em um arquivo de configuração (.env) mantido fora do pacote de instalação e do controle de versão.
```

> **Para a banca:** senha não se "criptografa" (criptografia é reversível); guarda-se um **hash com salt**, que não pode ser desfeito. No login, o sistema calcula o hash da senha digitada e compara. Se o banco vazar, as senhas não aparecem.

### 1.4 Requisito novo do login — colar SÓ depois que a tela existir 🆕

O Fluxo e a HU abaixo seguem o que você descreveu: um administrador, usuário e senha. Os detalhes finais saem do planejamento da tela; ajusto este texto quando ela estiver pronta.

**RF10 Autenticar Usuário** (Importância: essencial · Prioridade: 1 · Dependência: não se aplica)

```
Problema /Necessidades Identificadas:
O sistema guarda dados pessoais de clientes e informações financeiras da oficina, e não deve ser acessado por qualquer pessoa que use o computador.
Fluxo Esperado:
O sistema deve exigir usuário e senha ao ser aberto, antes de exibir qualquer tela.
O sistema possui um único usuário administrador.
A senha deve ser armazenada como hash com salt, nunca em texto puro (RNF05).
Em caso de usuário ou senha incorretos, o sistema deve exibir uma mensagem genérica, sem informar qual dos dois está errado.
```

**UC10 — HU27 Entrar no sistema**

```
História: HU27 – Entrar no sistema
Descrição: COMO Administrador/Gerente, QUERO informar usuário e senha ao abrir o sistema, PARA que apenas pessoas autorizadas acessem os dados da oficina.
Regras de Negócio: Apenas o usuário administrador cadastrado pode acessar o sistema. A senha é conferida pelo hash armazenado.
Critérios de Aceite: Com usuário e senha corretos, o sistema abre a tela principal. Com dados incorretos, exibe mensagem de erro e permanece na tela de login.
```

Ao colar o RF10, acrescente o **UC10** também no diagrama de casos de uso e a tabela de usuário no modelo lógico.

**RNF06** 🟢 (acrescentar a evidência ao final do texto atual):

```
Medição realizada com 50 mil ordens de serviço: as consultas dos relatórios levaram de 14 ms a 325 ms.
```

**RNF07** 🟡

```
O sistema deve ser compatível com o sistema operacional Windows. O processo de implantação deve contemplar o executável da aplicação gerado via PyInstaller (pasta com o Camaro.exe), o arquivo de configuração .env ao lado do executável e a instalação do PostgreSQL na máquina, configurado como serviço de inicialização automática do Windows, garantindo que o banco de dados esteja disponível localmente antes da execução do sistema. O executável deve oferecer um modo de autodiagnóstico (Camaro.exe --verificar) para conferir a instalação.
```

RNF01, RNF02, RNF03 e RNF08: sem alteração.

---

## 2. Histórias de usuário

Nos UCs, cada história aparece duas vezes na tabela do Word: num bloco corrido e nas linhas separadas (História / Descrição / Regras / Critérios). **Atualize as duas versões**, ou apague o bloco corrido se ele for só sobra de formatação.

### UC01 — HU01 Cadastrar cliente 🔴
```
Descrição: COMO Administrador/Gerente, QUERO cadastrar um novo cliente informando nome, idade, CPF, contato e endereço, PARA manter um registro centralizado dos clientes atendidos pela oficina.
Regras de Negócio: O nome, o CPF e o contato são campos obrigatórios. O CPF deve ser válido e único: não é permitido cadastrar dois clientes com o mesmo CPF. O contato pode se repetir.
Critérios de Aceite: Cliente é cadastrado com sucesso quando os campos obrigatórios são preenchidos corretamente. Sistema exibe mensagem de erro quando campos obrigatórios estão ausentes, quando o CPF é inválido ou quando o CPF já está cadastrado.
```

### UC01 — HU03 Excluir cliente 🔴
```
Regras de Negócio: O sistema não deve permitir a exclusão de clientes que possuam veículos, ordens de serviço ou agendamentos vinculados, preservando o histórico.
Critérios de Aceite: Cliente sem vínculos é excluído com sucesso. Sistema exibe mensagem explicando o motivo quando a exclusão é bloqueada.
```

### UC02 — HU05 Consultar histórico do veículo 🟢
```
Critérios de Aceite: Sistema exibe a lista de ordens de serviço associadas ao veículo, da mais recente para a mais antiga.
```

### UC02 — HU06 Atualizar/excluir veículo 🟡
```
Regras de Negócio: Não deve ser permitido excluir um veículo que possua ordens de serviço ou agendamentos vinculados.
Critérios de Aceite: Dados do veículo são atualizados com sucesso. Exclusão é bloqueada, com mensagem explicativa, quando há ordens de serviço ou agendamentos vinculados.
```

### UC03 — HU07 Cadastrar produto 🔴 (o DVP fala em "tipo" e "foto", que não existem)
```
Descrição: COMO Administrador/Gerente, QUERO cadastrar um novo produto informando nome, categoria, prateleira e quantidade mínima, PARA manter o controle dos itens disponíveis na oficina.
Regras de Negócio: O nome é obrigatório e não pode se repetir (sem diferenciar maiúsculas e minúsculas). O produto começa com quantidade zero; a quantidade entra pelas movimentações de estoque (RF09).
Critérios de Aceite: Produto é cadastrado e passa a aparecer na listagem de produtos. Sistema impede o cadastro de nome repetido.
```

### UC03 — HU08 Atualizar/editar produto 🟡
```
Regras de Negócio: Nome, categoria, prateleira, quantidade mínima e preço de venda podem ser alterados. A quantidade em estoque e o custo não são editáveis no cadastro: são atualizados pelas movimentações de estoque e pelas ordens de serviço.
Critérios de Aceite: Alterações são salvas e refletidas na consulta do produto.
```

### UC03 — HU09 Receber alerta de estoque baixo 🟢
```
Critérios de Aceite: Sistema exibe a situação "Estoque baixo" em destaque quando a quantidade do produto está abaixo do mínimo definido, e informa quantos produtos estão nessa situação.
```

### UC03 — HU25 Definir preço de venda 🆕 (nova história)
```
História: HU25 – Definir preço de venda do produto
Descrição: COMO Administrador/Gerente, QUERO que o preço de venda de cada produto seja calculado a partir do custo, podendo ajustá-lo manualmente, PARA cobrar as peças com margem de lucro sem refazer a conta a cada compra.
Regras de Negócio: No modo automático, o preço de venda é o custo acrescido de 20% (markup) e é recalculado a cada nova compra. No modo manual, o preço informado é mantido nas compras seguintes, e o sistema informa o novo preço sugerido. Produto sem compra registrada não possui preço automático.
Critérios de Aceite: Sistema exibe custo, preço de venda e margem sobre o custo de cada produto. Margem negativa é destacada. Voltar ao modo automático recalcula o preço na hora.
```

### UC04 — HU10 Criar ordem de serviço 🔴 (o DVP diz que inicia em "em andamento")
```
Regras de Negócio: A ordem de serviço deve estar vinculada a um cliente e a um veículo desse cliente, previamente cadastrados. Tipo de serviço, descrição do problema e quilometragem são obrigatórios. A ordem de serviço inicia como "somente orçamento" ou "em andamento", conforme escolha do usuário. Quilometragem menor que a da última ordem do veículo gera um aviso, sem bloquear.
Critérios de Aceite: Ordem de serviço é criada com sucesso e vinculada corretamente ao cliente e ao veículo selecionados, com o valor total calculado (peças + mão de obra).
```

### UC04 — HU11 Associar produtos à ordem de serviço 🟡
```
Regras de Negócio: O preço da peça vem preenchido com o preço de venda do produto e pode ser alterado. Em "somente orçamento" o estoque não é alterado; ao passar para "em andamento", o sistema verifica se há quantidade suficiente de todas as peças. O preço e o custo da peça ficam gravados na ordem de serviço, de modo que alterações futuras no produto não mudam ordens antigas.
Critérios de Aceite: Produto é associado à ordem de serviço e a quantidade em estoque é atualizada quando a ordem está em andamento. Sistema impede a baixa quando não há quantidade suficiente, listando as peças em falta. Preço abaixo do custo gera aviso.
```

### UC04 — HU12 Atualizar situação da ordem de serviço 🔴
```
Descrição: COMO Administrador/Gerente, QUERO atualizar a situação de uma ordem de serviço, PARA acompanhar o andamento do atendimento até a entrega.
Regras de Negócio: As situações possíveis são: somente orçamento, em andamento, pronto, aguardando pagamento e entregue, nesta ordem. É permitido voltar uma etapa, exceto depois de entregue ou quando a ordem já possui nota fiscal. A partir de "pronto" a ordem não pode mais ser editada. "Entregue" é a situação final e registra a data de entrega.
Critérios de Aceite: Situação é atualizada e refletida na consulta. Sistema oferece apenas as situações permitidas a partir da atual.
```

### UC05 — HU13 Criar agendamento 🟡
```
Regras de Negócio: O sistema não deve permitir mais de dois serviços simultâneos, considerando a duração estimada de cada agendamento. O mesmo veículo não pode ter dois agendamentos no mesmo intervalo. A duração estimada é obrigatória (até 12 horas). Não é permitido agendar no passado.
Critérios de Aceite: Agendamento é criado com sucesso quando o horário está disponível. Sistema bloqueia e exibe mensagem de erro ao tentar agendar em horário lotado.
```

### UC05 — HU15 Editar/cancelar agendamento 🟢
```
Regras de Negócio: Apenas agendamentos na situação "agendado" podem ser editados ou cancelados. Agendamentos cancelados liberam o horário para novos agendamentos.
```

### UC05 — HU26 Converter agendamento em ordem de serviço 🆕 (nova história)
```
História: HU26 – Converter agendamento em ordem de serviço
Descrição: COMO Administrador/Gerente, QUERO transformar um agendamento em ordem de serviço quando o cliente chega à oficina, PARA não digitar novamente os dados do cliente, do veículo e do serviço.
Regras de Negócio: Apenas agendamentos na situação "agendado" podem ser convertidos. A ordem de serviço é criada como "somente orçamento" e o agendamento passa a "concluído", vinculado à ordem criada, na mesma operação.
Critérios de Aceite: Ordem de serviço é criada com os dados do agendamento e o agendamento aparece como concluído.
```

### UC06 — HU16 Visualizar gráficos de ganhos e gastos 🔴
```
Descrição: COMO Administrador/Gerente, QUERO visualizar gráficos de ganhos e gastos por mês, PARA acompanhar o desempenho financeiro da oficina.
Regras de Negócio: Os ganhos são baseados nas ordens de serviço com situação "entregue", pela data de entrega, somadas às vendas de peças fora de ordem de serviço. Os gastos são as compras de estoque, descontados os ressarcimentos de devolução. Períodos de até dois meses são exibidos por dia; períodos maiores, por mês.
Critérios de Aceite: Sistema exibe o gráfico e os totais (entradas, saídas, saldo, lucro bruto das ordens de serviço e valor a receber) correspondentes ao mês, ano ou período selecionado.
```

### UC06 — HU17 Consultar serviços mais prestados 🔴
```
Regras de Negócio: O relatório considera apenas ordens de serviço com situação "entregue", pela data de entrega, no período selecionado. Tipos de serviço escritos com maiúsculas ou espaços diferentes são agrupados.
Critérios de Aceite: Sistema exibe a listagem dos serviços mais prestados, ordenada por quantidade de ordens de serviço, com o faturamento e o valor médio de cada serviço.
```

### UC06 — HU18 Exportar relatório 🟢
```
Critérios de Aceite: Sistema gera um arquivo PDF ou CSV com os dados do relatório visualizado, informando no cabeçalho o período e o agrupamento utilizados.
```

### UC07 — HU19 Enviar notificação pós-serviço 🔴 (status)
```
Regras de Negócio: A mensagem deve ser enviada apenas para ordens de serviço com situação "entregue", 7 dias após a data de entrega. O envio depende de conexão com a internet no momento da execução.
```

### UC08 — HU20 Consultar ordens disponíveis para faturamento 🔴 (status)
```
Descrição: COMO Administrador/Gerente, QUERO visualizar uma lista de ordens de serviço entregues ainda não faturadas, PARA selecionar quais devem ter nota fiscal emitida.
Regras de Negócio: A listagem deve exibir apenas ordens de serviço com situação "entregue". Ordens de serviço que já possuem nota fiscal não devem aparecer na listagem.
Critérios de Aceite: Sistema exibe corretamente as ordens de serviço entregues e pendentes de faturamento.
```

### UC09 — HU23 Registrar movimentação de estoque 🔴
```
História: HU23 – Registrar movimentação de estoque
Descrição: COMO Administrador/Gerente, QUERO registrar as movimentações de um produto já cadastrado (compra, doação, devolução ao fornecedor, venda fora de ordem de serviço e ajuste por contagem), PARA manter o controle de custos e a quantidade correta em estoque.
Regras de Negócio: O produto deve estar previamente cadastrado. Cada tipo exige seus campos: compra (quantidade, valor pago e fornecedor), devolução (quantidade e fornecedor), venda (quantidade e valor recebido), doação (quantidade) e ajuste (quantidade contada e justificativa). A quantidade do produto é atualizada automaticamente e nunca pode ficar negativa. A compra atualiza o custo do produto. Movimentações não podem ser editadas nem excluídas.
Critérios de Aceite: Movimentação é registrada com sucesso e a quantidade do produto é atualizada automaticamente. A tela mostra o saldo atual e o saldo após a movimentação antes de confirmar. Sistema impede movimentação que deixaria o saldo negativo.
```

### UC09 — HU24 Consultar histórico de movimentações 🟡
```
História: HU24 – Consultar histórico de movimentações de estoque
Descrição: COMO Administrador/Gerente, QUERO consultar o histórico de movimentações, PARA acompanhar compras, saídas e custos ao longo do tempo.
Regras de Negócio: O histórico deve exibir data, produto, tipo, quantidade, valor e fornecedor de cada movimentação, com filtro por texto (produto, fornecedor ou observação), tipo e período.
Critérios de Aceite: Sistema exibe a lista de movimentações filtrada, da mais recente para a mais antiga.
```

> Se a numeração das novas HUs (HU25 no UC03 e HU26 no UC05) incomodar, dá para renumerar. Assim fica mais simples: nenhuma HU existente muda de número, e as referências antigas continuam valendo.

---

## 3. Projeto técnico

### 2.1 Arquitetura Utilizada 🟡

Os cinco itens da lista continuam certos. Acrescentar este parágrafo **depois da lista**:

```
A comunicação entre as camadas segue regras fixas: a camada de apresentação acessa apenas a camada de controle; os controladores abrem a conexão com o banco, acionam os serviços e devolvem à interface apenas objetos de transferência de dados imutáveis (DTOs), nunca os objetos do banco; os serviços concentram as regras de negócio e controlam as transações (gravam tudo ou nada); e os repositórios apenas consultam e gravam dados. Essa separação permite testar as regras de negócio sem abrir a interface: cada módulo possui um script de testes executado contra o PostgreSQL.
```

### 2.2 Ferramentas e Tecnologias 🔴

Substituir as linhas da tabela por:

```
Python | 3.12+ | Linguagem principal de desenvolvimento do sistema
PyQt6 | 6.7 | Framework para construção da interface gráfica desktop
PyQt6-Charts | 6.7 | Gráficos dos relatórios (RF06)
PostgreSQL | 18 | Banco de dados relacional, responsável pelo armazenamento dos dados, executado localmente na máquina da oficina
psycopg2-binary | 2.9 | Driver de conexão entre a aplicação Python e o banco de dados PostgreSQL
SQLAlchemy | 2.0 | ORM utilizado para abstração e manutenção do acesso ao banco de dados
python-dotenv | 1.0 | Leitura do arquivo de configuração .env (credenciais fora do código, RNF05)
Requests | 2.32 | Biblioteca para integração com APIs externas (WhatsApp e NF-e/NFS-e)
PyInstaller | 6.x | Empacotamento da aplicação em executável nativo para Windows (RNF07)
Git / GitHub | — | Controle de versão e hospedagem do código-fonte
```

### 2.3 Modelo Lógico do Banco de Dados 🔴

**Imagem:** gerar de novo no dbdiagram.io colando o arquivo `docs/camaro.dbml` (já está pronto, gerado do schema real).

**Lista de relacionamentos**: substituir por:

```
CLIENTE (1) — (N) VEICULO
CLIENTE (1) — (N) ORDEM_SERVICO
VEICULO (1) — (N) ORDEM_SERVICO
CLIENTE (1) — (N) AGENDAMENTO
VEICULO (1) — (N) AGENDAMENTO
AGENDAMENTO (0,1) — (0,1) ORDEM_SERVICO (ordem de serviço gerada pela conversão do agendamento)
ORDEM_SERVICO (1) — (N) OS_PRODUTO
PRODUTO (1) — (N) OS_PRODUTO
PRODUTO (1) — (N) MOVIMENTACAO_ESTOQUE
NOTA_FISCAL (1) — (0,1) ORDEM_SERVICO
ORDEM_SERVICO (1) — (0,1) NOTIFICACAO
```

Principais mudanças, para citar se perguntarem:
- `ENTRADA_ESTOQUE` virou `MOVIMENTACAO_ESTOQUE` (5 tipos, quantidade com sinal);
- `produto` ganhou `valor_unitario` (custo), `preco_venda` e `preco_venda_manual`;
- `os_produto` guarda `preco_unitario` e `custo_unitario` (cópia do momento);
- `ordem_servico` ganhou `tipo_servico`, `valor_mao_de_obra` e `entregue_em`;
- `agendamento` ganhou `id_ordem_servico`;
- a relação com a nota fiscal passou a ser 1:1.

### 3.1 Cronograma 🟢

Sem alteração (decisão ❓3).

---

## 4. Revisão de texto (fora das seções acima)

- RF04 (texto antigo, se você não substituir tudo): "em que o veículo esta" → "em que o veículo está".
- Domínio, Gestão de Produtos: "nome, categoria prateleira" → "nome, categoria, prateleira" (já corrigido no texto novo).
- HU08 e HU14: "..", e HU17: "..." no fim das frases → um ponto só.
- 1.1.1: há um "." solto depois da lista de técnicas.
