from copy import deepcopy
from typing import ClassVar, Literal, override

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

DEFAULT_ENVS = {
    "ars": {
        "prod": "https://ars-prod.transltr.io/ars/api/messages",
        "test": "https://ars.test.transltr.io/ars/api/messages",
        "ci": "https://ars.ci.transltr.io/ars/api/messages",
        "dev": "https://ars-dev.transltr.io/ars/api/messages",
    },
    "retriever": {
        "local": "http://localhost:8080",
        "dev": "https://dev.retriever.biothings.io",
        "ci": "https://retriever.ci.transltr.io",
        "test": "https://retriever.test.transltr.io",
    },
    "shepherd": {
        "aragorn.dev": "https://shepherd.renci.org/aragorn",
        "arax.dev": "https://shepherd.renci.org/arax",
        "bte.dev": "https://shepherd.renci.org/bte",
        "sipr.dev": "https://shepherd.renci.org/sipr",
        "aragorn.ci": "https://shepherd.ci.transltr.io/aragorn",
        "arax.ci": "https://shepherd.ci.transltr.io/arax",
        "bte.ci": "https://shepherd.ci.transltr.io/bte",
        "sipr.ci": "https://shepherd.ci.transltr.io/sipr",
        "aragorn.test": "https://shepherd.test.transltr.io/aragorn",
        "arax.test": "https://shepherd.test.transltr.io/arax",
        "bte.test": "https://shepherd.test.transltr.io/bte",
        "sipr.test": "https://shepherd.test.transltr.io/sipr",
    },
}


class CallbackConfig(BaseModel):
    """Settings for receiving `/asyncquery` callbacks instead of polling.

    ``mode`` picks how TTT is reached: ``direct`` advertises the local receiver
    straight to the service, ``tunnel`` exposes it via a cloudflared quick tunnel,
    ``poll`` keeps the legacy status-polling, and ``auto`` chooses direct for
    loopback/private targets and tunnel otherwise (falling back to poll if
    cloudflared is unavailable).
    """

    mode: Literal["auto", "tunnel", "direct", "poll"] = "auto"
    host: str = (
        "127.0.0.1"  # advertised host for direct mode (e.g. host.docker.internal)
    )
    bind: str = "127.0.0.1"  # receiver bind address (0.0.0.0 to reach from a container)
    port: int = 0  # 0 = OS-assigned ephemeral port
    cloudflared_path: str = "cloudflared"


class TTTConfig(BaseSettings):
    """Basic config for the TRAPI Testing Tools."""

    timeout: float = 300
    test_repo: str = "NCATSTranslator/Tests"
    default_environment: str = "retriever"
    viewer: str = "fx"
    submitter: str = (
        "trapi-testing-tools"  # auto-injected into TRAPI bodies; "" disables
    )
    environments: dict[str, dict[str, str]] = Field(
        default_factory=lambda: DEFAULT_ENVS
    )
    callback: CallbackConfig = Field(default_factory=CallbackConfig)

    @field_validator("environments", mode="after")
    @classmethod
    def include_default(
        cls, value: dict[str, dict[str, str]]
    ) -> dict[str, dict[str, str]]:
        """Ensure the defaults are included, with the config taking precedence."""
        envs = deepcopy(DEFAULT_ENVS)
        envs.update(value)
        return envs

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        case_sensitive=False,
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        yaml_file="config.yaml",
        yaml_file_encoding="utf-8",
    )

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Ensure proper setting priority order."""
        return (
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            init_settings,
        )


CONFIG = TTTConfig()
