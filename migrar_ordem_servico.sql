-- ============================================================
-- RF04: Ordens de Serviço (valores, mão de obra, tipo, status "entregue")
--
-- Rode UMA vez no pgAdmin (Query Tool), no banco JÁ EXISTENTE
-- (depois do migrar_movimentacao_estoque.sql).
-- Num banco NOVO use o BancoDeDadods.sql atualizado (e NÃO rode este).
--
-- Tudo roda numa transação: se qualquer passo falhar, nada é alterado.
-- ============================================================
BEGIN;

-- 1) PRODUTO.valor_unitario = valor da compra mais recente ÷ quantidade
ALTER TABLE produto ADD COLUMN valor_unitario NUMERIC(12,4);
ALTER TABLE produto ADD CONSTRAINT ck_produto_valor_unitario
    CHECK (valor_unitario IS NULL OR valor_unitario >= 0);

UPDATE produto p SET valor_unitario = ROUND(m.valor / m.quantidade, 4)
FROM (SELECT DISTINCT ON (id_produto) id_produto, valor, quantidade
      FROM movimentacao_estoque WHERE tipo = 'compra'
      ORDER BY id_produto, data_movimentacao DESC, id_movimentacao_estoque DESC) m
WHERE m.id_produto = p.id_produto;

-- 2) ORDEM_SERVICO: novas colunas e novo status "entregue"
ALTER TABLE ordem_servico ADD COLUMN tipo_servico VARCHAR(150);
ALTER TABLE ordem_servico ADD COLUMN valor_mao_de_obra NUMERIC(10,2) NOT NULL DEFAULT 0;
ALTER TABLE ordem_servico ADD COLUMN entregue_em TIMESTAMP;

-- o CHECK antigo de status tem nome automático: localiza e remove
DO $$
DECLARE c TEXT;
BEGIN
    FOR c IN SELECT conname FROM pg_constraint
             WHERE conrelid = 'ordem_servico'::regclass AND contype = 'c'
               AND pg_get_constraintdef(oid) LIKE '%status%'
    LOOP
        EXECUTE format('ALTER TABLE ordem_servico DROP CONSTRAINT %I', c);
    END LOOP;
END $$;

ALTER TABLE ordem_servico ADD CONSTRAINT ck_ordem_servico_status
    CHECK (status IN ('orcamento', 'andamento', 'pronto', 'aguardando_pagamento', 'entregue'));
ALTER TABLE ordem_servico ADD CONSTRAINT ck_os_valor_mao_de_obra CHECK (valor_mao_de_obra >= 0);
ALTER TABLE ordem_servico ADD CONSTRAINT ck_os_entregue_em
    CHECK ((status = 'entregue') = (entregue_em IS NOT NULL));

-- 3) OS_PRODUTO: preço cobrado e custo (cópia do valor do produto)
ALTER TABLE os_produto ADD COLUMN preco_unitario NUMERIC(10,2) NOT NULL DEFAULT 0;
ALTER TABLE os_produto ALTER COLUMN preco_unitario DROP DEFAULT;
ALTER TABLE os_produto ADD COLUMN custo_unitario NUMERIC(12,4);
ALTER TABLE os_produto ADD CONSTRAINT ck_os_produto_preco CHECK (preco_unitario >= 0);
ALTER TABLE os_produto ADD CONSTRAINT ck_os_produto_custo
    CHECK (custo_unitario IS NULL OR custo_unitario >= 0);

UPDATE os_produto op SET custo_unitario = p.valor_unitario
FROM produto p WHERE p.id_produto = op.id_produto;

COMMIT;
