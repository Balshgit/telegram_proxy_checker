from types import SimpleNamespace

from app.di.dependency_injector import Container


class DummyContext:
    def __init__(self, container: Container) -> None:
        self.state = SimpleNamespace(container=container)
