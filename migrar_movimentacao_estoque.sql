-- ============================================================
-- RF09: entrada_estoque  ->  movimentacao_estoque (com tipo)
--
-- Rode UMA vez no pgAdmin (Query Tool), no banco OficinaBd JÁ EXISTENTE.
-- Num banco NOVO use o BancoDeDadods.sql atualizado (e NÃO rode este).
--
-- Tudo roda numa transação: se qualquer passo falhar, nada é alterado.
-- As 5 linhas que já existem viram tipo 'compra'.
-- ============================================================
BEGIN;

-- 1) Renomeia a tabela, as colunas e os objetos de apoio
ALTER TABLE entrada_estoque RENAME TO movimentacao_estoque;
ALTER TABLE movimentacao_estoque RENAME COLUMN id_entrada_estoque TO id_movimentacao_estoque;
ALTER TABLE movimentacao_estoque RENAME COLUMN valor_pago TO valor;
ALTER TABLE movimentacao_estoque RENAME COLUMN data_compra TO data_movimentacao;
ALTER SEQUENCE IF EXISTS entrada_estoque_id_entrada_estoque_seq
    RENAME TO movimentacao_estoque_id_movimentacao_estoque_seq;
ALTER INDEX IF EXISTS entrada_estoque_pkey RENAME TO movimentacao_estoque_pkey;
ALTER INDEX IF EXISTS idx_entrada_produto RENAME TO idx_movimentacao_produto;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entrada_estoque_id_produto_fkey') THEN
        ALTER TABLE movimentacao_estoque
            RENAME CONSTRAINT entrada_estoque_id_produto_fkey TO movimentacao_estoque_id_produto_fkey;
    END IF;
END $$;

-- 2) Remove os CHECK antigos (quantidade > 0 e valor_pago >= 0), que não
--    servem mais: agora a quantidade tem sinal. Os nomes são automáticos,
--    então o bloco abaixo remove todos os CHECK da tabela, qualquer que seja o nome.
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT conname FROM pg_constraint
             WHERE conrelid = 'movimentacao_estoque'::regclass AND contype = 'c'
    LOOP
        EXECUTE format('ALTER TABLE movimentacao_estoque DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;

-- 3) Valor e fornecedor deixam de ser obrigatórios para todo tipo
ALTER TABLE movimentacao_estoque ALTER COLUMN valor DROP NOT NULL;
ALTER TABLE movimentacao_estoque ALTER COLUMN fornecedor DROP NOT NULL;

-- 4) Novas colunas. As linhas existentes viram 'compra'.
ALTER TABLE movimentacao_estoque ADD COLUMN tipo VARCHAR(25) NOT NULL DEFAULT 'compra';
ALTER TABLE movimentacao_estoque ALTER COLUMN tipo DROP DEFAULT;
ALTER TABLE movimentacao_estoque ADD COLUMN observacao TEXT;

-- 5) Regras por tipo no banco (última linha de defesa)
ALTER TABLE movimentacao_estoque
    ADD CONSTRAINT ck_mov_estoque_tipo
        CHECK (tipo IN ('compra', 'doacao', 'devolucao_fornecedor', 'venda_avulsa', 'ajuste')),
    ADD CONSTRAINT ck_mov_estoque_quantidade CHECK (quantidade <> 0),
    ADD CONSTRAINT ck_mov_estoque_sinal
        CHECK ((tipo IN ('compra', 'doacao') AND quantidade > 0)
            OR (tipo IN ('devolucao_fornecedor', 'venda_avulsa') AND quantidade < 0)
            OR tipo = 'ajuste'),
    ADD CONSTRAINT ck_mov_estoque_valor CHECK (valor IS NULL OR valor >= 0),
    ADD CONSTRAINT ck_mov_estoque_valor_obrigatorio
        CHECK (tipo NOT IN ('compra', 'venda_avulsa') OR valor IS NOT NULL),
    ADD CONSTRAINT ck_mov_estoque_fornecedor_obrigatorio
        CHECK (tipo NOT IN ('compra', 'devolucao_fornecedor') OR fornecedor IS NOT NULL),
    ADD CONSTRAINT ck_mov_estoque_ajuste_observacao
        CHECK (tipo <> 'ajuste' OR observacao IS NOT NULL);

-- 6) Índice para a consulta por período
CREATE INDEX idx_movimentacao_data ON movimentacao_estoque(data_movimentacao);

COMMIT;
