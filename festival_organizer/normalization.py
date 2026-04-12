"""Text normalization: filename safety, scene tag stripping, alias resolution."""
import re
import unicodedata

import ftfy

# Characters illegal in Windows filenames
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Unicode characters that look like slashes but aren't (e.g. KI⧸KI)
UNICODE_SLASHES = re.compile(r'[\u2044\u2215\u29F8\u29F9\uFF0F]')

# Fullwidth pipe ｜ (U+FF5C) used in YouTube titles as separator
FULLWIDTH_PIPE = re.compile(r'\uFF5C')

# Fullwidth colon ： (U+FF1A) used in YouTube filenames where : is illegal
FULLWIDTH_COLON = re.compile(r'\uFF1A')

# Scene-release technical tags
SCENE_TAGS = re.compile(
    r"\b("
    r"1080[pi]|720[pi]|2160[pi]|4K|UHD|"
    r"HDTV|PDTV|WEB-?DL|WEBRip|BluRay|Blu-?Ray|BDRip|DVDRip|"
    r"x264|x265|H[\.\s]?264|H[\.\s]?265|HEVC|AVC|VP9|AV1|"
    r"AAC|AC3|EAC3|E-AC-3|DTS|TrueHD|Atmos|DDP?\d?[\.\s]\d|FLAC|Opus|"
    r"AMZN|NF|PROPER|REPACK|REMUX|"
    r"[A-Z0-9]+-[A-Z]{2,}[A-Z0-9]*"
    r")\b",
    re.IGNORECASE,
)

# YouTube video ID: [xCvaCI5GN1g]
YT_ID_PATTERN = re.compile(r"\s*\[([A-Za-z0-9_-]{11})\]\s*")

# Noise words to strip from filenames
NOISE_WORDS = re.compile(
    r"\b(Full\s+Set|Live\s+Set|Full\s+DJ\s+Set|DJ\s+Set|Official|"
    r"HD|HQ|4K\s+HD|Preview|US\s+Debut|Hardstyle\s+Exclusive|"
    r"LIVE(?=\s+[@|]|\s*$))\b",
    re.IGNORECASE,
)


def fix_mojibake(text: str) -> str:
    """Fix Latin-1/cp1252 mojibake and other encoding issues in tag values.

    Idempotent: calling on already-clean text returns it unchanged. Safe on
    empty strings and non-Latin text. Applied at every external read boundary
    (mkvextract XML, mediainfo/ffprobe JSON) so downstream code always sees
    proper Unicode.

    Example: "KÃ¶lsch" -> "Kölsch", "Ã©dition" -> "édition".
    """
    if not text:
        return text
    return ftfy.fix_text(text)


def strip_diacritics(text: str) -> str:
    """Remove diacritics for fuzzy matching. 'Tiesto' matches 'Tiësto'."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_pipes(text: str) -> str:
    """Normalize fullwidth pipe (U+FF5C) to regular pipe.

    YouTube titles from official festival channels use fullwidth pipes
    as separators (e.g. "Alesso WE2 ｜ Tomorrowland 2024").
    """
    return FULLWIDTH_PIPE.sub("|", text)


def normalize_colons(text: str) -> str:
    """Replace fullwidth colon (U+FF1A) with a space.

    YouTube filenames replace : with ： for filesystem safety.
    We use space (not colon) because colons in search queries add noise.
    """
    return FULLWIDTH_COLON.sub(" ", text)


def safe_filename(name: str) -> str:
    """Make a string safe for use as a Windows filename component."""
    name = UNICODE_SLASHES.sub("", name)
    name = ILLEGAL_CHARS.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")
    if len(name) > 200:
        name = name[:200].rstrip(". ")
    return name


def normalise_name(name: str) -> str:
    """Clean up a name: trim, collapse spaces, remove illegal chars."""
    if not name:
        return ""
    name = UNICODE_SLASHES.sub("", name)
    name = ILLEGAL_CHARS.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip(" -\u2013\u2014.,")
    return name


def strip_scene_tags(text: str) -> str:
    """Remove scene-release technical tags and clean up residue."""
    result = SCENE_TAGS.sub("", text)
    # Remove orphaned scene group suffixes like "-NTG", "-verum"
    result = re.sub(r"\s*-[A-Za-z]{2,}[A-Za-z0-9]*\s*$", "", result)
    # Clean up leftover separators and whitespace
    result = re.sub(r"[\s\-]+$", "", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def strip_noise_words(text: str) -> str:
    """Remove noise words like 'Full Set', 'Live Set', etc."""
    result = NOISE_WORDS.sub("", text)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def extract_youtube_id(stem: str) -> tuple[str, str]:
    """Extract and remove YouTube video ID from a filename stem.
    Returns (cleaned_stem, youtube_id). youtube_id is "" if not found."""
    match = YT_ID_PATTERN.search(stem)
    if match:
        yt_id = match.group(1)
        cleaned = YT_ID_PATTERN.sub("", stem)
        return cleaned, yt_id
    return stem, ""


def scene_dots_to_spaces(stem: str) -> str:
    """Convert scene-style dot-separated names to spaces.
    Only converts if there are many dots and few spaces (heuristic)."""
    if stem.count(".") > 3 and stem.count(" ") < 2:
        return stem.replace(".", " ")
    return stem
