-- ============================================================
-- PROJETO CAMARO — Sistema de Gerenciamento de Oficina Mecânica
-- Script de criação do banco de dados (PostgreSQL 16.x)
-- Baseado no Modelo Lógico do DVP (seção 2.3)
-- ============================================================


-- ------------------------------------------------------------
-- 1. CLIENTE
-- RF01 — nome e contato obrigatórios; contato não pode duplicar
-- ------------------------------------------------------------
CREATE TABLE cliente (
    id_cliente      SERIAL PRIMARY KEY,
    nome            VARCHAR(150) NOT NULL,
    idade           SMALLINT,
    cpf             VARCHAR(14) UNIQUE,
    contato         VARCHAR(20) NOT NULL UNIQUE,
    endereco        VARCHAR(255),
    criado_em       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 2. VEICULO
-- RF02 — cada veículo pertence a um único cliente; placa única
-- ------------------------------------------------------------
CREATE TABLE veiculo (
    id_veiculo      SERIAL PRIMARY KEY,
    id_cliente      INT NOT NULL REFERENCES cliente(id_cliente),
    modelo          VARCHAR(100) NOT NULL,
    marca           VARCHAR(100) NOT NULL,
    ano             SMALLINT,
    motor           VARCHAR(50),
    placa           VARCHAR(10) NOT NULL UNIQUE,
    criado_em       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 3. PRODUTO
-- RF03 — cadastro de produtos; quantidade_minima habilita o
-- alerta de estoque baixo (HU09)
-- ------------------------------------------------------------
CREATE TABLE produto (
    id_produto        SERIAL PRIMARY KEY,
    nome              VARCHAR(150) NOT NULL,
    categoria         VARCHAR(100),
    prateleira        VARCHAR(50),
    quantidade        INT NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
    quantidade_minima INT NOT NULL DEFAULT 0 CHECK (quantidade_minima >= 0),
    criado_em         TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 4. NOTA_FISCAL
-- RF08 — emitida manualmente; guarda número, chave e status
-- ------------------------------------------------------------
CREATE TABLE nota_fiscal (
    id_nota_fiscal  SERIAL PRIMARY KEY,
    numero          VARCHAR(50),
    chave_acesso    VARCHAR(60),
    status          VARCHAR(20) NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente', 'emitida', 'falha')),
    emitida_em      TIMESTAMP
);

-- ------------------------------------------------------------
-- 5. ORDEM_SERVICO
-- RF04 — vinculada a cliente e veículo; status controlado;
-- id_nota_fiscal fica NULL até a emissão (RF08 é ação manual
-- e posterior, nunca automática no pagamento/conclusão)
-- ------------------------------------------------------------
CREATE TABLE ordem_servico (
    id_ordem_servico    SERIAL PRIMARY KEY,
    id_cliente          INT NOT NULL REFERENCES cliente(id_cliente),
    id_veiculo          INT NOT NULL REFERENCES veiculo(id_veiculo),
    id_nota_fiscal      INT UNIQUE REFERENCES nota_fiscal(id_nota_fiscal),
    descricao_problema  TEXT,
    quilometragem       INT,
    status              VARCHAR(25) NOT NULL DEFAULT 'orcamento'
                            CHECK (status IN ('orcamento', 'andamento', 'pronto', 'aguardando_pagamento')),
    criado_em           TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 6. OS_PRODUTO (associativa N:N entre ORDEM_SERVICO e PRODUTO)
-- RF04/RF09 — produtos usados em uma OS; a quantidade em
-- estoque é debitada por esta ligação
-- ------------------------------------------------------------
CREATE TABLE os_produto (
    id_os_produto       SERIAL PRIMARY KEY,
    id_ordem_servico    INT NOT NULL REFERENCES ordem_servico(id_ordem_servico),
    id_produto          INT NOT NULL REFERENCES produto(id_produto),
    quantidade_utilizada INT NOT NULL CHECK (quantidade_utilizada > 0),
    UNIQUE (id_ordem_servico, id_produto)
);

-- ------------------------------------------------------------
-- 7. AGENDAMENTO
-- RF05 — vinculado a cliente e veículo; até 2 no mesmo horário
-- ------------------------------------------------------------
CREATE TABLE agendamento (
    id_agendamento          SERIAL PRIMARY KEY,
    id_cliente              INT NOT NULL REFERENCES cliente(id_cliente),
    id_veiculo              INT NOT NULL REFERENCES veiculo(id_veiculo),
    tipo_servico            VARCHAR(150) NOT NULL,
    data_hora               TIMESTAMP NOT NULL,
    duracao_estimada_horas  NUMERIC(4,2),
    status                  VARCHAR(20) NOT NULL DEFAULT 'agendado'
                                CHECK (status IN ('agendado', 'cancelado', 'concluido'))
);

-- ------------------------------------------------------------
-- 8. ENTRADA_ESTOQUE
-- RF09 — registro de compras; produto deve já existir (a FK
-- já garante isso, sem necessidade de checagem extra)
-- ------------------------------------------------------------
CREATE TABLE entrada_estoque (
    id_entrada_estoque  SERIAL PRIMARY KEY,
    id_produto          INT NOT NULL REFERENCES produto(id_produto),
    quantidade          INT NOT NULL CHECK (quantidade > 0),
    valor_pago          NUMERIC(10,2) NOT NULL CHECK (valor_pago >= 0),
    data_compra         DATE NOT NULL,
    fornecedor          VARCHAR(150) NOT NULL
);

-- ------------------------------------------------------------
-- 9. NOTIFICACAO
-- RF07 — 0..1 por ORDEM_SERVICO: o UNIQUE na FK garante que
-- uma OS tenha no máximo uma notificação vinculada
-- ------------------------------------------------------------
CREATE TABLE notificacao (
    id_notificacao          SERIAL PRIMARY KEY,
    id_ordem_servico        INT NOT NULL UNIQUE REFERENCES ordem_servico(id_ordem_servico),
    status_envio            VARCHAR(20) NOT NULL DEFAULT 'pendente'
                                CHECK (status_envio IN ('pendente', 'enviado', 'cancelado')),
    data_envio_prevista     DATE,
    data_envio_real         TIMESTAMP
);

-- ------------------------------------------------------------
-- ÍNDICES DE APOIO
-- Colunas usadas com frequência em filtros/joins (RNF06 — consultas
-- em até 3 segundos)
-- ------------------------------------------------------------
CREATE INDEX idx_veiculo_cliente        ON veiculo(id_cliente);
CREATE INDEX idx_os_cliente             ON ordem_servico(id_cliente);
CREATE INDEX idx_os_veiculo             ON ordem_servico(id_veiculo);
CREATE INDEX idx_os_status              ON ordem_servico(status);
CREATE INDEX idx_agendamento_data       ON agendamento(data_hora);
CREATE INDEX idx_entrada_produto        ON entrada_estoque(id_produto);
CREATE INDEX idx_os_produto_produto     ON os_produto(id_produto);