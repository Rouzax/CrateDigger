import festival_organizer.notify as notify


def test_chapter_counter_and_analyse_imports_exist():
    from festival_organizer.tracklists.chapters import extract_existing_chapters
    from festival_organizer.analyzer import analyse_file
    assert callable(extract_existing_chapters)
    assert callable(analyse_file)


def test_notify_entry_points_are_public():
    assert hasattr(notify, "notify_new_sets")
    assert hasattr(notify, "notify_updated_sets")
    assert hasattr(notify, "notify_test")
