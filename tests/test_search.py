from listings import sort_rows


def test_sort_rows_new_first():
    rows = [
        {"Company": "B", "Title": "PO", "Status": "Seen"},
        {"Company": "A", "Title": "PM", "Status": "New"},
    ]
    sorted_rows = sort_rows(rows)
    assert sorted_rows[0]["Status"] == "New"
