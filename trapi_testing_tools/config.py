from copy import deepcopy
from typing import ClassVar, Self, override

from pydantic import Field, field_validator
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
        "ci": "https://retriever.ci.transltr.io",
        "dev": "https://dev.retriever.biothings.io",
    },
    "shepherd": {
        "aragorn.dev": "https://shepherd.renci.org/aragorn",
        "arax.dev": "https://shepherd.renci.org/arax",
        "bte.dev": "https://shepherd.renci.org/bte",
        "sipr.dev": "https://shepherd.renci.org/sipr",
    },
}


class TTTConfig(BaseSettings):
    """Basic config for the TRAPI Testing Tools."""

    timeout: float = 300
    test_repo: str = "NCATSTranslator/Tests"
    default_environment: str = "retriever"
    environments: dict[str, dict[str, str]] = Field(
        default_factory=lambda: DEFAULT_ENVS
    )

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
