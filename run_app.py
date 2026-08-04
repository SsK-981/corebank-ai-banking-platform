"""Start CoreBank, the FastAPI agent, and Streamlit from one VS Code Run button."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
COREBANK_ROOT = ROOT / "corebank"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE_FILE = ROOT / ".env.example"


def ensure_env_file() -> None:
    if ENV_FILE.exists():
        return
    if not ENV_EXAMPLE_FILE.exists():
        raise RuntimeError("Could not find .env or .env.example")
    shutil.copyfile(ENV_EXAMPLE_FILE, ENV_FILE)
    print("Created .env from .env.example")


def start_process(
    name: str,
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[bytes]:
    print(f"Starting {name}...")
    return subprocess.Popen(command, cwd=cwd, env=env)


def url_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def wait_for_url(name: str, url: str, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if url_is_ready(url):
            print(f"{name} is ready.")
            return
        time.sleep(1)
    raise RuntimeError(f"{name} did not become ready at {url}")


def find_java_home() -> Path | None:
    configured = os.getenv("JAVA_HOME")
    if configured and (Path(configured) / "bin" / "java.exe").exists():
        return Path(configured)

    java_command = shutil.which("java")
    if java_command:
        return Path(java_command).resolve().parent.parent

    candidates = sorted(
        (Path.home() / ".jdks").glob("*/bin/java.exe"),
        reverse=True,
    )
    return candidates[0].parent.parent if candidates else None


def start_corebank() -> subprocess.Popen[bytes] | None:
    health_url = "http://127.0.0.1:8080/accounts/health"
    if url_is_ready(health_url):
        print("CoreBank is already running; reusing it.")
        return None

    java_home = find_java_home()
    if java_home is None:
        raise RuntimeError("Java was not found. Install JDK 21+ or configure JAVA_HOME.")

    wrapper = "mvnw.cmd" if os.name == "nt" else "./mvnw"
    child_env = os.environ.copy()
    child_env["JAVA_HOME"] = str(java_home)
    child_env["PATH"] = f"{java_home / 'bin'}{os.pathsep}{child_env.get('PATH', '')}"
    process = start_process(
        "CoreBank Spring Boot service",
        [str(COREBANK_ROOT / wrapper), "spring-boot:run"],
        cwd=COREBANK_ROOT,
        env=child_env,
    )
    wait_for_url("CoreBank", health_url)
    return process


def seed_corebank() -> None:
    print("Preparing deterministic CoreBank demo data...")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_corebank_demo.py")],
        cwd=ROOT,
        check=True,
    )


def stop_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    for process in reversed(processes):
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> int:
    ensure_env_file()
    load_dotenv(ENV_FILE, override=False)
    processes: list[subprocess.Popen[bytes]] = []

    try:
        if os.getenv("BANKING_DATA_SOURCE", "local").lower() == "corebank":
            corebank = start_corebank()
            if corebank is not None:
                processes.append(corebank)
            seed_corebank()

        backend = start_process(
            "FastAPI agent",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
        )
        processes.append(backend)
        wait_for_url("FastAPI", "http://127.0.0.1:8000/health/ready", timeout_seconds=45)

        frontend = start_process(
            "Streamlit chatbot",
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "frontend/app.py",
                "--server.address",
                "127.0.0.1",
                "--server.port",
                "8501",
            ],
        )
        processes.append(frontend)
        wait_for_url("Streamlit", "http://127.0.0.1:8501", timeout_seconds=45)

        print("\nCoreBank:    http://127.0.0.1:8080")
        print("FastAPI:     http://127.0.0.1:8000/docs")
        print("Chatbot UI:  http://127.0.0.1:8501")
        print("\nPress Ctrl+C to stop services started by this launcher.")
        if os.getenv("OPEN_BROWSER", "true").lower() in {"1", "true", "yes", "on"}:
            webbrowser.open("http://127.0.0.1:8501")

        while all(process.poll() is None for process in processes):
            time.sleep(1)
        return 1
    except KeyboardInterrupt:
        print("\nStopping platform...")
        return 0
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nStartup failed: {error}")
        return 1
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
