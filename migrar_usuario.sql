-- ============================================================
-- RF10: Login e perfis de usuário (tabela usuario)
--
-- Rode UMA vez no pgAdmin (Query Tool), no banco JÁ EXISTENTE
-- (depois do migrar_relatorios.sql).
-- Num banco NOVO use o BancoDeDadods.sql atualizado (e NÃO rode este).
--
-- Não cria nenhum usuário nem senha: na primeira vez que o sistema abrir,
-- a tela de configuração inicial pede os dados do dono.
--
-- Tudo roda numa transação: se qualquer passo falhar, nada é alterado.
-- ============================================================
BEGIN;

CREATE TABLE usuario (
    id_usuario          SERIAL PRIMARY KEY,
    nome                VARCHAR(100) NOT NULL,
    login               VARCHAR(30) NOT NULL
                            CONSTRAINT ck_usuario_login_minusculo CHECK (login = LOWER(login)),
    senha_hash          VARCHAR(60) NOT NULL,
    perfil              VARCHAR(20) NOT NULL
                            CONSTRAINT ck_usuario_perfil CHECK (perfil IN ('dono', 'mecanico')),
    ativo               BOOLEAN NOT NULL DEFAULT TRUE,
    tentativas_falhas   INT NOT NULL DEFAULT 0
                            CONSTRAINT ck_usuario_tentativas CHECK (tentativas_falhas >= 0),
    bloqueado_ate       TIMESTAMP,
    ultimo_login_em     TIMESTAMP,
    criado_em           TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_usuario_login ON usuario (LOWER(login));

COMMIT;
