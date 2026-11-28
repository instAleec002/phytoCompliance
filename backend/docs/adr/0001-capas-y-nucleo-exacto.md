# 0001. Capas del backend y núcleo exacto

Fecha: 27/10/2026. Estado: aceptada.

## Contexto
El sistema maneja conocimientos de distinta naturaleza: registros, LMR y reglas que tienen una respuesta exacta, y
manuales y etiquetas en texto libre. Una respuesta de cumplimiento equivocada puede llevar a un rechazo en destino.

## Decisión
El código se organiza en capas: `shared`, `domain`, `knowledge`, `assistant` e `interfaces`. El dominio resuelve el
cumplimiento con consultas y reglas sobre el grafo y no importa la capa de lenguaje; una prueba lo verifica
(`tests/unit/test_architecture.py`). El modelo de lenguaje interpreta, recupera y redacta con citas.

## Consecuencias
El núcleo exacto se puede probar y evaluar sin el modelo (línea base CR del protocolo). La API expone el dominio y el
asistente por separado.
