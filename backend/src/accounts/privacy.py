"""Privacy notice (Ley N.° 29733, Ley de Protección de Datos Personales) and the rights of access, rectification,
cancellation and opposition (ARCO).

The notice is versioned: activating an account requires accepting the current version, and an account that accepted an
older one (or none, if it predates the notice) is asked again on its next visit. Changing the text means changing
``VERSION``. Access is served at once (the person downloads their own data); the other three rights are requests that
an admin resolves with a written answer, all recorded in the activity log."""
from __future__ import annotations

VERSION = "2026-11-06"

RIGHTS = {
    "acceso": "Acceso",
    "rectificacion": "Rectificación",
    "cancelacion": "Cancelación",
    "oposicion": "Oposición",
}

SECTIONS: list[tuple[str, str]] = [
    ("Quién trata sus datos",
     "La empresa agroexportadora que administra esta instalación del sistema es la titular del banco de datos de "
     "cuentas. En el proyecto TP202620505 esa empresa es un caso de estudio simulado."),
    ("Qué datos se tratan",
     "Su nombre, su nombre de usuario y su correo; la contraseña, guardada solo como hash argon2id; las sesiones "
     "abiertas (fecha y navegador); el registro de actividad de la cuenta, y el trabajo que usted guarda: programas, "
     "lotes evaluados y conversaciones con el asistente."),
    ("Para qué se usan",
     "Para darle acceso, proteger la cuenta (bloqueo tras intentos fallidos, cierre de sesiones), dejar constancia de "
     "quién validó cada programa y cuándo, y conservar su trabajo. No se usan con fines publicitarios ni se ceden a "
     "terceros."),
    ("Qué sale del servidor",
     "En el modo en la nube, la pregunta que usted escribe, la conversación reciente y los pasajes públicos recuperados "
     "se envían al servicio de modelos de lenguaje de Google para redactar la respuesta. No se envían los datos de su "
     "cuenta, sus programas ni sus lotes. Ese proveedor puede conservar lo enviado según sus propios términos, por lo "
     "que conviene no escribir datos personales en las preguntas. En el modo local nada sale del servidor."),
    ("Cuánto tiempo se conservan",
     "Mientras la cuenta exista. Puede pedir su cancelación desde Mi cuenta; la administración puede desactivar la "
     "cuenta de inmediato y la eliminación se registra como respuesta a su solicitud."),
    ("Sus derechos",
     "Puede descargar en cualquier momento una copia de sus datos desde Mi cuenta (derecho de acceso) y, desde la misma "
     "página, pedir la rectificación, la cancelación o la oposición a un tratamiento. La administración responde por "
     "escrito dentro de los plazos de la Ley N.° 29733 y su reglamento; si no lo hace, puede acudir a la Autoridad "
     "Nacional de Protección de Datos Personales."),
    ("Cómo se protegen",
     "Cuentas solo por invitación con enlaces de un solo uso, contraseñas de 12 caracteres o más guardadas como hash, "
     "bloqueo de 15 minutos tras cinco intentos fallidos y sesiones que caducan por inactividad."),
]


def notice() -> dict:
    return {"version": VERSION, "secciones": [{"titulo": t, "texto": x} for t, x in SECTIONS]}
