"""HTTP client for reTerminal E1001 with retry logic."""

import io
from typing import Optional

import requests
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from reterminal.config import settings, get_host, IMAGE_BYTES
from reterminal.exceptions import ConnectionError, ImageError


def _get_retry_decorator():
    """Create retry decorator with current settings."""
    return retry(
        stop=stop_after_attempt(settings.retry_attempts),
        wait=wait_exponential(
            min=settings.retry_min_wait,
            max=settings.retry_max_wait,
        ),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError)),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )


class ReTerminal:
    """HTTP client for reTerminal E1001 ePaper display."""

    def __init__(self, host: Optional[str] = None, timeout: Optional[int] = None):
        """
        Initialize client.

        Args:
            host: Device IP address (uses RETERMINAL_HOST env var if not set)
            timeout: Request timeout in seconds (uses RETERMINAL_TIMEOUT if not set)
        """
        self.host = get_host(host)
        self.base_url = f"http://{self.host}"
        self.timeout = timeout or settings.timeout
        logger.debug(f"ReTerminal client initialized for {self.host}")

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> requests.Response:
        """Make HTTP request with timeout."""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.Timeout as e:
            logger.error(f"Request timeout: {url}")
            raise ConnectionError(f"Timeout connecting to {self.host}") from e
        except requests.ConnectionError as e:
            logger.error(f"Connection failed: {url}")
            raise ConnectionError(f"Cannot connect to {self.host}") from e
        except requests.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code}: {url}")
            raise

    @_get_retry_decorator()
    def status(self) -> dict:
        """Get device status."""
        logger.debug("Getting device status")
        response = self._request("GET", "/status")
        return response.json()

    @_get_retry_decorator()
    def buttons(self) -> dict:
        """Get button states."""
        logger.debug("Getting button states")
        response = self._request("GET", "/buttons")
        return response.json()

    @_get_retry_decorator()
    def beep(self) -> bool:
        """Trigger buzzer."""
        logger.debug("Triggering buzzer")
        response = self._request("GET", "/beep")
        return response.json().get("beeped", False)

    @_get_retry_decorator()
    def get_page(self) -> dict:
        """Get current page info."""
        logger.debug("Getting current page")
        response = self._request("GET", "/page")
        return response.json()

    @_get_retry_decorator()
    def set_page(self, page: int) -> dict:
        """Set current page."""
        logger.debug(f"Setting page to {page}")
        response = self._request("POST", "/page", json={"page": page})
        return response.json()

    @_get_retry_decorator()
    def next_page(self) -> dict:
        """Navigate to next page."""
        logger.debug("Navigating to next page")
        response = self._request("POST", "/page", json={"action": "next"})
        return response.json()

    @_get_retry_decorator()
    def prev_page(self) -> dict:
        """Navigate to previous page."""
        logger.debug("Navigating to previous page")
        response = self._request("POST", "/page", json={"action": "prev"})
        return response.json()

    @_get_retry_decorator()
    def push_raw(self, data: bytes, page: Optional[int] = None) -> dict:
        """
        Push raw 1-bit image data.

        Args:
            data: Raw bitmap data (48000 bytes, 1-bit per pixel)
            page: Page to store (0-3), or None to display immediately
        """
        if len(data) != IMAGE_BYTES:
            raise ImageError(f"Image must be {IMAGE_BYTES} bytes, got {len(data)}")

        endpoint = "/imageraw"
        if page is not None:
            endpoint += f"?page={page}"

        logger.info(f"Pushing image to {self.host}" + (f" page {page}" if page is not None else ""))

        files = {"image": ("image.raw", io.BytesIO(data), "application/octet-stream")}
        response = self._request("POST", endpoint, files=files)
        return response.json()

    def push_image(
        self,
        image_path: str,
        page: Optional[int] = None,
        invert: bool = False,
        dither: bool = True,
    ) -> dict:
        """
        Convert and push an image file.

        Args:
            image_path: Path to image file (PNG, JPG, etc.)
            page: Page to store (0-3), or None to display immediately
            invert: Invert black/white
            dither: Use Floyd-Steinberg dithering for grayscale
        """
        from reterminal.encoding import image_to_raw

        logger.info(f"Converting image: {image_path}")
        data = image_to_raw(image_path, invert=invert, dither=dither)
        return self.push_raw(data, page=page)

    def push_text(
        self,
        text: str,
        page: Optional[int] = None,
        font_size: int = 48,
        align: str = "center",
    ) -> dict:
        """
        Render and push text.

        Args:
            text: Text to display (supports newlines)
            page: Page to store (0-3), or None to display immediately
            font_size: Font size in pixels
            align: Text alignment ("left", "center", "right")
        """
        from reterminal.encoding import text_to_raw

        logger.info(f"Rendering text: {text[:50]}...")
        data = text_to_raw(text, font_size=font_size, align=align)
        return self.push_raw(data, page=page)
