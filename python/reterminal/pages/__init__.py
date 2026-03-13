"""Page registry and discovery for legacy fixed pages."""

from importlib import import_module
from typing import Dict, Type, Optional

from reterminal.pages.base import BasePage

# Page registry: name -> (page_class, default_page_number)
_registry: Dict[str, tuple] = {}

# Aliases for page groups
ALIASES = {
    "all": None,  # Will be populated dynamically
}


def register(name: str, page_number: int = 0):
    """
    Decorator to register a page class.

    Usage:
        @register("market", page_number=0)
        class MarketPage(BasePage):
            ...
    """
    def decorator(cls: Type[BasePage]):
        _registry[name] = (cls, page_number)
        return cls
    return decorator


def get_page(name: str) -> Optional[tuple]:
    """Get page class and default page number by name."""
    return _registry.get(name)


def get_page_class(name: str) -> Optional[Type[BasePage]]:
    """Get page class by name."""
    entry = _registry.get(name)
    return entry[0] if entry else None


def list_pages() -> Dict[str, int]:
    """List all registered pages with their default page numbers."""
    return {name: entry[1] for name, entry in _registry.items()}


def get_all_page_names() -> list:
    """Get list of all registered page names."""
    return list(_registry.keys())


# Import pages to trigger registration.
# Keep this dynamic so the legacy registry doesn't fight lint/import-order rules.
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

# Populate 'all' alias after imports
ALIASES["all"] = get_all_page_names()
