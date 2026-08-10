-- ============================================================
--  ALERTE AUR — repetare la 15 minute (cu protectie anti-blocare)
--  De rulat in Supabase → SQL Editor → RUN
-- ============================================================

-- Cate mesaje s-au trimis LA RAND pentru aceeasi alerta, fara ca pretul
-- sa revina in interval. Se reseteaza singur cand pretul revine.
ALTER TABLE alerte_aur ADD COLUMN IF NOT EXISTS notificari_consecutive INT NOT NULL DEFAULT 0;

ALTER TABLE alerte_aur DISABLE ROW LEVEL SECURITY;
