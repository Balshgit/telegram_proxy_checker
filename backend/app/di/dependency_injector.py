import os
from pathlib import Path

from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, T

from app.di.adapters import AdaptersContainer
from app.di.gateways import GatewaysContainer
from app.di.infra import InfraContainer
from app.di.repositories import RepositoriesContainer
from app.di.services import ServicesContainer


def _get_wiring_modules() -> set[str]:
    BASE_DIR = Path(__file__).parent.parent
    modules: set[str] = set()

    for directory, _, files in os.walk(BASE_DIR):
        for file_name in files:
            relative_dir = os.path.relpath(directory, BASE_DIR)
            relative_file = ".".join(
                [
                    BASE_DIR.name,
                    relative_dir.replace(os.sep, "."),
                    file_name.replace(".py", ""),
                ]
            )
            if (
                "deps" in relative_file or "controllers" in relative_file or "tasks" in relative_file
            ) and "__" not in relative_file:
                modules.add(relative_file)
    return modules


class AsyncProvide(Provide):  # type: ignore
    async def __call__(self) -> T:
        return self


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=_get_wiring_modules())

    config = providers.Configuration(strict=True)

    infra = providers.Container(InfraContainer, config=config)
    adapters = providers.Container(AdaptersContainer, config=config)
    gateways = providers.Container(GatewaysContainer, config=config, infra=infra, adapters=adapters)

    repositories: providers.Container[RepositoriesContainer] = providers.Container(
        RepositoriesContainer, config=config, infra=infra, gateways=gateways, adapters=adapters
    )
    services: providers.Container[ServicesContainer] = providers.Container(
        ServicesContainer, config=config, repositories=repositories, infra=infra, gateways=gateways
    )
