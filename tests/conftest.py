import pytest


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """재시도 대기 때문에 테스트가 느려지지 않게 한다. 대기 동작을 보는 테스트는 직접 덮어쓴다."""
    monkeypatch.setattr("newsbot.collect_news._sleep", lambda seconds: None, raising=False)
