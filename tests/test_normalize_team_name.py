from flashscore_scraper.scraper import normalize_team_name


def test_lowercase():
    assert normalize_team_name('VB Nantes') == 'vb nantes'


def test_strip_whitespace():
    assert normalize_team_name('  Team  ') == 'team'


def test_remove_suffix_w():
    assert normalize_team_name('Team W') == 'team'


def test_remove_suffix_f():
    assert normalize_team_name('Team F') == 'team'


def test_remove_suffix_women():
    assert normalize_team_name('Team Women') == 'team'


def test_remove_suffix_femmes():
    assert normalize_team_name('Team Femmes') == 'team'


def test_remove_suffix_parenthesized():
    assert normalize_team_name('Team (F)') == 'team'
    assert normalize_team_name('Team (W)') == 'team'


def test_no_false_positive():
    """Suffixes only removed at end, not in middle."""
    assert normalize_team_name('Few') == 'few'
