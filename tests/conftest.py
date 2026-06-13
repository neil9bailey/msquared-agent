import os
import shutil
import tempfile
from pathlib import Path

import pytest


TEST_APP_HOME = Path(tempfile.mkdtemp(prefix="msquared-agent-tests-"))
os.environ.setdefault("MSQUARED_AGENT_HOME", str(TEST_APP_HOME))

from msquared_agent.env_loader import ENV_KEYS


@pytest.fixture(autouse=True)
def reset_runtime_data(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    data_dir = TEST_APP_HOME / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir = TEST_APP_HOME / "config"
    if config_dir.exists():
        shutil.rmtree(config_dir)
    env_file = TEST_APP_HOME / ".env"
    if env_file.exists():
        env_file.unlink()
    yield
