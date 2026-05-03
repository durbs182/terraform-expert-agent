# terraform-expert Copilot Agent

A GitHub Copilot agent that gives Copilot Chat full access to the
[HashiCorp Terraform MCP Server](https://github.com/hashicorp/terraform-mcp-server).

## Quick Start

```bash
# Install Python deps (Python 3.11+ required)
/opt/homebrew/bin/python3.11 -m venv .venv && source .venv/bin/activate
pip install -r agent/requirements.txt

# Configure secrets (gitignored)
cp .env.example .env   # then fill in TFE_TOKEN

# Start the proxy
python agent/server.py
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `TFE_TOKEN` | For workspace ops | HCP Terraform / TFE API token |
| `TFE_ADDRESS` | No | Self-hosted TFE URL (default: `https://app.terraform.io`) |
| `TERRAFORM_MCP_SERVER` | No | Absolute path to binary (falls back to PATH) |

## See Also

- [IMPLEMENTATION.md](IMPLEMENTATION.md) — full architecture and design notes
- [agent/instructions.md](agent/instructions.md) — agent system prompt
- [docs/module-acceleration.md](docs/module-acceleration.md) — accelerating enterprise Azure Terraform module creation with Copilot
