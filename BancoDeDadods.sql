-- Camaro: schema + dados iniciais. Instalação NOVA: rode este arquivo inteiro
-- num banco vazio. O SET abaixo garante os acentos certos em qualquer cliente
-- (o psql do Windows, sem ele, grava "Óleo" corrompido).
SET client_encoding = 'UTF8';


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
    -- valor pago por UNIDADE na compra mais recente (atualizado pelo RF09)
    valor_unitario    NUMERIC(12,4) CONSTRAINT ck_produto_valor_unitario CHECK (valor_unitario IS NULL OR valor_unitario >= 0),
    criado_em         TIMESTAMP NOT NULL DEFAULT NOW(),
    -- preço de venda por unidade: custo × 1,20 (markup) recalculado a cada
    -- compra, ou definido à mão (preco_venda_manual = TRUE). Ficam no fim da
    -- tabela para coincidir com o banco migrado (ALTER TABLE ADD COLUMN acrescenta no fim).
    preco_venda        NUMERIC(10,2) CONSTRAINT ck_produto_preco_venda CHECK (preco_venda IS NULL OR preco_venda >= 0),
    preco_venda_manual BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT ck_produto_preco_manual CHECK (NOT preco_venda_manual OR preco_venda IS NOT NULL)
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
    tipo_servico        VARCHAR(150),
    valor_mao_de_obra   NUMERIC(10,2) NOT NULL DEFAULT 0
                            CONSTRAINT ck_os_valor_mao_de_obra CHECK (valor_mao_de_obra >= 0),
    status              VARCHAR(25) NOT NULL DEFAULT 'orcamento'
                            CONSTRAINT ck_ordem_servico_status
                            CHECK (status IN ('orcamento', 'andamento', 'pronto', 'aguardando_pagamento', 'entregue')),
    criado_em           TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMP NOT NULL DEFAULT NOW(),
    entregue_em         TIMESTAMP,
    CONSTRAINT ck_os_entregue_em CHECK ((status = 'entregue') = (entregue_em IS NOT NULL))
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
    -- preço cobrado por unidade (digitado na OS) e custo = último valor pago na hora
    preco_unitario      NUMERIC(10,2) NOT NULL CONSTRAINT ck_os_produto_preco CHECK (preco_unitario >= 0),
    custo_unitario      NUMERIC(12,4) CONSTRAINT ck_os_produto_custo CHECK (custo_unitario IS NULL OR custo_unitario >= 0),
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
                                CHECK (status IN ('agendado', 'cancelado', 'concluido')),
    -- OS gerada a partir do agendamento (conversão); se a OS for excluída, o vínculo some
    id_ordem_servico        INT UNIQUE REFERENCES ordem_servico(id_ordem_servico) ON DELETE SET NULL,
    CONSTRAINT ck_agendamento_duracao CHECK (duracao_estimada_horas IS NULL OR duracao_estimada_horas > 0)
);

