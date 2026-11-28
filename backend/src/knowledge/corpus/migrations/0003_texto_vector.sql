-- Tables written as sentences for the encoder (stage 3, 23/11/2026): «texto» stays the pipe table that the user and the
-- generator see; «texto_vector», when present, is what gets encoded. NULL = encode «texto» as before.
ALTER TABLE fragmentos ADD COLUMN IF NOT EXISTS texto_vector text;
