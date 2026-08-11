-- ============================================================
--  JURNAL TRANZACTII — adaptare pentru bursa
--  La bursa nu se cumpara grame: se cumpara uncii troy (spot/CFD,
--  futures) sau unitati de ETF, cotate in USD sau EUR, adesea cu
--  levier. Prima versiune presupunea grame si lei, ca la amanet.
--  De rulat in Supabase → SQL Editor → RUN (apoi bucata 2, separat)
-- ============================================================

ALTER TABLE tranzactii_aur ADD COLUMN IF NOT EXISTS unitate TEXT NOT NULL DEFAULT 'gram';
ALTER TABLE tranzactii_aur ADD COLUMN IF NOT EXISTS moneda  TEXT NOT NULL DEFAULT 'RON';
ALTER TABLE tranzactii_aur ADD COLUMN IF NOT EXISTS levier  NUMERIC(6,2) NOT NULL DEFAULT 1;
ALTER TABLE tranzactii_aur ADD COLUMN IF NOT EXISTS instrument TEXT;   -- ex: "XAUUSD CFD", "ETF Xetra-Gold"

-- `grame` devine `cantitate` — poate fi grame, uncii sau unitati de ETF
ALTER TABLE tranzactii_aur RENAME COLUMN grame TO cantitate;

ALTER TABLE tranzactii_aur DROP CONSTRAINT IF EXISTS tranzactii_unitate_valida;
ALTER TABLE tranzactii_aur ADD CONSTRAINT tranzactii_unitate_valida
  CHECK (unitate IN ('gram','uncie','unitate'));

ALTER TABLE tranzactii_aur DROP CONSTRAINT IF EXISTS tranzactii_moneda_valida;
ALTER TABLE tranzactii_aur ADD CONSTRAINT tranzactii_moneda_valida
  CHECK (moneda IN ('RON','USD','EUR'));

ALTER TABLE tranzactii_aur DROP CONSTRAINT IF EXISTS tranzactii_levier_valid;
ALTER TABLE tranzactii_aur ADD CONSTRAINT tranzactii_levier_valid
  CHECK (levier >= 1 AND levier <= 500);
