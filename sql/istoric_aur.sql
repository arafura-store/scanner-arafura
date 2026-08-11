-- ============================================================
--  ISTORIC AUR ZILNIC — pentru sectiunea de fluctuatii
--  De rulat in Supabase → SQL Editor → RUN
-- ============================================================

CREATE TABLE IF NOT EXISTS istoric_aur_zilnic (
  data          DATE PRIMARY KEY,
  xau_usd       NUMERIC(12,2) NOT NULL,   -- inchiderea aurului, USD / uncie troy
  eur_ron       NUMERIC(10,4),            -- curs de referinta BCE
  usd_ron       NUMERIC(10,4),
  eur_gram      NUMERIC(10,2),            -- EUR / gram brut
  ron_gram_24k  NUMERIC(10,2),            -- pretul nostru 24K, aceeasi formula
  actualizat_la TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_istoric_aur_data ON istoric_aur_zilnic (data DESC);

ALTER TABLE istoric_aur_zilnic DISABLE ROW LEVEL SECURITY;
