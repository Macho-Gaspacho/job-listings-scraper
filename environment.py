"""Plain-language checks that run before a beginner sees a Python traceback."""

from __future__ import annotations

import sys


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
