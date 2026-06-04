from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_start_batch_contains_dependency_port_and_pid_controls():
    start_file = ROOT / "src" / "start-dashboard.bat"

    contents = start_file.read_text(encoding="utf-8")

    assert start_file.exists()
    assert "BACKEND_PORT=8000" in contents
    assert "FRONTEND_PORT=5173" in contents
    assert "python -m venv" in contents
    assert "npm install" in contents
    assert "uvicorn" in contents
    assert "Start-Process" in contents
    assert ".dashboard-runtime" in contents
    assert "netstat -ano" in contents


def test_stop_batch_uses_pid_and_limited_port_fallback():
    stop_file = ROOT / "src" / "stop-dashboard.bat"

    contents = stop_file.read_text(encoding="utf-8")

    assert stop_file.exists()
    assert "taskkill /PID" in contents
    assert "netstat -ano" in contents
    assert "Get-CimInstance Win32_Process" in contents
    assert "Stop-Process" in contents
    assert "uvicorn|app.main" in contents
    assert "vite|node.*vite" in contents
