from app.di.dependency_injector import Container
from app.main import Application
from settings.config import StageEnum, load_app_settings


class ApplicationForTests(Application):
    def __init__(self, container: Container) -> None:
        super().__init__(container=container)


local_debug_settings = load_app_settings(stage=StageEnum.local_runtests)
