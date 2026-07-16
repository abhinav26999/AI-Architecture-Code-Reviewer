import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Architecture Code Reviewer"
    API_V1_STR: str = "/api/v1"

    # GitHub App configuration
    GITHUB_APP_ID: str = ""
    GITHUB_PRIVATE_KEY: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_WEBHOOK_SECRET: Optional[str] = None

    # Repository Ingestion settings
    TEMP_CLONE_DIR: str = ""

    # Database settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    DIRECT_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/postgres"

    # Embedding Settings
    EMBEDDING_PROVIDER: str = "ollama"
    OLLAMA_EMBED_URL: str = "http://localhost:11434/api/embeddings"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # LLM Reasoning Settings
    LLM_PROVIDER: str = "ollama"
    OLLAMA_GEN_MODEL: str = "llama3"
    OLLAMA_GEN_URL: str = "http://localhost:11434/api/generate"
    @property
    def resolved_temp_clone_dir(self) -> str:
        """Returns the absolute path of the clone directory, resolved relative to backend root if relative."""
        if not self.TEMP_CLONE_DIR:
            # Default to backend/temp_clones
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            path = os.path.join(backend_dir, "temp_clones")
        else:
            path = self.TEMP_CLONE_DIR
            if not os.path.isabs(path):
                backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                path = os.path.join(backend_dir, path)
        return os.path.abspath(path)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def private_key_content(self) -> str:
        """
        Returns the private key content. If GITHUB_PRIVATE_KEY is a path to a file,
        reads and returns file content. Otherwise, returns the value directly.
        """
        if not self.GITHUB_PRIVATE_KEY:
            return ""
        
        # If it looks like a file path and the file exists, read it
        if os.path.exists(self.GITHUB_PRIVATE_KEY):
            try:
                with open(self.GITHUB_PRIVATE_KEY, "r") as f:
                    return f.read()
            except Exception as e:
                # Fallback to direct string if reading fails
                pass
        
        # Clean up any escaped newlines if passed directly in env
        key = self.GITHUB_PRIVATE_KEY
        if "\\n" in key:
            key = key.replace("\\n", "\n")
            
        # Ensure it contains PEM headers
        if "BEGIN RSA PRIVATE KEY" not in key and "BEGIN PRIVATE KEY" not in key:
            # Reconstruct PEM formatting if headers are missing
            lines = [key[i:i+64] for i in range(0, len(key), 64)]
            key = "-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END RSA PRIVATE KEY-----\n"
            
        return key


settings = Settings()
