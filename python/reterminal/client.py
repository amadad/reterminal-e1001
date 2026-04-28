"""HTTP client for reTerminal E1001 with retry logic."""

from __future__ import annotations

import io

import requests
from loguru import logger
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from reterminal.config import IMAGE_BYTES, get_host, settings
from reterminal.exceptions import ConnectionError, ImageError
from reterminal.payloads import (
    CapabilitiesPayload,
    ClearResultPayload,
    JSONObject,
    PageInfoPayload,
    PushResultPayload,
    StatusPayload,
)


def _is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, ConnectionError):
        return True
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        return response is None or response.status_code >= 500
    return isinstance(exc, requests.RequestException)


def _get_retry_decorator():
    """Create retry decorator with current settings."""
    return retry(
        stop=stop_after_attempt(settings.retry_attempts),
        wait=wait_exponential(
            min=settings.retry_min_wait,
            max=settings.retry_max_wait,
        ),
        retry=retry_if_exception(_is_retryable_exception),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )


class ReTerminal:
    """HTTP client for reTerminal E1001 ePaper display."""

    def __init__(self, host: str | None = None, timeout: int | None = None):
        self.host = get_host(host)
        self.base_url = f"http://{self.host}"
        self.timeout = timeout or settings.timeout
        self._session = requests.Session()
        logger.debug(f"ReTerminal client initialized for {self.host}")

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: object,
    ) -> requests.Response:
        """Make an HTTP request with the configured timeout."""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)

        try:
            response = self._session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.Timeout as exc:
            logger.error(f"Request timeout: {url}")
            raise ConnectionError(f"Timeout connecting to {self.host}") from exc
        except requests.ConnectionError as exc:
            logger.error(f"Connection failed: {url}")
            raise ConnectionError(f"Cannot connect to {self.host}") from exc
        except requests.HTTPError as exc:
            logger.error(f"HTTP error {exc.response.status_code}: {url}")
            raise

    @_get_retry_decorator()
    def status(self) -> StatusPayload:
        logger.debug("Getting device status")
        response = self._request("GET", "/status")
        return response.json()

    @_get_retry_decorator()
    def capabilities(self) -> CapabilitiesPayload:
        logger.debug("Getting firmware capabilities")
        response = self._request("GET", "/capabilities")
        return response.json()

    @_get_retry_decorator()
    def buttons(self) -> JSONObject:
        logger.debug("Getting button states")
        response = self._request("GET", "/buttons")
        return response.json()

    @_get_retry_decorator()
    def beep(self) -> bool:
        logger.debug("Triggering buzzer")
        response = self._request("GET", "/beep")
        return bool(response.json().get("beeped", False))

    @_get_retry_decorator()
    def get_page(self) -> PageInfoPayload:
        logger.debug("Getting current page")
        response = self._request("GET", "/page")
        return response.json()

    @_get_retry_decorator()
    def set_page(self, page: int) -> JSONObject:
        logger.debug(f"Setting page to {page}")
        response = self._request("POST", "/page", json={"page": page})
        return response.json()

    @_get_retry_decorator()
    def next_page(self) -> JSONObject:
        logger.debug("Navigating to next page")
        response = self._request("POST", "/page", json={"action": "next"})
        return response.json()

    @_get_retry_decorator()
    def prev_page(self) -> JSONObject:
        logger.debug("Navigating to previous page")
        response = self._request("POST", "/page", json={"action": "prev"})
        return response.json()

    @_get_retry_decorator()
    def clear(self, *, page: int | None = None, all: bool = False) -> ClearResultPayload:
        payload = {"all": True} if all else ({"page": page} if page is not None else {})
        logger.info(
            f"Clearing device cache on {self.host}"
            + (" (all slots)" if all else (f" page {page}" if page is not None else " current page"))
        )
        response = self._request("POST", "/clear", json=payload)
        return response.json()

    @_get_retry_decorator()
    def snapshot_raw(self, page: int | None = None) -> bytes:
        endpoint = "/snapshot"
        if page is not None:
            endpoint += f"?page={page}"
        logger.debug(f"Fetching snapshot from {self.host}" + (f" page {page}" if page is not None else ""))
        response = self._request("GET", endpoint)
        return response.content

    @_get_retry_decorator()
    def push_raw(self, data: bytes, page: int | None = None) -> PushResultPayload:
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
        page: int | None = None,
        invert: bool = False,
        dither: bool = True,
    ) -> PushResultPayload:
        from reterminal.encoding import image_to_raw

        logger.info(f"Converting image: {image_path}")
        data = image_to_raw(image_path, invert=invert, dither=dither)
        return self.push_raw(data, page=page)

    def push_text(
        self,
        text: str,
        page: int | None = None,
        font_size: int = 48,
        align: str = "center",
    ) -> PushResultPayload:
        from reterminal.encoding import text_to_raw

        logger.info(f"Rendering text: {text[:50]}...")
        data = text_to_raw(text, font_size=font_size, align=align)
        return self.push_raw(data, page=page)
