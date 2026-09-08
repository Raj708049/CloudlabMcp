"""cloudlabMcp — MCP server that provisions/creates CloudLab labs & sandboxes.

Connection settings (base URL, credentials, ids) come from the mcp.json "env"
block and are loaded in config.py. API calls go through client.py.

Tools are added one per API. Run locally:
    python server.py
"""

import asyncio
import secrets
import string

import httpx
from mcp.server.mcpserver import MCPServer

from config import config


def _random_token(length: int = 8) -> str:
    """Lowercase alphanumeric token used to keep usernames unique."""
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _launch_not_ready(response) -> bool:
    """True if the launch response means 'not ready yet, retry'.

    The API returns HTTP 200 with an error body while the lab is still being
    created (e.g. code 1026 'Lab is under creation'). Treat those as retryable.
    """
    if not isinstance(response, dict):
        return False
    if str(response.get("ResponseStatus", "")).upper() != "ERROR":
        return False
    code = str(response.get("MessageCode", ""))
    detail = str(response.get("MessageDetail", "")).lower()
    retryable_codes = {"1026"}
    if code in retryable_codes:
        return True
    # Fallback: message text mentions the lab is still being created/provisioned.
    return any(k in detail for k in ("under creation", "creating", "in progress", "provision"))


def _random_password(length: int = 12) -> str:
    """Strong random password meeting CloudLab rules.

    Guarantees at least one uppercase, one lowercase, one digit and one
    special character, min length 8, and no spaces.
    """
    length = max(length, 8)
    specials = "!@#$%"
    # One guaranteed char from each required class.
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(specials),
    ]
    pool = string.ascii_letters + string.digits + specials
    rest = [secrets.choice(pool) for _ in range(length - len(required))]
    chars = required + rest
    # Shuffle so the required chars are not always at the front.
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)

# The name shows up in the MCP client UI.
mcp = MCPServer("cloudlabMcp")


@mcp.tool()
def config_check() -> dict:
    """Show which CloudLab connection settings are loaded (password masked).

    Use this to confirm the mcp.json 'env' values reached the server before
    calling the real provisioning tools.
    """
    return {
        "base_url": config.base_url or "(missing)",
        "username": config.username or "(missing)",
        "password": "***set***" if config.password else "(missing)",
        "company_id": config.company_id or "(missing)",
        "team_id": config.team_id or "(missing)",
        "username_suffix": config.username_suffix or "(missing)",
        "plan_id": config.plan_id or "(missing)",
    }


# ---------------------------------------------------------------------------
# CloudLab API tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def login() -> dict:
    """Authenticate to CloudLab (POST /v1/users/login) and store the session.

    Uses username/password from config. The session cookie is kept
    for subsequent tool calls. Returns the raw login response so you can see
    what the API sent back.
    """
    from client import client

    result = await client.login()
    return {"logged_in": True, "response": result}


@mcp.tool()
async def create_user(
    user_name: str = "",
    password: str = "",
    first_name: str = "",
    last_name: str = "",
    team_id: str = "",
) -> dict:
    """Create a CloudLab user (POST /v1/users). Logs in first if needed.

    All fields are optional and auto-filled from config when omitted:
      - user_name : defaults to '<username_suffix>.<random>.nuvepro.com'
      - password  : defaults to a random strong password
      - first_name/last_name : default to the configured username_suffix
      - team_id   : defaults to the configured team id
      - company_id is always taken from config.

    Returns the API response plus the generated credentials so you can
    capture the username/password of the created user.
    """
    from client import client

    suffix = config.username_suffix or "user"
    if not user_name:
        # userName must be a valid email address for the API to accept it.
        user_name = f"{suffix}.{_random_token()}@nuvepro.com"
    if not password:
        password = _random_password()
    if not first_name:
        first_name = suffix
    if not last_name:
        last_name = suffix
    if not team_id:
        team_id = config.team_id

    config.require("company_id")

    form = {
        "userName": user_name,
        "password": password,
        "firstName": first_name,
        "lastName": last_name,
        "companyId": config.company_id,
        "teamId": team_id,
    }

    response = await client.post("/v1/users", data=form)
    return {
        "created": True,
        "credentials": {"userName": user_name, "password": password},
        "response": response,
    }


@mcp.tool()
async def create_subscription(
    user_name: str,
    plan_id: str = "",
    team_id: str = "",
    provision_data: str = '{"#UID_NL_RESOURCE_TAGS": "VGVzdE5Q"}',
) -> dict:
    """Create a subscription / provision a lab for a user (POST /v1/subscriptions).

    Logs in first if needed and sends the X-CSRF-Token + session cookie.

    Args:
      user_name     : the user to subscribe (e.g. the one from create_user). Required.
      plan_id       : defaults to the configured plan id.
      team_id       : defaults to the configured team id.
      provision_data: a JSON string of provisioning tags; defaults to the sample.
    """
    from client import client

    if not plan_id:
        plan_id = config.plan_id
    if not team_id:
        team_id = config.team_id

    config.require("company_id")

    form = {
        "planId": plan_id,
        "userName": user_name,
        "companyId": config.company_id,
        "teamId": team_id,
        "provisionData": provision_data,
    }

    response = await client.post("/v1/subscriptions", data=form)
    return {"subscribed": True, "userName": user_name, "response": response}


