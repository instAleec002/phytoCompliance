// Errors of the API turned into messages a user can act on.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Fired when the API says the session is missing, expired or revoked; the session provider signs out. */
export const SESSION_LOST = "tp:sesion-perdida";

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((d) => `${(d.loc ?? []).filter((p) => p !== "body").join(".")}: ${d.msg ?? ""}`.trim())
      .join("; ");
  }
  return null;
}

export function toApiError(status: number, body: unknown, apiUrl: string): ApiError {
  const detail = detailText((body as { detail?: unknown } | null)?.detail);
  switch (status) {
    case 0:
      return new ApiError(0, `Sin conexión con la API en ${apiUrl}. Revise la dirección en Ajustes o que el servicio esté activo.`);
    case 401:
      return new ApiError(401, detail ?? "Sesión vencida o cerrada. Inicie sesión de nuevo.");
    case 403:
      return new ApiError(403, detail ?? "Su cuenta no tiene permiso para esto.");
    case 422:
      return new ApiError(422, `Datos no válidos: ${detail ?? "revise el formulario"}`);
    default:
      return new ApiError(status, detail ?? `Error ${status} de la API`);
  }
}
