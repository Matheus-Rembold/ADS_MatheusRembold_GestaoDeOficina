-- ============================================================
-- RF05: Agendamentos (vínculo com a OS gerada + CHECK da duração)
--
-- Num banco NOVO use o banco/BancoDeDados.sql atualizado (e NÃO rode este).
--
-- Tudo roda numa transação: se qualquer passo falhar, nada é alterado.
-- ============================================================
BEGIN;

ALTER TABLE agendamento
    ADD COLUMN id_ordem_servico INT UNIQUE
        REFERENCES ordem_servico(id_ordem_servico) ON DELETE SET NULL;

ALTER TABLE agendamento
    ADD CONSTRAINT ck_agendamento_duracao
    CHECK (duracao_estimada_horas IS NULL OR duracao_estimada_horas > 0);

COMMIT;
