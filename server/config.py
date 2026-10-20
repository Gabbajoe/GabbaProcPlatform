"""Read deployment values from environment or private bind-mounted files."""

import os
from pathlib import Path


def value(name, default=""):
    filename = os.environ.get(name + "_FILE")
    return (
        Path(filename).read_text().strip()
        if filename
        else os.environ.get(name, default)
    )


def postgres_enabled():
    return bool(
        os.environ.get("GABBAPROC_DATABASE_URL")
        or os.environ.get("GABBAPROC_DATABASE_URL_FILE")
    )
