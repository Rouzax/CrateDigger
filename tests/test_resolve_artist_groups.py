from festival_organizer.config import Config


class _FakeDjCache:
    def derive_artist_aliases(self):
        return {}

    def derive_artist_groups(self):
        return set()

    def derive_entry_names(self):
        return {"above & beyond"}


def test_resolve_artist_keeps_group_entry_unsplit(monkeypatch):
    monkeypatch.setattr(Config, "dj_cache", property(lambda self: _FakeDjCache()))
    cfg = Config({})
    assert cfg.resolve_artist("Above & Beyond") == "Above & Beyond"


def test_resolve_artist_still_splits_real_b2b(monkeypatch):
    monkeypatch.setattr(Config, "dj_cache", property(lambda self: _FakeDjCache()))
    cfg = Config({})
    assert cfg.resolve_artist("Martin Garrix & Alesso") == "Martin Garrix"
