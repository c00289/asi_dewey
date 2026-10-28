"""The local automation server: loopback HTTP, JSON ``Result`` answers, owned by the window.

``AutomationServer`` binds ``127.0.0.1`` on an ephemeral port, serves on a daemon thread, and
writes nothing itself: the window starts it, writes the session file (``session.py``) and stops
it in ``close()``. The HTTP handler runs on a server thread and may not touch a Tk widget or the
window's state, so every job crosses to the Tk thread through ``on_main``: the job is queued, the
window drains the queue every 50 ms (``_pump``, an ``after`` job on the root), and the handler
waits on a ``threading.Event`` with a timeout. Only the queue and the event cross the thread
boundary; the server thread never calls ``after``, never reads ``window.current``, never touches
``Brain``. A job that times out is not cancelled: it still runs when the window gets to it and
its answer is discarded; the handler answers 504.

What a job may call on the window: ``brain.execute``, ``show``, ``factory.items()``,
``current_key``, ``theme``, ``remote_guard`` and ``close`` through ``after``. Never ``run``,
``pick_theme``, ``notify_error``, ``confirm``, ``about`` or ``export_workbook``: those may open
a dialog, and a dialog would block the Tk thread with a request waiting on it.

Endpoints: ``GET /status``, ``POST /execute``, ``GET /screens``, ``POST /screen``,
``GET /events?since=<n>&limit=<m>``, ``POST /quit``. Every request carries
``Authorization: Bearer <token>``; a request with an ``Origin`` header is refused (403) so a
browser page never gets in. The HTTP status is about transport: a failed command is 200 with
``ok: false``, exactly as the CLI prints it and exits 1.
"""

from __future__ import annotations

import datetime as dt
import hmac
import json
import logging
import os
import queue
import secrets
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import parse_qs, urlsplit

from ..commands import Result
from ..errors import NotFound
from ..locks import guard
from ..version import __version__
from .session import TOOL

if TYPE_CHECKING:
    from ..gui.main_window import MainWindow

__all__ = ["AutomationServer", "WindowTimeout", "current_server"]

log = logging.getLogger("asi_dewey.automation.server")

T = TypeVar("T")

PUMP_MS = 50
JOB_TIMEOUT = 60.0
QUIT_DELAY_MS = 100
MAX_BODY = 1024 * 1024
DEFAULT_ACTOR = "agent"
EVENTS_LIMIT = 200
ROUTES: dict[str, str] = {
    "/status": "GET",
    "/execute": "POST",
    "/screens": "GET",
    "/screen": "POST",
    "/events": "GET",
    "/quit": "POST",
}

_current: AutomationServer | None = None


def current_server() -> AutomationServer | None:
    """The server started in this process, if one is running (the ``session`` verb reports it)."""
    return _current


class WindowTimeout(TimeoutError):
    """The Tk thread did not answer a job in time (the handler answers 504)."""


class WindowClosing(RuntimeError):
    """The window stopped the server while a job was waiting."""


class _Job:
    __slots__ = ("done", "error", "fn", "result")

    def __init__(self, fn: Callable[[], Any]) -> None:
        self.fn = fn
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


