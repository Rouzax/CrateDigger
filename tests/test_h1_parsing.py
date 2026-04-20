from festival_organizer.tracklists.api import _parse_h1_structure


def test_simple_stage():
    """Afrojack @ kineticFIELD, EDC Las Vegas"""
    h1 = '<a href="/dj/afrojack/index.html" class="notranslate ">AFROJACK</a> @ kineticFIELD, <a href="/source/unkguv/edc-las-vegas/index.html">EDC Las Vegas</a>, United States 2025-05-17'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "kineticFIELD"
    assert ("unkguv", "edc-las-vegas", "EDC Las Vegas") in result["sources"]
    assert result["date"] == "2025-05-17"


def test_set_name_and_stage():
    """Tiesto @ In Search Of Sunrise, kineticFIELD, EDC Las Vegas"""
    h1 = '<a href="/dj/tiesto/index.html" class="notranslate ">Ti&euml;sto</a> @ In Search Of Sunrise, kineticFIELD, <a href="/source/unkguv/edc-las-vegas/index.html">EDC Las Vegas</a>, United States 2025-05-18'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "In Search Of Sunrise, kineticFIELD"
    assert len(result["sources"]) == 1


def test_no_stage():
    """Hardwell @ AMF, Johan Cruijff ArenA, ADE"""
    h1 = '<a href="/dj/hardwell/index.html" class="notranslate ">Hardwell</a> @ <a href="/source/5tb5n3/amsterdam-music-festival/index.html">Amsterdam Music Festival</a>, <a href="/source/hdfr2c/johan-cruijff-arena-amsterdam/index.html">Johan Cruijff ArenA</a>, <a href="/source/f4lzj3/amsterdam-dance-event/index.html">Amsterdam Dance Event</a>, Netherlands 2025-10-25'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == ""
    assert len(result["sources"]) == 3


def test_complex_set_and_venue():
    """Armin @ 25 Years Celebration Set, Area One, ASOT Festival, Ahoy Rotterdam"""
    h1 = '<a href="/dj/arminvanbuuren/index.html" class="notranslate ">Armin van Buuren</a> @ 25 Years Celebration Set, Area One, <a href="/source/rch80m/a-state-of-trance-festival/index.html">A State Of Trance Festival</a>, <a href="/source/tslp1m/ahoy-rotterdam/index.html">Ahoy Rotterdam</a>, Netherlands 2026-02-27'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "25 Years Celebration Set, Area One"
    assert len(result["sources"]) == 2
    ids = [s[0] for s in result["sources"]]
    assert "rch80m" in ids
    assert "tslp1m" in ids
    assert result["date"] == "2026-02-27"


def test_no_at_sign():
    """Mysteryland - Aftermovie (no @)"""
    h1 = 'Mysteryland - Aftermovie 2025-09-15'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == ""
    assert result["sources"] == []
    assert result["dj_artists"] == []


def test_h1_extracts_single_dj():
    h1 = '<a href="/dj/tiesto/index.html" class="notranslate ">Ti&euml;sto</a> @ Mainstage, <a href="/source/fgcfkm/tomorrowland/index.html">Tomorrowland</a>'
    result = _parse_h1_structure(h1)
    assert result["dj_artists"] == [("tiesto", "Tiësto")]
    assert result["stage_text"] == "Mainstage"


def test_h1_extracts_collab_djs():
    h1 = '<a href="/dj/arminvanbuuren/index.html" class="notranslate ">Armin van Buuren</a> &amp; <a href="/dj/kislashki/index.html" class="notranslate ">KI/KI</a> @ Two Is One, <a href="/source/5tb5n3/amsterdam-music-festival/index.html">Amsterdam Music Festival</a>'
    result = _parse_h1_structure(h1)
    assert result["dj_artists"] == [("arminvanbuuren", "Armin van Buuren"), ("kislashki", "KI/KI")]
    assert result["stage_text"] == "Two Is One"


def test_h1_extracts_group_dj():
    h1 = '<a href="/dj/dimitrivegasandlikemike/index.html" class="notranslate ">Dimitri Vegas &amp; Like Mike</a> @ Mainstage, <a href="/source/fgcfkm/tomorrowland/index.html">Tomorrowland</a> Weekend 2, Belgium 2025-07-26'
    result = _parse_h1_structure(h1)
    assert result["dj_artists"] == [("dimitrivegasandlikemike", "Dimitri Vegas & Like Mike")]


