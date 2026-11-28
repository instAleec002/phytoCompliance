// Measurements pasted from a lab report or a spreadsheet: one per line, "ingrediente;0,25" or "ingrediente<TAB>0.25".
// "ND", "<LOQ" and empty values are not detections and are skipped with a note.

export interface PastedMeasurement {
  ingredient: string;
  value: string;
}

export function parsePastedMeasurements(text: string): { rows: PastedMeasurement[]; skipped: string[] } {
  const rows: PastedMeasurement[] = [];
  const skipped: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(/^(.*?)[;\t]\s*([^;\t]*)$/) ?? line.match(/^(.*\S)\s+(\S+)$/);
    const ingredient = m?.[1]?.trim() ?? "";
    const value = (m?.[2] ?? "").trim().replace(",", ".");
    if (!ingredient || !/^\d*\.?\d+$/.test(value)) {
      skipped.push(line);
      continue;
    }
    rows.push({ ingredient: ingredient.toLowerCase(), value });
  }
  return { rows, skipped };
}
