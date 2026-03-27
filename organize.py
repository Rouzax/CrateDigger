#!/usr/bin/env python3
"""CrateDigger — Festival set & concert library manager.

Usage:
    organize.py scan <path>          Preview what would happen
    organize.py organize <path>      Move/copy files into library
    organize.py enrich <path>        Add metadata artifacts in place
    organize.py chapters <path>      Add 1001Tracklists chapters
"""
import sys
from festival_organizer.cli import run

sys.exit(run())
