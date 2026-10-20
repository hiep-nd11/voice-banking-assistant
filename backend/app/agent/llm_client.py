import httpx

from app.core.config import settings


async def chat_completion_stream(messages, tools=None):
    payload = {'model': settings.llm_model, 'messages': messages, 'stream': True, 'temperature': 0.2}
    if tools:
        payload['tools'] = tools
    headers = {'Authorization': f'Bearer {settings.llm_api_key}'}
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream('POST', f'{settings.llm_base_url.rstrip("/")}/chat/completions', json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith('data: '):
                    yield line[6:]
