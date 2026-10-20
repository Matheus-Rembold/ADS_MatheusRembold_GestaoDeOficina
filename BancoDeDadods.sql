
-- ------------------------------------------------------------
-- 1. CLIENTE
-- RF01 — nome e contato obrigatórios;
-- ------------------------------------------------------------
CREATE TABLE cliente (
    id_cliente      SERIAL PRIMARY KEY,
    nome            VARCHAR(150) NOT NULL,
    idade           SMALLINT,
    cpf             VARCHAR(14) NOT NULL UNIQUE,
    contato         VARCHAR(20) NOT NULL ,
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
CREATE UNIQUE INDEX uq_produto_nome ON produto (LOWER(nome));

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



-- ============================================================
-- PROJETO CAMARO — Massa de dados de teste
-- ============================================================

-- ------------------------------------------------------------
-- 1. CLIENTE
--------
INSERT INTO cliente (nome, idade, cpf, contato, endereco) VALUES
('Osvaldo Rembold',      58, '111.111.111-11', '(54) 99911-1111', 'Rua das Palmeiras, 120 - Passo Fundo/RS'),
('João da Silva',        41, '222.222.222-22', '(54) 99922-2222', 'Av. Brasil, 480 - Passo Fundo/RS'),
('Maria Fernandes',      35, '333.333.333-33', '(54) 99933-3333', 'Rua 7 de Setembro, 88 - Passo Fundo/RS'),
('Carlos Eduardo Souza', 47, '444.444.444-44', '(54) 99944-4444', 'Rua Uruguai, 210 - Passo Fundo/RS'),
('Fernanda Lima',        29, '555.555.555-55', '(54) 99955-5555', 'Rua Paraná, 33 - Passo Fundo/RS');

-- ------------------------------------------------------------
-- 2. VEICULO
-- ------------------------------------------------------------
INSERT INTO veiculo (id_cliente, modelo, marca, ano, motor, placa) VALUES
(1, 'Camaro SS',   'Chevrolet', 2019, '6.2 V8',  'CAM1A19'),
(1, 'Onix',        'Chevrolet', 2021, '1.0',     'ABC1D23'),
(2, 'Gol',         'Volkswagen',2015, '1.6',     'GOL2B45'),
(2, 'Saveiro',     'Volkswagen',2018, '1.6',     'SAV3C67'),
(3, 'HB20',        'Hyundai',   2020, '1.0',     'HBX4D89'),
(4, 'Corolla',     'Toyota',    2022, '2.0',     'COR5E01');

-- ------------------------------------------------------------
-- 3. PRODUTO
-- ------------------------------------------------------------
INSERT INTO produto (nome, categoria, prateleira, quantidade, quantidade_minima) VALUES
('Óleo de Motor 5W30 (litro)', 'Fluidos',    'A1', 40, 10),
('Filtro de Óleo',             'Filtros',    'A2', 25, 8),
('Pastilha de Freio Dianteira','Freios',     'B1', 2,  6),
('Correia Dentada',            'Motor',      'B3', 12, 4),
('Bateria 60Ah',                'Elétrica',  'C1', 8,  3),
('Amortecedor Dianteiro',       'Suspensão', 'C2', 6,  2);

-- ------------------------------------------------------------
-- 4. NOTA_FISCAL
-- ------------------------------------------------------------
INSERT INTO nota_fiscal (numero, chave_acesso, status, emitida_em) VALUES
('NF-000123', '43260900000000000000550010000001231000001234', 'emitida', '2026-09-15 14:30:00'),
(NULL, NULL, 'pendente', NULL);

-- ------------------------------------------------------------
-- 5. ORDEM_SERVICO
-- ------------------------------------------------------------
INSERT INTO ordem_servico (id_cliente, id_veiculo, id_nota_fiscal, descricao_problema, quilometragem, status, criado_em) VALUES
(1, 1, 1,    'Troca de óleo e revisão geral',            52000, 'pronto',               '2026-09-10 09:00:00'),
(2, 3, NULL, 'Ruído no motor ao acelerar',                88000, 'andamento',            '2026-09-18 10:15:00'),
(3, 5, NULL, 'Orçamento para troca de pastilhas',         31000, 'orcamento',            '2026-09-20 11:00:00'),
(4, 6, NULL, 'Troca de bateria - carro não liga',         15500, 'aguardando_pagamento', '2026-09-19 16:20:00'),
(2, 4, 2,    'Revisão de suspensão dianteira',            60200, 'pronto',               '2026-09-05 08:45:00');

-- ------------------------------------------------------------
-- 6. OS_PRODUTO
-- ------------------------------------------------------------
INSERT INTO os_produto (id_ordem_servico, id_produto, quantidade_utilizada) VALUES
(1, 1, 4),  -- 4 litros de óleo na OS 1
(1, 2, 1),  -- 1 filtro de óleo na OS 1
(2, 4, 1),  -- 1 correia dentada na OS 2
(4, 5, 1),  -- 1 bateria na OS 4
(5, 6, 2);  -- 2 amortecedores na OS 5

-- ------------------------------------------------------------
-- 7. AGENDAMENTO
-- ------------------------------------------------------------
INSERT INTO agendamento (id_cliente, id_veiculo, tipo_servico, data_hora, duracao_estimada_horas, status) VALUES
(3, 5, 'Troca de pastilhas de freio', '2026-09-25 09:00:00', 1.5, 'agendado'),
(4, 6, 'Alinhamento e balanceamento', '2026-09-25 09:00:00', 1.0, 'agendado'),
(1, 2, 'Revisão dos 30.000 km',       '2026-09-26 14:00:00', 2.0, 'agendado'),
(2, 3, 'Diagnóstico de ruído',        '2026-09-22 08:00:00', 1.0, 'cancelado');

-- ------------------------------------------------------------
-- 8. ENTRADA_ESTOQUE
-- ------------------------------------------------------------
INSERT INTO entrada_estoque (id_produto, quantidade, valor_pago, data_compra, fornecedor) VALUES
(1, 50, 850.00,  '2026-08-01', 'Distribuidora Lubrimax'),
(2, 30, 420.00,  '2026-08-01', 'Distribuidora Lubrimax'),
(3, 10, 380.00,  '2026-07-15', 'Auto Peças Sul'),
(3, 4,  160.00,  '2026-09-01', 'Auto Peças Sul'),
(5, 10, 1800.00, '2026-08-20', 'Baterias Center');

-- ------------------------------------------------------------
-- 9. NOTIFICACAO
-- ------------------------------------------------------------
INSERT INTO notificacao (id_ordem_servico, status_envio, data_envio_prevista, data_envio_real) VALUES
(1, 'pendente', '2026-09-17', NULL),
(5, 'enviado',  '2026-09-12', '2026-09-12 10:03:00');