@mcp.tool()
async def launch_subscription(
    subscription_id: str,
    retry_interval_seconds: int = 30,
    max_attempts: int = 10,
) -> dict:
    """Launch a subscription (POST /v1/subscriptions/launch) by subscriptionId.

    This endpoint is sometimes not ready immediately, so it is retried every
    `retry_interval_seconds` (default 30s) up to `max_attempts` times until it
    succeeds. Returns the launch info once available.

    Args:
      subscription_id        : the id returned by create_subscription. Required.
      retry_interval_seconds : wait between retries (default 30).
      max_attempts           : how many times to try (default 10 = ~5 min).
    """
    from client import client

    await client.ensure_login()
    last_info = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = await client.post(
                "/v1/subscriptions/launch",
                data={"subscriptionId": subscription_id},
            )
            last_info = response
            if not _launch_not_ready(response):
                return {
                    "launched": True,
                    "subscriptionId": subscription_id,
                    "attempts": attempt,
                    "response": response,
                }
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_info = str(exc)

        if attempt < max_attempts:
            await asyncio.sleep(retry_interval_seconds)

    return {
        "launched": False,
        "subscriptionId": subscription_id,
        "attempts": max_attempts,
        "error": "Launch not ready after all retries (lab still under creation "
        "or endpoint unavailable).",
        "last_response": last_info,
    }


@mcp.tool()
async def provision_lab(
    provision_data: str = '{"#UID_NL_RESOURCE_TAGS": "VGVzdE5Q"}',
    wait_for_launch: bool = True,
    retry_interval_seconds: int = 30,
    max_attempts: int = 10,
) -> dict:
    """One-shot: provision a full sandbox/lab for a new user.

    Runs the whole flow in order:
      1. login (get CSRF token + session)
      2. create_user (random email username + strong password)
      3. create_subscription (create the lab for that user)
      4. launch_subscription (launch; retries while 'under creation')

    Use this when a user says "I want a sandbox" / "create a lab". Returns the
    new user's credentials, the subscription id, and the launch info.

    Args:
      provision_data        : JSON string of provisioning tags (has a default).
      wait_for_launch        : if False, stop after creating the lab (skip launch).
      retry_interval_seconds : launch retry gap while lab is under creation.
      max_attempts           : launch retry count.
    """
    # 1 + 2: create the user (login happens automatically inside).
    user_result = await create_user()
    if not (isinstance(user_result.get("response"), dict)
            and user_result["response"].get("userid")):
        return {"provisioned": False, "step": "create_user", "detail": user_result}

    user_name = user_result["credentials"]["userName"]

    # 3: create the subscription / lab.
    sub_result = await create_subscription(
        user_name=user_name, provision_data=provision_data
    )
    sub_resp = sub_result.get("response")
    subscription_id = (
        sub_resp.get("subscriptionId") if isinstance(sub_resp, dict) else None
    )
    if not subscription_id:
        return {
            "provisioned": False,
            "step": "create_subscription",
            "credentials": user_result["credentials"],
            "detail": sub_result,
        }

    result = {
        "provisioned": True,
        "credentials": user_result["credentials"],
        "subscriptionId": subscription_id,
        "create_lab_response": sub_resp,
    }

    # 4: launch (get info), retrying while the lab is still under creation.
    if wait_for_launch:
        launch_result = await launch_subscription(
            subscription_id,
            retry_interval_seconds=retry_interval_seconds,
            max_attempts=max_attempts,
        )
        result["launch"] = launch_result
        result["provisioned"] = launch_result.get("launched", False)

    return result


# More API tools get added below, one per API you provide.


@mcp.custom_route("/.well-known/mcp/server-card.json", methods=["GET"])
async def server_card(request):
    """Static server card so Smithery can read metadata without scanning.

    Smithery's scanner sometimes fails to initialize the MCP session (422);
    advertising this endpoint lets it skip scanning and read tools directly.
    """
    from starlette.responses import JSONResponse

    tools = await mcp.list_tools()
    return JSONResponse(
        {
            "serverInfo": {"name": "cloudlabMcp", "version": "1.0.0"},
            "authentication": {"required": False},
            "tools": [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.input_schema,
                }
                for t in tools
            ],
            "resources": [],
            "prompts": [],
        }
    )


if __name__ == "__main__":
    import os

    # Transport is chosen via env var so the same file works both ways:
    #   MCP_TRANSPORT=stdio           -> local child process (Cline/Cursor, default)
    #   MCP_TRANSPORT=streamable-http -> hosted HTTP server (Smithery / any host)
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport in ("streamable-http", "sse"):
        import uvicorn

        from middleware import SmitheryConfigMiddleware

        host = os.environ.get("MCP_HOST", "0.0.0.0")
        # Smithery (and many PaaS) inject the port via PORT; fall back to MCP_PORT.
        port = int(os.environ.get("PORT") or os.environ.get("MCP_PORT") or "8000")

        # Build the HTTP app and attach middleware that reads Smithery's
        # per-request ?config=<base64 json> parameter.
        app = mcp.streamable_http_app()
        app.add_middleware(SmitheryConfigMiddleware)
        uvicorn.run(app, host=host, port=port)
    else:
        mcp.run()
