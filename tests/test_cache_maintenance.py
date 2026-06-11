from festival_organizer.cache_maintenance import reconcile_artist_cache


def test_reconcile_removes_non_slug_dirs(tmp_path):
    root = tmp_path / "artists"
    for name in ["aboveandbeyond", "tiesto", "Above", "Ti�sto", "K_lsch", "fredagain"]:
        (root / name).mkdir(parents=True)
    valid = {"aboveandbeyond", "tiesto", "fredagain"}

    removed = reconcile_artist_cache(root, valid)

    remaining = {p.name for p in root.iterdir()}
    assert remaining == {"aboveandbeyond", "tiesto", "fredagain"}
    assert {p.name for p in removed} == {"Above", "Ti�sto", "K_lsch"}


def test_reconcile_idempotent_on_clean_cache(tmp_path):
    root = tmp_path / "artists"
    (root / "tiesto").mkdir(parents=True)
    assert reconcile_artist_cache(root, {"tiesto"}) == []


def test_reconcile_missing_root_is_noop(tmp_path):
    assert reconcile_artist_cache(tmp_path / "nope", {"x"}) == []
