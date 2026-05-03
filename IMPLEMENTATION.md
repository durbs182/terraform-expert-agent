# Terraform Expert Copilot Agent — Implementation

## Overview

This repo implements the `terraform-expert` GitHub Copilot agent.

GitHub Copilot in this environment blocks direct MCP server connections. This agent
works around that constraint by running a **Python MCP proxy server** that:

1. Spawns the Terraform MCP server binary as a subprocess (stdio transport)
2. Discovers all available tools via the MCP `tools/list` call at startup
3. Re-exposes every discovered tool through the Python `mcp` library
4. Proxies all tool calls transparently to the Go binary
5. Injects `TFE_TOKEN` / `TFE_ADDRESS` from environment — never hardcoded

The Copilot agent is configured via `.github/copilot/agents/terraform-expert.yml`.
Its system prompt lives in `agent/instructions.md` and is referenced from the agent config.

---

## Architecture

```
Copilot Chat
    │  (tool calls over MCP)
    ▼
agent/server.py          ← Python MCP server (this repo)
    │  (subprocess stdio)
    ▼
terraform-mcp-server     ← HashiCorp Go binary (found on PATH or via TERRAFORM_MCP_SERVER env var)
    │
    ├── registry toolset     (public Terraform Registry)
    ├── registry-private     (HCP Terraform private registry)
    └── terraform toolset    (workspace / run management)
```

### Binary Resolution

The Python server locates the `terraform-mcp-server` binary in this order:

1. `TERRAFORM_MCP_SERVER` environment variable (absolute path)
2. `terraform-mcp-server` on `PATH` via `shutil.which`
3. Fatal error with clear instructions if not found

The binary path is **never hardcoded**.

---

## Repository Structure

```
terraform-expert-agent/
├── IMPLEMENTATION.md          ← this file
├── README.md                  ← setup and usage guide
├── .gitignore
├── .env.example               ← template for secrets (safe to commit)
├── agent/
│   ├── server.py              ← Python MCP proxy server (entry point)
│   ├── instructions.md        ← Copilot agent system prompt
│   └── requirements.txt       ← Python dependencies
└── .github/
    └── copilot/
        └── agents/
            └── terraform-expert.yml   ← Copilot agent registration
```

---

## Tool Surface (all toolsets enabled)

| Toolset            | Tools |
|--------------------|-------|
| `registry`         | `search_providers`, `get_provider_details`, `search_modules`, `get_module_details`, `get_latest_module_version`, `get_latest_provider_version`, `get_provider_capabilities` |
| `registry-private` | `search_private_modules`, `get_private_module_details`, `search_private_providers`, `get_private_provider_details` |
| `terraform`        | `list_terraform_orgs`, `list_terraform_projects`, `list_workspaces`, `get_workspace_details`, `create_workspace`, `update_workspace`, `list_workspace_variables`, `create_workspace_variable`, `update_workspace_variable`, `create_run`, `list_runs`, `get_run_details`, `get_plan_details`, `get_plan_logs`, `get_plan_json_output`, `get_apply_details`, `get_apply_logs`, `list_variable_sets`, `create_variable_set`, `create_variable_in_variable_set`, `delete_variable_in_variable_set`, `attach_variable_set_to_workspaces`, `detach_variable_set_from_workspaces`, `list_stacks`, `get_stack_details`, `list_workspace_policy_sets`, `attach_policy_set_to_workspaces`, `create_workspace_tags`, `read_workspace_tags`, `create_no_code_workspace`, `get_token_permissions` |

---

## Security Notes

- `TFE_TOKEN` **must never** appear in source code, logs, or agent responses
- Store real secrets in a gitignored `.env` file (see `.env.example`)
- The proxy sanitises error messages before surfacing them to the agent
- Destructive Terraform operations require **explicit user confirmation** before forwarding

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | Tested with 3.11 and 3.12 |
| `terraform-mcp-server` binary | Install to PATH or set `TERRAFORM_MCP_SERVER` env var |
| HCP Terraform / TFE token | Only needed for workspace/run operations |

### Installing the binary (macOS ARM64)

```bash
# Download from HashiCorp releases
curl -Lo /tmp/tf-mcp.zip \
  https://releases.hashicorp.com/terraform-mcp-server/0.5.2/terraform-mcp-server_0.5.2_darwin_arm64.zip
unzip /tmp/tf-mcp.zip -d /usr/local/bin/
chmod +x /usr/local/bin/terraform-mcp-server
```

Or place the binary anywhere and set `TERRAFORM_MCP_SERVER=/path/to/binary` in `.env`.

---

## Setup

```bash
# 1. Enter repo
cd terraform-expert-agent

# 2. Create virtualenv and install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r agent/requirements.txt

# 3. Configure secrets
cp .env.example .env
# Edit .env — set TFE_TOKEN and optionally TFE_ADDRESS / TERRAFORM_MCP_SERVER

# 4. Run the proxy server
python agent/server.py
```

---

## Registering the Copilot Agent

The agent definition is in `.github/copilot/agents/terraform-expert.yml`.
Commit this file to a GitHub repository. The agent will be available in
Copilot Chat as `@terraform-expert` for anyone with access to that repo.
