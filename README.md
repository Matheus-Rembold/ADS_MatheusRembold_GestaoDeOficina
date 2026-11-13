# Camaro — Sistema de Gerenciamento de Oficina Mecânica

Projeto final da disciplina de Análise e Desenvolvimento de Sistemas — UPF.

## Arquitetura em camadas

A estrutura de pastas espelha a arquitetura descrita no DVP (seção 2.1):

```
src/
├── apresentacao/    # Telas PyQt6 (Camada de Apresentação)
│   └── telas/
├── controle/        # Intermediação entre tela e serviço (Camada de Controle)
├── servico/         # Regras de negócio (Camada de Serviço)
├── persistencia/     # Acesso a dados via SQLAlchemy (Camada de Persistência)
│   ├── models/        # Classes ORM (uma por tabela do banco)
│   └── repositories/  # Padrão Repository — uma classe por entidade
├── integracao/       # APIs externas: WhatsApp e NF-e/NFS-e (Camada de Integração)
├── config/          # Configuração de banco e variáveis de ambiente
└── main.py          # Ponto de entrada da aplicação

tests/               # Testes automatizados (espelha a estrutura de src/)
```

**Regra de dependência:** cada camada só pode chamar a camada imediatamente
abaixo dela. `apresentacao` nunca acessa `persistencia` diretamente, por
exemplo — sempre passa por `controle` e `servico`. Isso mantém a lógica de
negócio testável sem precisar abrir a interface gráfica..

## Como rodar o ambiente

```bash
# 1. Criar e ativar o ambiente virtual
python -m venv venv
venv\Scripts\activate        # Windows
venv\Scripts\Activate.ps1

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
copy .env.example .env       # Windows
cp .env.example .env         # Linux/Mac
# edite o .env com os dados reais do seu PostgreSQL local (banco OficinaBd)

# 4. Executar a aplicação
python -m src.main

# Autodiagnóstico (banco, telas, gráficos e PDF), sem abrir janela
python -m src.main --verificar
```

O `.env` é lido da raiz do projeto. Para ver todo o SQL no console, use `DB_ECHO=true` no `.env`.
Erros ficam registrados em `%LOCALAPPDATA%\Camaro\camaro.log`.

## Gerar o executável (Windows)

```bash
pyinstaller camaro.spec --noconfirm --clean
```

O resultado é a pasta `dist\Camaro\` (cerca de 82 MB), com o `Camaro.exe` e a pasta `_internal`.
Para instalar em outro computador:

1. Instale o PostgreSQL e crie o banco com o `BancoDeDadods.sql` (instalação nova).
2. Copie a pasta `dist\Camaro\` inteira.
3. Ao lado do `Camaro.exe`, crie o `.env` a partir de `_internal\.env.example` com os dados do PostgreSQL.
4. Rode `Camaro.exe --verificar` e confira o resultado no log (`%LOCALAPPDATA%\Camaro\camaro.log`).
   O código de saída é 0 quando está tudo certo.
5. Abra o `Camaro.exe`.

A receita do build está comentada em `camaro.spec`: modo pasta (onedir), sem console, sem o `.env`
dentro do pacote e sem as DLLs que o sistema não usa.

## Cronograma (seção 3.1 do DVP)

Ver `requirements-and-architecture` — desenvolvimento segue a ordem de
dependência entre requisitos: RF01 → RF02 → RF03 → RF09 → RF04 → RF05 →
RF06 → RF07/RF08 → empacotamento final.
