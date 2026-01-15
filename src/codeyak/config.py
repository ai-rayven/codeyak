from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # GitLab Configuration
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_TOKEN: str
    
    # Azure OpenAI Configuration
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    AZURE_DEPLOYMENT_NAME: str = "gpt-4o"
    
    # Observability (Optional but recommended)
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # Loads from .env file automatically
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Private singleton instance
_settings = None

def get_settings() -> Settings:
    """
    Get or create the settings singleton.

    Raises:
        pydantic.ValidationError: If required environment variables are missing
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings