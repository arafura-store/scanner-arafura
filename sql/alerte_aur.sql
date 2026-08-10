-- ============================================================
--  ALERTE PRET AUR — Perfecta Invest IFN
--  De rulat O SINGURA DATA in Supabase → SQL Editor → RUN
--  https://supabase.com/dashboard/project/bxsfzfnpejkmwxkuoshb/sql/new
-- ============================================================

CREATE TABLE IF NOT EXISTS alerte_aur (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eticheta          TEXT,                            -- nume dat de utilizator, ex: "vand la 640"
  directie          TEXT NOT NULL CHECK (directie IN ('peste','sub')),
  prag              NUMERIC(10,2) NOT NULL,          -- RON / gram, aur 24K
  email             TEXT NOT NULL,
  activa            BOOLEAN NOT NULL DEFAULT TRUE,
  o_singura_data    BOOLEAN NOT NULL DEFAULT TRUE,   -- dupa declansare se dezactiveaza singura
  ultima_declansare TIMESTAMPTZ,
  pret_declansare   NUMERIC(10,2),
  creata_la         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerte_aur_activa ON alerte_aur (activa);

-- Ca restul tabelelor din proiect (acces cu cheia publishable + guards in UI)
ALTER TABLE alerte_aur DISABLE ROW LEVEL SECURITY;
