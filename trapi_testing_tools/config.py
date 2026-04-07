from typing import ClassVar, override

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, YamlConfigSettingsSource


class TTTConfig(BaseSettings):
    """Basic config for the TRAPI Testing Tools."""

    timeout: float = 300
    test_repo: str = "NCATSTranslator/Tests"
    default_environment: str = "retriever"
    environments: dict[str, dict[str, str]] = {
        "retriever": {
            "local": "http://localhost:8080",
            "ci": "https://retriever.ci.transltr.io",
            "dev": "https://dev.retriever.biothings.io",
        },
    }

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
