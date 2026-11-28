"""Generates the internal documents of the simulated agro-exporter (case study; the company is fictitious). They play
the part of the organisation's own procedures in the corpus and cite the official sources the system also loads.

    uv run python data/corpus_interno/generar.py
"""
from pathlib import Path

from docx import Document

HERE = Path(__file__).parent
EMPRESA = "Agroexportadora Valle Andino S.A.C. (empresa simulada)"


def procedimiento_aplicacion() -> None:
    d = Document()
    d.core_properties.title = "Procedimiento de aplicación de productos fitosanitarios"
    d.core_properties.author = EMPRESA
    d.add_heading("Procedimiento de aplicación de productos fitosanitarios", level=0)
    d.add_paragraph(f"{EMPRESA}. Código PR-SAN-004, versión 3. Cultivos: arándano, palto y uva de mesa.")

    d.add_heading("1. Objetivo", level=1)
    d.add_paragraph("Asegurar que cada aplicación de un producto fitosanitario use un producto registrado para el cultivo "
                    "y la plaga, respete la carencia y el límite máximo de residuos de cada mercado de destino del lote, y "
                    "quede registrada para la trazabilidad y las auditorías.")
    d.add_heading("2. Alcance", level=1)
    d.add_paragraph("Todos los bloques de producción de la empresa y todas las aplicaciones de insecticidas, fungicidas, "
                    "herbicidas y productos biológicos, incluidas las que hace un contratista.")
    d.add_heading("3. Responsables", level=1)
    t = d.add_table(rows=4, cols=2)
    rows = [("Rol", "Responsabilidad"),
            ("Jefe de sanidad vegetal", "Define el programa fitosanitario de la campaña y aprueba cada aplicación."),
            ("Responsable de calidad", "Verifica antes de la cosecha que el lote cumple los LMR y el perfil del cliente."),
            ("Operario aplicador", "Prepara la mezcla, aplica con el equipo calibrado y registra la aplicación.")]
    for r, (a, b) in enumerate(rows):
        t.cell(r, 0).text, t.cell(r, 1).text = a, b

    d.add_heading("4. Verificaciones antes de aplicar", level=1)
    d.add_heading("4.1 Registro del producto", level=2)
    d.add_paragraph("El producto debe figurar en el registro del SENASA para el cultivo y la plaga del bloque. La consulta "
                    "se hace en el SIGIA o en el módulo de registro del sistema y se anota el número de registro (PQUA). "
                    "Un producto registrado para otro cultivo no se usa, aunque contenga el mismo ingrediente activo.")
    d.add_heading("4.2 Límite de residuos por mercado", level=2)
    d.add_paragraph("Para cada mercado de destino del lote se revisa el límite máximo de residuos vigente del ingrediente "
                    "en el cultivo. Si la Unión Europea no fija un límite específico rige 0,01 mg/kg, y en la práctica "
                    "cualquier residuo detectable incumple. En Estados Unidos, sin tolerancia en 40 CFR 180 el residuo no "
                    "está permitido. Cuando el cliente aplica un perfil propio, como un porcentaje del LMR legal, se "
                    "verifica también ese perfil.")
    d.add_heading("4.3 Carencia y fecha de cosecha", level=2)
    d.add_paragraph("La fecha de la última aplicación más la carencia de la etiqueta debe ser anterior a la cosecha "
                    "planificada del bloque. La carencia de etiqueta no garantiza el LMR de otro mercado: si el margen es "
                    "corto, el jefe de sanidad decide otro producto o reprograma la cosecha.")
    d.add_heading("4.4 Rotación de modos de acción", level=2)
    d.add_paragraph("No se aplican dos veces seguidas productos del mismo grupo FRAC (fungicidas) o IRAC (insecticidas) "
                    "contra la misma plaga en el mismo bloque. Se alternan grupos y se prefieren los agentes de control "
                    "biológico registrados cuando el nivel de la plaga lo permite.")

    d.add_heading("5. Preparación y aplicación", level=1)
    for text in ("Calibrar el equipo al inicio de la campaña y cada vez que se cambie de boquilla.",
                 "Usar el equipo de protección personal que indica la etiqueta.",
                 "Preparar solo la mezcla que se aplicará en la jornada y respetar la dosis de la etiqueta.",
                 "No aplicar con viento fuerte ni antes de una lluvia anunciada."):
        d.add_paragraph(text, style="List Number")

    d.add_heading("6. Registro de la aplicación", level=1)
    d.add_paragraph("Cada aplicación se registra el mismo día en el cuaderno de campo y en el sistema: fecha, bloque, "
                    "plaga, producto, número de registro, dosis, volumen de agua, operario y equipo. El registro permite "
                    "reconstruir el historial de un lote ante una auditoría o un rechazo.")

    d.add_heading("7. Antes de la cosecha", level=1)
    d.add_paragraph("El responsable de calidad toma una muestra por lote para el análisis multirresiduos en un laboratorio "
                    "acreditado y compara cada residuo medido con el LMR de cada mercado de destino y con el perfil del "
                    "cliente. Un lote que no cumple con un mercado puede destinarse a otro mercado con el que sí cumpla.")
    d.add_heading("8. Atención de un rechazo en destino", level=1)
    d.add_paragraph("Se identifican las aplicaciones del lote rechazado, se comparan con el límite que motivó el rechazo y "
                    "se revisan los demás lotes que recibieron el mismo producto. El jefe de sanidad registra la causa y la "
                    "acción correctiva en el programa de la campaña siguiente.")
    d.save(HERE / "procedimiento_aplicacion_fitosanitaria.docx")


if __name__ == "__main__":
    procedimiento_aplicacion()
    print("generado:", HERE / "procedimiento_aplicacion_fitosanitaria.docx")
