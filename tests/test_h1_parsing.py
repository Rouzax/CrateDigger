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
