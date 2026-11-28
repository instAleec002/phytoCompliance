"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Icon, SECTION_ICON } from "@/components/ui/Icon";
import { useSession } from "@/lib/session";
import { showIcons, showNumbers } from "@/styles/ui.config";

import styles from "./shell.module.css";

interface Item {
  href: string;
  index: string;
  label: string;
  hint: string;
}

const WORK: Item[] = [
  { href: "/consulta/", index: "01", label: "Consulta", hint: "Preguntas con respuesta citada" },
  { href: "/lmr/", index: "02", label: "Límites", hint: "LMR vigente por mercado y fecha" },
  { href: "/programa/", index: "03", label: "Programa", hint: "Validar aplicaciones por bloque" },
  { href: "/laboratorio/", index: "04", label: "Laboratorio", hint: "Resultados de un lote y perfil" },
  { href: "/alertas/", index: "05", label: "Alertas", hint: "Límites que cambian pronto" },
];
// Numbers follow the order on screen. Administration goes last, so a user who does not see it finds no gap.
const MINE: Item[] = [
  { href: "/mis-programas/", index: "06", label: "Mis programas", hint: "Programas guardados en la cuenta" },
  { href: "/mis-lotes/", index: "07", label: "Mis lotes", hint: "Evaluaciones de laboratorio" },
];
const REFERENCE: Item[] = [
  { href: "/registro/", index: "08", label: "Registro SENASA", hint: "Plagas y productos autorizados" },
  { href: "/", index: "09", label: "Estado de datos", hint: "Fuentes e instantáneas" },
];
const ACCOUNT: Item[] = [
  { href: "/mi-cuenta/", index: "10", label: "Mi cuenta", hint: "Contraseña, sesiones y actividad" },
  { href: "/ajustes/", index: "11", label: "Ajustes", hint: "Dirección de la API" },
];
const ADMIN: Item[] = [
  { href: "/administracion/", index: "12", label: "Administración", hint: "Usuarios, enlaces y actividad" },
];

// Columns follow the switches in ui.config.ts: [icon] [number] label, with the hint under the label.
const COLUMNS = [showIcons && "30px", showNumbers && "24px", "minmax(0, 1fr)"].filter(Boolean).join(" ");

function NavItem({ item, active }: { item: Item; active: boolean }) {
  return (
    <li>
      <Link prefetch={false} href={item.href} className={styles.link} style={{ gridTemplateColumns: COLUMNS }}
        aria-current={active ? "page" : undefined}>
        {showIcons && <Icon name={SECTION_ICON[item.index] ?? "datos"} size={20} className={styles.linkIcon} />}
        {showNumbers && <span className={styles.linkIndex}>{item.index}</span>}
        <span>{item.label}</span>
        <span className={styles.linkHint}>{item.hint}</span>
      </Link>
    </li>
  );
}

export function Rail() {
  const path = usePathname() ?? "/";
  const { isAdmin } = useSession();
  const isActive = (href: string) => (href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, "")));
  return (
    <nav className={`${styles.rail} no-print`} aria-label="Secciones">
      <div className={styles.mark}>
        <div className={styles.markCode}>TP202620505</div>
        <div className={styles.markName}>Cumplimiento fitosanitario</div>
      </div>
      <ul className={styles.nav}>
        <li className={styles.navSection}>Trabajo</li>
        {WORK.map((i) => (
          <NavItem key={i.href} item={i} active={isActive(i.href)} />
        ))}
        <li className={styles.navSection}>Mi trabajo</li>
        {MINE.map((i) => (
          <NavItem key={i.href} item={i} active={isActive(i.href)} />
        ))}
        <li className={styles.navSection}>Referencia</li>
        {REFERENCE.map((i) => (
          <NavItem key={i.href} item={i} active={isActive(i.href)} />
        ))}
        <li className={styles.navSection}>Cuenta</li>
        {ACCOUNT.map((i) => (
          <NavItem key={i.href} item={i} active={isActive(i.href)} />
        ))}
        {isAdmin && <li className={styles.navSection}>Administración</li>}
        {isAdmin && ADMIN.map((i) => <NavItem key={i.href} item={i} active={isActive(i.href)} />)}
      </ul>
      <div className={styles.railFoot}>Cumplimiento con reglas exactas · consulta con fuentes citadas</div>
    </nav>
  );
}
