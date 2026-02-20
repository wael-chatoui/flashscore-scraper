from flashscore_scraper.sort_sheet import col_to_index


def test_single_letter():
    assert col_to_index('A') == 0
    assert col_to_index('B') == 1
    assert col_to_index('Z') == 25


def test_double_letter():
    assert col_to_index('AA') == 26
    assert col_to_index('AB') == 27
    assert col_to_index('AZ') == 51
    assert col_to_index('BA') == 52


def test_case_insensitive():
    assert col_to_index('a') == 0
    assert col_to_index('aa') == 26


def test_known_columns():
    """Verify columns used in the actual spreadsheet presets."""
    assert col_to_index('M') == 12
    assert col_to_index('AJ') == 35
    assert col_to_index('AL') == 37
