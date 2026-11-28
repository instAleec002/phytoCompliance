// Fixed vocabulary of the interface: statuses, severities, markets and finding codes, in Spanish.

export type Tone = "blocking" | "risk" | "info" | "ok" | "neutral";

export const MARKETS = ["EU", "US", "CODEX"] as const;
export type Market = (typeof MARKETS)[number];

export const MARKET_LABEL: Record<string, string> = { EU: "Unión Europea", US: "EE. UU.", CODEX: "Codex" };
export const MARKET_SHORT: Record<string, string> = { EU: "UE", US: "EE. UU.", CODEX: "Codex" };

export const LIMIT_STATUS: Record<string, { label: string; tone: Tone }> = {
  specific: { label: "Específico", tone: "ok" },
  default: { label: "Por defecto", tone: "risk" },
  exempt: { label: "Exento", tone: "ok" },
  not_permitted: { label: "No permitido", tone: "blocking" },
  no_reference: { label: "Sin referencia", tone: "neutral" },
  without_value: { label: "Sin valor", tone: "risk" },
  no_data: { label: "Sin datos", tone: "neutral" },
};

export const SEVERITY: Record<string, { label: string; tone: Tone; rank: number }> = {
  blocking: { label: "Bloquea", tone: "blocking", rank: 0 },
  risk: { label: "Riesgo", tone: "risk", rank: 1 },
  info: { label: "Info", tone: "info", rank: 2 },
};

// Short titles for the finding codes the domain returns; the message carries the detail.
export const FINDING_TITLE: Record<string, string> = {
  NOT_REGISTERED: "Sin registro en SENASA",
  UNKNOWN_BLOCK: "Bloque inexistente",
  APPLIED_AFTER_HARVEST: "Aplicación posterior a la cosecha",
  PHI_NOT_MET: "Carencia no cumplida",
  PHI_UNKNOWN: "Carencia no registrada",
  DEFAULT_LIMIT: "Sin LMR específico",
  NOT_PERMITTED: "Sin tolerancia",
  LIMIT_AT_LOQ: "LMR en el límite de determinación",
  LIMIT_WITHOUT_VALUE: "LMR listado sin valor",
  AMBIGUOUS_RESIDUE: "Residuo ambiguo",
  MARKET_NOT_LOADED: "Mercado sin datos",
  ROTATION_SAME_GROUP: "Mismo modo de acción seguido",
  ROTATION_NOT_CHECKED: "Rotación no revisada",
  MRL_EXCEEDED: "Supera el LMR",
  RESIDUE_NOT_PERMITTED: "Residuo no permitido",
  PROFILE_SUBSTANCE: "Perfil: fracción del LMR",
  PROFILE_SUM: "Perfil: suma de fracciones",
  PROFILE_COUNT: "Perfil: número de residuos",
  PROFILE_ARFD: "Perfil: exposición aguda",
  PROFILE_ARFD_NOT_CHECKED: "Perfil: ARfD no evaluada",
};

export function cropLabel(crops: { key: string; name_es?: string | null }[] | undefined, key: string): string {
  return crops?.find((c) => c.key === key)?.name_es ?? key;
}

// Actions of the activity log.
export const ACTION_LABEL: Record<string, string> = {
  admin_creado: "Cuenta de administración creada",
  usuario_invitado: "Usuario invitado",
  enlace_emitido: "Enlace emitido",
  usuario_actualizado: "Cuenta modificada",
  cuenta_activada: "Cuenta activada",
  contrasena_restablecida: "Contraseña restablecida",
  contrasena_restablecida_consola: "Contraseña restablecida desde la consola",
  contrasena_cambiada: "Contraseña cambiada",
  ingreso: "Inicio de sesión",
  ingreso_fallido: "Inicio de sesión fallido",
  salida: "Cierre de sesión",
  programa_guardado: "Programa guardado",
  programa_eliminado: "Programa eliminado",
  programa_validado: "Programa validado",
  lote_evaluado: "Lote evaluado",
};

export const ACCOUNT_STATE: Record<string, { label: string; tone: Tone }> = {
  activo: { label: "Activa", tone: "ok" },
  invitado: { label: "Invitada", tone: "info" },
  desactivado: { label: "Desactivada", tone: "neutral" },
};

/** "Mozilla/5.0 (Windows NT 10.0…) … Edg/141" -> "Edge · Windows"; the desktop app reports Tauri. */
export function deviceLabel(agent: string | null | undefined): string {
  if (!agent) return "Dispositivo desconocido";
  const browser = /Tauri/i.test(agent) ? "Aplicación de escritorio" : /Edg\//.test(agent) ? "Edge" : /Firefox\//.test(agent) ? "Firefox"
    : /Chrome\//.test(agent) ? "Chrome" : /Safari\//.test(agent) ? "Safari" : agent.split(" ")[0] ?? "Navegador";
  const os = /Windows/.test(agent) ? "Windows" : /Android/.test(agent) ? "Android" : /iPhone|iPad/.test(agent) ? "iOS"
    : /Mac OS/.test(agent) ? "macOS" : /Linux/.test(agent) ? "Linux" : "";
  return os ? `${browser} · ${os}` : browser;
}
