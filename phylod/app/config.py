import os


class Settings:
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://phylo:phylo@localhost:5432/phylo")
    VERSIONS_DIR: str = os.environ.get("VERSIONS_DIR", "versions")