def test_h1_existing_source_extraction_unchanged():
    """Existing source extraction still works after adding DJ parsing."""
    h1 = '<a href="/dj/arminvanbuuren/index.html">Armin van Buuren</a> @ Mainstage, <a href="/source/fgcfkm/tomorrowland/index.html">Tomorrowland</a>'
    result = _parse_h1_structure(h1)
    assert result["sources"] == [("fgcfkm", "tomorrowland", "Tomorrowland")]
    assert result["stage_text"] == "Mainstage"


def test_stage_from_source_link_with_suffix():
    """Eric Prydz @ Resistance Megastructure, Ultra Music Festival Miami.

    'Resistance' is a /source/ link (Event Promoter). The stage is the
    compound 'Resistance Megastructure', not empty.
    """
    h1 = (
        '<a href="/dj/ericprydz/index.html" class="notranslate ">Eric Prydz</a>'
        ' @ <a href="/source/v088zc/resistance/index.html">Resistance</a>'
        " Megastructure,"
        ' <a href="/source/u8bf5c/ultra-music-festival-miami/index.html">'
        "Ultra Music Festival Miami</a>, United States 2026-03-27"
    )
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "Resistance Megastructure"
    assert result["dj_artists"] == [("ericprydz", "Eric Prydz")]
    assert ("v088zc", "resistance", "Resistance") in result["sources"]
    assert ("u8bf5c", "ultra-music-festival-miami", "Ultra Music Festival Miami") in result["sources"]


def test_stage_from_source_link_the_cove():
    """Dennis Cruz & Seth Troxler @ Resistance The Cove, UMF Miami.

    Same pattern as Megastructure but with different suffix.
    """
    h1 = (
        '<a href="/dj/denniscruz/index.html" class="notranslate ">Dennis Cruz</a>'
        " &amp; "
        '<a href="/dj/sethtroxler/index.html" class="notranslate ">Seth Troxler</a>'
        ' @ <a href="/source/v088zc/resistance/index.html">Resistance</a>'
        " The Cove,"
        ' <a href="/source/u8bf5c/ultra-music-festival-miami/index.html">'
        "Ultra Music Festival Miami</a>, United States 2026-03-29"
    )
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "Resistance The Cove"
    assert len(result["dj_artists"]) == 2


def test_no_sources_strips_trailing_country_and_date():
    """FISHER @ Bay Oval Park, New Zealand 2026-01-31 (no source links).

    Without source-link delimiters, the trailing "Country YYYY-MM-DD" would
    otherwise be absorbed into stage_text. Stage should be venue only, and
    country should surface via the new fallback.
    """
    h1 = (
        '<a href="/dj/fisher/index.html" class="notranslate ">FISHER</a>'
        ' @ Bay Oval Park, New Zealand 2026-01-31'
    )
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "Bay Oval Park"
    assert result["country"] == "New Zealand"
    assert result["sources"] == []


def test_no_sources_strips_trailing_date_only():
    """No country present, just trailing date."""
    h1 = (
        '<a href="/dj/fisher/index.html" class="notranslate ">FISHER</a>'
        ' @ Bay Oval Park 2026-01-31'
    )
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "Bay Oval Park"
    assert result["country"] == ""


def test_no_sources_unknown_country_kept_in_stage():
    """Unknown country names stay in stage (defensive, avoids false positives)."""
    h1 = (
        '<a href="/dj/fisher/index.html" class="notranslate ">FISHER</a>'
        ' @ Some Venue, Unknownland 2026-01-31'
    )
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "Some Venue, Unknownland"
    assert result["country"] == ""


def test_sources_present_country_still_extracted_from_tail():
    """When source links are present, the trailing country is still parsed
    out of the tail (the new unconditional path). Callers that prefer the
    source cache as authoritative suppress the h1 result themselves."""
    h1 = '<a href="/dj/afrojack/index.html" class="notranslate ">AFROJACK</a> @ kineticFIELD, <a href="/source/unkguv/edc-las-vegas/index.html">EDC Las Vegas</a>, United States 2025-05-17'
    result = _parse_h1_structure(h1)
    assert result["country"] == "United States"
    assert result["stage_text"] == "kineticFIELD"


def test_parse_h1_extracts_country_when_source_link_present():
    """h1 tail with a linked source still yields country from the trailing text.

    Fred again.. @ USB002, Alexandra Palace London, United Kingdom 2026-02-27.
    The source link ("USB002") precedes a venue + country + date tail; the
    trailing country must be captured even when source links are present.
    """
    h1 = (
        '<a href="/dj/fredagain/index.html" class="notranslate ">Fred again..</a>'
        ' @ <a href="/source/abc/usb002-slug/index.html">USB002</a>,'
        " Alexandra Palace London, United Kingdom 2026-02-27"
    )
    result = _parse_h1_structure(h1)
    assert result["country"] == "United Kingdom"


