from flashscore_scraper.hockey_scraper import detect_sexe, parse_hockey_score


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
    """Test the categorization logic: <=4, <=5, =6, >=7 total goals."""

    def test_under_four_goals(self):
        # 2+1=3 total goals → <=4 and <=5
        a, b = parse_hockey_score('2:1')
        total = a + b
        assert total <= 4
        assert total <= 5

    def test_exactly_four_goals(self):
        # 3+1=4 total goals → <=4 and <=5
        a, b = parse_hockey_score('3:1')
        total = a + b
        assert total <= 4
        assert total <= 5

    def test_exactly_five_goals(self):
        # 3+2=5 → <=5 but NOT <=4
        a, b = parse_hockey_score('3:2')
        total = a + b
        assert total > 4
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

    def test_four_goals_boundary(self):
        # 2+2=4 → <=4 category
        a, b = parse_hockey_score('2:2')
        total = a + b
        assert total <= 4

    def test_five_goals_boundary(self):
        # 3+2=5 → <=5 but not <=4
        a, b = parse_hockey_score('3:2')
        total = a + b
        assert total <= 5
        assert total > 4

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


class TestDetectSexe:
    def test_default_is_homme(self):
        assert detect_sexe('NHL') == 'H'
        assert detect_sexe('KHL') == 'H'
        assert detect_sexe('SHL') == 'H'

    def test_women_keyword(self):
        assert detect_sexe("IIHF Women's World Championship") == 'F'

    def test_femme_keyword(self):
        assert detect_sexe('Ligue Femme') == 'F'

    def test_feminine_keyword(self):
        assert detect_sexe('Division 1 Féminin') == 'F'

    def test_dames_keyword(self):
        assert detect_sexe('Championnat Dames') == 'F'

    def test_ladies_keyword(self):
        assert detect_sexe('Ladies League') == 'F'

    def test_f_suffix(self):
        assert detect_sexe('SDHL (F)') == 'F'

    def test_w_suffix(self):
        assert detect_sexe('PWHL (W)') == 'F'

    def test_case_insensitive(self):
        assert detect_sexe('WOMEN HOCKEY LEAGUE') == 'F'

    def test_empty_string(self):
        assert detect_sexe('') == 'H'
