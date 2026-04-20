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
    #
    # Hosted examples (set in .env or as environment variables):
    #   Azure Database for PostgreSQL — Flexible Server:
    #     postgresql+asyncpg://<user>:<password>@<server>.postgres.database.azure.com:5432/ecommerce?ssl=require
    #   Google Cloud SQL: postgresql+asyncpg://user:pass@<cloud-sql-ip>:5432/ecommerce
    #   Supabase / Neon also work — they speak standard Postgres.
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
    #   Azure Cache for Redis: rediss://<user>:<access-key>@<name>.redis.cache.windows.net:6380
    #   Upstash:               rediss://default:<pass>@<host>.upstash.io:6379
    # ------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379"

    # ------------------------------------------------------------------
    # Elasticsearch (product search engine)
    #
    # Local Docker has no auth. Hosted providers usually require one of:
    #   - Basic auth (Elastic Cloud on Azure, Bonsai)   → set es_username + es_password
    #   - API key   (Elastic Cloud on Azure, recommended) → set es_api_key
    #
    # Azure does not offer a first-party managed Elasticsearch service;
    # the official path is Elastic Cloud on the Azure Marketplace, which
    # runs on Azure infrastructure but is operated by Elastic.
    #
    # Leave all auth fields unset for the local Docker setup.
    # If both an api_key and username/password are set, the api_key wins.
    # ------------------------------------------------------------------
    elasticsearch_url: str = "http://localhost:9200"
    es_username: str | None = None
    es_password: str | None = None
    es_api_key: str | None = None

    # ------------------------------------------------------------------
    # Object storage (product images) — Azure Blob Storage
    #
    # Local:      Azurite (Microsoft's official Azure Blob emulator,
    #             running in Docker via mcr.microsoft.com/azure-storage/azurite)
    # Production: Azure Blob Storage in your Azure subscription
    #
    # The connection string is the single setting that switches between
    # local and production — same SDK code path either way.
    #
    # Local (Azurite well-known dev connection string):
    #   DefaultEndpointsProtocol=http;
    #   AccountName=devstoreaccount1;
    #   AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;
    #   BlobEndpoint=http://localhost:10000/devstoreaccount1;
    #
    # Production (real Azure storage account):
    #   DefaultEndpointsProtocol=https;
    #   AccountName=<your-storage-account>;
    #   AccountKey=<your-storage-account-key>;
    #   EndpointSuffix=core.windows.net
    # ------------------------------------------------------------------
    azure_storage_connection_string: str = (
        "DefaultEndpointsProtocol=http;"
        "AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
        "BlobEndpoint=http://localhost:10000/devstoreaccount1;"
    )
    azure_storage_container: str = "product-images"

    # ------------------------------------------------------------------
    # RabbitMQ (async message queue for post-order tasks)
    # Local:      RabbitMQ running in Docker
    # Hosted examples:
    #   CloudAMQP (also available as an Azure Marketplace plan):
    #     amqps://<user>:<pass>@<host>.cloudamqp.com/<vhost>
    #   Self-host on Azure Kubernetes Service (AKS) with the bitnami chart.
    #
    # Note: Azure Service Bus is not AMQP 0-9-1 compatible with aio_pika
    # in the way RabbitMQ is — switching to it would require rewriting
    # queue.py and order_worker.py with the azure-servicebus SDK.
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
