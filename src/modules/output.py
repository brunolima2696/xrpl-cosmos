import time
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def stage(label: str) -> Iterator[None]:
    started = time.monotonic()
    print(f"[{timestamp()}] INICIO: {label}", flush=True)
    try:
        yield
    except Exception:
        elapsed = time.monotonic() - started
        print(f"[{timestamp()}] ERRO: {label} ({elapsed:.1f}s)", flush=True)
        raise
    elapsed = time.monotonic() - started
    print(f"[{timestamp()}] FIM: {label} ({elapsed:.1f}s)", flush=True)
