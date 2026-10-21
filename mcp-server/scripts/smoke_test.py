"""
Gọi MCP server thật qua HTTP như agent sẽ gọi (kiểm tra sau khi deploy).

    python scripts/smoke_test.py --url http://localhost:8080 --key $MCP_API_KEY --customer KH0001
    python scripts/smoke_test.py --url https://<endpoint-agentbase> --key ... --customer KH0001
"""
import argparse
import asyncio
import json

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main(url, key, customer):
    async with httpx2.AsyncClient(timeout=30) as http:
        r = await http.get(url.rstrip("/") + "/health")
        print("GET /health ->", r.status_code, r.text)
    headers = {"X-Api-Key": key, "X-Customer-Id": customer, "X-Session-Id": "smoke-test"}
    async with httpx2.AsyncClient(headers=headers, timeout=60) as http:
        async with streamable_http_client(url.rstrip("/") + "/mcp", http_client=http) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as s:
                await s.initialize()
                tools = await s.list_tools()
                print(f"{len(tools.tools)} tools:", ", ".join(t.name for t in tools.tools))
                for name, args in [
                    ("get_current_date", {}),
                    ("get_account_balances", {}),
                    ("get_month_overview", {}),
                    ("parse_vnd_amount", {"text": "chuyển cho con trai một triệu rưỡi"}),
                    ("find_beneficiary", {"name": "con trai"}),
                    ("open_transfer_screen", {"amount": 1500000, "beneficiary_id": 2}),
                    ("detect_unusual_transactions", {}),
                ]:
                    res = await s.call_tool(name, args)
                    raw = res.content[0].text if res.content else ""
                    try:
                        data = json.loads(raw)
                    except ValueError:
                        data = {"text": raw}
                    print(f"\n[{name}] error={res.is_error}")
                    print("   speech:", data.get("speech") or data.get("text") or json.dumps(data, ensure_ascii=False)[:300])
                    if data.get("ui_action"):
                        print("   ui_action:", json.dumps(data["ui_action"], ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--key", required=True)
    ap.add_argument("--customer", default="KH0001")
    a = ap.parse_args()
    asyncio.run(main(a.url, a.key, a.customer))
