"""Internal procedures of the simulated agro-exporter (case study; the company is fictitious), added on 11/11/2026 so
the internal level of the corpus reaches the 15 to 30 documents of the corpus plan (pendientes/25).

They state the company's own rules (frequencies, roles, records, criteria) and, for anything regulatory, point to the
official source the system loads (SENASA registry, EU and US limits, FRAC/IRAC/HRAC) instead of stating values, so the
assistant never learns a limit or a pre-harvest interval from an internal text.

    uv run python data/corpus_interno/procedimientos.py
"""
from pathlib import Path

from docx import Document

HERE = Path(__file__).parent
EMPRESA = "Agroexportadora Valle Andino S.A.C. (empresa simulada)"
CULTIVOS = "arándano, palto y uva de mesa"

# (archivo, código, título, [(sección, [párrafos o ("tabla", filas)])])
PROCEDIMIENTOS = [
    ("procedimiento_monitoreo_plagas", "PR-SAN-001", "Monitoreo y evaluación de plagas y enfermedades", [
        ("1. Objetivo", ["Detectar a tiempo las plagas y enfermedades de cada bloque y decidir si una intervención se "
                         "justifica, con datos registrados y comparables entre campañas."]),
        ("2. Frecuencia y puntos de muestreo", [
            "El evaluador recorre cada bloque una vez por semana, y dos veces por semana en floración y en los 30 días "
            "previos a la cosecha. En cada bloque evalúa 20 plantas elegidas en zigzag y marca con cinta las plantas "
            "con daño para seguirlas.",
            "En arándano se revisan brotes, flores y frutos; en palto, brotes, hojas maduras y frutos; en uva de mesa, "
            "racimos, hojas y sarmientos. Las trampas amarillas y de feromona se revisan en la misma visita."]),
        ("3. Qué se registra", [
            ("tabla", [("Dato", "Cómo se registra"),
                       ("Plaga o enfermedad", "Nombre común y científico; si hay duda, foto y muestra al laboratorio"),
                       ("Nivel de infestación", "Individuos por órgano o porcentaje de órganos dañados"),
                       ("Estado fenológico", "Según la escala usada por la empresa para cada cultivo"),
                       ("Controladores biológicos vistos", "Especie y cantidad aproximada")])]),
        ("4. Umbral de acción", [
            "La empresa fija para cada plaga un umbral de acción por cultivo y estado fenológico, revisado cada campaña "
            "por el jefe de sanidad vegetal con base en los manuales técnicos del INIA y la experiencia de campo. Si el "
            "nivel supera el umbral, el evaluador avisa el mismo día y se evalúa una intervención según PR-SAN-002."]),
        ("5. Registros", ["La evaluación se registra en el formato FR-SAN-001 o en la aplicación de campo y se conserva "
                          "tres años. Los registros alimentan la trazabilidad del lote (PR-CAL-003)."]),
    ]),
    ("procedimiento_manejo_integrado", "PR-SAN-002", "Manejo integrado de plagas", [
        ("1. Objetivo", ["Mantener las plagas por debajo del daño económico combinando medidas culturales, biológicas, "
                         "etológicas y químicas, de modo que el uso de plaguicidas sea el último recurso y el lote cumpla "
                         "los límites de residuos de sus mercados."]),
        ("2. Orden de las medidas", [
            "Primero se aplican las medidas culturales: poda y raleo que mejoren la aireación, manejo del riego para "
            "evitar exceso de humedad, eliminación de frutos caídos y de restos de poda, y control de malezas "
            "hospederas.",
            "Después, el control biológico y etológico: liberación de controladores (PR-SAN-009), trampas de feromona y "
            "confusión sexual donde exista. El control químico se usa solo si el monitoreo supera el umbral y no hay "
            "alternativa eficaz, con un producto registrado y elegido según PR-SAN-003 y PR-SAN-008."]),
        ("3. Criterios para elegir una intervención química", [
            "Se prefiere el producto con menor riesgo de residuo para los mercados del lote, menor toxicidad para los "
            "controladores biológicos y un modo de acción distinto del usado en la aplicación anterior. La decisión se "
            "anota con su motivo en el programa del bloque."]),
        ("4. Revisión", ["Al cierre de cada campaña se revisa qué medidas funcionaron, qué plagas superaron el umbral y "
                         "cuántas aplicaciones químicas se hicieron por bloque, para ajustar el programa siguiente."]),
    ]),
    ("procedimiento_programa_fitosanitario", "PR-SAN-003", "Elaboración y aprobación del programa fitosanitario", [
        ("1. Objetivo", ["Planificar por bloque y por campaña qué productos podrían usarse, en qué etapa y con qué "
                         "restricciones, antes de que haga falta aplicar."]),
        ("2. Contenido del programa", [
            ("tabla", [("Campo", "Contenido"),
                       ("Bloque", "Código, cultivo, variedad y superficie"),
                       ("Mercados de destino", "Todos los mercados posibles para la fruta del bloque y el perfil de cada cliente"),
                       ("Aplicaciones previstas", "Producto, ingrediente activo, dosis, plaga objetivo y etapa fenológica"),
                       ("Fecha estimada de cosecha", "Para verificar la carencia de cada aplicación")])]),
        ("3. Validación antes de aprobar", [
            "Cada aplicación prevista se valida con el sistema de verificación de cumplimiento: registro del producto en "
            "el SENASA para el cultivo y la plaga, carencia frente a la fecha de cosecha, límite máximo de residuos "
            "vigente en cada mercado y rotación de modos de acción. Las cifras se toman del sistema, que las obtiene de "
            "las fuentes oficiales, y no de este documento.",
            "Una aplicación con un hallazgo de severidad alta no se aprueba. Si el hallazgo afecta a un solo mercado, el "
            "responsable de calidad decide si el lote se destina a otro mercado o se cambia el producto."]),
        ("4. Aprobación y cambios", ["El jefe de sanidad vegetal aprueba el programa y el responsable de calidad lo "
                                     "revisa. Todo cambio durante la campaña se valida de nuevo y queda registrado con la "
                                     "fecha y quién lo aprobó."]),
    ]),
    ("procedimiento_calibracion", "PR-SAN-005", "Calibración de equipos de aplicación", [
        ("1. Objetivo", ["Garantizar que cada equipo aplique el volumen y la dosis previstos, porque una dosis mayor a la "
                         "de la etiqueta puede dejar residuos por encima del límite aunque se respete la carencia."]),
        ("2. Frecuencia", ["Cada equipo se calibra al inicio de la campaña, cada tres meses, cuando se cambian boquillas "
                           "y siempre que se sospeche una falla."]),
        ("3. Pasos", [
            "Se revisa el estado de mangueras, filtros y boquillas; se reemplaza toda boquilla cuyo caudal se desvíe más "
            "de 10 % del nominal. Se mide el caudal de cada boquilla con agua durante un minuto y se calcula el volumen "
            "por hectárea con la velocidad de avance real medida en el bloque.",
            "Con el volumen por hectárea se ajusta la concentración de la mezcla para respetar la dosis de la etiqueta. "
            "El resultado se anota en el formato FR-SAN-005 con la firma del operario y del supervisor."]),
        ("4. Equipo no conforme", ["Un equipo que no pasa la calibración queda fuera de uso con una etiqueta visible "
                                   "hasta su reparación y una nueva calibración."]),
    ]),
    ("procedimiento_almacen_plaguicidas", "PR-SAN-006", "Almacenamiento y manejo de plaguicidas", [
        ("1. Objetivo", ["Guardar y manipular los plaguicidas sin riesgo para las personas, el ambiente ni la fruta, y "
                         "saber en todo momento qué hay en el almacén."]),
        ("2. Condiciones del almacén", [
            "El almacén es de uso exclusivo, ventilado, con piso impermeable y bordes de contención, bajo llave y con "
            "acceso solo para personal capacitado. Los productos se guardan en sus envases originales, con la etiqueta "
            "legible, separados por tipo (insecticidas, fungicidas, herbicidas) y lejos de fertilizantes y alimentos.",
            "Se mantienen a la vista las hojas de seguridad de cada producto, un botiquín, material absorbente para "
            "derrames y los teléfonos de emergencia."]),
        ("3. Inventario", ["Cada entrada y salida se registra con el número de lote del producto. Al recibir un producto "
                           "se verifica que su número de registro figure vigente en el SENASA; un producto sin registro "
                           "vigente no se recibe. El inventario se concilia una vez al mes."]),
        ("4. Derrames", ["Ante un derrame se aísla la zona, se usa el equipo de protección, se contiene con material "
                         "absorbente y se recoge en un recipiente rotulado para su disposición. El incidente se informa al "
                         "jefe de sanidad vegetal el mismo día."]),
    ]),
    ("procedimiento_envases_vacios", "PR-SAN-007", "Triple lavado y disposición de envases vacíos", [
        ("1. Objetivo", ["Evitar que los envases vacíos de plaguicidas contaminen el agua, el suelo o la fruta, y "
                         "entregarlos a un gestor autorizado."]),
        ("2. Triple lavado", [
            "Al vaciar el envase durante la preparación de la mezcla, se llena hasta un cuarto con agua, se tapa, se "
            "agita y el enjuague se vierte en el tanque de aplicación. La operación se repite tres veces. Después se "
            "perfora el envase para que no se reutilice."]),
        ("3. Acopio y entrega", ["Los envases lavados y perforados se guardan en un área techada y rotulada hasta su "
                                 "entrega a un gestor o centro de acopio autorizado, que emite una constancia. La "
                                 "constancia se archiva con el registro del almacén."]),
    ]),
    ("procedimiento_rotacion_modos_accion", "PR-SAN-008", "Rotación de modos de acción y manejo de resistencia", [
        ("1. Objetivo", ["Retrasar la aparición de poblaciones resistentes alternando ingredientes de distinto modo de "
                         "acción, según las clasificaciones del FRAC (fungicidas), el IRAC (insecticidas) y el HRAC "
                         "(herbicidas)."]),
        ("2. Reglas de la empresa", [
            "No se aplican más de dos veces seguidas productos del mismo grupo de modo de acción contra la misma plaga en "
            "un bloque. Cuando el fabricante o el comité de resistencia indica un número máximo de aplicaciones por "
            "campaña para un grupo, se respeta el menor de los dos límites.",
            "Las mezclas de dos ingredientes cuentan como aplicación de ambos grupos. El grupo de cada ingrediente se "
            "toma del sistema, que lo carga de las listas oficiales del FRAC, el IRAC y el HRAC."]),
        ("3. Seguimiento", ["Si una plaga sigue por encima del umbral después de dos aplicaciones de grupos distintos, "
                            "se envía una muestra al laboratorio para evaluar resistencia antes de seguir aplicando."]),
    ]),
    ("procedimiento_control_biologico", "PR-SAN-009", "Uso de controladores biológicos", [
        ("1. Objetivo", ["Integrar las liberaciones de enemigos naturales y los productos biológicos al manejo de plagas "
                         "sin anular su efecto con aplicaciones químicas incompatibles."]),
        ("2. Recepción y liberación", [
            "Cada lote de controladores se recibe con su certificado de calidad del proveedor y se libera el mismo día, "
            "en las primeras horas de la mañana o al atardecer, distribuido en los focos que señaló el monitoreo. Los "
            "productos biológicos (hongos entomopatógenos, Bacillus y otros) se usan solo si cuentan con registro del "
            "SENASA para el cultivo."]),
        ("3. Compatibilidad", ["Antes de una aplicación química en un bloque con liberaciones recientes se consulta la "
                               "compatibilidad del producto con el controlador y, si es tóxico para él, se espera el "
                               "tiempo que indica el proveedor o se elige otro producto."]),
        ("4. Evaluación", ["El monitoreo semanal registra la presencia de los controladores liberados y su efecto sobre "
                           "la plaga, para decidir nuevas liberaciones."]),
    ]),
    ("procedimiento_muestreo_residuos", "PR-CAL-001", "Muestreo de fruta para análisis de residuos", [
        ("1. Objetivo", ["Tomar muestras representativas de cada lote para que el laboratorio mida los residuos de "
                         "plaguicidas antes del embarque."]),
        ("2. Cuándo se muestrea", ["Se muestrea cada lote antes de la cosecha comercial, después de que vencieron las "
                                   "carencias de todas las aplicaciones registradas, y cada vez que un cliente lo exige "
                                   "en su perfil."]),
        ("3. Cómo se muestrea", [
            "La muestra se compone de frutos tomados de varios puntos del bloque, en la cantidad que pide el laboratorio "
            "acreditado. Se usan guantes nuevos, bolsas limpias y rotuladas con el código del lote, y la muestra se "
            "envía refrigerada el mismo día con la cadena de custodia firmada.",
            "Se adjunta al pedido la lista de ingredientes aplicados en el bloque, tomada del registro de aplicaciones, "
            "para que el laboratorio confirme que su método los cubre."]),
        ("4. Resultados", ["Los resultados se cargan en el sistema, que los compara con el límite de cada mercado del "
                           "lote y con el perfil del cliente (PR-CAL-002)."]),
    ]),
    ("procedimiento_liberacion_lotes", "PR-CAL-002", "Liberación de lotes y perfil del cliente", [
        ("1. Objetivo", ["Decidir si un lote puede despacharse a cada mercado y cliente, con evidencia de que cumple los "
                         "límites legales y las exigencias propias del comprador."]),
        ("2. Criterios", [
            "Un lote se libera para un mercado si todos los residuos medidos están por debajo del límite vigente en ese "
            "mercado a la fecha de llegada prevista. Si el mercado no fija un límite específico, se aplica el que prevé "
            "su norma para ese caso; el sistema indica cuál rige.",
            "Muchos clientes exigen además un perfil propio, por ejemplo un porcentaje del límite legal o un número "
            "máximo de ingredientes detectados. El lote debe cumplir el perfil de cada cliente al que se destina."]),
        ("3. Decisión y registro", ["El responsable de calidad firma la liberación en el sistema, que guarda los "
                                    "resultados, la versión de los límites usada y el veredicto. Un lote que no cumple "
                                    "para un mercado puede liberarse para otro donde sí cumpla."]),
    ]),
    ("procedimiento_trazabilidad", "PR-CAL-003", "Trazabilidad del lote", [
        ("1. Objetivo", ["Poder reconstruir, para cualquier caja despachada, de qué bloque salió, qué se le aplicó y qué "
                         "resultados de laboratorio tuvo."]),
        ("2. Identificación", ["Cada lote recibe un código que une la fecha de cosecha, el bloque y el turno. El código "
                               "se imprime en las jabas de campo, se mantiene en el empaque y figura en cada caja y en la "
                               "guía de despacho."]),
        ("3. Registros enlazados", [
            ("tabla", [("Registro", "Dónde está"),
                       ("Aplicaciones del bloque", "Registro de aplicaciones (PR-SAN-004)"),
                       ("Monitoreo de plagas", "FR-SAN-001 (PR-SAN-001)"),
                       ("Resultados de residuos", "Sistema, módulo de laboratorio (PR-CAL-001)"),
                       ("Liberación por mercado", "Sistema, con la firma de calidad (PR-CAL-002)")])]),
        ("4. Simulacro", ["Dos veces por campaña se hace un simulacro: se elige una caja al azar y se reconstruye su "
                          "historia completa. El tiempo y los vacíos encontrados se registran y se corrigen."]),
    ]),
    ("procedimiento_rechazos", "PR-CAL-004", "Atención de rechazos y notificaciones en destino", [
        ("1. Objetivo", ["Responder de forma ordenada cuando un lote es rechazado o notificado en destino por residuos, "
                         "plagas o documentación, y evitar que se repita."]),
        ("2. Pasos", [
            "Se identifica el lote con la trazabilidad (PR-CAL-003) y se reúnen sus registros. Se compara el hallazgo "
            "del destino con los resultados propios y con el límite que estaba vigente en la fecha del embarque.",
            "Se determina la causa: producto no permitido en ese mercado, carencia no respetada, dosis mayor, deriva "
            "desde un bloque vecino, contaminación en el empaque o un cambio normativo no detectado."]),
        ("3. Acciones", ["Se bloquean los lotes del mismo bloque y periodo hasta tener resultados, se informa al cliente "
                         "y se corrige la causa en el programa o en el procedimiento afectado. Si la causa fue un cambio "
                         "de límite, se revisa por qué la alerta del sistema no se atendió a tiempo."]),
    ]),
    ("procedimiento_cosecha_carencia", "PR-COS-001", "Cosecha y verificación de la carencia", [
        ("1. Objetivo", ["Asegurar que ningún bloque se coseche antes de que venza la carencia de todas sus aplicaciones."]),
        ("2. Verificación", [
            "Un día antes de la cosecha, el responsable de calidad consulta en el sistema la fecha segura de cosecha "
            "del bloque, calculada con la última aplicación de cada producto y su carencia oficial. Si la fecha segura "
            "es posterior a la prevista, la cosecha se reprograma.",
            "La carencia de la etiqueta no garantiza que el residuo quede por debajo del límite de todos los mercados; "
            "para mercados exigentes se verifica también el resultado de laboratorio (PR-CAL-001)."]),
        ("3. Autorización", ["El jefe de campo solo inicia la cosecha con la autorización firmada de calidad en el "
                             "sistema, que queda enlazada al código del lote."]),
    ]),
    ("instructivo_consulta_lmr", "IN-SAN-001", "Instructivo: consulta de límites máximos de residuos por mercado", [
        ("1. Objetivo", ["Indicar cómo consultar el límite vigente de un ingrediente en un cultivo para cada mercado, "
                         "sin copiar valores a documentos que luego quedan desactualizados."]),
        ("2. Pasos", [
            "En el sistema, abrir «Límites», elegir el cultivo, el ingrediente activo y la fecha de evaluación (la de "
            "llegada prevista del embarque). El sistema muestra el límite de cada mercado con su norma, la fecha de la "
            "instantánea de la fuente y si el valor es específico, por defecto o si no hay datos.",
            "Si el sistema indica «sin datos» para un mercado, no se asume ningún valor: se consulta al responsable de "
            "calidad antes de aplicar o despachar."]),
        ("3. Advertencias", ["Los límites cambian. Un valor anotado en un correo o en una hoja de cálculo puede no estar "
                             "vigente; la referencia es siempre la consulta del día en el sistema. Las alertas avisan de "
                             "límites aprobados que todavía no se aplican."]),
    ]),
    ("procedimiento_seguridad_aplicador", "PR-SST-001", "Seguridad del personal en aplicaciones", [
        ("1. Objetivo", ["Proteger la salud de quienes preparan y aplican plaguicidas y de quienes ingresan después a "
                         "los bloques tratados."]),
        ("2. Equipo de protección", ["El equipo de protección se elige según la hoja de seguridad del producto: "
                                     "respirador con filtros adecuados, lentes, guantes de nitrilo, traje impermeable y "
                                     "botas. Se revisa antes de cada uso y se lava separado de la ropa personal."]),
        ("3. Reingreso", ["Después de una aplicación, el bloque se señaliza y nadie entra sin protección hasta que vence "
                          "el periodo de reingreso indicado en la etiqueta. La señal indica el producto, la fecha y la hora "
                          "en que se puede volver a entrar."]),
        ("4. Salud del personal", ["El personal que aplica recibe capacitación anual y un control médico ocupacional "
                                   "periódico. Ante cualquier síntoma de intoxicación se suspende la labor y se sigue la "
                                   "hoja de seguridad mientras se traslada a la persona al centro de salud."]),
    ]),
]


def generar() -> list[Path]:
    salidas = []
    for archivo, codigo, titulo, secciones in PROCEDIMIENTOS:
        d = Document()
        d.core_properties.title = titulo
        d.core_properties.author = EMPRESA
        d.add_heading(titulo, level=0)
        d.add_paragraph(f"{EMPRESA}. Código {codigo}, versión 1. Cultivos: {CULTIVOS}.")
        for seccion, contenido in secciones:
            d.add_heading(seccion, level=1)
            for parte in contenido:
                if isinstance(parte, tuple) and parte[0] == "tabla":
                    filas = parte[1]
                    t = d.add_table(rows=len(filas), cols=len(filas[0]))
                    for r, fila in enumerate(filas):
                        for c, valor in enumerate(fila):
                            t.cell(r, c).text = valor
                else:
                    d.add_paragraph(parte)
        ruta = HERE / f"{archivo}.docx"
        d.save(ruta)
        salidas.append(ruta)
    return salidas


if __name__ == "__main__":
    for p in generar():
        print(p.name)
