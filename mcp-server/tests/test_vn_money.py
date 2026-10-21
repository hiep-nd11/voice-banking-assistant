import json
import random
from pathlib import Path

import pytest

from app.vn_money import parse_vnd_amount, read_number, vnd_text, vnd_words

CASES = [json.loads(l) for l in (Path(__file__).parents[1] / "evals" / "amount_cases.jsonl").read_text().splitlines()
         if l.strip()]


@pytest.mark.parametrize("case", CASES, ids=[c["text"] or "<empty>" for c in CASES])
def test_amount_cases(case):
    r = parse_vnd_amount(case["text"])
    got = r.get("amount") if r.get("ok") else None
    assert got == case["amount"], r


@pytest.mark.parametrize("n,words", [
    (21, "hai mươi mốt"), (24, "hai mươi tư"), (25, "hai mươi lăm"), (15, "mười lăm"), (105, "một trăm linh năm"),
    (1_050_000, "một triệu không trăm năm mươi nghìn"), (2_005_000_000, "hai tỷ không trăm linh năm triệu"),
])
def test_read_number(n, words):
    assert read_number(n) == words


def test_round_trip_words_to_amount():
    """Đọc thành chữ rồi hiểu ngược lại phải ra đúng số (thứ TTS đọc và STT nghe lại)."""
    rnd = random.Random(7)
    for _ in range(3000):
        n = rnd.choice([rnd.randrange(1, 1000) * 1000, rnd.randrange(1, 1000) * 1_000_000,
                        rnd.randrange(1000, 10**9, 1000), rnd.randrange(1, 50) * 100_000])
        r = parse_vnd_amount(vnd_words(n))
        assert r.get("amount") == n, (n, vnd_words(n), r)


def test_text_format():
    assert vnd_text(1500000) == "1.500.000đ"
    assert parse_vnd_amount("một triệu rưỡi")["needs_confirmation"] is True
