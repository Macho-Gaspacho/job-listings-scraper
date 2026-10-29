from daily import commit_daily_files


def test_commit_daily_files_exists():
    assert callable(commit_daily_files)
