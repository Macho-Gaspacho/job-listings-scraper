"""Plain-language checks that run before a beginner sees a Python traceback."""

from __future__ import annotations

import sys
import urllib.error


def python_version_problem(version: tuple[int, ...]) -> str | None:
    """Explain where to get Python when the installed one is too old."""
    if (version[0], version[1]) >= (3, 10):
        return None
    installed = ".".join(str(part) for part in version[:3])
    return (
        "This program needs Python 3.10 or newer.\n"
        f"You are using Python {installed}.\n"
        "\n"
        "Install Python 3.12 from:\n"
        "    https://www.python.org/downloads/\n"
        "\n"
        "Mac: open the installer and follow the steps. Then in Finder go to\n"
        "Applications, open the Python 3.12 folder, and double-click\n"
        "Install Certificates.command.\n"
        "\n"
        "Windows: on the first screen of the installer, turn on\n"
        '"Add python.exe to PATH", then click Install.\n'
    )


def missing_package_message(exc: BaseException) -> str:
    """Tell someone to install the libraries listed in requirements.txt."""
    detail = str(exc).strip() or exc.__class__.__name__
    return (
        "A required package is not installed "
        f"({detail}).\n"
        "\n"
        "From this project folder, run:\n"
        "    pip install -r requirements.txt\n"
    )


class CertificateHint:
    """Print the Mac certificate fix once per run, not once per failed site."""

    def __init__(self) -> None:
        self.shown = False
        self.platform: str | None = None
        self.version: tuple[int, ...] | None = None

    def note(self, exc: BaseException) -> str | None:
        if self.shown:
            return None
        text = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" not in text and "certificate verify failed" not in text.lower():
            return None
        platform = sys.platform if self.platform is None else self.platform
        if platform != "darwin":
            return None
        version = self.version or sys.version_info
        self.shown = True
        ver = f"{version[0]}.{version[1]}"
        return (
            "Python on this Mac could not verify a website certificate.\n"
            "Run this once (double-click the file in Finder), then start the search again:\n"
            f'    "/Applications/Python {ver}/Install Certificates.command"\n'
        )


certificate_hint = CertificateHint()


def explain_certificate_error(exc: BaseException) -> None:
    """Print the certificate hint when this error is the Mac SSL problem."""
    message = certificate_hint.note(exc)
    if message:
        print(message, flush=True)


def _iter_exceptions(exc: BaseException):
    """The error itself, plus the errors that caused it."""
    seen: set[int] = set()
    pending: list[object] = [exc]
    while pending:
        current = pending.pop()
        if not isinstance(current, BaseException):
            continue
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        yield current
        pending.append(current.__cause__)
        pending.append(current.__context__)
        pending.append(getattr(current, "reason", None))


def network_problem(exc: BaseException) -> str | None:
    """One plain sentence for a connection problem, or None for other errors."""
    http_codes: list[int] = []
    saw_timeout = False
    saw_url = False
    texts: list[str] = []
    for item in _iter_exceptions(exc):
        texts.append(str(item))
        if isinstance(item, urllib.error.HTTPError):
            http_codes.append(item.code)
        elif isinstance(item, urllib.error.URLError):
            saw_url = True
        if isinstance(item, TimeoutError):
            saw_timeout = True
    blob = " ".join(texts).lower()
    for code in http_codes:
        if code == 403:
            return "The site refused the request (403)."
        if code == 429:
            return "The site asked us to slow down (429). Wait a bit and try again."
        if 500 <= code <= 599:
            return f"The site had a problem ({code}). Try again later."
    if "http 403" in blob:
        return "The site refused the request (403)."
    if "http 429" in blob:
        return "The site asked us to slow down (429). Wait a bit and try again."
    if "certificate_verify_failed" in blob or "certificate verify failed" in blob:
        return "The website certificate could not be verified."
    if saw_timeout or "timed out" in blob:
        return "The site took too long to answer."
    if "proxy" in blob:
        return "Could not connect through the proxy. Check your network settings."
    if saw_url or "connection refused" in blob or "urlopen" in blob:
        return "Could not connect to the site. Check your internet connection."
    return None


def report_skip(exc: BaseException) -> None:
    """Print a one-line reason for a skipped site, then the Mac certificate hint."""
    friendly = network_problem(exc)
    if friendly:
        print(f"  Skipped. {friendly}", flush=True)
    else:
        text = str(exc).strip().splitlines()
        detail = text[0] if text else exc.__class__.__name__
        print(f"  Skipped ({detail}).", flush=True)
    hint = certificate_hint.note(exc)
    if hint:
        print(hint, flush=True)
