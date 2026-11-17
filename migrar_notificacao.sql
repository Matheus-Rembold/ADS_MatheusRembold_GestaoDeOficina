-- ============================================================
-- RF07: Notificações pelo WhatsApp (pós-venda + lembrete de agendamento)
--
-- Rode UMA vez no pgAdmin (Query Tool), no banco JÁ EXISTENTE
-- (depois do migrar_usuario.sql).
-- Num banco NOVO use o BancoDeDadods.sql atualizado (e NÃO rode este).
--
-- Tudo roda numa transação: se qualquer passo falhar, nada é alterado.
-- ============================================================
BEGIN;

-- 1) Cliente pode recusar mensagens (LGPD / RNF04)
ALTER TABLE cliente ADD COLUMN aceita_mensagens BOOLEAN NOT NULL DEFAULT TRUE;

-- 2) Notificação passa a ter dois tipos: pós-venda (OS) e lembrete (agendamento)
ALTER TABLE notificacao ALTER COLUMN id_ordem_servico DROP NOT NULL;
ALTER TABLE notificacao DROP CONSTRAINT notificacao_status_envio_check;
ALTER TABLE notificacao ADD CONSTRAINT ck_notificacao_status_envio
    CHECK (status_envio IN ('pendente', 'enviado', 'cancelado'));
ALTER TABLE notificacao
    ADD COLUMN tipo VARCHAR(25) NOT NULL DEFAULT 'pos_venda'
        CONSTRAINT ck_notificacao_tipo CHECK (tipo IN ('pos_venda', 'lembrete_agendamento')),
    ADD COLUMN id_agendamento INT UNIQUE REFERENCES agendamento(id_agendamento) ON DELETE CASCADE,
    ADD COLUMN mensagem TEXT,
    ADD COLUMN motivo_cancelamento VARCHAR(150),
    ADD COLUMN criado_em TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE notificacao ADD CONSTRAINT ck_notificacao_alvo CHECK (
    (tipo = 'pos_venda' AND id_ordem_servico IS NOT NULL AND id_agendamento IS NULL)
    OR (tipo = 'lembrete_agendamento' AND id_agendamento IS NOT NULL AND id_ordem_servico IS NULL)
);
CREATE INDEX idx_notificacao_previsao ON notificacao(status_envio, data_envio_prevista);

-- 3) Histórico inicial (decidido em 15/11/2026):
--    pós-venda só das OS entregues nos ÚLTIMOS 30 DIAS (mandar "como está o
--    carro?" meses depois não faz sentido); as mais antigas não ganham notificação.
INSERT INTO notificacao (tipo, id_ordem_servico, status_envio, data_envio_prevista, motivo_cancelamento)
SELECT 'pos_venda', os.id_ordem_servico,
       CASE WHEN c.aceita_mensagens THEN 'pendente' ELSE 'cancelado' END,
       (os.entregue_em::date + 7),
       CASE WHEN c.aceita_mensagens THEN NULL ELSE 'Cliente não aceita mensagens' END
FROM ordem_servico os
JOIN cliente c ON c.id_cliente = os.id_cliente
WHERE os.status = 'entregue'
  AND os.entregue_em >= NOW() - INTERVAL '30 days'
  AND NOT EXISTS (SELECT 1 FROM notificacao n WHERE n.id_ordem_servico = os.id_ordem_servico);

--    lembrete dos agendamentos que ainda vão acontecer: na véspera
--    (ou hoje, se o horário é hoje ou amanhã)
INSERT INTO notificacao (tipo, id_agendamento, status_envio, data_envio_prevista)
SELECT 'lembrete_agendamento', a.id_agendamento, 'pendente',
       GREATEST(a.data_hora::date - 1, CURRENT_DATE)
FROM agendamento a
WHERE a.status = 'agendado'
  AND a.data_hora > NOW()
  AND NOT EXISTS (SELECT 1 FROM notificacao n WHERE n.id_agendamento = a.id_agendamento);

COMMIT;
