from festival_organizer.notify import throttle


def test_not_notified_when_marker_absent(tmp_path):
    m = tmp_path / "marker.json"
    assert throttle.already_notified("0.20.0", marker_path=m) is False


def test_record_then_already_notified_same_version(tmp_path):
    m = tmp_path / "marker.json"
    throttle.record_notified("0.20.0", marker_path=m)
    assert throttle.already_notified("0.20.0", marker_path=m) is True


def test_newer_version_not_yet_notified(tmp_path):
    m = tmp_path / "marker.json"
    throttle.record_notified("0.20.0", marker_path=m)
    assert throttle.already_notified("0.21.0", marker_path=m) is False


def test_corrupt_marker_treated_as_not_notified(tmp_path):
    m = tmp_path / "marker.json"
    m.write_text("not json")
    assert throttle.already_notified("0.20.0", marker_path=m) is False
