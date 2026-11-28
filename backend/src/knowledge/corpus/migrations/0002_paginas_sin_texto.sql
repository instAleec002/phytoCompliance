-- Pages with and without extractable text per document. OCR is off by default (decision of 06/11/2026), so pages of
-- scanned PDFs, or scanned pages inside a native PDF, are skipped; the counter reports how many (11/11/2026).
ALTER TABLE documentos ADD COLUMN IF NOT EXISTS paginas_con_texto integer;
ALTER TABLE documentos ADD COLUMN IF NOT EXISTS paginas_sin_texto integer;
