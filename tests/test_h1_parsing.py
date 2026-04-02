from festival_organizer.tracklists.api import _parse_h1_structure


def test_simple_stage():
    """Afrojack @ kineticFIELD, EDC Las Vegas"""
    h1 = '<a href="/dj/afrojack/index.html" class="notranslate ">AFROJACK</a> @ kineticFIELD, <a href="/source/unkguv/edc-las-vegas/index.html">EDC Las Vegas</a>, United States 2025-05-17'
    result = _parse_h1_structure(h1)
    assert result["stage_text"] == "kineticFIELD"
    assert ("unkguv", "edc-las-vegas", "EDC Las Vegas") in result["sources"]


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
