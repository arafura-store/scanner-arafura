-- ============================================================
--  ALERTE PRET AUR — Perfecta Invest IFN
--  De rulat O SINGURA DATA in Supabase → SQL Editor → RUN
--  https://supabase.com/dashboard/project/bxsfzfnpejkmwxkuoshb/sql/new
-- ============================================================

CREATE TABLE IF NOT EXISTS alerte_aur (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eticheta          TEXT,                            -- nota, ex: "vand la pretul asta"
  directie          TEXT NOT NULL CHECK (directie IN ('peste','sub')),
  prag              NUMERIC(10,2) NOT NULL,          -- RON / gram, aur 24K

  -- canale de notificare (macar unul trebuie ales)
  email             TEXT,                            -- NULL = fara mail
  telegram          BOOLEAN NOT NULL DEFAULT TRUE,

  activa            BOOLEAN NOT NULL DEFAULT TRUE,
  o_singura_data    BOOLEAN NOT NULL DEFAULT TRUE,   -- dupa declansare se dezactiveaza singura
  ultima_declansare TIMESTAMPTZ,
  pret_declansare   NUMERIC(10,2),
  creata_la         TIMESTAMPTZ DEFAULT NOW(),

  CONSTRAINT alerte_aur_macar_un_canal CHECK (email IS NOT NULL OR telegram = TRUE)
);

CREATE INDEX IF NOT EXISTS idx_alerte_aur_activa ON alerte_aur (activa);

-- Ca restul tabelelor din proiect (acces cu cheia publishable + guards in UI)
ALTER TABLE alerte_aur DISABLE ROW LEVEL SECURITY;
