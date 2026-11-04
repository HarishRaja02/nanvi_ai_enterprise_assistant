"""Audio bridge server: a media-plane sidecar (e.g. the Go SFU) streams participant audio here.

WebSocket, default ws://0.0.0.0:8766
  client -> server: BINARY = one 20 ms PCM frame (16 kHz mono S16LE, 640 bytes)
                    TEXT   = {"type":"chunk_ack",...} | {"type":"interrupt"} (same as gateway protocol)
  server -> client: TEXT events identical to gateway.py (speak / stop / interrupted / ...)
The media plane never waits on this service: frames are fire-and-forget.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import websockets

from .audio import AudioPipeline
from .gateway import WsSink
from .providers.registry import registry
from .session import AgentSession
from .types import new_id

log = logging.getLogger("nanvi.bridge")


async def handle(ws) -> None:
    llm = registry.create("llm", os.environ.get("NANVI_LLM_PROVIDER", "mock"))
    stt = registry.create("stt", os.environ.get("NANVI_STT_PROVIDER", "mock"))
    session = AgentSession(new_id(), llm, WsSink(ws))
    pipe = AudioPipeline(session, stt)
    async for msg in ws:
        try:
            if isinstance(msg, bytes):
                await pipe.feed_frame(msg)
            else:
                m = json.loads(msg)
                if m.get("type") == "chunk_ack":
                    await session.on_chunk_ack(m["response_id"], m["generation_id"], int(m["index"]))
                elif m.get("type") == "interrupt":
                    await session.interrupt("client")
        except Exception:
            log.exception("bridge message failed")  # one bad frame must not kill the session
    await session.interrupt("disconnect")


def main() -> None:
    from .config import load_env
    load_env(".env", "../../.env")
    logging.basicConfig(level=logging.INFO)
    async def run():
        async with websockets.serve(handle, "0.0.0.0", int(os.environ.get("NANVI_BRIDGE_PORT", "8766"))):
            await asyncio.Future()
    asyncio.run(run())


if __name__ == "__main__":
    main()
