"""
로컬 LLM — Ollama (OpenAI 호환 /v1/chat/completions).

- 대화 + function/tool calling 을 담당.
- OpenAI SDK 를 그대로 쓰되 base_url 만 localhost:11434 로 → 클라우드 전환 시 base_url 만 교체.
- Realtime 용 TOOLS(플랫 포맷)를 Chat Completions tools 포맷으로 변환.

할루시네이션 억제:
  - temperature 낮춤 (config.LLM_TEMPERATURE)
  - 메뉴/규칙을 시스템 프롬프트에 강하게 grounding (프롬프트는 호출측에서 주입)
  - 툴 인자는 실제 메뉴에 대해 호출측(handlers)에서 재검증
"""

import asyncio
from typing import Optional

from openai import AsyncOpenAI

from src.engines import config


def to_chat_tools(realtime_tools: list) -> list:
    """Realtime 플랫 tool 포맷 → Chat Completions {'type','function':{...}} 포맷."""
    out = []
    for t in realtime_tools:
        if t.get("type") != "function":
            continue
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            },
        })
    return out


class LocalLLM:
    def __init__(self, model: Optional[str] = None):
        self.model = model or config.LLM_MODEL
        self._client = AsyncOpenAI(
            base_url=config.LLM_BASE_URL,
            api_key=config.LLM_API_KEY,
        )

    async def chat(self, messages: list, tools: Optional[list] = None):
        """
        messages: [{"role","content"} | tool 메시지] 리스트
        tools: Chat Completions 포맷 tool 목록 (없으면 미전달)
        반환: choice.message (content / tool_calls 포함)
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = await self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message


# ─── 단독 테스트 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    from src.tools.handlers import TOOLS

    async def _main():
        llm = LocalLLM()
        tools = to_chat_tools(TOOLS)
        messages = [
            {"role": "system", "content":
             "너는 햄버거 가게 카운터 직원 '케이'야. 손님이 메뉴를 말하면 반드시 add_to_cart 툴을 호출해. "
             "메뉴: 치즈버거, 더블버거, 감자튀김, 콜라. 한국어로 짧게 답해."},
            {"role": "user", "content": "치즈버거 하나랑 콜라 주세요"},
        ]
        msg = await llm.chat(messages, tools)
        print("content:", repr(msg.content))
        if msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"tool_call: {tc.function.name}({tc.function.arguments})")
        else:
            print("(툴 콜 없음)")

    asyncio.run(_main())
