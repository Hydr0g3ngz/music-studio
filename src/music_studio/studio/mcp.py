"""Local stdio MCP adapter: python -m music_studio.studio.mcp --workspace PATH."""

import argparse
import asyncio
import json
from pathlib import Path

from ..config import Settings
from .service import StudioService
from .tools import ToolCatalog


async def serve(workspace: Path, settings=None):
    try:
        import mcp.server.stdio
        import mcp.types as types
        from mcp.server.lowlevel import Server
    except ImportError as error:
        raise RuntimeError("Install agent support: pip install -e '.[agent,audio]' ") from error

    service = StudioService(workspace, settings)
    service.tasks.wake.set()
    catalog = ToolCatalog(service)
    server = Server(
        "music-studio",
        version="0.2.0-dev",
        instructions="Local audio workbench. Read the session and selection before editing. "
        "Create previews by default. Adopt only on an explicit request. "
        "Original audio is retained. Never upload audio or run arbitrary shell commands.",
    )

    @server.list_tools()
    async def list_tools():
        return [types.Tool(**tool) for tool in catalog.describe()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            result = await asyncio.to_thread(catalog.call, name, arguments)
            return types.CallToolResult(
                content=[
                    types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))
                ],
                structuredContent=result,
            )
        except (ValueError, OSError) as error:
            return types.CallToolResult(
                isError=True, content=[types.TextContent(type="text", text=str(error))]
            )

    try:
        async with mcp.server.stdio.stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        service.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--inference-python", type=Path)
    parser.add_argument("--lyrics-python", type=Path)
    args = parser.parse_args()
    configured = {k: str(v) for k, v in vars(args).items() if k != "workspace" and v is not None}
    asyncio.run(serve(args.workspace, Settings(**configured) if configured else None))


if __name__ == "__main__":
    main()
