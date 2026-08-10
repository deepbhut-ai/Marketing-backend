from src.services.agent_starter import _resolve_agent_paths


def test_resolve_agent_paths_finds_local_agent_stub():
    agent_script, python_exe = _resolve_agent_paths()

    assert agent_script is not None
    assert agent_script.name == "agent.py"
    assert agent_script.parent.name == "local_agent"
    assert agent_script.exists()
    assert python_exe is None or python_exe.exists()
