from flashscore_scraper.hockey_scraper import parse_hockey_score


class TestParseHockeyScore:
    def test_colon_format(self):
        assert parse_hockey_score('4:2') == (4, 2)

    def test_dash_format(self):
        assert parse_hockey_score('4-2') == (4, 2)

    def test_spaced_dash(self):
        assert parse_hockey_score('4 - 2') == (4, 2)

    def test_spaced_colon(self):
        assert parse_hockey_score('4 : 2') == (4, 2)

    def test_overtime_ap_suffix(self):
        assert parse_hockey_score('3:2 AP') == (3, 2)

    def test_overtime_ot_suffix(self):
        assert parse_hockey_score('3-2 OT') == (3, 2)

    def test_shootout_tb_suffix(self):
        assert parse_hockey_score('2:1 TB') == (2, 1)

    def test_shootout_so_suffix(self):
        assert parse_hockey_score('5-4 SO') == (5, 4)

    def test_penalty_p_suffix(self):
        assert parse_hockey_score('3:2 P') == (3, 2)

    def test_empty_string(self):
        assert parse_hockey_score('') == (None, None)

    def test_none_returns_none(self):
        assert parse_hockey_score(None) == (None, None)

    def test_invalid_format(self):
        assert parse_hockey_score('abc') == (None, None)

    def test_zero_zero(self):
        assert parse_hockey_score('0:0') == (0, 0)

    def test_high_scoring(self):
        assert parse_hockey_score('8:5') == (8, 5)

    def test_concatenated_digits(self):
        """FlashScore H2H pages use concatenated format like '42' for 4-2."""
        assert parse_hockey_score('42') == (4, 2)

    def test_concatenated_zero(self):
        assert parse_hockey_score('01') == (0, 1)

    def test_concatenated_high(self):
        assert parse_hockey_score('63') == (6, 3)


class TestGoalCategorization:
    """Test the categorization logic: <=5, =6, >=7 total goals."""

    def test_under_five_goals(self):
        # 2+1=3 total goals → <=5
        a, b = parse_hockey_score('2:1')
        total = a + b
        assert total <= 5

    def test_exactly_six_goals(self):
        # 4+2=6 total goals → =6
        a, b = parse_hockey_score('4:2')
        total = a + b
        assert total == 6

    def test_seven_or_more_goals(self):
        # 5+3=8 total goals → >=7
        a, b = parse_hockey_score('5:3')
        total = a + b
        assert total >= 7

    def test_five_goals_boundary(self):
        # 3+2=5 → <=5 category
        a, b = parse_hockey_score('3:2')
        total = a + b
        assert total <= 5

    def test_six_goals_boundary(self):
        # 3+3=6 → =6 category
        a, b = parse_hockey_score('3:3')
        total = a + b
        assert total == 6

    def test_seven_goals_boundary(self):
        # 4+3=7 → >=7 category
        a, b = parse_hockey_score('4:3')
        total = a + b
        assert total >= 7
