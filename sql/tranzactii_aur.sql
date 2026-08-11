-- ============================================================
--  JURNAL DE TRANZACTII AUR — Perfecta / Eugen
--  De rulat in Supabase → SQL Editor → RUN
--  ATENTIE: ruleaza si a doua bucata (DISABLE ROW LEVEL SECURITY)
--  SEPARAT, dupa ce tabelele exista — Supabase reactiveaza RLS
--  imediat dupa CREATE TABLE.
-- ============================================================

CREATE TABLE IF NOT EXISTS tranzactii_aur (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- intrare
  data_intrare    DATE NOT NULL,
  pret_intrare    NUMERIC(10,2) NOT NULL CHECK (pret_intrare > 0),  -- RON / gram, 24K
  grame           NUMERIC(12,3) NOT NULL CHECK (grame > 0),
  costuri_intrare NUMERIC(12,2) NOT NULL DEFAULT 0,                 -- comision, spread, taxe

  -- iesire (NULL cat timp pozitia e deschisa)
  data_iesire     DATE,
  pret_iesire     NUMERIC(10,2) CHECK (pret_iesire IS NULL OR pret_iesire > 0),
  costuri_iesire  NUMERIC(12,2) NOT NULL DEFAULT 0,

  -- disciplina: de ce am intrat si de ce am iesit. Cel mai valoros camp din jurnal.
  motiv_intrare   TEXT,
  motiv_iesire    TEXT,

  creata_la       TIMESTAMPTZ DEFAULT NOW(),

  CONSTRAINT tranzactii_iesire_completa
    CHECK ((data_iesire IS NULL AND pret_iesire IS NULL)
        OR (data_iesire IS NOT NULL AND pret_iesire IS NOT NULL)),
  CONSTRAINT tranzactii_ordine_date
    CHECK (data_iesire IS NULL OR data_iesire >= data_intrare)
);

CREATE INDEX IF NOT EXISTS idx_tranzactii_deschise ON tranzactii_aur (data_iesire) WHERE data_iesire IS NULL;
CREATE INDEX IF NOT EXISTS idx_tranzactii_data ON tranzactii_aur (data_intrare DESC);

-- capitalul alocat tranzactionarii, ca sa stim ce procent e expus
CREATE TABLE IF NOT EXISTS setari_trading (
  cheie   TEXT PRIMARY KEY,
  valoare NUMERIC NOT NULL
);

INSERT INTO setari_trading (cheie, valoare) VALUES ('capital_alocat', 0)
ON CONFLICT (cheie) DO NOTHING;
