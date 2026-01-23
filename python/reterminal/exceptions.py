"""Custom exception hierarchy for reTerminal client."""


class ReTerminalError(Exception):
    """Base exception for all reTerminal errors."""
    pass


class ConnectionError(ReTerminalError):
    """Failed to connect to the device."""
    pass


class ImageError(ReTerminalError):
    """Invalid image data or format."""
    pass


class PageError(ReTerminalError):
    """Invalid page number or page operation failed."""
    pass


class DataFetchError(ReTerminalError):
    """Failed to fetch data for a page."""
    pass
