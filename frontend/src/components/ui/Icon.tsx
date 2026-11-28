"use client";

import { useId, type ReactNode } from "react";

// Glossy section icons: small objects with a light top, a deep bottom, an edge and a shine. Original drawings for this
// project. Every color is a theme token (--icon-<hue>-hi/-lo/-edge in src/styles/theme.css), so they follow the theme.

export type IconName =
  | "limites" | "programa" | "laboratorio" | "alertas" | "registro" | "datos"
  | "mis-programas" | "mis-lotes" | "cuenta" | "administracion" | "ajustes" | "consulta";

type Hue = "blue" | "green" | "amber" | "paper" | "steel" | "red";

function Gloss({ id, hue }: { id: string; hue: Hue }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" style={{ stopColor: `var(--icon-${hue}-hi)` }} />
      <stop offset="1" style={{ stopColor: `var(--icon-${hue}-lo)` }} />
    </linearGradient>
  );
}

const edge = (hue: Hue) => `var(--icon-${hue}-edge)`;
const SHINE = { fill: "var(--icon-shine)", opacity: 0.55 };

export function Icon({ name, size = 20, className }: { name: IconName; size?: number; className?: string }) {
  const uid = useId().replace(/:/g, "");
  const g = (hue: Hue) => `url(#${uid}-${hue})`;
  const hues: Hue[] = ["blue", "green", "amber", "paper", "steel", "red"];

  const art: Record<IconName, ReactNode> = {
    // two speech bubbles: a question and its answer
    consulta: (
      <>
        <path d="M3 5.5A2.5 2.5 0 0 1 5.5 3h8A2.5 2.5 0 0 1 16 5.5v4A2.5 2.5 0 0 1 13.5 12H8l-3.5 3v-3.1A2.5 2.5 0 0 1 3 9.5z"
          fill={g("blue")} stroke={edge("blue")} strokeWidth="1" />
        <path d="M10 13.5A2 2 0 0 1 12 11.5h6.5a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H18v2.5l-3-2.5h-3a2 2 0 0 1-2-2z"
          fill={g("green")} stroke={edge("green")} strokeWidth="1" />
        <ellipse cx="8" cy="5.2" rx="3.2" ry="0.9" {...SHINE} />
      </>
    ),
    // a dial with its needle: the limit in force
    limites: (
      <>
        <path d="M3 17a9 9 0 0 1 18 0v2H3z" fill={g("blue")} stroke={edge("blue")} strokeWidth="1" />
        <path d="M6 17a6 6 0 0 1 12 0" fill="none" stroke="var(--icon-shine)" strokeWidth="1.2" opacity="0.7" />
        <path d="M12 17 16.5 10.5" stroke="var(--icon-red-edge)" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="12" cy="17" r="1.8" fill={g("steel")} stroke={edge("steel")} strokeWidth="0.8" />
        <ellipse cx="9" cy="11" rx="4" ry="1.6" {...SHINE} />
      </>
    ),
    // a calendar page with rings: the season program
    programa: (
      <>
        <rect x="3.5" y="5" width="17" height="15" rx="2.5" fill={g("paper")} stroke={edge("paper")} strokeWidth="1" />
        <path d="M3.5 7.5a2.5 2.5 0 0 1 2.5-2.5h12a2.5 2.5 0 0 1 2.5 2.5V10h-17z" fill={g("red")} stroke={edge("red")} strokeWidth="1" />
        <rect x="7" y="3" width="2" height="4" rx="1" fill={g("steel")} stroke={edge("steel")} strokeWidth="0.6" />
        <rect x="15" y="3" width="2" height="4" rx="1" fill={g("steel")} stroke={edge("steel")} strokeWidth="0.6" />
        <path d="M7 13h3M11.5 13h3M7 16.5h3M11.5 16.5h5.5" stroke="var(--icon-paper-edge)" strokeWidth="1.2" strokeLinecap="round" />
        <ellipse cx="10" cy="6.8" rx="4.5" ry="0.9" {...SHINE} />
      </>
    ),
    // a flask with liquid: the lab result
    laboratorio: (
      <>
        <path d="M9.5 3h5v5.5l5 8.5A2 2 0 0 1 17.8 20H6.2a2 2 0 0 1-1.7-3l5-8.5z" fill={g("paper")} stroke={edge("steel")} strokeWidth="1" />
        <path d="M7.3 13.5h9.4l2.3 3.8a1.6 1.6 0 0 1-1.4 2.2H6.4A1.6 1.6 0 0 1 5 17.3z" fill={g("green")} stroke={edge("green")} strokeWidth="0.8" />
        <rect x="8.8" y="2" width="6.4" height="2" rx="1" fill={g("steel")} stroke={edge("steel")} strokeWidth="0.6" />
        <circle cx="10.5" cy="16.5" r="0.9" fill="var(--icon-shine)" opacity="0.8" />
        <circle cx="13.5" cy="17.6" r="0.6" fill="var(--icon-shine)" opacity="0.8" />
        <path d="M10.8 5.5v3.4" stroke="var(--icon-shine)" strokeWidth="1.2" strokeLinecap="round" opacity="0.8" />
      </>
    ),
    // a bell: a limit that changes soon
    alertas: (
      <>
        <path d="M12 3.2a5.6 5.6 0 0 1 5.6 5.6v3.6l2 3.4H4.4l2-3.4V8.8A5.6 5.6 0 0 1 12 3.2z" fill={g("amber")} stroke={edge("amber")} strokeWidth="1" />
        <path d="M9.6 18a2.4 2.4 0 0 0 4.8 0z" fill={g("steel")} stroke={edge("steel")} strokeWidth="0.8" />
        <ellipse cx="10" cy="7.5" rx="2.2" ry="1.4" {...SHINE} />
      </>
    ),
    // a closed book: the official register
    registro: (
      <>
        <path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5z" fill={g("green")} stroke={edge("green")} strokeWidth="1" />
        <path d="M5 19.5A1.5 1.5 0 0 1 6.5 18H19v3H6.5A1.5 1.5 0 0 1 5 19.5z" fill={g("paper")} stroke={edge("paper")} strokeWidth="0.8" />
        <rect x="9" y="6.5" width="7" height="2.5" rx="0.6" fill="var(--icon-paper-hi)" opacity="0.85" />
        <path d="M6.5 4.5h11" stroke="var(--icon-shine)" strokeWidth="1" opacity="0.7" />
      </>
    ),
    // stacked disks: the data sources
    datos: (
      <>
        <path d="M4.5 6v12c0 1.6 3.4 2.8 7.5 2.8s7.5-1.2 7.5-2.8V6" fill={g("blue")} stroke={edge("blue")} strokeWidth="1" />
        <path d="M4.5 10c0 1.6 3.4 2.8 7.5 2.8s7.5-1.2 7.5-2.8M4.5 14c0 1.6 3.4 2.8 7.5 2.8s7.5-1.2 7.5-2.8" fill="none" stroke={edge("blue")} strokeWidth="0.8" />
        <ellipse cx="12" cy="6" rx="7.5" ry="2.8" fill={g("steel")} stroke={edge("blue")} strokeWidth="1" />
        <ellipse cx="10" cy="5.4" rx="3.5" ry="0.9" {...SHINE} />
      </>
    ),
    // a folder: saved programs
    "mis-programas": (
      <>
        <path d="M3 7a2 2 0 0 1 2-2h4.2l2 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill={g("amber")} stroke={edge("amber")} strokeWidth="1" />
        <path d="M3 10a1.5 1.5 0 0 1 1.5-1.5h15A1.5 1.5 0 0 1 21 10v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill={g("amber")} stroke={edge("amber")} strokeWidth="1" />
        <path d="M4.5 10.5h15" stroke="var(--icon-shine)" strokeWidth="1" opacity="0.75" />
      </>
    ),
    // a crate: harvested lots
    "mis-lotes": (
      <>
        <path d="M12 3 20 7v10l-8 4-8-4V7z" fill={g("paper")} stroke={edge("paper")} strokeWidth="1" />
        <path d="M4 7l8 4 8-4M12 11v10" fill="none" stroke={edge("paper")} strokeWidth="1" />
        <path d="M12 11 20 7v10l-8 4z" fill={g("amber")} opacity="0.55" />
        <path d="M8 5 16 9" stroke={edge("amber")} strokeWidth="1.4" />
        <path d="M6 7.6 11 10" stroke="var(--icon-shine)" strokeWidth="1" opacity="0.8" />
      </>
    ),
    // a person: the account
    cuenta: (
      <>
        <circle cx="12" cy="8" r="4" fill={g("blue")} stroke={edge("blue")} strokeWidth="1" />
        <path d="M4 20a8 6 0 0 1 16 0z" fill={g("blue")} stroke={edge("blue")} strokeWidth="1" />
        <ellipse cx="10.8" cy="6.4" rx="1.8" ry="1.1" {...SHINE} />
        <ellipse cx="10" cy="16.2" rx="3.5" ry="1" {...SHINE} />
      </>
    ),
    // a shield: administration
    administracion: (
      <>
        <path d="M12 2.8 19.5 5.5v5.6c0 4.6-3.2 8.3-7.5 10-4.3-1.7-7.5-5.4-7.5-10V5.5z" fill={g("blue")} stroke={edge("blue")} strokeWidth="1" />
        <path d="M8.5 12 11 14.5 15.8 9.5" fill="none" stroke="var(--icon-shine)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M6.5 6.7 12 4.8l5.5 1.9" fill="none" stroke="var(--icon-shine)" strokeWidth="1" opacity="0.7" />
      </>
    ),
    // a gear: settings
    ajustes: (
      <>
        <path
          d="M10.6 2.5h2.8l.5 2.4 1.6.7 2.1-1.3 2 2-1.3 2.1.7 1.6 2.4.5v2.8l-2.4.5-.7 1.6 1.3 2.1-2 2-2.1-1.3-1.6.7-.5 2.4h-2.8l-.5-2.4-1.6-.7-2.1 1.3-2-2 1.3-2.1-.7-1.6-2.4-.5v-2.8l2.4-.5.7-1.6-1.3-2.1 2-2 2.1 1.3 1.6-.7z"
          fill={g("steel")} stroke={edge("steel")} strokeWidth="0.9" strokeLinejoin="round"
        />
        <circle cx="12" cy="12" r="3.2" fill="var(--icon-paper-hi)" stroke={edge("steel")} strokeWidth="0.9" />
        <ellipse cx="10" cy="6.5" rx="3" ry="1" {...SHINE} />
      </>
    ),
  };

  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden focusable="false">
      <defs>
        {hues.map((h) => (
          <Gloss key={h} id={`${uid}-${h}`} hue={h} />
        ))}
      </defs>
      {art[name]}
    </svg>
  );
}

/** The icon of each section, by the index its page shows. */
export const SECTION_ICON: Record<string, IconName> = {
  "01": "consulta", "02": "limites", "03": "programa", "04": "laboratorio", "05": "alertas", "06": "mis-programas", "07": "mis-lotes",
  "08": "registro", "09": "datos", "10": "cuenta", "11": "ajustes", "12": "administracion",
};
