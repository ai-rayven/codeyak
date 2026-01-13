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

# Singleton instance to import elsewhere
settings = Settings()