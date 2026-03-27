"""Font resolution: bundled fonts with config override."""
from pathlib import Path

_FONT_DIR = Path(__file__).parent

_BUNDLED_FONTS = {
    "bold": _FONT_DIR / "Inter-Bold.ttf",
    "light": _FONT_DIR / "Inter-Light.ttf",
    "semilight": _FONT_DIR / "Inter-SemiBold.ttf",
    "regular": _FONT_DIR / "Inter-Regular.ttf",
}


def get_font_path(
    weight: str,
    overrides: dict[str, str] | None = None,
) -> str:
    """Resolve font path for a given weight.

    Priority:
    1. overrides dict (from user config font_paths)
    2. Bundled font

    Returns path string to the font file.
    """
    # Config override
    if overrides and weight in overrides:
        override_path = Path(overrides[weight])
        if override_path.is_file():
            return str(override_path)

    # Bundled font
    bundled = _BUNDLED_FONTS.get(weight)
    if bundled and bundled.is_file():
        return str(bundled)

    raise FileNotFoundError(f"No font found for weight '{weight}'")
