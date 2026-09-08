# cloudlabMcp

MCP server that provisions CloudLab labs/sandboxes. Tools: `login`,
`create_user`, `create_subscription`, `launch_subscription`, `provision_lab`,
`config_check`.

## 1. Setup (run once)

Requires Python 3.10+.

```powershell
# from the project folder
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

(macOS/Linux: use `python3 -m venv .venv` and `./.venv/bin/python`.)

## 2. Configure

Edit `.cursor/mcp.json` and set:

- the two paths (`command` and `args`) to **your** absolute path to
  `.venv\Scripts\python.exe` and `server.py`
- the `env` values (`CLOUDLAB_BASE_URL`, `CLOUDLAB_USERNAME`, ... ) for your
  CloudLab environment.

`CLOUDLAB_BASE_URL` must be reachable from this machine (e.g. the machine also
running CloudLab, or a reachable host).

## 3. Test (no editor needed)

```powershell
.\.venv\Scripts\python.exe test_client.py
```

Expected: it prints the connected tools and your `config_check` values. If you
see those, the server works.

## 4. Use in Cline / Cursor

- Add the same block from `.cursor/mcp.json` to your MCP config
  (Cline: `cline_mcp_settings.json`, Cursor: `.cursor/mcp.json`).
- Reload, confirm the server shows green with the tools.
- In **Agent** mode, say: **"Use cloudlabMcp provision_lab to create a lab."**

`provision_lab` runs the whole flow: login -> create user -> create lab ->
launch (retries every 30s while the lab is still being created).
