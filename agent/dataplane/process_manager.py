import subprocess
import requests as http_requests


class ProcessManager:
    def __init__(self):
        self.process = None

    def start(self, script_path: str):
        self.process = subprocess.Popen(["python", script_path])

    def stop(self, timeout: int = 5) -> bool:
        if self.process is None:
            return True
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None
        return True

    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    def health_check(self, port: int, timeout: int) -> bool:
        try:
            resp = http_requests.get(f"http://localhost:{port}/healthz", timeout=timeout)
            return resp.status_code == 200
        except Exception:
            return False

    def get_version(self, port: int) -> str:
        try:
            resp = http_requests.get(f"http://localhost:{port}/healthz", timeout=3)
            return resp.json().get("version", "unknown")
        except Exception:
            return "unknown"
