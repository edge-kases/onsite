import os


class Config:
    def __init__(self, agent_id, tenant_id, phylod_url, auto_upgrade, sync_interval, health_check_timeout, agent_port):
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.phylod_url = phylod_url
        self.auto_upgrade = auto_upgrade
        self.sync_interval = sync_interval
        self.health_check_timeout = health_check_timeout
        self.agent_port = agent_port

    @classmethod
    def from_env(cls):
        return cls(
            agent_id=os.environ["AGENT_ID"],
            tenant_id=os.environ["TENANT_ID"],
            phylod_url=os.environ["PHYLOD_URL"],
            auto_upgrade=os.environ.get("AUTO_UPGRADE", "true").lower() == "true",
            sync_interval=int(os.environ.get("SYNC_INTERVAL", "10")),
            health_check_timeout=int(os.environ.get("HEALTH_CHECK_TIMEOUT", "5")),
            agent_port=int(os.environ.get("AGENT_PORT", "8080")),
        )
