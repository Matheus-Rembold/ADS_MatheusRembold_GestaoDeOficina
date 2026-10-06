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
negócio testável sem precisar abrir a interface gráfica.

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
```

## Cronograma (seção 3.1 do DVP)

Ver `requirements-and-architecture` — desenvolvimento segue a ordem de
dependência entre requisitos: RF01 → RF02 → RF03 → RF09 → RF04 → RF05 →
RF06 → RF07/RF08 → empacotamento final.
