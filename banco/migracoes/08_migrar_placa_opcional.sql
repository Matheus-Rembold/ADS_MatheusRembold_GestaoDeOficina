-- ============================================================
-- RF02: placa do veículo passa a ser OPCIONAL (decidido em 20/11/2026)
--
-- Motivo: o veículo pode ser cadastrado antes de chegar à oficina, sem
-- que se saiba a placa; ela é preenchida depois, editando o veículo.
-- A placa continua ÚNICA quando informada (o UNIQUE aceita vários NULL).
--
-- Num banco NOVO use o banco/BancoDeDados.sql atualizado (e NÃO rode este).
-- ============================================================
BEGIN;

ALTER TABLE veiculo ALTER COLUMN placa DROP NOT NULL;

COMMIT;
