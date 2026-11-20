# Camaro — Gestão de Oficina Mecânica

Sistema desktop para Windows que organiza o dia a dia de uma oficina mecânica: clientes,
veículos, peças e estoque, ordens de serviço, agenda, mensagens pelo WhatsApp e relatórios
financeiros.

Trabalho final da disciplina de Análise e Desenvolvimento de Sistemas — Universidade de
Passo Fundo (UPF), 2026.
**Autor:** Matheus Rembold · **Orientador:** Prof. Jeangrei Veiga

---

## Funcionalidades

| Requisito | Módulo | O que faz |
|---|---|---|
| RF01 | Clientes | Cadastro com CPF validado e único; opção de aceitar ou não mensagens (LGPD) |
| RF02 | Veículos | Veículos de cada cliente (placa opcional) e histórico de ordens de serviço |
| RF03 | Produtos | Peças com custo, preço de venda automático (custo + 20%) ou manual e margem |
| RF09 | Estoque | Compras, ajustes, doações, vendas por fora e devoluções; alerta de estoque baixo |
| RF04 | Ordens de Serviço | Orçamento → em andamento → serviço realizado → aguardando pagamento → entregue; baixa de estoque, painel de situações e **impressão / PDF** |
| RF05 | Agendamentos | Agenda com no máximo 2 serviços ao mesmo tempo; conversão do agendamento em OS |
| RF06 | Relatórios | Entradas × saídas, lucro bruto, valores a receber e serviços mais prestados; exportação em CSV e PDF |
| RF07 | Notificações | Pós-venda 7 dias após a entrega e lembrete na véspera do agendamento, enviados pelo WhatsApp |
| RF10 | Usuários | Login com senha criptografada (bcrypt), perfis **Administrador** e **Funcionário**, bloqueio após 5 tentativas |
| RF08 | Nota fiscal | *Trabalho futuro* (combinado com o orientador): aparece como "Em breve" no menu |

## Tecnologias

- **Python 3.12+** e **PyQt6** (interface nativa do Windows) com **PyQt6-Charts** (gráficos)
- **PostgreSQL 18** em `localhost` (funciona sem internet), acessado com **SQLAlchemy 2**
- **bcrypt** para as senhas; **PyInstaller** para gerar o executável

## Arquitetura

Arquitetura em camadas. Cada camada só conversa com a camada logo abaixo, então as regras de
negócio podem ser testadas sem abrir a interface.

```
Apresentação (telas)  →  Controle  →  Serviço (regras)  →  Persistência (banco)
                                         ↘ Integração (WhatsApp)
```

```
src/
├── apresentacao/    telas PyQt6, tema visual, gráficos, PDF e impressão
├── controle/        ponte entre tela e serviço; sessão do usuário e controle de permissões
├── servico/         regras de negócio, validações e transações
├── persistencia/    models (uma classe por tabela) e repositories (consultas)
├── integracao/      WhatsApp (link wa.me)
├── config/          .env, conexão com o banco e log
└── main.py          ponto de entrada (login → janela principal)
tests/               testes automatizados contra o PostgreSQL + rodar_todos.py
banco/               BancoDeDados.sql (instalação nova) e migrações numeradas
scripts/             gerar_dados_exemplo.py
docs/                DVP (Documento de Visão do Projeto) e modelo do banco (DBML)
camaro.spec          receita do executável (PyInstaller)
```

## Como instalar e rodar

**Pré-requisitos:** Windows, Python 3.12 ou mais novo e PostgreSQL 18.

```bash
# 1. Ambiente virtual e dependências
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Banco de dados: crie um banco vazio e rode o script de instalação
createdb camaro_db
psql -d camaro_db -f banco/BancoDeDados.sql

# 3. Configuração: copie o modelo e preencha com os dados do seu PostgreSQL
copy .env.example .env

# 4. Abrir o sistema
python -m src.main
```

No **primeiro acesso** o sistema pede para criar o usuário **administrador**; não existe senha
padrão. Os detalhes do banco (instalação nova × atualização com migrações) estão em
[`banco/LEIA-ME.md`](banco/LEIA-ME.md).

### Configuração (`.env`)

| Variável | Para que serve |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Conexão com o PostgreSQL |
| `DB_ECHO` | `true` mostra todo o SQL no console (só para depurar) |
| `OFICINA_NOME` | Nome da oficina nas mensagens do WhatsApp e na OS impressa |
| `OFICINA_ENDERECO`, `OFICINA_TELEFONE`, `OFICINA_CNPJ` | Cabeçalho da OS impressa / PDF (opcionais) |

O `.env` tem a senha do banco e **não vai para o Git**. O log de erros fica em
`%LOCALAPPDATA%\Camaro\camaro.log`.

### Dados de exemplo (opcional)

Para ver as telas e os relatórios com volume, o script abaixo cria cerca de dois anos de
movimento (clientes, OS, estoque, agenda e notificações), todo marcado com "(exemplo)":

```bash
python -m scripts.gerar_dados_exemplo            # cria (~1 min)
python -m scripts.gerar_dados_exemplo --remover  # apaga tudo o que criou
```

## Testes

Os testes rodam contra o PostgreSQL de verdade e limpam o que criam. Para rodar todos e ver o
placar:

```bash
python -m tests.rodar_todos
python -m tests.rodar_todos os notificacao   # só alguns, pelo nome
```

São 15 testes e mais de 700 verificações das regras de negócio. O autodiagnóstico confere
conexão, telas, gráficos e geração de PDF sem abrir a janela:

```bash
python -m src.main --verificar
```

## Gerar o executável

```bash
pyinstaller camaro.spec --noconfirm --clean
```

O resultado é a pasta `dist\Camaro\`, com o `Camaro.exe`. Para usar em outro computador:
instale o PostgreSQL, crie o banco com `banco/BancoDeDados.sql`, copie a pasta `dist\Camaro\`,
crie o `.env` ao lado do `Camaro.exe` (a partir do `.env.example`) e rode
`Camaro.exe --verificar` para conferir a instalação.

## Algumas decisões de projeto

- **PostgreSQL local, e não SQLite:** roda no próprio computador da oficina (funciona sem
  internet) e permite, no futuro, várias estações usando o mesmo banco.
- **WhatsApp semiautomático (link wa.me):** o sistema prepara a mensagem e uma pessoa confirma o
  envio. Não tem custo, usa o WhatsApp da própria oficina e não viola os termos de uso (automatizar
  o WhatsApp Web pode bloquear o número).
- **Preço de venda por markup:** custo + 20% (20% de markup = 16,67% de margem sobre a venda).
- **Nome na tela separado do valor no banco:** por exemplo, a situação gravada como `pronto`
  aparece como "Serviço realizado". Trocar o texto não exige mudar dados.
- **Segurança:** senhas só como hash bcrypt; as permissões são conferidas no controle a cada
  operação, e não apenas escondendo itens do menu.

A documentação completa (requisitos, casos de uso, histórias de usuário e modelo do banco)
está no DVP, em [`docs/`](docs/).
