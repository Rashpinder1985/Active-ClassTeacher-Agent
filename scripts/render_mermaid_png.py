#!/usr/bin/env python3
"""Render a Mermaid (.mmd) file to PNG.

Tries, in order (unless --kroki-only or --mmdc-only):
  1. `mmdc` on PATH (@mermaid-js/mermaid-cli)
  2. `npx --yes @mermaid-js/mermaid-cli` (downloads on first use; needs Node/npm)
  3. Kroki HTTPS API (needs network; may return 403 in some environments)

Usage:
  uv run python scripts/render_mermaid_png.py docs/multiagent_flowchart.mmd docs/multiagent_flowchart.png
  uv run python scripts/render_mermaid_png.py docs/multiagent_flowchart.mmd  # writes .png next to .mmd
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


KROKI_PNG = "https://kroki.io/mermaid/png"


def _run_mmdc(mmd_path: Path, png_path: Path, mmdc_bin: str) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [mmdc_bin, "-i", str(mmd_path), "-o", str(png_path), "-b", "white"],
        check=True,
    )


def _run_npx(mmd_path: Path, png_path: Path, timeout: float) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "--yes",
            "@mermaid-js/mermaid-cli",
            "-i",
            str(mmd_path),
            "-o",
            str(png_path),
            "-b",
            "white",
        ],
        check=True,
        timeout=timeout,
    )


def render_kroki(mmd_text: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(
        KROKI_PNG,
        data=mmd_text.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "User-Agent": "Mozilla/5.0 (compatible; classroom-report-render/1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def main() -> int:
    p = argparse.ArgumentParser(description="Render Mermaid .mmd to PNG")
    p.add_argument("input_mmd", type=Path, help="Path to .mmd file")
    p.add_argument(
        "output_png",
        type=Path,
        nargs="?",
        help="Output PNG path (default: same name as .mmd with .png)",
    )
    p.add_argument("--mmdc-only", action="store_true", help="Only use mmdc (must be on PATH)")
    p.add_argument("--kroki-only", action="store_true", help="Only use Kroki HTTP API")
    p.add_argument("--timeout", type=float, default=300.0, help="Timeout for npx / HTTP (seconds)")
    args = p.parse_args()

    mmd_path = args.input_mmd.resolve()
    if not mmd_path.is_file():
        print(f"Not found: {mmd_path}", file=sys.stderr)
        return 1

    out = args.output_png
    if out is None:
        out = mmd_path.with_suffix(".png")
    else:
        out = out.resolve()

    text = mmd_path.read_text(encoding="utf-8")

    if args.kroki_only:
        try:
            png = render_kroki(text, timeout=min(args.timeout, 120.0))
        except urllib.error.URLError as e:
            print(f"Kroki request failed: {e}", file=sys.stderr)
            return 1
        if not png.startswith(b"\x89PNG"):
            print("Kroki did not return a PNG.", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
        print(f"Wrote {out} (Kroki)")
        return 0

    mmdc = shutil.which("mmdc")
    if args.mmdc_only:
        if not mmdc:
            print("mmdc not on PATH. Install: npm install -g @mermaid-js/mermaid-cli", file=sys.stderr)
            return 1
        try:
            _run_mmdc(mmd_path, out, mmdc)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(e, file=sys.stderr)
            return 1
        print(f"Wrote {out} (mmdc)")
        return 0

    # Auto: mmdc → npx → Kroki
    if mmdc:
        try:
            _run_mmdc(mmd_path, out, mmdc)
            print(f"Wrote {out} (mmdc)")
            return 0
        except subprocess.CalledProcessError:
            print("mmdc failed; trying npx…", file=sys.stderr)

    try:
        _run_npx(mmd_path, out, timeout=args.timeout)
        print(f"Wrote {out} (npx @mermaid-js/mermaid-cli)")
        return 0
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"npx mermaid-cli failed: {e}", file=sys.stderr)
        print("Trying Kroki…", file=sys.stderr)

    try:
        png = render_kroki(text, timeout=min(args.timeout, 120.0))
    except urllib.error.URLError as e:
        print(f"Kroki request failed: {e}", file=sys.stderr)
        print(
            "Install Node.js and run again, or: npm install -g @mermaid-js/mermaid-cli",
            file=sys.stderr,
        )
        return 1

    if not png.startswith(b"\x89PNG"):
        print("Kroki did not return a valid PNG.", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"Wrote {out} (Kroki)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
