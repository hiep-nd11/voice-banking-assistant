"""Eval bộ hiểu số tiền: python -m evals.run_amount_eval"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.vn_money import parse_vnd_amount  # noqa: E402

cases = [json.loads(l) for l in (pathlib.Path(__file__).parent / "amount_cases.jsonl").read_text().splitlines() if l.strip()]
ok = 0
fails = []
for c in cases:
    r = parse_vnd_amount(c["text"])
    got = r.get("amount") if r.get("ok") else None
    if got == c["amount"]:
        ok += 1
    else:
        fails.append((c["text"], c["amount"], got, r.get("reason")))
print(f"Amount parsing: {ok}/{len(cases)} đúng ({ok / len(cases):.1%})")
for f in fails:
    print("  SAI:", f)
sys.exit(0 if not fails else 1)
