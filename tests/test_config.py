import pytest

from newsbot.config import CATEGORIES, get_env


def test_categories_are_the_six_agreed_names_in_order():
    assert list(CATEGORIES) == [
        "정치·사회",
        "경제·산업",
        "국제",
        "IT·과학·인공지능",
        "문화연예·스포츠",
        "재난·환경·지역",
    ]


def test_get_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("NEWSBOT_MISSING_VAR", raising=False)
    with pytest.raises(RuntimeError):
        get_env("NEWSBOT_MISSING_VAR")


def test_get_env_returns_value(monkeypatch):
    monkeypatch.setenv("NEWSBOT_SOME_VAR", "abc")
    assert get_env("NEWSBOT_SOME_VAR") == "abc"
