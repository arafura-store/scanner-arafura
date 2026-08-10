-- ============================================================
--  ALERTE AUR — adaugare canal WhatsApp (CallMeBot)
--  De rulat DUPA alerte_aur.sql, in Supabase → SQL Editor → RUN
-- ============================================================

ALTER TABLE alerte_aur ADD COLUMN IF NOT EXISTS whatsapp BOOLEAN NOT NULL DEFAULT TRUE;

-- Telegram nu mai e canalul implicit (Eugen nu foloseste aplicatia)
ALTER TABLE alerte_aur ALTER COLUMN telegram SET DEFAULT FALSE;

-- Constrangerea trebuie sa accepte si WhatsApp ca singur canal ales
ALTER TABLE alerte_aur DROP CONSTRAINT IF EXISTS alerte_aur_macar_un_canal;
ALTER TABLE alerte_aur ADD CONSTRAINT alerte_aur_macar_un_canal
  CHECK (email IS NOT NULL OR telegram = TRUE OR whatsapp = TRUE);

-- Supabase reactiveaza RLS pe tabelele noi — ma asigur ca ramane oprit
ALTER TABLE alerte_aur DISABLE ROW LEVEL SECURITY;