-- ------------------------------------------------------------
-- 8. MOVIMENTACAO_ESTOQUE
-- RF09 — movimentações manuais de estoque (só registro e consulta).
-- tipo: compra, doacao, devolucao_fornecedor, venda_avulsa, ajuste.
-- quantidade COM SINAL: positiva aumenta o saldo do produto, negativa
-- diminui. As regras por tipo ficam nos CHECK abaixo (e também no
-- MovimentacaoEstoqueService, que dá a mensagem amigável).
-- O consumo de peças em OS NÃO é movimentação: fica em os_produto (RF04).
-- ------------------------------------------------------------
CREATE TABLE movimentacao_estoque (
    id_movimentacao_estoque SERIAL PRIMARY KEY,
    id_produto              INT NOT NULL REFERENCES produto(id_produto),
    tipo                    VARCHAR(25) NOT NULL,
    quantidade              INT NOT NULL,
    valor                   NUMERIC(10,2),
    data_movimentacao       DATE NOT NULL,
    fornecedor              VARCHAR(150),
    observacao              TEXT,
    CONSTRAINT ck_mov_estoque_tipo
        CHECK (tipo IN ('compra', 'doacao', 'devolucao_fornecedor', 'venda_avulsa', 'ajuste')),
    CONSTRAINT ck_mov_estoque_quantidade CHECK (quantidade <> 0),
    CONSTRAINT ck_mov_estoque_sinal
        CHECK ((tipo IN ('compra', 'doacao') AND quantidade > 0)
            OR (tipo IN ('devolucao_fornecedor', 'venda_avulsa') AND quantidade < 0)
            OR tipo = 'ajuste'),
    CONSTRAINT ck_mov_estoque_valor CHECK (valor IS NULL OR valor >= 0),
    CONSTRAINT ck_mov_estoque_valor_obrigatorio
        CHECK (tipo NOT IN ('compra', 'venda_avulsa') OR valor IS NOT NULL),
    CONSTRAINT ck_mov_estoque_fornecedor_obrigatorio
        CHECK (tipo NOT IN ('compra', 'devolucao_fornecedor') OR fornecedor IS NOT NULL),
    CONSTRAINT ck_mov_estoque_ajuste_observacao
        CHECK (tipo <> 'ajuste' OR observacao IS NOT NULL)
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
CREATE INDEX idx_movimentacao_produto   ON movimentacao_estoque(id_produto);
CREATE INDEX idx_movimentacao_data      ON movimentacao_estoque(data_movimentacao);
CREATE INDEX idx_os_produto_produto     ON os_produto(id_produto);
-- RF06: os relatórios filtram as OS entregues pelo período de entrega
CREATE INDEX idx_os_entregue_em         ON ordem_servico(entregue_em);



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
INSERT INTO ordem_servico (id_cliente, id_veiculo, id_nota_fiscal, descricao_problema, quilometragem, tipo_servico, valor_mao_de_obra, status, criado_em, entregue_em) VALUES
(1, 1, 1,    'Troca de óleo e revisão geral',            52000, 'Revisão',    120.00, 'entregue',             '2026-09-10 09:00:00', '2026-09-12 17:00:00'),
(2, 3, NULL, 'Ruído no motor ao acelerar',                88000, 'Motor',      250.00, 'andamento',            '2026-09-18 10:15:00', NULL),
(3, 5, NULL, 'Orçamento para troca de pastilhas',         31000, 'Freios',      80.00, 'orcamento',            '2026-09-20 11:00:00', NULL),
(4, 6, NULL, 'Troca de bateria - carro não liga',         15500, 'Elétrica',    50.00, 'aguardando_pagamento', '2026-09-19 16:20:00', NULL),
(2, 4, 2,    'Revisão de suspensão dianteira',            60200, 'Suspensão',  300.00, 'entregue',             '2026-09-05 08:45:00', '2026-09-08 16:30:00');

-- ------------------------------------------------------------
-- 6. OS_PRODUTO
-- ------------------------------------------------------------
INSERT INTO os_produto (id_ordem_servico, id_produto, quantidade_utilizada, preco_unitario) VALUES
(1, 1, 4, 25.00),   -- 4 litros de óleo na OS 1
(1, 2, 1, 30.00),   -- 1 filtro de óleo na OS 1
(2, 4, 1, 180.00),  -- 1 correia dentada na OS 2
(4, 5, 1, 320.00),  -- 1 bateria na OS 4
(5, 6, 2, 290.00);  -- 2 amortecedores na OS 5

-- ------------------------------------------------------------
-- 7. AGENDAMENTO
-- ------------------------------------------------------------
INSERT INTO agendamento (id_cliente, id_veiculo, tipo_servico, data_hora, duracao_estimada_horas, status) VALUES
(3, 5, 'Troca de pastilhas de freio', '2026-09-25 09:00:00', 1.5, 'agendado'),
(4, 6, 'Alinhamento e balanceamento', '2026-09-25 09:00:00', 1.0, 'agendado'),
(1, 2, 'Revisão dos 30.000 km',       '2026-09-26 14:00:00', 2.0, 'agendado'),
(2, 3, 'Diagnóstico de ruído',        '2026-09-22 08:00:00', 1.0, 'cancelado');

-- ------------------------------------------------------------
-- 8. MOVIMENTACAO_ESTOQUE
-- ------------------------------------------------------------
INSERT INTO movimentacao_estoque (id_produto, tipo, quantidade, valor, data_movimentacao, fornecedor) VALUES
(1, 'compra', 50, 850.00,  '2026-08-01', 'Distribuidora Lubrimax'),
(2, 'compra', 30, 420.00,  '2026-08-01', 'Distribuidora Lubrimax'),
(3, 'compra', 10, 380.00,  '2026-07-15', 'Auto Peças Sul'),
(3, 'compra', 4,  160.00,  '2026-09-01', 'Auto Peças Sul'),
(5, 'compra', 10, 1800.00, '2026-08-20', 'Baterias Center');

-- valor_unitario do produto = valor da compra mais recente ÷ quantidade
UPDATE produto p SET valor_unitario = ROUND(m.valor / m.quantidade, 4)
FROM (SELECT DISTINCT ON (id_produto) id_produto, valor, quantidade
      FROM movimentacao_estoque WHERE tipo = 'compra'
      ORDER BY id_produto, data_movimentacao DESC, id_movimentacao_estoque DESC) m
WHERE m.id_produto = p.id_produto;

-- preço de venda automático = custo × 1,20 (markup de 20%); sem custo fica vazio
UPDATE produto SET preco_venda = ROUND(valor_unitario * 1.20, 2)
WHERE valor_unitario IS NOT NULL;

-- custo_unitario das peças já lançadas nas OS (cópia do valor do produto)
UPDATE os_produto op SET custo_unitario = p.valor_unitario
FROM produto p WHERE p.id_produto = op.id_produto;

-- ------------------------------------------------------------
-- 9. NOTIFICACAO
-- ------------------------------------------------------------
INSERT INTO notificacao (id_ordem_servico, status_envio, data_envio_prevista, data_envio_real) VALUES
(1, 'pendente', '2026-09-17', NULL),
(5, 'enviado',  '2026-09-12', '2026-09-12 10:03:00');