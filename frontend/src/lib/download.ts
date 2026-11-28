// Files handed to the user with the browser's own download (Tauri supports it too, ADR 0001).

export function downloadText(name: string, text: string, type = "text/plain;charset=utf-8"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

/** CSV with a byte-order mark, so Excel opens accents correctly. */
export function downloadCsv(name: string, text: string): void {
  downloadText(name, "\ufeff" + text, "text/csv;charset=utf-8");
}
