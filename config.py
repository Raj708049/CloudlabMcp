"""Configuration for the cloudlabMcp server.

All values are read from environment variables, which are supplied by the MCP
client (Cursor / Cline) through the "env" block in mcp.json. This keeps
secrets out of the source code.
"""

import os
from dataclasses import dataclass


@dataclass
class Config:
    base_url: str
    username: str
    password: str
    company_id: str
    team_id: str
    username_suffix: str
    plan_id: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            base_url=os.environ.get("CLOUDLAB_BASE_URL", "").rstrip("/"),
            username=os.environ.get("CLOUDLAB_USERNAME", ""),
            password=os.environ.get("CLOUDLAB_PASSWORD", ""),
            company_id=os.environ.get("CLOUDLAB_COMPANY_ID", ""),
            team_id=os.environ.get("CLOUDLAB_TEAM_ID", ""),
            username_suffix=os.environ.get("CLOUDLAB_USERNAME_SUFFIX", ""),
            plan_id=os.environ.get("CLOUDLAB_PLAN_ID", ""),
        )

    def apply(self, data: dict) -> None:
        """Apply config values from a dict (e.g. Smithery's per-request config).

        Accepts the camelCase keys used in smithery.yaml's configSchema and
        maps them onto this config object. Only non-empty values overwrite.
        """
        mapping = {
            "baseUrl": "base_url",
            "username": "username",
            "password": "password",
            "companyId": "company_id",
            "teamId": "team_id",
            "usernameSuffix": "username_suffix",
            "planId": "plan_id",
        }
        for key, attr in mapping.items():
            val = data.get(key)
            if val:
                if attr == "base_url":
                    val = str(val).rstrip("/")
                setattr(self, attr, val)

    def require(self, *fields: str) -> None:
        """Raise a clear error if any required config field is empty."""
        missing = [f for f in fields if not getattr(self, f)]
        if missing:
            raise ValueError(
                "Missing required CloudLab config: "
                + ", ".join(missing)
                + ". Set them in the mcp.json 'env' block."
            )


config = Config.from_env()
