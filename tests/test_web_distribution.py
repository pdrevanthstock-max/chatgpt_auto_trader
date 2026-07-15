from pathlib import Path


def test_web_launcher_uses_one_python_runtime_for_setup_and_server():
    launcher = Path("run_web_app.bat").read_text(encoding="utf-8")

    assert '.venv\\Scripts\\python.exe' in launcher
    assert 'import fastapi, uvicorn' in launcher
    assert '-m pip install -r requirements.txt' in launcher
    assert '"%PYTHON%" -m uvicorn api.app:app' in launcher
