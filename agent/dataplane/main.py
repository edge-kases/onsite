import sys
import time
import shutil
import logging

from config import Config
from sync_client import SyncClient
from process_manager import ProcessManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dataplane")

AGENT_SCRIPT = "/app/agent/agent.py"
AGENT_ROLLBACK = "/app/agent/agent_rollback.py"
AGENT_NEW = "/app/agent/agent_new.py"


def main():
    config = Config.from_env()
    client = SyncClient(config.phylod_url)
    pm = ProcessManager()

    # -- INIT: start baked-in agent --
    logger.info("Starting initial agent...")
    pm.start(AGENT_SCRIPT)

    # Health check with retries (up to 3 attempts, 2s apart)
    healthy = False
    for attempt in range(3):
        time.sleep(2)
        healthy = pm.health_check(config.agent_port, config.health_check_timeout)
        if healthy:
            break
        logger.warning(f"Health check attempt {attempt+1} failed, retrying...")
    if not healthy:
        logger.error("Initial agent failed health check after 3 attempts. Exiting.")
        pm.stop()
        sys.exit(1)

    current_version = pm.get_version(config.agent_port)
    failed_version = None
    logger.info(f"Agent started: version={current_version}")

    # -- RUNNING LOOP --
    while True:
        time.sleep(config.sync_interval)

        # Runtime crash detection
        if not pm.is_running():
            logger.warning("Agent process died unexpectedly. Restarting...")
            pm.start(AGENT_SCRIPT)
            time.sleep(2)
            if pm.health_check(config.agent_port, config.health_check_timeout):
                current_version = pm.get_version(config.agent_port)
                logger.info(f"Agent restarted successfully: version={current_version}")
            else:
                logger.error("Agent restart failed. Will retry next cycle.")
            continue

        # Sync with phylod
        try:
            response = client.sync(
                agent_id=config.agent_id,
                tenant_id=config.tenant_id,
                current_version=current_version,
                health_status="healthy",
                auto_upgrade=config.auto_upgrade,
                failed_version=failed_version,
            )
            failed_version = None  # clear after successful report
        except Exception as e:
            logger.warning(f"Sync failed: {e}. Continuing with current agent.")
            continue

        if response["action"] == "none":
            logger.debug("No action needed.")
            continue

        # -- UPGRADE --
        target = response["target_version"]
        binary_url = response["binary_url"]
        logger.info(f"Upgrading: {current_version} -> {target}")

        # 1. Download new binary
        try:
            client.download_binary(binary_url, AGENT_NEW)
        except Exception as e:
            logger.error(f"Binary download failed: {e}. Skipping upgrade.")
            continue

        # 2. Stop current agent
        pm.stop(timeout=5)

        # 3. Backup current -> rollback
        shutil.copy2(AGENT_SCRIPT, AGENT_ROLLBACK)

        # 4. Replace with new
        shutil.move(AGENT_NEW, AGENT_SCRIPT)

        # 5. Start new agent
        pm.start(AGENT_SCRIPT)
        time.sleep(2)

        # 6. Health check new agent
        if pm.health_check(config.agent_port, config.health_check_timeout):
            current_version = pm.get_version(config.agent_port)
            logger.info(f"Upgrade SUCCESS: now on {current_version}")
        else:
            # ROLLBACK
            logger.error(f"Upgrade FAILED: {target} unhealthy. Rolling back...")
            pm.stop(timeout=5)
            shutil.copy2(AGENT_ROLLBACK, AGENT_SCRIPT)
            pm.start(AGENT_SCRIPT)
            time.sleep(2)

            if pm.health_check(config.agent_port, config.health_check_timeout):
                current_version = pm.get_version(config.agent_port)
                failed_version = target
                logger.info(f"Rollback SUCCESS: back on {current_version}. Will report {target} as failed.")
            else:
                logger.error("CRITICAL: Rollback also failed. Will retry next cycle.")


if __name__ == "__main__":
    main()
