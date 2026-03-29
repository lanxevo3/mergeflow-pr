import os

def _load_secrets():
    secrets = {}
    base = os.path.dirname(os.path.abspath(__file__))
    secrets_path = os.path.join(base, "..", ".secrets")
    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    secrets[key.strip()] = value.strip()
    return secrets

_SECRETS = _load_secrets()

class Config:
    APP_NAME = "MergeFlow"
    APP_URL = "https://mergeflow.ai"
    DEBUG = False

    DATABASE_URL = _SECRETS.get("DATABASE_URL") or os.getenv(
        "DATABASE_URL",
        "postgresql://user:pass@localhost:5432/mergeflow"
    )
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    STRIPE_SECRET_KEY = _SECRETS.get("STRIPE_SECRET_KEY") or os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = _SECRETS.get("STRIPE_WEBHOOK_SECRET") or os.getenv("STRIPE_WEBHOOK_SECRET", "")

    GITHUB_CLIENT_ID = _SECRETS.get("GITHUB_CLIENT_ID") or os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = _SECRETS.get("GITHUB_CLIENT_SECRET") or os.getenv("GITHUB_CLIENT_SECRET", "")

    SECRET_KEY = _SECRETS.get("SECRET_KEY") or os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    SESSION_LIFETIME_HOURS = 720
