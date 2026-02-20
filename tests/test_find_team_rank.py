from flashscore_scraper.scraper import find_team_rank


def test_exact_match():
    standings = {'paris': 1, 'lyon': 2}
    assert find_team_rank('Paris', standings) == '1'


def test_partial_match_team_in_standing():
    standings = {'paris volley': 3}
    assert find_team_rank('Paris', standings) == '3'


def test_partial_match_standing_in_team():
    standings = {'paris': 4}
    assert find_team_rank('Paris Volley', standings) == '4'


def test_no_match():
    standings = {'paris': 1, 'lyon': 2}
    assert find_team_rank('Nantes', standings) == ''


def test_empty_standings():
    assert find_team_rank('Paris', {}) == ''


def test_suffix_stripping():
    """Team name with suffix should still match after normalization."""
    standings = {'team': 5}
    assert find_team_rank('Team W', standings) == '5'
