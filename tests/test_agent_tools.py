import asyncio
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from music_studio.io import sha256, write_json
from music_studio.studio.codex import CodexBridge
from music_studio.studio.models import SelectionRequest
from music_studio.studio.service import StudioError, StudioService
from music_studio.studio.tools import ToolCatalog


@pytest.fixture
def agent_project(tmp_path):
    project = "1234567890abcdef"
    folder = tmp_path / project
    studio = folder / ".studio"
    studio.mkdir(parents=True)
    sf.write(studio / "source.wav", np.full((44100, 2), 0.2), 44100, subtype="FLOAT")
    write_json(studio / "source.json", {"file": ".studio/source.wav"})
    write_json(
        folder / "job.json",
        {
            "id": project,
            "title": "Audio test",
            "filename": "audio.wav",
            "status": "ready",
            "created_at": 1,
        },
    )
    return StudioService(tmp_path), project


def test_tools_share_selection_and_reject_cross_project_and_arbitrary_fields(agent_project):
    service, project = agent_project
    catalog = ToolCatalog(service, actor="codex", project=project)
    catalog.call(
        "audio_set_selection", {"project": project, "revision": 0, "start": 0.2, "end": 0.8}
    )
    selected = StudioService(service.root).session(project)["selection"]
    assert selected == {"asset": "source", "start": 0.2, "end": 0.8}
    assert service.session(project)["revision"] == 0
    with pytest.raises(StudioError) as denied:
        catalog.call("audio_get_session", {"project": "abcdef1234567890"})
    assert denied.value.status == 403
    with pytest.raises(ValueError):
        catalog.call(
            "audio_render_preview",
            {
                "project": project,
                "revision": 0,
                "operations": [{"type": "gain", "db": -3, "shell": "arbitrary"}],
            },
        )
    with pytest.raises(StudioError):
        catalog.call("run_shell", {})
    assert service.session(project)["candidates"] == []
    assert len(catalog.describe()) == 8
    assert "waveform" not in catalog.call("audio_get_session", {"project": project})
    with pytest.raises(StudioError):
        service.selection(project, SelectionRequest(revision=0, start=0.2, end=2))


def test_real_mcp_stdio_client_generates_preview_and_shared_state(agent_project):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    service, project = agent_project
    original = sha256(service.asset_path(project, "source"))

    async def run():
        environment = {
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        }
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "music_studio.studio.mcp", "--workspace", str(service.root)],
            env=environment,
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            tools = await client.list_tools()
            assert len(tools.tools) == 8
            session = await client.call_tool("audio_get_session", {"project": project})
            assert not session.isError and session.structuredContent["revision"] == 0
            preview = await client.call_tool(
                "audio_render_preview",
                {
                    "project": project,
                    "revision": 0,
                    "operations": [{"type": "gain", "db": -6}],
                },
            )
            assert not preview.isError
            candidate = preview.structuredContent["id"]
            assert service.session(project)["active"] == "source"
            assert service.session(project)["candidates"][0]["actor"] == "mcp"
            adopted = await client.call_tool(
                "audio_adopt_preview",
                {
                    "project": project,
                    "revision": 0,
                    "candidate": candidate,
                },
            )
            assert not adopted.isError
            assert StudioService(service.root).session(project)["revision"] == 1
            invalid = await client.call_tool(
                "audio_history",
                {
                    "project": project,
                    "revision": 0,
                    "direction": "undo",
                },
            )
            assert invalid.isError

    asyncio.run(run())
    assert sha256(service.asset_path(project, "source")) == original


def test_app_server_protocol_streams_and_dispatches_audio_tools(
    agent_project, monkeypatch, tmp_path
):
    """Protocol fixture only. Real Codex inference is a separate manual integration check."""
    service, project = agent_project
    fake = tmp_path / "protocol_fixture.py"
    fake.write_text(
        """import json,sys
def emit(message):
 print(json.dumps(message),flush=True)
thread='fixture-thread'
for line in sys.stdin:
 m=json.loads(line); method=m.get('method'); rid=m.get('id')
 if method=='initialize': emit({'id':rid,'result':{'userAgent':'protocol-fixture'}})
 elif method=='thread/start':
  assert m['params']['sandbox']=='read-only'
  assert len(m['params']['dynamicTools'])==8
  emit({'id':rid,'result':{'thread':{'id':thread}}})
 elif method=='turn/start':
  emit({'id':rid,'result':{'turn':{'id':'turn-1'}}})
  emit({'method':'turn/started','params':{'threadId':thread,'turn':{'id':'turn-1'}}})
  emit({'id':100,'method':'item/tool/call','params':{'threadId':thread,'turnId':'turn-1','callId':'c1','tool':'audio_get_session','arguments':{'project':'1234567890abcdef'}}})
 elif rid==100:
  assert m['result']['success']
  session=json.loads(m['result']['contentItems'][0]['text'])
  emit({'id':101,'method':'item/tool/call','params':{'threadId':thread,'turnId':'turn-1','callId':'c2','tool':'audio_render_preview','arguments':{'project':'1234567890abcdef','revision':session['revision'],'operations':[{'type':'gain','db':-3}]}}})
 elif rid==101:
  assert m['result']['success']
  emit({'method':'item/agentMessage/delta','params':{'threadId':thread,'delta':'Preview ready.'}})
  emit({'method':'turn/completed','params':{'threadId':thread,'turn':{'id':'turn-1','status':'completed'}}})
""",
        encoding="utf-8",
    )
    import music_studio.studio.codex as module

    real_popen = module.subprocess.Popen
    arguments = []

    def spawn(command, **kwargs):
        arguments.extend(command)
        return real_popen([sys.executable, str(fake)], **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    bridge = CodexBridge(service, executable="protocol-fixture")
    try:
        connected = bridge.connect(project)
        assert bridge.connect(project) == connected
        thread = connected["thread"]
        bridge.message(thread, "Make a quieter preview")
        deadline = time.monotonic() + 5
        while bridge.events(thread)["busy"] and time.monotonic() < deadline:
            time.sleep(0.01)
        events = bridge.events(thread)
        assert not events["busy"]
        assert any(e.get("text") == "Preview ready." for e in events["events"])
        assert service.session(project)["candidates"][0]["actor"] == "codex"
        assert service.session(project)["active"] == "source"
        assert "features.shell_tool=false" in arguments
        assert "features.multi_agent=false" in arguments
        assert "mcp_servers={}" in arguments
        assert "model=" not in " ".join(arguments)
    finally:
        bridge.close()
