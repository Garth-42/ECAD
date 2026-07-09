"""Optional runner: shell out to an installed ``wireviz`` CLI.

WireViz is GPL-3.0 and an OPTIONAL dependency. The boundary stays arms-length:
PanelKit writes a YAML file and invokes the separate ``wireviz`` process; it
never imports or vendors WireViz code. PanelKit core must work with WireViz
absent — everything WireViz-related stays inside this module.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class WirevizNotFoundError(RuntimeError):
    pass


def wireviz_available() -> bool:
    return shutil.which("wireviz") is not None


def render(yaml_path: str | Path, out_dir: str | Path) -> list[Path]:
    """Run ``wireviz`` on ``yaml_path``, emitting drawing + BOM into ``out_dir``.

    Returns the files WireViz produced (sorted). Raises a clear error when the
    CLI is missing or fails.
    """
    exe = shutil.which("wireviz")
    if exe is None:
        raise WirevizNotFoundError(
            "the 'wireviz' CLI was not found on PATH. Install it with "
            "\"pip install 'panelkit[wireviz]'\" (rendering also requires GraphViz)."
        )
    yaml_path = Path(yaml_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [exe, str(yaml_path), "-o", str(out_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"wireviz failed (exit {result.returncode}) on {yaml_path}:\n{result.stderr.strip()}"
        )
    stem = yaml_path.stem
    return sorted(p for p in out_dir.iterdir() if p.stem.startswith(stem) and p != yaml_path)
