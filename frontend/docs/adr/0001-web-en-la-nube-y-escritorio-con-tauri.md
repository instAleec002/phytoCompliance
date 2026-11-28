# 0001. Aplicación web en la nube y aplicación de escritorio que la refleja (Tauri)

Fecha: 27/10/2026. Estado: aceptada (decisión de la autora).

## Contexto
La versión principal del sistema vive en la nube, con URL pública para demostraciones y evaluadores. Además se quiere
una aplicación de escritorio que refleje la web y dependa del mismo backend en la nube; no necesita funcionar sin
conexión.

## Decisión
El frontend se construye de modo que pueda empaquetarse con Tauri sin reescribirse:

1. El frontend habla con el backend solo por la API (`/api/...` de FastAPI). No usa rutas de API, Server Actions ni
   lógica de servidor de Next.js.
2. Las páginas se renderizan en el cliente y el proyecto debe poder exportarse como sitio estático
   (`output: "export"`). Lo que no sea compatible con la exportación estática no se usa.
3. La URL del backend es configurable (`NEXT_PUBLIC_API_URL`): la web y la aplicación de escritorio apuntan al mismo
   backend en la nube.
4. La autenticación usa tokens en la cabecera `Authorization`, no cookies atadas al dominio, porque el escritorio carga
   la interfaz desde un origen propio.
5. El backend permite por CORS el origen de la web y el del escritorio (`tauri://localhost` y
   `http://tauri.localhost`).
6. Archivos locales (cargar el Excel del programa, guardar el reporte) se hacen con las API estándar del navegador, que
   Tauri también soporta; los accesos nativos, si se necesitan, se agregan solo en la capa de Tauri.

## Consecuencias
La aplicación de escritorio se agrega después como una carpeta `desktop/` al nivel de `frontend/`, con la
configuración de Tauri apuntando a la exportación estática del frontend. El backend no cambia.
