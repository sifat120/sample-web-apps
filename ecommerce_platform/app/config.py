"""
config.py — Application configuration

All settings are read from environment variables at startup.
The defaults here match the local Docker Compose setup so the app
works out-of-the-box without any extra configuration.

In production, set the real values as environment variables (or in a
secrets manager). Never commit actual credentials to source control.

How it works:
  pydantic-settings reads each field from the matching environment
  variable name (case-insensitive). If the variable is not set, it
  falls back to the default value defined here.

  Example: if REDIS_URL=redis://my-prod-host:6379 is set in the
  environment, settings.redis_url will be "redis://my-prod-host:6379".
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Tell pydantic-settings to also read from a ".env" file if it
    # exists in the working directory. The file is optional — real
    # environment variables always take precedence over the file.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ------------------------------------------------------------------
    # PostgreSQL (primary database)
    # Format: postgresql+asyncpg://user:password@host:port/database
    # asyncpg is the async PostgreSQL driver used by SQLAlchemy.
    # ------------------------------------------------------------------
    postgres_url: str = "postgresql+asyncpg://postgres:secret@localhost:5432/ecommerce"

    # ------------------------------------------------------------------
    # Valkey (cache + session store + rate limiting)
    #
    # Valkey is a BSD-licensed open-source fork of Redis. It uses the
    # same protocol, so the redis-py client connects to it unchanged.
    #
    # Local default connects to the Valkey Docker container.
    # Hosted examples (set in .env or as environment variables):
    #   AWS ElastiCache: rediss://default:<token>@<cluster>.cache.amazonaws.com:6379
    #   Upstash:         rediss://default:<pass>@<host>.upstash.io:6379
    # ------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379"

    # ------------------------------------------------------------------
    # Elasticsearch (product search engine)
    # ------------------------------------------------------------------
    elasticsearch_url: str = "http://localhost:9200"

    # ------------------------------------------------------------------
    # Object storage (product images)
    #
    # Local:      storage_endpoint_url = "http://localhost:9000"  (MinIO)
    # Production: leave storage_endpoint_url unset — boto3 will
    #             automatically connect to AWS S3.
    #
    # "str | None" means this value can be either a string or absent
    # (None). When it is None, boto3 uses its built-in AWS S3 endpoint.
    # ------------------------------------------------------------------
    storage_endpoint_url: str | None = None
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "product-images"
    storage_region: str = "us-east-1"

    # ------------------------------------------------------------------
    # RabbitMQ (async message queue for post-order tasks)
    # Local:      RabbitMQ running in Docker
    # Production: replace with a managed service URL (e.g. CloudAMQP)
    # ------------------------------------------------------------------
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # ------------------------------------------------------------------
    # General application settings
    # ------------------------------------------------------------------
    app_env: str = "local"      # "local" or "production"
    secret_key: str = "change-me-in-production"  # used for signing tokens


# Create a single shared instance.
# Every other module imports this object: `from app.config import settings`
settings = Settings()
