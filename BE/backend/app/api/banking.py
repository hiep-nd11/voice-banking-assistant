"""Read-only banking data from the same MCP source used by the assistant."""

import asyncio

import httpx
from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from app.tools.banking_catalog import FEATURES, MODELS, TOOLS, validate_dates
from app.tools.mcp_client import call_mcp, dispatch_tool

router = APIRouter(prefix="/api/banking", tags=["banking"])


@router.get("/features")
async def features():
    return {
        "features": [
            {
                "id": key,
                "title": title,
                "schema": TOOLS[tool]["inputSchema"],
                "read_only": TOOLS[tool]["annotations"].get("readOnlyHint", False),
            }
            for key, (title, tool) in FEATURES.items()
        ]
    }


@router.post("/features/{feature}")
async def query_feature(feature: str, args: dict = Body(default={})):
    if feature not in FEATURES:
        raise HTTPException(404, "Chức năng không tồn tại")
    try:
        values = MODELS[feature].model_validate(args).model_dump(exclude_none=True)
        validate_dates(values)
    except ValidationError as e:
        raise HTTPException(
            422, "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        )
    except ValueError:
        raise HTTPException(422, "Ngày hoặc khoảng thời gian không hợp lệ")
    try:
        result = await dispatch_tool(FEATURES[feature][1], None, values)
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, "Không truy vấn được dữ liệu ngân hàng. Vui lòng thử lại.")
    if not isinstance(result, dict):
        raise HTTPException(502, "Nguồn dữ liệu trả sai định dạng")
    if "error" in result:
        raise HTTPException(502, str(result["error"]))
    return result


@router.get("/overview")
async def overview():
    # The upstream MCP instance determines the customer; customer_id does not
    # switch its database context. Never pretend that this endpoint can do so.
    try:
        profile, balances, transactions = await asyncio.gather(
            call_mcp("get_customer_profile"),
            call_mcp("get_account_balances"),
            call_mcp("get_recent_transactions", {"limit": 20}),
        )
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Không tải được dữ liệu ngân hàng từ MCP")
    for result in (profile, balances, transactions):
        if not isinstance(result, dict) or "error" in result:
            raise HTTPException(502, "Nguồn dữ liệu ngân hàng trả lỗi")
    if (
        not isinstance(profile.get("full_name"), str)
        or not isinstance(balances.get("accounts"), list)
        or not isinstance(transactions.get("items"), list)
    ):
        raise HTTPException(502, "Dữ liệu ngân hàng không đúng định dạng")
    return {
        "source": "mcp",
        "profile": profile,
        "accounts": balances["accounts"],
        "as_of": balances.get("as_of"),
        "transactions": transactions["items"],
    }
