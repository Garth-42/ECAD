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
    """The ``wireviz`` executable is not installed / not on PATH."""


class WirevizRenderError(RuntimeError):
    """``wireviz`` ran but failed (commonly: GraphViz is not installed)."""


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
        check=False,  # the return code is turned into a clearer error below
        text=True,
    )
    if result.returncode != 0:
        # WireViz reports failures as a Python traceback; its last line is the
        # actual reason (e.g. GraphViz's "dot" executable not being found).
        lines = result.stderr.strip().splitlines()
        reason = lines[-1] if lines else "no error output"
        raise WirevizRenderError(
            f"wireviz failed (exit {result.returncode}) on {yaml_path}: {reason}"
        )
    stem = yaml_path.stem
    # WireViz names its outputs <stem>.<ext> (and <stem>.bom.tsv); matching on
    # the dotted prefix keeps harness "H1" from claiming "H10"'s files.
    return sorted(
        p
        for p in out_dir.iterdir()
        if p != yaml_path and (p.stem == stem or p.name.startswith(stem + "."))
    )
