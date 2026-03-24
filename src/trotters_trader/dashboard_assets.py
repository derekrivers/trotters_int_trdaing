from __future__ import annotations

from pathlib import Path
import re


_ASSET_DIR = Path(__file__).resolve().with_name("assets")
SOURCE_PATH = _ASSET_DIR / "dashboard.src.css"
OUTPUT_PATH = _ASSET_DIR / "dashboard.css"


def compile_dashboard_css(source: str) -> str:
    without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    compact_lines = [line.strip() for line in without_comments.splitlines() if line.strip()]
    compact = " ".join(compact_lines)
    compact = re.sub(r"\s+", " ", compact)
    compact = re.sub(r"\s*([{}:;,])\s*", r"\1", compact)
    compact = re.sub(r";}", "}", compact)
    return compact + "\n"


def build_dashboard_assets() -> Path:
    css = SOURCE_PATH.read_text(encoding="utf-8")
    OUTPUT_PATH.write_text(compile_dashboard_css(css), encoding="utf-8")
    return OUTPUT_PATH


def main() -> int:
    output_path = build_dashboard_assets()
    print(f"Built {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
