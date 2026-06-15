#!/usr/bin/env python3
"""Generate tiny, fully-tagged MKV fixtures for the folder-poster tests.

These fixtures are committed so the tests run anywhere (no mount, no network).
Regenerating them is a manual dev step that needs ffmpeg + mkvtoolnix; the tests
themselves only need ffprobe (to read tags) + Pillow.

Each fixture is a ~30 KB 1-second black MKV carrying the container tags an
identified 1001Tracklists set has (CRATEDIGGER_1001TL_* at TTV=70, ARTIST/TITLE
at TTV=50), one chapter, and both cover attachments (portrait cover.jpg +
landscape cover_land.jpg). Filenames follow the organize convention so the
analyzer/parser resolve place/edition/year/artist.

Run:  python tests/fixtures/build_folder_poster_fixtures.py
"""
import hashlib
import subprocess
from pathlib import Path

from PIL import Image

OUT = Path(__file__).parent / "folder_posters"

# (filename, ARTIST, festival-tag, stage, date, artists, slugs, country)
FIXTURES = [
    ("2025 - AFROJACK - EDC Las Vegas [kineticFIELD].mkv",
     "AFROJACK", "EDC Las Vegas", "kineticFIELD", "2025-05-16", "AFROJACK", "afrojack", "United States"),
    ("2025 - Alesso - EDC Las Vegas [kineticFIELD].mkv",
     "Alesso", "EDC Las Vegas", "kineticFIELD", "2025-05-17", "Alesso", "alesso", "United States"),
    ("2026 - Armin van Buuren - Tomorrowland Winter [Mainstage].mkv",
     "Armin van Buuren", "Tomorrowland Winter", "Mainstage", "2026-03-14",
     "Armin van Buuren", "arminvanbuuren", "France"),
]

PLACES_JSON = """{
  "EDC Las Vegas": {"color": "#ED3895"},
  "Tomorrowland": {"color": "#9B1B5A", "editions": {"Winter": {"color": "#5B9BD5"}}}
}
"""
CONFIG_TOML = 'default_layout = "place_nested"\n'


def _run(*args):
    subprocess.run(list(args), check=True, capture_output=True)


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_one(spec, work: Path):
    filename, artist, festival, stage, date, artists, slugs, country = spec
    year = date[:4]
    base = work / "base.mkv"
    _run("ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x90:d=1",
         "-c:v", "libx264", "-t", "1", "-pix_fmt", "yuv420p", str(base))

    poster = work / "poster.jpg"
    Image.new("RGB", (1000, 1500), (24, 24, 32)).save(poster, quality=70)
    thumb = work / "thumb.jpg"
    Image.new("RGB", (320, 180), (40, 60, 90)).save(thumb, quality=70)

    tags = work / "tags.xml"
    tags.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<Tags>
 <Tag><Targets><TargetTypeValue>50</TargetTypeValue></Targets>
  <Simple><Name>ARTIST</Name><String>{_xml_escape(artist)}</String></Simple>
  <Simple><Name>TITLE</Name><String>{_xml_escape(artist)} @ {_xml_escape(stage)}, {_xml_escape(festival)}</String></Simple>
  <Simple><Name>DATE_RELEASED</Name><String>{year}</String></Simple>
 </Tag>
 <Tag><Targets><TargetTypeValue>70</TargetTypeValue></Targets>
  <Simple><Name>CRATEDIGGER_1001TL_URL</Name><String>https://www.1001tracklists.com/set/fixture-{slugs}-{year}</String></Simple>
  <Simple><Name>CRATEDIGGER_1001TL_TITLE</Name><String>{_xml_escape(artist)} @ {_xml_escape(festival)} {year}</String></Simple>
  <Simple><Name>CRATEDIGGER_1001TL_DATE</Name><String>{date}</String></Simple>
  <Simple><Name>CRATEDIGGER_1001TL_FESTIVAL</Name><String>{_xml_escape(festival)}</String></Simple>
  <Simple><Name>CRATEDIGGER_1001TL_STAGE</Name><String>{_xml_escape(stage)}</String></Simple>
  <Simple><Name>CRATEDIGGER_1001TL_ARTISTS</Name><String>{_xml_escape(artists)}</String></Simple>
  <Simple><Name>CRATEDIGGER_ALBUMARTIST_SLUGS</Name><String>{slugs}</String></Simple>
  <Simple><Name>CRATEDIGGER_1001TL_COUNTRY</Name><String>{country}</String></Simple>
 </Tag>
</Tags>""")

    uid = int(hashlib.md5(f"{filename}:0:Intro".encode()).hexdigest()[:15], 16)
    chapters = work / "chapters.xml"
    chapters.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<Chapters><EditionEntry>
 <ChapterAtom><ChapterUID>{uid}</ChapterUID><ChapterTimeStart>00:00:00.000</ChapterTimeStart>
  <ChapterDisplay><ChapterString>Intro</ChapterString><ChapterLanguage>eng</ChapterLanguage></ChapterDisplay>
 </ChapterAtom>
</EditionEntry></Chapters>""")

    _run("mkvpropedit", str(base), "--tags", f"global:{tags}", "--chapters", str(chapters))
    _run("mkvpropedit", str(base), "--attachment-name", "cover.jpg",
         "--attachment-mime-type", "image/jpeg", "--add-attachment", str(poster))
    _run("mkvpropedit", str(base), "--attachment-name", "cover_land.jpg",
         "--attachment-mime-type", "image/jpeg", "--add-attachment", str(thumb))

    final = OUT / filename
    if final.exists():
        final.unlink()
    base.rename(final)
    for tmp in (poster, thumb, tags, chapters):
        tmp.unlink()
    return final


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "places.json").write_text(PLACES_JSON)
    (OUT / "config.toml").write_text(CONFIG_TOML)
    work = OUT / "_work"
    work.mkdir(exist_ok=True)
    for spec in FIXTURES:
        f = build_one(spec, work)
        print("built", f.name, f.stat().st_size, "bytes")
    work.rmdir()


if __name__ == "__main__":
    main()
