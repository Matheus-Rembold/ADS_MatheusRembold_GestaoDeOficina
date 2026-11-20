# Banco de dados do Camaro (PostgreSQL)

## Instalação nova: use só o `BancoDeDados.sql`

1. No pgAdmin, crie um banco vazio (ex.: `camaro_db`).
2. Abra o **Query Tool** nesse banco, carregue o `BancoDeDados.sql` e execute.
   Ele cria todas as tabelas, índices e restrições e um pequeno conjunto de dados iniciais.
3. Configure o `.env` com o nome do banco e abra o sistema: no primeiro acesso ele pede
   para criar o usuário administrador.

Pela linha de comando:

```bash
createdb camaro_db
psql -d camaro_db -f banco/BancoDeDados.sql
```

**Não rode as migrações numa instalação nova**: o `BancoDeDados.sql` já está atualizado.

## Banco que já existia: use as `migracoes/`, na ordem

As migrações levam um banco criado com uma versão antiga do sistema até a versão atual.
Rode **só as que ainda não foram rodadas**, **uma vez cada**, **na ordem do número**:

| Arquivo | O que muda |
|---|---|
| `01_migrar_movimentacao_estoque.sql` | RF09: entrada de estoque vira movimentação (compra, ajuste, doação, venda, devolução) |
| `02_migrar_ordem_servico.sql` | RF04: situações da OS, mão de obra, data de entrega e preço/custo das peças |
| `03_migrar_agendamento.sql` | RF05: duração do agendamento e vínculo com a OS gerada |
| `04_migrar_preco_venda.sql` | RF03: preço de venda (custo + 20%) e preço manual |
| `05_migrar_relatorios.sql` | RF06: índice para os relatórios por período de entrega |
| `06_migrar_usuario.sql` | RF10: tabela de usuários (login e perfis) |
| `07_migrar_notificacao.sql` | RF07: notificações do WhatsApp e aceite de mensagens do cliente |
| `08_migrar_placa_opcional.sql` | RF02: placa do veículo opcional |

Cada migração roda **dentro de uma transação** (`BEGIN` … `COMMIT`): se algum passo falhar,
nada é alterado.

## Regra do projeto

Toda mudança de estrutura atualiza **os dois**: o `BancoDeDados.sql` (instalação nova) e uma
migração nova numerada. Depois, confere-se que um banco novo e um banco migrado ficam com a
estrutura **idêntica** (`pg_dump --schema-only` dos dois + comparação).
