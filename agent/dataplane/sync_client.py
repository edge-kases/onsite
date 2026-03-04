import requests


class SyncClient:
    def __init__(self, phylod_url: str):
        self.base_url = phylod_url.rstrip("/")

    def sync(self, agent_id, tenant_id, current_version, health_status, auto_upgrade, failed_version) -> dict:
        resp = requests.post(
            f"{self.base_url}/api/v1/agent/sync",
            json={
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "current_version": current_version,
                "health_status": health_status,
                "auto_upgrade": auto_upgrade,
                "failed_version": failed_version,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def download_binary(self, binary_url: str, dest_path: str):
        resp = requests.get(f"{self.base_url}{binary_url}", timeout=30)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(resp.content)
