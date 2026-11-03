"""Uygulama ayarları. Değerler ortam değişkenlerinden ve `.env` dosyasından okunur (spec §14)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HAVA_", extra="ignore")

    env: Literal["dev", "prod", "test"] = "dev"

    # Veritabanı: TimescaleDB konteyneri POSTGRES_* değişkenlerini kullanır; uygulama da okur.
    db_host: str = "db"
    db_port: int = 5432
    postgres_db: str = Field(default="hava", validation_alias="POSTGRES_DB")
    postgres_user: str = Field(default="hava", validation_alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(
        default=SecretStr(""), validation_alias="POSTGRES_PASSWORD"
    )
    # Testler/CI için tam bağlantı adresi (verilirse yukarıdakilerin yerine geçer).
    database_url: str | None = None

    http_user_agent: str = "istweather/0.1 (+https://github.com/hsngllc/istweather)"
    cors_origins: str = "http://localhost:3000"
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("")
    mgm_enabled: bool = False

    # Gözlem kaynakları (spec §5.3). Adresler kaynak kapatma denemesi için değiştirilebilir.
    metar_awc_url: str = "https://aviationweather.gov/api/data/metar"
    metar_iem_url: str = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
    metar_awc_hours: int = 3
    # Tazelik eşikleri (dakika). METAR 30 dakikada bir yayımlanır.
    metar_stale_minutes: int = 90
    awc_fetch_stale_minutes: int = 30

    # Model verisi (spec §5.1). Kırpma kutusu bölge kutusu + pay (nokta komşulukları için).
    ecmwf_base_url: str = "https://data.ecmwf.int/forecasts"
    dwd_base_url: str = "https://opendata.dwd.de/weather/nwp/v1/m"  # yalnız ~24 sa saklar
    gfs_base_url: str = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"  # AWS NODD, anonim
    model_max_lead_h: int = 168
    model_crop_margin_deg: float = 1.0
    model_download_workers: int = 8
    model_lookback_hours: int = 72  # portal ~12 çalıştırma tutar; kaçırılanlar bu pencerede aranır
    grib_retention_days: int = 30

    # Bildirimler (spec §14). Kanal ayarı boşsa yalnız loga yazılır.
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    alert_email_to: str = ""

    region_config: str = "config/region.istanbul.yaml"
    models_config: str = "config/models.yaml"
    parquet_dir: str = "/data/parquet"
    grib_dir: str = "/data/grib"

    @property
    def sqlalchemy_url(self) -> str | URL:
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value() or None,
            host=self.db_host,
            port=self.db_port,
            database=self.postgres_db,
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
