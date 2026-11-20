import os

CATEGORIES: dict[str, str] = {
    "정치·사회": "정치 OR 국회 OR 사회",
    "경제·산업": "경제 OR 산업 OR 증시",
    "국제": "국제 OR 외교 OR 해외",
    "IT·과학·인공지능": "IT OR 과학 OR 인공지능",
    "문화연예·스포츠": "문화 OR 연예 OR 스포츠",
    "재난·환경·지역": "재난 OR 환경 OR 지역",
}


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
