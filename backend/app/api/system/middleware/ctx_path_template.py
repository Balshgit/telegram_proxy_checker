"""Т.к. при вычислении path_template итерируемся по всем роутам и ищем совпадения регулярками, то было решено вынести
извлеченный path_template в контекстную переменную, чтобы это можно было использовать в нескольких местах без повторных
вычислений.
"""

from contextvars import ContextVar

_ctx_path_template: ContextVar[str | None] = ContextVar("ctx_path_template", default=None)


def get_ctx_path_template() -> str | None:
    return _ctx_path_template.get()


def set_ctx_path_template(path_template: str) -> None:
    _ctx_path_template.set(path_template)
