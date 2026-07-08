"""Shared non-blocking HTTP POST helper used by replay and receiver processes."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from queue import Full, Queue

from lw.logger_setup import LOG

# ---------------------------------------------------------------------------
# Tunable env-var defaults (callers may override before first use)
# ---------------------------------------------------------------------------
_HTTP_TIMEOUT_S: float = 2.0
_HTTP_QUEUE_MAX: int = 1024

# ---------------------------------------------------------------------------
# Module-level singleton state
# ---------------------------------------------------------------------------
_http_dispatch_q: Queue[tuple[str, bytes] | None] | None = None
_http_dispatch_thread: threading.Thread | None = None
_http_dropped_count: int = 0


def _http_dispatch_loop() -> None:
	"""Background HTTP worker: best-effort delivery, never raises to caller."""
	assert _http_dispatch_q is not None
	while True:
		item = _http_dispatch_q.get()
		if item is None:
			return
		url, body = item
		try:
			req = urllib.request.Request(
				url,
				data=body,
				headers={"Content-Type": "application/json"},
				method="POST",
			)
			with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S):
				pass
		except urllib.error.URLError as exc:
			LOG.warning("[HTTP] POST %s failed: %s", url, exc.reason)
		except Exception:
			LOG.exception("[HTTP] POST %s unexpected error", url)


def _ensure_http_dispatcher_started() -> None:
	global _http_dispatch_q, _http_dispatch_thread
	if _http_dispatch_thread is not None and _http_dispatch_thread.is_alive():
		return
	_http_dispatch_q = Queue(maxsize=max(16, int(_HTTP_QUEUE_MAX)))
	_http_dispatch_thread = threading.Thread(
		target=_http_dispatch_loop,
		daemon=True,
		name="lw-http-dispatch",
	)
	_http_dispatch_thread.start()


def _stop_http_dispatcher() -> None:
	global _http_dispatch_q, _http_dispatch_thread
	if _http_dispatch_q is None:
		return
	try:
		_http_dispatch_q.put_nowait(None)
	except Full:
		pass
	if _http_dispatch_thread is not None and _http_dispatch_thread.is_alive():
		_http_dispatch_thread.join(timeout=max(2.0, float(_HTTP_TIMEOUT_S) * 2.0))
	_http_dispatch_q = None
	_http_dispatch_thread = None


def _http_post_json(url: str, payload: dict) -> None:
	"""Non-blocking fire-and-log HTTP POST.

	Payload is queued to a background worker so callers are never blocked
	by server downtime, DNS errors, or network timeouts.
	"""
	global _http_dropped_count
	_ensure_http_dispatcher_started()
	try:
		body = json.dumps(payload, default=str).encode("utf-8")
		assert _http_dispatch_q is not None
		_http_dispatch_q.put_nowait((url, body))
	except Full:
		_http_dropped_count += 1
		if (_http_dropped_count % 100) == 1:
			LOG.warning(
				"[HTTP] dispatch queue full; dropping payloads (dropped=%d)",
				_http_dropped_count,
			)
	except Exception:
		LOG.exception("[HTTP] enqueue %s unexpected error", url)
