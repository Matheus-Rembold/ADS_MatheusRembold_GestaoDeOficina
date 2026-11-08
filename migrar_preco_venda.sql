-- ============================================================
-- RF03/RF09/RF04: preço de venda do produto (custo + markup de 20%)
--
-- Rode UMA vez no pgAdmin (Query Tool), no banco JÁ EXISTENTE
-- (depois do migrar_agendamento.sql).
-- Num banco NOVO use o BancoDeDadods.sql atualizado (e NÃO rode este).
--
-- Tudo roda numa transação: se qualquer passo falhar, nada é alterado.
-- ============================================================
BEGIN;

ALTER TABLE produto
    ADD COLUMN preco_venda NUMERIC(10,2)
        CONSTRAINT ck_produto_preco_venda CHECK (preco_venda IS NULL OR preco_venda >= 0),
    ADD COLUMN preco_venda_manual BOOLEAN NOT NULL DEFAULT FALSE;

-- preço manual sem valor não faz sentido
ALTER TABLE produto
    ADD CONSTRAINT ck_produto_preco_manual
    CHECK (NOT preco_venda_manual OR preco_venda IS NOT NULL);

-- Preço inicial dos produtos já cadastrados: custo × 1,20, modo automático.
-- Produto sem custo (nunca comprado) fica com preço vazio: o preço é
-- digitado na OS ou definido manualmente no cadastro do produto.
-- O 1,20 aqui é fixo de propósito: registra a regra vigente nesta data.
-- Depois disso, quem calcula é o sistema (MARKUP_PADRAO em src/servico/precificacao.py).
UPDATE produto
SET preco_venda = ROUND(valor_unitario * 1.20, 2)
WHERE valor_unitario IS NOT NULL;

COMMIT;
