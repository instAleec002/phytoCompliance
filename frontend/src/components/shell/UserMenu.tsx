"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { useSession } from "@/lib/session";
import { useTheme, type Theme } from "@/lib/theme";

import styles from "./shell.module.css";

// The signed-in user's name opens a menu with the account, the theme and sign-out, so the bar keeps one control.

const THEMES: { key: Theme; label: string }[] = [
  { key: "light", label: "Claro" },
  { key: "dark", label: "Oscuro" },
];

export function UserMenu() {
  const { me, isAdmin, signOut } = useSession();
  const [theme, setTheme] = useTheme();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!me) return null;
  const initial = (me.nombre || me.usuario).trim().charAt(0).toUpperCase();

  return (
    <div className={styles.who} ref={box}>
      <button
        type="button"
        className={styles.whoButton}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen(!open)}
      >
        <span className={styles.avatar} aria-hidden>{initial}</span>
        <span className={styles.whoName}>{me.usuario}</span>
        {isAdmin && <span className="stamp" data-tone="info">admin</span>}
        <svg className={styles.chevron} viewBox="0 0 10 10" aria-hidden>
          <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>

      {open && (
        <div className={styles.menu} id={menuId} role="menu" aria-label="Cuenta">
          <div className={styles.menuHead}>
            <div className={styles.menuName}>{me.nombre}</div>
            <div className={styles.menuMail}>{me.email}</div>
          </div>
          <Link prefetch={false} href="/mi-cuenta/" role="menuitem" className={styles.menuItem} onClick={() => setOpen(false)}>
            Mi cuenta
          </Link>
          <div className={styles.menuRow}>
            <span>Tema</span>
            <div className="checks" role="radiogroup" aria-label="Tema">
              {THEMES.map((t) => (
                <label key={t.key} className="check">
                  <input type="radio" name="tema" checked={theme === t.key} onChange={() => setTheme(t.key)} />
                  <span>{t.label}</span>
                </label>
              ))}
            </div>
          </div>
          <div className={styles.menuSep} />
          <button type="button" role="menuitem" className={`${styles.menuItem} ${styles.danger}`} onClick={() => signOut()}>
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  );
}
