#!/usr/bin/env python3
"""Render the example run-summary email to docs/assets/example-email.png.

Dogfoods festival_organizer.notify.render so the documented image always
matches real output. Pass real poster .jpg paths (in the order of SAMPLE_SETS)
to bake real artwork into the committed PNG; missing ones use the bundled
fixture. Re-run after any email style change:

    python scripts/render_sample_email.py POSTER1.jpg POSTER2.jpg ...
"""

import base64
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from festival_organizer.notify.models import EmailSet, RunReport, UpdateInfo
from festival_organizer.notify.render import render
from festival_organizer.notify.thumbnails import make_thumbnail

OUT_PNG = ROOT / "docs" / "assets" / "example-email.png"
FIXTURE = ROOT / "festival_organizer" / "notify" / "fixtures" / "sample-poster.jpg"

# Grouped sample: two events, plus one more, matching the approved mockup shape.
SAMPLE_SETS = [
    (
        "Eric Prydz",
        "UMF Miami",
        "2026",
        "Resistance Megastructure",
        ["Progressive House", "Techno"],
        "19 tracks · 1h 30m",
    ),
    (
        "Armin van Buuren",
        "UMF Miami",
        "2026",
        "Mainstage",
        ["Trance", "Uplifting"],
        "34 tracks · 1h 12m",
    ),
    (
        "Madeon",
        "Coachella",
        "2026",
        "Quasar",
        ["Electronic", "Pop"],
        "18 tracks · 1h 00m",
    ),
    (
        "Kaskade",
        "Coachella",
        "2026",
        "Sahara",
        ["House", "Progressive"],
        "22 tracks · 1h 15m",
    ),
    ("Hardwell", "AMF", "2025", "", ["Big Room"], "26 tracks · 1h 02m"),
]


def main() -> int:
    posters = [Path(a) for a in sys.argv[1:]]
    sets = []
    for i, (artist, event, year, note, genres, metric) in enumerate(SAMPLE_SETS):
        poster = posters[i] if i < len(posters) and posters[i].exists() else FIXTURE
        sets.append(
            EmailSet(
                artist,
                event,
                year,
                note,
                genres,
                metric,
                poster if poster.exists() else None,
                "festival_set",
            )
        )
    report = RunReport(
        channel="new_sets",
        sets=sets,
        update=UpdateInfo("0.19.9", "0.20.0", True),
        stats={"added": len(sets), "up_to_date": 12, "errors": 0},
        timestamp="11 Jun 2026, 22:14",
    )

    thumbs = {}
    for idx, s in enumerate(report.sets):
        if s.poster_path:
            thumbs[idx] = (f"poster{idx}", make_thumbnail(s.poster_path, 140))
    rendered = render(report, thumbs)

    html = rendered.html
    for cid, data in rendered.images:
        uri = "data:image/jpeg;base64," + base64.b64encode(data).decode()
        html = html.replace(f"cid:{cid}", uri)
    page = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800'
        '&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">'
        "<style>body{margin:0;background:#05060a;padding:24px;}</style></head>"
        f"<body>{html}</body></html>"
    )

    with tempfile.TemporaryDirectory() as td:
        html_path = Path(td) / "email.html"
        html_path.write_text(page, encoding="utf-8")
        OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "google-chrome",
            "--headless=new",
            "--no-sandbox",
            "--hide-scrollbars",
            "--force-device-scale-factor=2",
            "--window-size=720,1500",
            f"--screenshot={OUT_PNG}",
            str(html_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    print(f"wrote {OUT_PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
