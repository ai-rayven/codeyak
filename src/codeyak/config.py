import tomllib
from pathlib import Path
from typing import Any, Tuple, Type

from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def get_config_path() -> Path:
    """Get the path to the config file (~/.config/codeyak/config.toml)."""
    return Path.home() / ".config" / "codeyak" / "config.toml"


def config_file_exists() -> bool:
    """Check if the config file exists."""
    return get_config_path().exists()


class TomlConfigSettingsSource(PydanticBaseSettingsSource):
    """
    Custom settings source that reads from TOML config file.
    """

    def get_field_value(
        self, _field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        config_path = get_config_path()
        if not config_path.exists():
            return None, field_name, False

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        field_value = data.get(field_name)
        return field_value, field_name, field_value is not None

    def __call__(self) -> dict[str, Any]:
        config_path = get_config_path()
        if not config_path.exists():
            return {}

        with open(config_path, "rb") as f:
            return tomllib.load(f)


class Settings(BaseSettings):
    # GitLab Configuration (optional - for MR reviews)
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_TOKEN: str = ""

    # Azure OpenAI Configuration (required for reviews)
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    AZURE_DEPLOYMENT_NAME: str = "gpt-4o"

    # Observability (Optional but recommended)
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        Customize settings sources priority.

        Priority (highest to lowest):
        1. TOML config file (if exists)
        2. Environment variables (fallback for CI/CD when no config file)
        3. .env file
        4. Default values
        """
        toml_source = TomlConfigSettingsSource(settings_cls)

        # If config file exists, it takes priority over env vars
        if config_file_exists():
            return (
                init_settings,
                toml_source,
                env_settings,
                dotenv_settings,
                file_secret_settings,
            )
        else:
            # No config file - env vars are primary (CI/CD scenario)
            return (
                init_settings,
                env_settings,
                dotenv_settings,
                file_secret_settings,
            )


# Private singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Get or create the settings singleton.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """
    Reset the settings singleton.
    Call after init to reload config.
    """
    global _settings
    _settings = None


def is_llm_configured() -> bool:
    """Check if LLM (Azure OpenAI) settings are configured."""
    settings = get_settings()
    return bool(settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT)


def is_gitlab_configured() -> bool:
    """Check if GitLab settings are configured."""
    settings = get_settings()
    return bool(settings.GITLAB_TOKEN)


def is_langfuse_configured() -> bool:
    """Check if Langfuse settings are configured."""
    settings = get_settings()
    return bool(settings.LANGFUSE_SECRET_KEY and settings.LANGFUSE_PUBLIC_KEY)