class AutomationServer:
    """One per window. ``start`` binds and serves; ``stop`` (Tk thread only) tears it down."""

    def __init__(self, window: MainWindow, host: str = "127.0.0.1", port: int = 0) -> None:
        self.window = window
        self.host = host
        self.port = port
        self.token = secrets.token_hex(16)
        self.started_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
        self.requests = 0
        self.timeout = JOB_TIMEOUT  # how long a handler waits for the Tk thread
        self._started = time.monotonic()
        self._jobs: queue.SimpleQueue[_Job] = queue.SimpleQueue()
        self._pump_job: str | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._closing = False
        self._count_lock = threading.Lock()

    @property
    def address(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def running(self) -> bool:
        return self._httpd is not None and not self._closing

    # -- lifecycle (Tk thread) ------------------------------------------------------------------
    def start(self) -> None:
        """Bind, start the daemon serving thread, and start the main-thread pump."""
        global _current
        if self._httpd is not None:
            return
        httpd = _Server((self.host, self.port), _Handler)
        httpd.automation = self
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        self._started = time.monotonic()
        self._closing = False
        self._thread = threading.Thread(
            target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, name="asi-dewey-automation", daemon=True
        )
        self._thread.start()
        self._pump_job = self.window.after(PUMP_MS, self._pump)
        _current = self

    def stop(self) -> None:
        """Cancel the pump, fail every waiting job, shut the listener down. Tk thread only."""
        global _current
        self._closing = True
        if self._pump_job is not None:
            try:
                self.window.after_cancel(self._pump_job)
            except Exception:  # the root may already be half gone
                pass
            self._pump_job = None
        self._fail_pending(WindowClosing("the window is closing"))
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._fail_pending(WindowClosing("the window is closing"))
        if _current is self:
            _current = None

    def _fail_pending(self, error: BaseException) -> None:
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return
            job.error = error
            job.done.set()

    # -- the handshake --------------------------------------------------------------------------
    def on_main(self, fn: Callable[[], T], timeout: float | None = None) -> T:
        """Run ``fn`` on the Tk thread and return its value; called on a server thread."""
        if self._closing:
            raise WindowClosing("the window is closing")
        job = _Job(fn)
        self._jobs.put(job)
        wait = self.timeout if timeout is None else timeout
        if not job.done.wait(wait):
            raise WindowTimeout(f"the window did not answer within {wait:.1f} s")
        if job.error is not None:
            raise job.error
        return job.result

    def _pump(self) -> None:
        """Tk thread: run every queued job, then reschedule."""
        self._pump_job = None
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                break
            try:
                job.result = job.fn()
            except BaseException as exc:  # the handler turns it into a Result.failure
                job.error = exc
            job.done.set()
        if not self._closing:
            self._pump_job = self.window.after(PUMP_MS, self._pump)

    # -- the jobs (Tk thread) -------------------------------------------------------------------
    def status_data(self) -> dict[str, Any]:
        """``/status`` data; Tk thread only (reads the window)."""
        window = self.window
        brain = window.brain
        return {
            "tool": TOOL,
            "version": __version__,
            "pid": os.getpid(),
            "db": brain.db_path,
            "screen": window.current_key,
            "theme": {"key": window.theme.key, "title": window.theme.title},
            "started_at": self.started_at,
            "uptime_s": round(time.monotonic() - self._started, 3),
            "port": self.port,
            "requests": self.requests,
            "events_seq": brain.events.seq,
            "lock": guard.describe(brain.db_path),
        }

    def execute(self, body: dict[str, Any]) -> Result:
        """``/execute``: the dispatcher's wire format, run on the Tk thread with the agent's actor."""
        verb = body.get("verb")
        if not isinstance(verb, str) or not verb:
            return Result.failure("payload must be an object with a 'verb' key")
        args = body.get("args") or {}
        if not isinstance(args, dict):
            return Result.failure("'args' must be an object", verb=verb)
        actor = str(body.get("actor") or DEFAULT_ACTOR)
        if verb == "gui":
            return Result.failure("the window is already open", verb=verb)
        refused = self.window.remote_guard(verb, args)
        if refused is not None:
            return refused
        return self.window.brain.execute(verb, args, actor=actor)

    def screens(self) -> Result:
        window = self.window
        return Result.success({
            "screens": [
                {"key": key, "title": title, "current": key == window.current_key}
                for key, title in window.factory.items()
            ],
        })

    def screen(self, body: dict[str, Any]) -> Result:
        key = body.get("show")
        if not isinstance(key, str) or not key:
            return Result.failure("payload must be an object with a 'show' key naming a screen")
        try:
            self.window.show(key)
        except NotFound as exc:
            return Result.failure(str(exc))
        return Result.success({"screen": key, "title": self.window.factory.title(key)})

    def events(self, since: int, limit: int) -> Result:
        bus = self.window.brain.events
        warnings: list[str] = []
        oldest = bus.oldest_seq()
        if oldest is not None and oldest > since + 1:
            warnings.append(f"events before seq {oldest} are no longer in the history (asked since {since})")
        return Result.success({"since": since, "seq": bus.seq, "events": bus.since(since, limit)}, warnings=warnings)

    def quit(self) -> Result:
        self.window.after(QUIT_DELAY_MS, self.window.close)
        return Result.success({"quit": True})

    def count_request(self) -> None:
        with self._count_lock:
            self.requests += 1


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    automation: AutomationServer


class _Handler(BaseHTTPRequestHandler):
    server: _Server
    server_version = f"asi-dewey/{__version__}"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # the base class's parameter name
        log.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    # -- plumbing --------------------------------------------------------------------------------
    def _handle(self, method: str) -> None:
        automation = self.server.automation
        automation.count_request()
        if self.headers.get("Origin") is not None:
            self._answer(HTTPStatus.FORBIDDEN, Result.failure("browser requests are refused"))
            return
        if not self._authorised(automation.token):
            self._answer(HTTPStatus.UNAUTHORIZED, Result.failure("bad token"))
            return
        parts = urlsplit(self.path)
        path = parts.path.rstrip("/") or "/"
        expected = ROUTES.get(path)
        if expected is None:
            self._answer(HTTPStatus.NOT_FOUND, Result.failure(f"unknown path {path!r}"))
            return
        if method != expected:
            self._answer(HTTPStatus.METHOD_NOT_ALLOWED, Result.failure(f"{path} takes {expected}, not {method}"))
            return
        try:
            body = self._body() if method == "POST" else {}
        except _BadRequest as exc:
            self._answer(exc.status, Result.failure(str(exc)))
            return
        try:
            query = {k: v[-1] for k, v in parse_qs(parts.query).items()}
            result = self._route(automation, path, body, query)
        except _BadRequest as exc:
            self._answer(exc.status, Result.failure(str(exc)))
        except WindowTimeout as exc:
            self._answer(HTTPStatus.GATEWAY_TIMEOUT, Result.failure(str(exc)))
        except WindowClosing as exc:
            self._answer(HTTPStatus.SERVICE_UNAVAILABLE, Result.failure(str(exc)))
        except Exception as exc:  # a job raised: the window's show of a broken screen, little else
            log.exception("automation request %s %s crashed", method, path)
            self._answer(HTTPStatus.INTERNAL_SERVER_ERROR, Result.failure(f"{type(exc).__name__}: {exc}"))
        else:
            self._answer(HTTPStatus.OK, result)

    def _route(self, automation: AutomationServer, path: str, body: dict[str, Any], query: dict[str, str]) -> Result:
        if path == "/status":
            return automation.on_main(lambda: Result.success(automation.status_data()))
        if path == "/execute":
            return automation.on_main(lambda: automation.execute(body))
        if path == "/screens":
            return automation.on_main(automation.screens)
        if path == "/screen":
            return automation.on_main(lambda: automation.screen(body))
        if path == "/events":
            since = _int(query.get("since"), 0, "since")
            limit = _int(query.get("limit"), EVENTS_LIMIT, "limit")
            return automation.on_main(lambda: automation.events(since, limit))
        if path == "/quit":
            return automation.on_main(automation.quit)
        raise _BadRequest(HTTPStatus.NOT_FOUND, f"unknown path {path!r}")

    def _authorised(self, token: str) -> bool:
        header = self.headers.get("Authorization") or ""
        scheme, _, given = header.strip().partition(" ")
        if scheme.lower() != "bearer" or not given.strip():
            return False
        return hmac.compare_digest(given.strip().encode("utf-8"), token.encode("utf-8"))

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise _BadRequest(HTTPStatus.BAD_REQUEST, "bad Content-Length") from None
        if length > MAX_BODY:
            raise _BadRequest(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"body over {MAX_BODY} bytes")
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise _BadRequest(HTTPStatus.BAD_REQUEST, f"body is not JSON: {exc}") from None
        if not isinstance(data, dict):
            raise _BadRequest(HTTPStatus.BAD_REQUEST, "body must be a JSON object")
        return data

    def _answer(self, status: HTTPStatus, result: Result) -> None:
        payload = result.to_json(indent=None).encode("utf-8")
        try:
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
        except OSError:  # the client went away: nothing to tell it
            pass


class _BadRequest(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def _int(text: str | None, default: int, name: str) -> int:
    if text is None or text == "":
        return default
    try:
        value = int(text)
    except ValueError:
        raise _BadRequest(HTTPStatus.BAD_REQUEST, f"{name} must be an integer") from None
    if value < 0:
        raise _BadRequest(HTTPStatus.BAD_REQUEST, f"{name} must not be negative")
    return value
