-- ============================================================
-- RF06: Relatórios e Gráficos (índice para o filtro por período)
--
-- Rode UMA vez no pgAdmin (Query Tool), no banco JÁ EXISTENTE
-- (depois do migrar_preco_venda.sql).
-- Num banco NOVO use o BancoDeDadods.sql atualizado (e NÃO rode este).
--
-- Tudo roda numa transação: se qualquer passo falhar, nada é alterado.
-- ============================================================
BEGIN;

-- Todas as consultas do relatório filtram as OS entregues por entregue_em
-- (RNF06: consultas em até 3 segundos). A coluna só tem valor quando a OS
-- está entregue (CHECK ck_os_entregue_em), então o índice já cobre só elas.
CREATE INDEX idx_os_entregue_em ON ordem_servico(entregue_em);

COMMIT;
