import pytest


@pytest.fixture(autouse=True)
def isolate_local_demo_setting(monkeypatch):
    # Local presentation preferences must not change unrelated test scenarios.
    # Tests of automatic rosters opt in explicitly through Settings.
    monkeypatch.setenv('CREW_RANDOM_DEMO', 'false')
