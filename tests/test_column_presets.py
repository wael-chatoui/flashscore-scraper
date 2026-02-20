from flashscore_scraper.sheets import COLUMN_PRESETS, get_column_preset


def test_presets_have_required_keys():
    for name, preset in COLUMN_PRESETS.items():
        assert 'sheetName' in preset, f'{name} missing sheetName'
        assert 'teamA' in preset, f'{name} missing teamA'
        assert 'teamB' in preset, f'{name} missing teamB'
        assert 'h2h' in preset, f'{name} missing h2h'


def test_stats_keys():
    """Each stats group must define set3, set4, set5."""
    for name, preset in COLUMN_PRESETS.items():
        for group in ('teamA', 'teamB', 'h2h'):
            for key in ('set3', 'set4', 'set5'):
                assert key in preset[group], f'{name}.{group} missing {key}'


def test_get_column_preset_returns_dict():
    result = get_column_preset()
    assert isinstance(result, dict)
    assert 'sheetName' in result


def test_original_preset_has_match_info():
    preset = COLUMN_PRESETS['ORIGINAL']
    mi = preset['matchInfo']
    assert mi['date'] == 'A'
    assert mi['teamA'] == 'E'
    assert mi['teamB'] == 'G'
