"use client";

import { useState } from "react";

// A new password and its confirmation, with the policy shown as it is typed. The server checks it again (common
// passwords, the email and the username); this only spares a round trip.

export const MIN_PASSWORD = 12;

export function passwordHints(password: string, confirm: string, username?: string) {
  const lowered = password.toLowerCase();
  return [
    { ok: password.length >= MIN_PASSWORD, text: `${MIN_PASSWORD} caracteres o más` },
    { ok: new Set(lowered).size >= 4, text: "no repetitiva" },
    {
      ok: password.length > 0 && (!username || username.length < 4 ? lowered !== (username ?? "").toLowerCase() : !lowered.includes(username.toLowerCase())),
      text: "sin el nombre de usuario",
    },
    { ok: password.length > 0 && password === confirm, text: "las dos coinciden" },
  ];
}

export function PasswordFields({
  password,
  confirm,
  onPassword,
  onConfirm,
  username,
  label = "Contraseña nueva",
}: {
  password: string;
  confirm: string;
  onPassword: (v: string) => void;
  onConfirm: (v: string) => void;
  username?: string;
  label?: string;
}) {
  const [show, setShow] = useState(false);
  const hints = passwordHints(password, confirm, username);
  return (
    <div className="stack" style={{ gap: 10 }}>
      <label className="field"><span>{label}</span>
        <input type={show ? "text" : "password"} value={password} autoComplete="new-password" onChange={(e) => onPassword(e.target.value)} /></label>
      <label className="field"><span>Repítala</span>
        <input type={show ? "text" : "password"} value={confirm} autoComplete="new-password" onChange={(e) => onConfirm(e.target.value)} /></label>
      <div className="row" style={{ gap: 6 }}>
        {hints.map((h) => (
          <span key={h.text} className="stamp" data-tone={h.ok ? "ok" : "neutral"}>{h.ok ? "✓" : "·"} {h.text}</span>
        ))}
        <button type="button" className="btn btn-quiet" onClick={() => setShow(!show)}>{show ? "Ocultar" : "Mostrar"}</button>
      </div>
    </div>
  );
}

export const passwordReady = (password: string, confirm: string, username?: string) =>
  passwordHints(password, confirm, username).every((h) => h.ok);
