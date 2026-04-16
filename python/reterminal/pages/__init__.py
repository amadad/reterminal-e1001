"""Page registry and discovery for legacy fixed pages."""

from __future__ import annotations

from importlib import import_module
from typing import TypeVar

from reterminal.pages.base import BasePage

PageT = TypeVar("PageT", bound=BasePage[object])
PageEntry = tuple[type[BasePage[object]], int]

_registry: dict[str, PageEntry] = {}
ALIASES: dict[str, list[str] | None] = {"all": None}


def register(name: str, page_number: int = 0):
    """Register a legacy page class under a CLI name and default slot."""

    def decorator(cls: type[PageT]) -> type[PageT]:
        _registry[name] = (cls, page_number)
        return cls

    return decorator


def get_page(name: str) -> PageEntry | None:
    """Get page class and default page number by name."""
    return _registry.get(name)


def get_page_class(name: str) -> type[BasePage[object]] | None:
    """Get page class by name."""
    entry = _registry.get(name)
    return entry[0] if entry else None


def list_pages() -> dict[str, int]:
    """List all registered pages with their default page numbers."""
    return {name: entry[1] for name, entry in _registry.items()}


def get_all_page_names() -> list[str]:
    """Get list of all registered page names."""
    return list(_registry.keys())


for _module in (
    "market",
    "clock",
    "github",
    "status",
    "portfolio",
    "dashboard",
    "weather",
):
    import_module(f"reterminal.pages.{_module}")

ALIASES["all"] = get_all_page_names()
