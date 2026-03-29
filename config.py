import os
from pydantic_settings import BaseSettings

def _load_secrets():
    """Load secrets from .secrets file."""
    secrets = {}
    secrets_path = os.path.join(os.path.dirname(__file__), "..", ".secrets")
    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    secrets[key.strip()] = value.strip()
    return secrets

_SECRETS = _load_secrets()

class Settings(BaseSettings):
    # App
    app_name: str = "MergeFlow"
    app_url: str = "https://mergeflow.ai"
    debug: bool = False

    # Database
    database_url: str = _SECRETS.get("DATABASE_URL", os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mergeflow"))

    # Stripe
    stripe_secret_key: str = _SECRETS.get("STRIPE_SECRET_KEY", os.getenv("STRIPE_SECRET_KEY", ""))
    stripe_webhook_secret: str = _SECRETS.get("STRIPE_WEBHOOK_SECRET", os.getenv("STRIPE_WEBHOOK_SECRET", ""))

    # GitHub OAuth
    github_client_id: str = _SECRETS.get("GITHUB_CLIENT_ID", os.getenv("GITHUB_CLIENT_ID", ""))
    github_client_secret: str = _SECRETS.get("GITHUB_CLIENT_SECRET", os.getenv("GITHUB_CLIENT_SECRET", ""))

    # Session
    secret_key: str = _SECRETS.get("SECRET_KEY", os.getenv("SECRET_KEY", "dev-secret-change-in-production"))
    session_lifetime_hours: int = 720

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
