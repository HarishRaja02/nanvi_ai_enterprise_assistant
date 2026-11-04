"""WebSocket gateway so a browser can talk to an AgentSession.

Browser -> server:  user_text | interrupt | chunk_ack | set_provider
Server  -> browser: speak | stop | interrupted | resumed | response_done | error | provider | ready
Playback happens on the client (the demo uses speechSynthesis); the client acks each chunk.
Run:  python -m nanvi_agents.gateway
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import websockets

from .providers.registry import registry
from .session import AgentSession
from .types import new_id

log = logging.getLogger("nanvi.agents")


class WsSink:
    def __init__(self, ws):
        self.ws = ws

    async def _send(self, obj: dict) -> None:
        try:
            await self.ws.send(json.dumps(obj))
        except websockets.ConnectionClosed:
            pass

    async def send_chunk(self, *, response_id, generation_id, index, text, audio=None):
        await self._send({"type": "speak", "response_id": response_id,
                          "generation_id": generation_id, "index": index, "text": text})

    async def stop(self, generation_id):
        await self._send({"type": "stop", "generation_id": generation_id})

    async def pause(self, generation_id):
        await self._send({"type": "pause", "generation_id": generation_id})

    async def emit(self, event):
        await self._send(event)


async def handle(ws) -> None:
    provider = os.environ.get("NANVI_LLM_PROVIDER", "mock")
    try:
        llm = registry.create("llm", provider)
    except Exception as e:  # missing key etc: fall back so the demo still works
        log.warning("provider %s unavailable (%s); using mock", provider, e)
        provider, llm = "mock", registry.create("llm", "mock")
    session = AgentSession(new_id(), llm, WsSink(ws))
    await ws.send(json.dumps({"type": "ready", "provider": provider,
                              "providers": registry.names("llm")}))
    async for raw in ws:
        try:
            m = json.loads(raw)
            t = m.get("type")
            if t == "user_text":
                await session.handle_user_text(m.get("text", ""))
            elif t == "interrupt":
                await session.interrupt("client")
            elif t == "pause":
                await session.pause("client")
            elif t == "resume":
                await session.resume_paused("client")
            elif t == "chunk_ack":
                await session.on_chunk_ack(m["response_id"], m["generation_id"], int(m["index"]))
            elif t == "set_provider":
                try:
                    session.set_llm(registry.create("llm", m["name"]))
                    await ws.send(json.dumps({"type": "provider", "provider": m["name"]}))
                except Exception as e:
                    await ws.send(json.dumps({"type": "error", "where": "provider", "message": str(e)}))
        except Exception as e:
            log.exception("bad message")
            await ws.send(json.dumps({"type": "error", "where": "gateway", "message": str(e)}))
    await session.interrupt("disconnect")


async def serve(host: str = "0.0.0.0", port: int = 8765) -> None:
    async with websockets.serve(handle, host, port):
        log.info("agent gateway on ws://%s:%s", host, port)
        await asyncio.Future()


def main() -> None:
    from .config import load_env
    load_env(".env", "../../.env")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve(os.environ.get("NANVI_AGENT_HOST", "0.0.0.0"),
                      int(os.environ.get("NANVI_AGENT_PORT", "8765"))))


if __name__ == "__main__":
    main()

