"""Configuración del backend: lee non_private/non_envs/.env (fuera del repositorio)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO / "non_private" / "non_envs" / ".env", extra="ignore")

    postgres_user: str = "fito"
    postgres_password: str = ""
    postgres_db: str = "fito"
    postgres_host: str = "localhost"
    postgres_port: int = 5434

    # esquema de las cuentas de usuario; otro valor sirve para pruebas aisladas
    accounts_schema: str = "cuentas"

    # Modo nube del generador. Con GEMINI_API_KEY (Google AI Studio) se usa esa clave; sin ella, Vertex AI con las
    # credenciales ADC de la máquina y el proyecto y la región de abajo.
    gemini_api_key: str = ""
    vertex_project: str = ""
    vertex_location: str = "us-central1"

    # API (interfaces.api). Las sesiones de usuario reemplazan al token compartido.
    # dirección de la interfaz, para armar los enlaces de activación y restablecimiento
    api_web_url: str = "http://localhost:3000"
    # orígenes permitidos por CORS, separados por comas: la web y la aplicación de escritorio (Tauri)
    api_cors_origins: str = "http://localhost:3000,tauri://localhost,http://tauri.localhost"

    @property
    def web_url(self) -> str:
        return self.api_web_url

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return (f"postgresql://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}")


settings = Settings()


def get_settings() -> Settings:
    """Dependency for the API, so tests can replace the settings."""
    return settings