def test_parse_h1_extracts_location_when_source_link_present():
    """Same h1 as above: location field holds the middle segment."""
    h1 = (
        '<a href="/dj/fredagain/index.html" class="notranslate ">Fred again..</a>'
        ' @ <a href="/source/abc/usb002-slug/index.html">USB002</a>,'
        " Alexandra Palace London, United Kingdom 2026-02-27"
    )
    result = _parse_h1_structure(h1)
    assert result["location"] == "Alexandra Palace London"


def test_parse_h1_location_empty_when_no_middle_segment():
    """Tail with only country + date → country set, location empty."""
    h1 = (
        '<a href="/dj/fredagain/index.html" class="notranslate ">Fred again..</a>'
        ' @ <a href="/source/abc/someevent-slug/index.html">Some Event</a>,'
        " Belgium 2026-02-27"
    )
    result = _parse_h1_structure(h1)
    assert result["country"] == "Belgium"
    assert result["location"] == ""


def test_parse_h1_no_country_match_still_captures_location():
    """When the trailing tail ends in an unknown country, location keeps the
    full middle text and country stays empty."""
    h1 = (
        '<a href="/dj/fredagain/index.html" class="notranslate ">Fred again..</a>'
        ' @ <a href="/source/abc/someevent-slug/index.html">Some Event</a>,'
        " Some Venue, Atlantis 2026-02-27"
    )
    result = _parse_h1_structure(h1)
    assert result["country"] == ""
    assert result["location"] == "Some Venue, Atlantis"


def test_bare_promoter_source_is_not_stage():
    """Tiesto @ We Belong Here, Historic Virginia Key Park.

    'We Belong Here' is a /source/ link (Event Promoter) with no suffix.
    It should NOT be treated as a stage.
    """
    h1 = (
        '<a href="/dj/tiesto/index.html" class="notranslate ">Ti&euml;sto</a>'
        ' @ <a href="/source/5j4wgtv/we-belong-here/index.html">'
        "We Belong Here</a>,"
        ' <a href="/source/7xp1dkc/historic-virginia-key-park/index.html">'
        "Historic Virginia Key Park</a>, United States 2026-03-01"
    )
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == ""
    assert len(result["sources"]) == 2


def test_parse_h1_captures_event_date_red_rocks_case():
    """Martin Garrix & Alesso @ Red Rocks Amphitheatre, United States 2025-10-24.

    The trailing ISO date is the event date. It must be captured into
    result["date"] so downstream code can write CRATEDIGGER_1001TL_DATE
    instead of falling back to the YouTube publish date.
    """
    h1 = (
        '<a href="/dj/martingarrix/index.html" class="notranslate ">Martin Garrix</a>'
        " &amp; "
        '<a href="/dj/alesso/index.html" class="notranslate ">Alesso</a>'
        ' @ <a href="/source/abc/red-rocks-amphitheatre/index.html">'
        "Red Rocks Amphitheatre</a>, United States 2025-10-24"
    )
    result = _parse_h1_structure(h1)
    assert result["date"] == "2025-10-24"


def test_parse_h1_captures_date_when_no_source_links():
    """FISHER @ Bay Oval Park, New Zealand 2026-01-31 (no source links).

    The date must still be captured when the h1 tail has no /source/ link."""
    h1 = (
        '<a href="/dj/fisher/index.html" class="notranslate ">FISHER</a>'
        ' @ Bay Oval Park, New Zealand 2026-01-31'
    )
    result = _parse_h1_structure(h1)
    assert result["date"] == "2026-01-31"


def test_parse_h1_captures_date_when_only_date_in_tail():
    """No country, only a trailing date — still captured."""
    h1 = (
        '<a href="/dj/fisher/index.html" class="notranslate ">FISHER</a>'
        ' @ Bay Oval Park 2026-01-31'
    )
    result = _parse_h1_structure(h1)
    assert result["date"] == "2026-01-31"


def test_parse_h1_date_empty_when_no_trailing_date():
    """When the h1 has no trailing ISO date, result["date"] is empty."""
    h1 = (
        '<a href="/dj/tiesto/index.html" class="notranslate ">Ti&euml;sto</a>'
        ' @ Mainstage, <a href="/source/fgcfkm/tomorrowland/index.html">Tomorrowland</a>'
    )
    result = _parse_h1_structure(h1)
    assert result["date"] == ""


def test_parse_h1_date_empty_when_no_at_sign():
    """Aftermovie-style h1 with no @ returns early — date is empty."""
    h1 = 'Mysteryland - Aftermovie 2025-09-15'
    result = _parse_h1_structure(h1)
    assert result["date"] == ""
