"""Retry inference requests before any resulting tool calls are dispatched."""
import asyncio
from datetime import timezone
from email.utils import parsedate_to_datetime
import math
import random
import time


ATTEMPTS = 7
TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504, 529}


class ProviderUnavailable(RuntimeError):
    def __init__(self, failure):
        self.failure = failure
        super().__init__(f"Provider remained unavailable after {failure['attempt']} attempts "
                         f"({failure['status'] or failure['error_type']})")


def retry_delay(headers, attempt):
    value = headers.get('retry-after', '')
    if not value and 'retry-after-ms' in headers:
        try:
            seconds = float(headers['retry-after-ms']) / 1000
            if math.isfinite(seconds) and seconds >= 0:
                return seconds
        except (TypeError, ValueError):
            pass
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = date.timestamp() - time.time()
        except (TypeError, ValueError, OverflowError, AttributeError):
            seconds = None
    if seconds is not None and math.isfinite(seconds):
        return max(0, seconds)
    return random.uniform(0.8, 1.2) * min(32, 2 ** attempt)


def provider_rejected(error):
    import httpx

    if getattr(error, 'code', None) == 'insufficient_quota':
        return True
    response = getattr(error, 'response', None)
    if response is None:
        return False
    if response.status_code in (401, 403):
        return True
    if response.status_code == 429:
        try:
            detail = response.json().get('error', {})
        except (ValueError, AttributeError, httpx.ResponseNotRead):
            return False
        return isinstance(detail, dict) and detail.get('code') == 'insufficient_quota'
    return False


async def retry_request(send, record_failure):
    import httpx

    network_errors = (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ProxyError)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return await send(attempt)
        except Exception as error:
            response = getattr(error, 'response', None)
            status = response.status_code if response is not None else None
            # A provider may open SSE with HTTP 200, then emit a structured rate-limit error.
            code = getattr(error, 'code', None)
            if provider_rejected(error):
                raise
            if status is None and (code in ('rate_limit_exceeded', 'rate_limit_error', 'rate_limited')
                                   or getattr(error, 'type', None) == 'rate_limit_error'):
                status = 429
            transport = isinstance(error, network_errors) or isinstance(error.__cause__, network_errors)
            if status not in TRANSIENT_STATUS and not (status is None and transport):
                raise
            headers = response.headers if response is not None else {}
            delay = retry_delay(headers, attempt)
            failure = dict(attempt=attempt, status=status, error_type=type(error).__name__,
                           request_id=headers.get('x-request-id'), delay_seconds=delay,
                           retry_not_before=time.time() + delay)
            record_failure(failure)
            if attempt == ATTEMPTS:
                raise ProviderUnavailable(failure) from error
            await asyncio.sleep(delay)
