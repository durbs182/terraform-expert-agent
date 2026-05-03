# Phase 1 — Module Catalogue Review: Detailed Instructions

## Purpose

This document provides step-by-step instructions for executing Phase 1 of the
[module acceleration process](module-acceleration.md). It is written so that a
**low-cost Copilot model** (e.g. GPT-4o mini or Claude Haiku) can follow it without
expert Terraform knowledge. Every step is explicit. Every output format is specified.

Do not skip steps. Do not infer what a step means. If a step cannot be completed,
record the reason and move to the next.

---

## Inputs Required Before Starting

You must have the following before beginning:

| Input | Where to find it |
|-------|-----------------|
| `TFC_ORG` | The HCP Terraform organisation name (e.g. `acme-corp`) |
| `TFE_TOKEN` | An HCP Terraform API token with read access to the private registry |
| GitHub access | A GitHub token or the `gh` CLI authenticated to read the module repos |

Set these as environment variables before running any commands:

```bash
export TFE_TOKEN="<your-token>"
export TFC_ORG="<your-org-name>"
export GH_TOKEN="<your-github-token>"   # or: gh auth login
```

---

## Step 1 — Catalogue All azurerm Modules

### What you are doing

Fetching the complete list of `azurerm` provider modules from the private TFC registry
and recording them in a table.

### Command

```bash
curl -s \
  -H "Authorization: Bearer $TFE_TOKEN" \
  "https://app.terraform.io/api/v2/organizations/$TFC_ORG/registry-modules?filter%5Bprovider%5D=azurerm&page%5Bsize%5D=100" \
  | jq -r '.data[] | [.attributes.name, .attributes["registry-name"], .attributes.provider, .attributes.status, (.attributes["vcs-repo"].identifier // "no-vcs")] | @tsv'
```

If there are more than 100 modules, paginate:

```bash
# Check if there are more pages
curl -s \
  -H "Authorization: Bearer $TFE_TOKEN" \
  "https://app.terraform.io/api/v2/organizations/$TFC_ORG/registry-modules?filter%5Bprovider%5D=azurerm&page%5Bsize%5D=100" \
  | jq '.meta.pagination'
```

Repeat the request with `page%5Bnumber%5D=2`, `3`, etc. until all pages are retrieved.

### Output — Master Catalogue Table

Record every module in this format. Save the table as `phase1-catalogue.md` in your
working directory.

```markdown
## Master Catalogue

| # | Module Name | Registry | Provider | Status | GitHub Repo |
|---|-------------|----------|----------|--------|-------------|
| 1 | storage-account | private | azurerm | setup_complete | org/tf-mod-storage-account |
| 2 | key-vault | private | azurerm | setup_complete | org/tf-mod-key-vault |
...
```

**Important:** If a module has `no-vcs` in the GitHub Repo column, flag it. You cannot
review source code for VCS-disconnected modules. Record `FLAGGED: no VCS connection`
and skip it in later steps.

---

## Step 2 — Classify Each Module

### What you are doing

For each module in the Master Catalogue, deciding whether it is an **Azure Service**
module or a **Utility** module. This classification determines whether it gets a deep
review.

### Classification Rules

Read the module name and description from the TFC registry. Apply these rules in order:

1. **Azure Service** — the module name maps directly to a specific Azure resource
   (e.g. `storage-account`, `key-vault`, `aks`, `sql-database`, `app-service`,
   `service-bus`, `event-hub`, `vnet`, `subnet`).

2. **Azure Service** — the module creates one primary `azurerm_*` resource and
   supporting resources for that single service (e.g. diagnostic settings, role
   assignments scoped to that resource).

3. **Utility** — the module name suggests shared logic: `naming`, `tags`, `policy`,
   `rbac`, `governance`, `baseline`, `common`, `shared`, `helpers`.

4. **Utility** — the module composes other modules (its `main.tf` contains `module`
   blocks calling other internal modules rather than `resource` blocks).

5. **Unknown** — if you cannot classify from the name and description alone, record
   `Unknown` and note what additional information is needed.

### Command to Get Module Description

```bash
curl -s \
  -H "Authorization: Bearer $TFE_TOKEN" \
  "https://app.terraform.io/api/v2/organizations/$TFC_ORG/registry-modules/private/$TFC_ORG/<MODULE_NAME>/azurerm" \
  | jq '.data.attributes | {name: .name, description: .description}'
```

### Output — Classification Column

Add a `Classification` column to the Master Catalogue table:

```markdown
| # | Module Name | ... | GitHub Repo | Classification |
|---|-------------|-----|-------------|----------------|
| 1 | storage-account | ... | org/tf-mod-storage | Azure Service |
| 2 | naming | ... | org/tf-mod-naming | Utility |
```

After classifying all modules, create two sub-lists:

```markdown
## Azure Service Modules (to be deep-reviewed)
1. storage-account (org/tf-mod-storage-account)
2. key-vault (org/tf-mod-key-vault)
...

## Utility Modules (not deep-reviewed in Phase 1)
1. naming (org/tf-mod-naming)
...
```

---

## Step 3 — Retrieve Source Code for Each Azure Service Module

### What you are doing

For each Azure Service module, fetching the Terraform source files from GitHub. You
need these specific files: `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`
(if present), and `README.md`.

### Command

Use the GitHub API to fetch each file. Replace `ORG/REPO` with the GitHub repo
identifier from the Master Catalogue.

```bash
# List all files at the root of the repo
gh api repos/ORG/REPO/contents/ --jq '.[].name'

# Fetch a specific file (outputs raw content)
gh api repos/ORG/REPO/contents/main.tf --jq '.content' | base64 -d

# Or use the raw URL directly
curl -s -H "Authorization: Bearer $GH_TOKEN" \
  "https://raw.githubusercontent.com/ORG/REPO/main/main.tf"
```

If the module files are in a subdirectory (common for monorepos), check:

```bash
gh api repos/ORG/REPO/contents/modules/ --jq '.[].name'
```

### What to Record

For each module, note which of these files exist:

```
[ ] main.tf
[ ] variables.tf
[ ] outputs.tf
[ ] versions.tf
[ ] README.md
[ ] examples/ directory
```

A missing file is itself a finding that will affect Q5 (file layout) scoring.

#### ⚠️ CRITICAL: File Naming Convention Check

**Terraform module best practice:** All module logic should be in `main.tf`. This is the
standard entry point that both practitioners and tools (Terraform validators, linters,
documentation generators) expect.

**If the module does NOT have a `main.tf`:** check the root directory for named .tf files
instead (e.g. `function.tf`, `aca.tf`, `storage.tf`, `networking.tf`, or any other
service-specific .tf file).

**Action:** Record which file(s) contain the primary resource definitions. If the module
uses named .tf files instead of `main.tf`, **flag this as a Q5 code quality deviation**.

**Example findings to record:**

```
Module: app-service
❌ DEVIATION FOUND: No main.tf. Primary resources in:
   - app-service.tf (lines 1-45)
   - monitoring.tf (lines 46-92)
   
Impact: Q5 (File Layout) = Partial/Fail
Reason: Non-standard layout violates Terraform module best practice.
        Module is harder to navigate and may confuse automation tools.
```

```
Module: key-vault
✓ STANDARD: Has main.tf with primary resource definitions.
Impact: Q5 (File Layout) = Pass
```

This deviation will be scored under **Q5 — File Layout** as part of the Code Quality
scorecard (Step 5).

#### ⚠️ CRITICAL: Inline Sub-Module Detection

**Context for this review:** In this company's module strategy, sub-modules are NOT reused
outside of the published modules they are defined in. Inline sub-modules are therefore
**acceptable** as internal implementation details — provided they are NOT duplicated across
multiple parent modules.

**When inline sub-modules are acceptable:**
- Sub-module logic is specific to ONE parent module only
- No other parent modules use the same sub-module
- Sub-module source path is local (`./modules/...`)

**When inline sub-modules should be flagged:**
- The same sub-module appears in MULTIPLE parent modules (sign of hidden reusability)
- Sub-module has generic logic that could benefit other teams (naming, tagging, RBAC patterns)
- Sub-module is complex enough to warrant independent testing/documentation
- Sub-module README/variables suggest it was designed for reuse

**Detection:** Search the module source code for `module` blocks in:
- `main.tf` (or the primary resource file if main.tf doesn't exist)
- Any .tf file that would normally contain resources

**What to look for:**

```hcl
# ACCEPTABLE PATTERN (in this context):
module "diagnostics" {
  source = "./modules/diagnostics"        # Local path, implementation detail
  parent_resource_id = azurerm_storage_account.this.id
  # Used ONLY by this parent module
}

# FLAG THIS PATTERN (duplicate reuse):
# Module "rbac" appears in BOTH storage-account.tf AND key-vault.tf
module "rbac" {
  source = "./modules/rbac"      # Same sub-module used in multiple places
  resource_type = var.service   # Generic logic → should be published
}

# ALWAYS USE PUBLISHED MODULES (not inline):
module "network_security" {
  source = "app.terraform.io/acme-corp/network-security/azurerm"
  version = "3.2.1"                                                    # Independent version
}
```

**Action:** Record inline sub-modules found and check for reuse patterns.

**Example findings to record:**

```
Module: storage-account
✓ ACCEPTABLE: Inline sub-modules detected (internal use only):
   - main.tf:15-18:  module "diagnostics" { source = "./modules/diagnostics" }
   - main.tf:20-25:  module "monitoring" { source = "./modules/monitoring" }
   
Assessment: Each sub-module appears ONLY in this parent module.
           No reuse detected across other modules in catalogue.
Impact: Q5 (File Layout) = Pass
Reason: Internal composition is acceptable; no duplication across modules.
```

```
Module: app-service
❌ FLAG: Inline sub-modules with reuse pattern detected:
   - main.tf:12-16:  module "rbac" { source = "./modules/rbac" }
   - ALSO FOUND IN: key-vault module (same rbac sub-module)
   
Assessment: "rbac" sub-module appears in MULTIPLE parent modules.
           Suggests either: (a) hidden reusability, or (b) duplicate code.
Impact: Q2 (Variable Completeness) / Q5 (File Layout) = Partial
Reason: Generic logic across multiple modules should be published separately
        to the registry OR consolidated into a shared utility module.
```

```
Module: networking
✓ ACCEPTABLE: Uses published registry modules (best practice):
   - Example: module "azure_firewall" { source = "app.terraform.io/acme-corp/firewall/azurerm", version = "1.5.0" }
Impact: Q5 (File Layout) = Pass
```

This finding will be recorded as a **Q2 (Variable Completeness)** or **Q5 (File Layout)** issue
in the Code Quality scorecard (Step 5), depending on the reuse pattern and architectural
significance.

---

## Step 4 — Score Each Module Against the Security Controls Scorecard

### What you are doing

Reading the fetched source files and evaluating each security control. Record a score
for every control for every module. Use exactly these scores:

- **Pass** — the control is fully implemented
- **Partial** — the control is partially implemented (a variable exists but no default
  or validation; or a resource exists but is optional when it should be required)
- **Fail** — the control is absent or actively misconfigured
- **N/A** — the control is architecturally irrelevant to this specific service (you
  must write a one-line justification for every N/A)

### ⚠️ CRITICAL: Evidence Requirements

**For EVERY score, you MUST record evidence.** Do not guess. Do not assume.

- **Quote exact line numbers** from source code (e.g. "main.tf:42")
- **Quote 2–3 lines of code** showing the pattern you found (or NOT FOUND)
- **If you cannot find the pattern, write "NOT FOUND IN FILES" and mark the criterion Fail/N/A**

**Example:**

```
S1 — Network Isolation: PARTIAL
Evidence: main.tf:28-30
  network_rules {
    default_action = "Allow"    ← Problem: defaults to Allow, not Deny
  }
variable "allowed_ip_ranges" is not defined — caller cannot restrict access.
```

**Failure mode to avoid:** Making up evidence. If you don't see `network_rules`, don't claim it exists.

### S1 — Network Isolation

**Question:** Does the module restrict network access by default?

**FILE SCOPE:** Search ALL `.tf` files (not just `main.tf`). Resource definitions may be in
`main.tf`, `networking.tf`, `security.tf`, or any named .tf file. Variables are in `variables.tf`.

**If main.tf does not exist:** Search for files named: `storage.tf`, `network*.tf`, `security*.tf`,
or any .tf file containing the primary resource definition (identified in Step 3).

**What to look for:**

- Look for any of: `network_rules`, `network_acls`, `ip_rules`, `virtual_network_subnet_ids`,
  `service_endpoints`, `subnet_id`, `vnet_integration`, `network_profile`
- Specifically search for `default_action = "Deny"` or `default_action = "Allow"`

**CONCRETE EXAMPLES (what to search for):**

```hcl
# PASS pattern:
resource "azurerm_storage_account" "this" {
  network_rules {
    default_action             = "Deny"  ← Hardcoded restriction
    bypass                     = ["AzureServices"]
  }
}

# FAIL pattern:
# File has NO network_rules block at all, OR:
network_rules {
  default_action = "Allow"   ← Open by default
}
```

**Scoring:**

| Finding | Score |
|---------|-------|
| Network rules block with `default_action = "Deny"` hardcoded | Pass |
| Network rules block exists but `default_action = "Allow"` by default | Partial |
| Variable to set subnet IDs / IP rules exists but defaults to empty (no restriction) | Partial |
| No `network_rules` block found in ANY .tf file (NOT FOUND) | Fail |

**Record your evidence:** Filename + line number + 2–3 lines of code.

---

### S2 — Private Endpoints

**Question:** Does the module support or create private endpoints?

**FILE SCOPE:** Search ALL `.tf` files. Private endpoint resources may be in `main.tf`,
`networking.tf`, `private-endpoints.tf`, or any named .tf file. Variables are in `variables.tf`.

**If main.tf does not exist:** Search for files named: `network*.tf`, `endpoint*.tf`,
`private*.tf`, or any .tf file containing the primary resource definition.

**EXACT SEARCH PATTERN:**

Search ALL `.tf` files line-by-line for: `azurerm_private_endpoint`

In `variables.tf`, search for ANY variable name containing:
  - `"private_endpoint"` (exact substring)
  - `"private"` AND `"endpoint"` (both must appear in name)

**CONCRETE EXAMPLES:**

```hcl
# PASS pattern (resource):
resource "azurerm_private_endpoint" "this" {
  name          = "pe-storage"
  ...
}

# PASS pattern (split file example):
# networking.tf:
resource "azurerm_private_endpoint" "storage" {
  ...
}

# PARTIAL pattern:
variable "private_endpoint_subnet_id" {
  type    = string
  default = ""    ← Optional, defaults to empty (no endpoint created)
}

# FAIL pattern:
# No azurerm_private_endpoint resource in ANY .tf file
# No variable with "private_endpoint" in the name
```

**Scoring:**

| Finding | Score |
|---------|-------|
| `azurerm_private_endpoint` resource created in module (found in any .tf file) | Pass |
| Variable `private_endpoint_subnet_id` or similar exists AND is used | Pass |
| Variable exists in variables.tf BUT NOT used in any resource file (defined but ignored) | Partial |
| Variable exists AND optional (has default value) | Partial |
| No private endpoint support found in ANY .tf file (NOT FOUND) | Fail |
| Service is internal-only by architecture (e.g. VNet-internal load balancer) | N/A — justify |

**Record your evidence:** Filename + line numbers + exact variable/resource names found.

---

### S3 — Public Access Blocked

**Question:** Is public network access disabled by default?

**FILE SCOPE:** Search ALL `.tf` files (security, main, networking, or any named .tf file).
Variables are in `variables.tf`.

**If main.tf does not exist:** Search for files named: `security*.tf`, `main*.tf`, `storage.tf`,
or any .tf file containing the primary resource definition.

**What to look for:**

- `public_network_access_enabled`
- `allow_blob_public_access`, `enable_https_traffic_only`
- `public_ip_address_id` (presence of public IP)
- Variables that control public access and their `default` values

**Scoring:**

| Finding | Score |
|---------|-------|
| `public_network_access_enabled = false` hardcoded in ANY .tf file | Pass |
| Variable exists with `default = false` AND a `validation` block preventing `true` | Pass |
| Variable exists with `default = false` but no validation (caller can override to `true`) | Partial |
| Variable exists with `default = true` | Fail |
| No variable — public access controlled by network rules only | Partial (document the mitigation) |

**Record your evidence:** Filename + line number + exact code pattern found.

---

### S4 — Managed Identity

**Question:** Does the module configure a managed identity for the resource?

**FILE SCOPE:** Search ALL `.tf` files. The `identity` block may be in `main.tf`, `identity.tf`,
`auth.tf`, or any named .tf file. Variables are in `variables.tf`.

**If main.tf does not exist:** Search for files named: `identity*.tf`, `auth*.tf`, `security*.tf`,
or any .tf file containing the primary resource definition.

**What to look for:**

- `identity` block inside the primary resource (in any .tf file)
- `type = "SystemAssigned"` or `type = "UserAssigned"` or `type = "SystemAssigned, UserAssigned"`
- Variables: `identity_type`, `user_assigned_identity_ids`

**What to look for that indicates reliance on secrets instead:**

- Variables named `connection_string`, `primary_access_key`, `admin_password` being
  passed to other resources or outputs (not just stored in Key Vault)

**Scoring:**

| Finding | Score |
|---------|-------|
| `identity` block present in ANY .tf file, system-assigned by default | Pass |
| `identity` block present but only via optional variable (default = no identity) | Partial |
| No `identity` block found in ANY .tf file | Fail |
| Service does not support managed identity (e.g. some legacy services) | N/A — justify |

**Record your evidence:** Filename + line number + identity block code.

---

### S5 — Key Vault Integration

**Question:** Are secrets stored in or referenced from Azure Key Vault?

**FILE SCOPE:** Search ALL `.tf` files and `outputs.tf`. Key Vault integration may be in
`main.tf`, `security.tf`, `vault.tf`, `secrets.tf`, or any named .tf file.

**If main.tf does not exist:** Search for files named: `vault*.tf`, `secret*.tf`, `security*.tf`,
or any .tf file containing the primary resource definition.

**What to look for in ALL .tf files and outputs.tf:**

- `azurerm_key_vault_secret` resource that writes generated secrets to Key Vault
- Variables accepting `key_vault_id` or `key_vault_secret_id`
- Outputs that expose plaintext secrets (connection strings, access keys, passwords)
  WITHOUT `sensitive = true`
- `@Microsoft.KeyVault(...)` reference patterns in variable descriptions

**Scoring:**

| Finding | Score |
|---------|-------|
| Module writes generated secrets to Key Vault using `azurerm_key_vault_secret` | Pass |
| Module accepts `key_vault_id` and writes secrets there | Pass |
| Outputs expose sensitive values but with `sensitive = true` (terraform protects them) | Partial |
| Outputs expose plaintext secrets without `sensitive = true` | Fail |
| Module generates no secrets (e.g. a VNet — nothing to store) | N/A — justify |

**Record your evidence.**

---

## Step 5 — Score Each Module Against the Code Quality Scorecard

### Q1 — Variable Naming

**What to check in `variables.tf`:**

1. Are all variable names in `snake_case`? (no camelCase, no hyphens, no dots)
2. Do boolean variables start with `enable_`?
3. Are names self-explanatory without needing comments? (e.g. `resource_group_name`
   not `rg`)

**Score:**
- **Pass**: All variables snake_case, booleans use `enable_` prefix, no unexplained abbreviations
- **Partial**: Mostly snake_case but 1–3 exceptions; or booleans inconsistently named
- **Fail**: Mixed conventions throughout, or systematic use of abbreviated/unclear names

---

### Q2 — Variable Completeness

**What to check in `variables.tf`:**

For every `variable` block, verify:
1. `type` is set (not missing)
2. `description` is set and not empty
3. Either `default` is set OR the variable is intentionally required (no default = required)

**Score:**
- **Pass**: Every variable has `type` and `description`
- **Partial**: Up to 20% of variables missing `description` or `type`
- **Fail**: More than 20% of variables missing `description` or `type`, or `type = any` used

---

### Q3 — Validation Blocks

**What to check in `variables.tf`:**

Find every `string` variable that accepts a fixed set of values. Common examples:
- SKU tiers: `"Standard"`, `"Premium"`, `"Basic"`
- Replication types: `"LRS"`, `"GRS"`, `"ZRS"`
- TLS versions: `"TLS1_0"`, `"TLS1_1"`, `"TLS1_2"`
- Access tiers: `"Hot"`, `"Cool"`, `"Archive"`

For each such variable, check whether a `validation` block is present.

**Score:**
- **Pass**: All enum-accepting string variables have `validation` blocks with meaningful `error_message`
- **Partial**: Some enum variables have validation, others do not
- **Fail**: No enum variables have validation blocks

---

### Q4 — Output Completeness

**What to check in `outputs.tf`:**

1. Is there an output for the `id` of every primary resource?
2. Is there an output for the `name` of every primary resource?
3. Are connection endpoints (FQDN, endpoint URL) exported?
4. Are any sensitive values (access keys, connection strings, passwords) exported
   WITHOUT `sensitive = true`?

**Score:**
- **Pass**: `id` and `name` exported for all primary resources; no sensitive values without `sensitive = true`
- **Partial**: `id` exported but `name` missing, or sensitive values marked `sensitive = true` but not in Key Vault
- **Fail**: `id` missing, or sensitive values exported in plaintext

---

### Q5 — File Layout

**What to check:**

Look at the file list retrieved in Step 3. Check for:
- **Primary resource file:** `main.tf` OR named .tf file (storage.tf, aca.tf, etc.) identified in Step 3
- **Variables file:** `variables.tf` (must exist)
- **Outputs file:** `outputs.tf` (must exist)
- **Versions file:** `versions.tf` (recommended) OR `terraform {}` block in primary resource file

| Expected file | Purpose |
|---------------|---------|
| Primary resource file (main.tf, storage.tf, aca.tf, or other) | Resource definitions only. No variable declarations. No output declarations. |
| `variables.tf` | Variable declarations only. No resource blocks. |
| `outputs.tf` | Output declarations only. No resource blocks. |
| `versions.tf` (or `terraform {}` in primary resource file) | `terraform {}` block with `required_version` and `required_providers`. Preferred: separate file. |

**Score:**
- **Pass**: All three core files present (primary resource, variables.tf, outputs.tf) and used for their correct purpose
- **Partial**: All core files present but `terraform {}` block mixed into primary resource file, or minor mixing of concerns
- **Fail**: Core files missing, or variable/output declarations mixed into primary resource file

---

### Q6 — Provider Version Pin

**What to check in `versions.tf` (or primary resource file if `versions.tf` is absent):**

Search ALL `.tf` files for the `required_providers` block. If versions.tf doesn't exist,
search the primary resource file (main.tf, storage.tf, aca.tf, etc. identified in Step 3).
For the `azurerm` provider, check the `version` value.

| Pattern found | Score |
|---------------|-------|
| `version = "~> 3.90"` (minor pin) or `version = "= 3.90.0"` (exact pin) | Pass |
| `version = ">= 3.90.0, < 4.0.0"` (bounded range) | Pass |
| `version = "~> 3.0"` (major only — allows any 3.x, including breaking minor changes) | Partial |
| `version = ">= 3.0"` (unbounded) | Fail |
| No `required_providers` block found in ANY .tf file | Fail |

---

### Q7 — Tagging

**What to check in `variables.tf` and primary resource file (main.tf or named .tf):**

1. Is there a `variable "tags"` with `type = map(string)` in variables.tf?
2. In the primary resource file, is there a `locals` block that merges the caller's `var.tags` with
   module-required tags?
3. Are the merged tags (`local.tags`) applied to every resource that supports a `tags`
   argument?

**Score:**
- **Pass**: `tags` variable present, merged in `locals`, applied to all taggable resources
- **Partial**: `tags` variable present and passed through, but not merged with required tags; or not applied to all resources
- **Fail**: No `tags` variable, or tags hardcoded, or caller tags silently ignored

---

### Q8 — for_each / dynamic Usage

**What to check in primary resource file (main.tf or named .tf):**

Search for `count = ` in the primary resource file. For every `count =` found:
- If it controls whether an entire optional sub-resource block is created (e.g.
  `count = var.enable_diagnostic_settings ? 1 : 0`), this is a **Fail** (should use
  `dynamic` block or separate `for_each` resource).
- If it controls scaling of identical resources (e.g. `count = var.node_count`), this
  is acceptable.

Also check for `for_each` and `dynamic` usage — their presence is positive signal.

**Score:**
- **Pass**: No `count` used for optional boolean resource creation; `dynamic` blocks used instead
- **Partial**: `count` used for optional resources in 1–2 places; rest uses `dynamic`
- **Fail**: `count = X ? 1 : 0` pattern used throughout for optional sub-resources

---

## Step 6 — Score Each Module Against the README Scorecard

Open `README.md` for each module. Score each criterion below.

### R1 — README Present

Does `README.md` exist? **Pass** = yes. **Fail** = no. (Skip R2–R7 if R1 is Fail.)

---

### R2 — Description Accurate

Read the first paragraph of the README. Then look at the primary resource file (main.tf or
named .tf file identified in Step 3) and identify what resources are actually created.

**Pass**: The description accurately names the Azure service and what the module creates.
**Fail**: The description refers to a different service, is empty, or is clearly copy-pasted
from another module (check for mismatched service names).

---

### R3 — Inputs Table Accurate

Find the inputs/variables table in the README. Compare it against `variables.tf` (or any
file containing variable declarations — search all .tf files).

Check:
1. Is every variable in `variables.tf` listed in the README?
2. Are the types correct?
3. Are `required` / `optional` indicators correct (a variable with a `default` is optional)?

**Pass**: All variables present with correct types and required/optional status.
**Partial**: Up to 20% of variables missing or have wrong type/required status.
**Fail**: More than 20% wrong, or no inputs table at all.

---

### R4 — Outputs Table Accurate

Find the outputs table in the README. Compare it against `outputs.tf` (or any file
containing output declarations — search all .tf files).

Check:
1. Is every output in `outputs.tf` listed in the README?
2. Are descriptions accurate?

**Pass**: All outputs listed with accurate descriptions.
**Partial**: Some outputs missing or descriptions wrong.
**Fail**: No outputs table, or outputs listed that don't exist in outputs files.

---

### R5 — Usage Example Present

Search the README for a `module "..."` block or a `hcl` code block showing how to
call the module.

**Pass**: At least one complete `module` block example is present.
**Fail**: No usage example.

---

### R6 — Usage Example Accurate

Read the usage example. Check it against `variables.tf` (or any file with variables):

1. Does the `source` path look correct for the TFC private registry format?
   (expected: `app.terraform.io/ORG/MODULE_NAME/azurerm`)
2. Are all **required** variables (those without a `default`) included in the example?
3. Are the variable names exactly as defined in variable files? (look for typos,
   renamed variables that weren't updated in the README)
4. Would a user be able to copy-paste the example and `terraform init` without errors
   (ignoring real values like subscription IDs)?

**Pass**: Source path correct, all required variables present, all variable names match.
**Partial**: Minor issues — 1–2 variable names wrong, or a non-critical required variable missing.
**Fail**: Source path wrong, most required variables missing, or variable names don't match declared variables.

---

### R7 — Security Controls Documented

Search the README for any section covering security. Look for:

- A "Security Controls" or "Security" section
- Mention of private endpoints, network rules, managed identity, or Key Vault
- Explanation of what the module enforces and what the caller must configure

**Pass**: Dedicated security section explaining enforced controls and caller responsibilities.
**Partial**: Security mentioned inline but no dedicated section; or partial coverage.
**Fail**: No mention of security posture anywhere in the README.

---

## Step 7 — Compile the Module Scorecard

For each Azure Service module, produce a scorecard table:

```markdown
### Module: storage-account
**Repo:** org/tf-mod-storage-account
**Classification:** Azure Service

#### Security Controls
| Control | Score | Evidence |
|---------|-------|---------|
| S1 Network isolation | Pass | `default_action = "Deny"` hardcoded in `network_rules` block (main.tf:42) |
| S2 Private endpoints | Partial | Variable `private_endpoint_subnet_id` exists but endpoint creation is optional |
| S3 Public access blocked | Pass | `public_network_access_enabled = false` hardcoded (main.tf:28) |
| S4 Managed identity | Pass | `identity { type = "SystemAssigned" }` in resource block (main.tf:15) |
| S5 Key Vault integration | Fail | Output `primary_access_key` exposed without `sensitive = true` (outputs.tf:18) |

#### Code Quality
| Dimension | Score | Evidence |
|-----------|-------|---------|
| Q1 Variable naming | Pass | All snake_case, booleans use enable_ prefix |
| Q2 Variable completeness | Partial | 3 of 18 variables missing description |
| Q3 Validation blocks | Fail | account_tier and account_replication_type have no validation |
| Q4 Output completeness | Partial | id and name present; primary_access_key missing sensitive=true |
| Q5 File layout | Pass | All 4 files present, correctly scoped |
| Q6 Provider version pin | Pass | azurerm ~> 3.90 |
| Q7 Tagging | Pass | tags merged in locals, applied to all resources |
| Q8 for_each/dynamic | Pass | No count-based optional resources |

#### README Quality
| Dimension | Score | Evidence |
|-----------|-------|---------|
| R1 README present | Pass | README.md exists |
| R2 Description accurate | Pass | Correctly describes Azure Storage Account creation |
| R3 Inputs table accurate | Partial | 2 variables missing from table |
| R4 Outputs table accurate | Fail | Lists `connection_string` output that doesn't exist in outputs.tf |
| R5 Usage example present | Pass | Example module block present |
| R6 Usage example accurate | Partial | Example uses `account_kind` which was renamed to `account_tier` |
| R7 Security controls documented | Fail | No security section in README |

#### Summary
- **Critical findings:** S5 (secrets exposed), R4 (stale outputs table), R6 (wrong variable name in example)
- **Recommended priority:** High — secrets handling must be fixed before this module is used in new projects
```

Repeat for every Azure Service module.

---

## Step 8 — Aggregate Results and Derive the Canonical Standard

### 8a. Cross-Module Summary Table

Create a summary table showing all modules and their scores at a glance:

```markdown
## Phase 1 Summary

| Module | S1 | S2 | S3 | S4 | S5 | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | R1 | R2 | R3 | R4 | R5 | R6 | R7 |
|--------|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|
| storage-account | Pass | Partial | Pass | Pass | Fail | Pass | Partial | Fail | Partial | Pass | Pass | Pass | Pass | Pass | Pass | Partial | Fail | Pass | Partial | Fail |
| key-vault | ... |
```

Use these abbreviations: `P` = Pass, `Pa` = Partial, `F` = Fail, `-` = N/A

---

### 8b. Pattern Analysis

For each scored dimension, identify:

1. **The dominant pattern** (what ≥ 75% of modules do)
2. **The best implementation** (the highest-quality example found, even if not the most common)
3. **Anti-patterns** (patterns that appear in at least one module and should be explicitly avoided)

Document this analysis dimension by dimension. Example format:

```markdown
### Q3 — Validation Blocks

**Dominant pattern:** 60% of modules have no validation blocks on enum variables.
**Best implementation found in:** `key-vault` module — all SKU and tier variables
  have validation blocks with clear error messages referencing permitted values.
**Anti-patterns identified:**
  - Using validation to check for non-empty string (`length(var.x) > 0`) without
    also checking against permitted values — seen in `sql-database` module
  - No validation at all on TLS version variable — seen in 4 modules

**Canonical standard decision:** All string variables accepting a fixed set of values
MUST have a validation block listing the permitted values and citing the policy reason
in the error_message.
```

---

### 8c. Security Gap Summary

Produce a dedicated section listing every **Fail** finding across all modules in the
security controls category (S1–S5), grouped by control:

```markdown
## Security Gap Summary

### S5 — Key Vault Integration (most critical)
Modules exposing secrets without Key Vault:
- storage-account: `primary_access_key` output without sensitive=true
- sql-database: `admin_password` variable with no Key Vault integration
- redis-cache: connection string output in plaintext

**Required action before these modules are used:** Remediate S5 findings or document
accepted risk with sign-off.

### S2 — Private Endpoints
Modules with no private endpoint support:
- app-service: no private endpoint variable
- service-bus: endpoint creation optional with insecure default
...
```

---

### 8d. Canonical Standard Output

Produce the final canonical standard document. This is the output that Phase 2–6 of the
module acceleration process will reference.

```markdown
## Canonical Standard (derived from Phase 1 review)

**Review date:** <date>
**Modules reviewed:** <N>
**Modules with all security controls passing:** <N>

### Naming
- Variables: snake_case, no abbreviations, `enable_` prefix for booleans
- Outputs: `<resource_type>_<attribute>` (e.g. `storage_account_id`, `key_vault_uri`)
- Resources: use the azurerm resource type name as the local label (e.g. `resource "azurerm_storage_account" "this"`)

### Security Defaults (NON-NEGOTIABLE for all new modules)
- S1: Network rules block with `default_action = "Deny"` is required for all applicable resources
- S2: Private endpoint support is required; endpoint creation should be enabled by default
- S3: `public_network_access_enabled = false` must be hardcoded or default to false with validation blocking true
- S4: `identity { type = "SystemAssigned" }` must be present by default for all applicable resources
- S5: No output may expose a secret without `sensitive = true`; Key Vault write-back required for all generated secrets

### Code Structure
- Required files: main.tf, variables.tf, outputs.tf, versions.tf
- `terraform {}` block MUST be in versions.tf, not main.tf
- azurerm version pin: `~> 3.90` (update this value when the org standard changes)
- Optional sub-resources: `dynamic` blocks — never `count = var.enable_x ? 1 : 0`
- Tag merging: `locals { tags = merge({ managed_by = "terraform", module = "<name>" }, var.tags) }`

### README Requirements
- Must have: Description, Security Controls section, Inputs table, Outputs table,
  Usage example, Threat Model link
- Inputs and outputs tables must be regenerated (not hand-maintained) using terraform-docs

### Anti-Patterns (do not repeat in new modules)
1. `count = var.enable_x ? 1 : 0` for optional sub-resources
2. Enum string variables without validation blocks
3. `version = "~> 3.0"` major-only provider pin
4. Sensitive outputs without `sensitive = true`
5. README inputs table maintained by hand (gets stale — use terraform-docs)
6. No `tags` variable, or `var.tags` passed through without merging required internal tags
```

---

## Step 9 — Save and Share Output

Save the completed review as two files:

1. **`phase1-results/catalogue-and-scores.md`** — the Master Catalogue, classifications,
   and all individual module scorecards (Steps 1–7 output)
2. **`phase1-results/canonical-standard.md`** — the canonical standard derived in Step 8
   (this is the input to Phase 2 onwards)

These files are inputs for the next phases of the module acceleration process. Share
them with the team before proceeding to Phase 2.

---

## Scoring Quick Reference

| Score | Meaning |
|-------|---------|
| **Pass** | Fully implemented. No action needed. |
| **Partial** | Partially implemented. Note what is missing. Action recommended before using module as reference. |
| **Fail** | Not implemented or misconfigured. Action required. Do not use this module as a reference pattern. |
| **N/A** | Not applicable to this service type. Must include a one-line justification. |

## Criteria Quick Reference

| ID | Name | Key question |
|----|------|-------------|
| S1 | Network isolation | Is network access restricted by default? |
| S2 | Private endpoints | Is private endpoint support present? |
| S3 | Public access blocked | Is public access off by default? |
| S4 | Managed identity | Does the resource have an identity block? |
| S5 | Key Vault integration | Are secrets stored in / referenced from Key Vault? |
| Q1 | Variable naming | Consistent snake_case with enable_ for booleans? |
| Q2 | Variable completeness | Every variable has type and description? |
| Q3 | Validation blocks | Enum variables have validation blocks? |
| Q4 | Output completeness | id, name exported; no plaintext secrets? |
| Q5 | File layout | Four required files, correctly scoped? |
| Q6 | Provider version pin | azurerm pinned to minor version? |
| Q7 | Tagging | tags merged with required internal tags? |
| Q8 | for_each/dynamic | No count-based optional resources? |
| R1 | README present | README.md exists? |
| R2 | Description accurate | Describes the right service? |
| R3 | Inputs table accurate | All variables listed correctly? |
| R4 | Outputs table accurate | All outputs listed correctly? |
| R5 | Usage example present | At least one module block example? |
| R6 | Usage example accurate | Source, variable names, required vars correct? |
| R7 | Security controls documented | Security section in README? |

---

## 🚨 Cheap Model Failure Modes & How to Avoid Them

This section documents the most common mistakes low-cost models make and how to prevent them.

### Failure 1: Hallucinating Evidence ("Making up code")

**What happens:** Model claims to find a pattern that doesn't exist in the module.

Example error:
```
S1 - Network Isolation: PASS
Evidence: main.tf has network_rules with default_action = "Deny"
[But when you check main.tf, there is NO network_rules block at all]
```

**Prevention:**

✅ **ALWAYS quote the exact line number and code.**

❌ Bad: "The module has network isolation."
✅ Good: "main.tf:42-45 shows: `network_rules { default_action = "Deny" }`"

❌ Bad: "I found a private endpoint resource."
✅ Good: "main.tf:18: `resource "azurerm_private_endpoint" "this" {`"

**If you cannot find the pattern, say so explicitly:**

```
S2 - Private Endpoints: FAIL
Evidence: Searched entire main.tf for "azurerm_private_endpoint" — NOT FOUND.
Searched variables.tf for variable names containing "private_endpoint" — NOT FOUND.
Conclusion: No private endpoint support.
```

---

### Failure 2: Incomplete File Search ("Giving up early")

**What happens:** Model checks only the first few lines or gives up searching.

Example error:
```
Q1 - Variable Naming: PASS
"I scanned variables.tf and all variables look good."
[But variables.tf is 200 lines long, model only scanned first 50]
```

**Prevention:**

✅ **Report a TOTAL COUNT.**

❌ Bad: "Variables look like snake_case."
✅ Good: "Checked all 18 variables in variables.tf. Line count: 1-250. All use snake_case except variable `laResource` at line 42 (camelCase — FAIL on Q1)."

**For Q1, Q2, Q3, Q7 — provide a count:**

```
Q2 - Variable Completeness: PARTIAL
Total variables in variables.tf: 18
Variables WITH both type and description: 16
Variables MISSING description: 2 (lines 45, 67)
Score: 2/18 missing = 11% → Passes <20% threshold → PARTIAL (almost Pass)
```

---

### Failure 3: Ambiguous Decision Boundaries

**What happens:** Model cannot decide between Pass/Partial/Fail and guesses.

Example error:
```
Q3 - Validation Blocks: PASS
"Most enum variables have validation, so I scored Pass."
[But the scoring rule says "all enum vars MUST have validation" — should be PARTIAL or FAIL]
```

**Prevention:**

✅ **Follow the EXACT scoring table. Do not interpret.**

For Q3:
```
Scoring rule (EXACT — do not change):
  - PASS: All enum-accepting string variables have validation blocks
  - PARTIAL: Some enum variables have validation, others do not
  - FAIL: No enum variables have validation blocks

My findings:
  - Enum variables: account_tier, access_tier, replication_type (3 total)
  - With validation blocks: account_tier, access_tier (2 of 3)
  - Without validation: replication_type (1 of 3 missing)

Scoring: Since 1 out of 3 enum variables is missing validation → PARTIAL (matches rule 2)
```

---

### Failure 4: False Positives (Seeing patterns that aren't there)

**What happens:** Model matches on substring or partial pattern, not the actual criterion.

Example error:
```
S5 - Key Vault Integration: PASS
Evidence: "variable name contains 'vault' so module uses Key Vault"
[But the actual variable is vault_admin_username, which is just a name prefix, not Key Vault integration]
```

**Prevention:**

✅ **Check CONTEXT, not just substrings.**

❌ Bad: "Found 'vault' in the code → uses Key Vault"
✅ Good: "Found variable vault_admin_username (line 50) but it's just a string — not azurerm_key_vault_secret. No actual Key Vault integration."

✅ **For S5 specifically:**

```
S5 - Key Vault Integration: FAIL
Search for actual patterns:
  - azurerm_key_vault_secret resource? NOT FOUND
  - var.key_vault_id used to write secrets? NOT FOUND
  - @Microsoft.KeyVault(...) pattern in outputs? NOT FOUND
  - Outputs with sensitive=true? Found at line 120 (password output marked sensitive)
  
Decision: Output is protected but no actual Key Vault integration → FAIL
(Module exposes sensitive output, even if marked sensitive — lacks proper Key Vault)
```

---

### Failure 5: Scoring Both Pass AND Fail

**What happens:** Model scores the same criterion with contradictory evidence.

Example error:
```
Q7 - Tagging: PASS
Evidence: "var.tags exists" (true)

But also:
Evidence: "var.tags not merged with required tags" (also true)

Result: Confused scoring
```

**Prevention:**

✅ **Make a decision tree:**

```
Q7 - Tagging Decision Tree:

IF no tags variable exists THEN → FAIL
  └─ verified: no "variable \"tags\"" in variables.tf

ELSE IF tags variable exists BUT not merged in locals THEN → PARTIAL
  └─ verified: var.tags = map(string) at line 15 but locals block (line 32) does NOT merge

ELSE IF tags merged in locals AND applied to all resources THEN → PASS
  └─ verified: locals merge var.tags with required_tags at line 32,
     and all azurerm_* resources use local.tags argument

My module: Has var.tags (line 15), but locals block NOT merged → PARTIAL
```

---

### Failure 6: README Table Mismatches

**What happens:** Model compares README inputs/outputs table to .tf files but doesn't check for drift.

Example error:
```
R3 - Inputs table accurate: PASS
[But README lists variable "account_kind" while variables.tf defines "account_tier"]
```

**Prevention:**

✅ **MATCH variable names exactly.**

```
R3 - Inputs Table Accuracy:

Variables in variables.tf (total: 18):
  - resource_group_name (line 5)
  - account_tier (line 10)
  - https_only (line 15)
  ... [full list]

Variables in README Inputs Table:
  - resource_group_name ✓
  - account_kind [MISMATCH — should be account_tier] ✗
  - https_only ✓

Result: 1 mismatch out of 18 variables → R3 = FAIL
```

---

### Failure 7: N/A Without Justification

**What happens:** Model uses N/A score but forgets to explain why.

Example error:
```
S2 - Private Endpoints: N/A
[No justification provided]
```

**Prevention:**

✅ **Always provide ONE sentence justifying N/A:**

```
S2 - Private Endpoints: N/A
Justification: Azure App Service does not natively support private endpoints 
in the way Storage or Key Vault do. Private access via VNet integration 
is handled separately (Q7/S1). Not applicable per Azure service architecture.
```

---

### Failure 8: Scoring on Missing Required Files

**What happens:** Model tries to score a criterion in a file that doesn't exist.

Example error:
```
Q3 - Validation Blocks: PARTIAL
Evidence: "Checked variables.tf and found 50% of enums have validation"
[But wait — module has NO variables.tf at all]
```

**Prevention:**

✅ **ALWAYS verify file existence first (from Step 3).**

```
Q5 - File Layout:

Files retrieved in Step 3:
  [ ] main.tf
  [ ] variables.tf
  [ ] outputs.tf
  [ ] versions.tf
  [ ] README.md

My findings:
  ✓ main.tf exists (lines 1-150)
  ✗ variables.tf MISSING
  ✓ outputs.tf exists (lines 1-40)
  ✗ versions.tf MISSING
  ✓ README.md exists

Result: Q5 = FAIL (missing 2 of 4 required files)

Now trying to score Q1 (Variable Naming):
Since variables.tf MISSING → Q1 = FAIL or N/A?
Decision: Q1 = FAIL (cannot name variables if file doesn't exist)
```

---

## Summary: The Golden Rules

1. **ALWAYS quote evidence** (line number + 2–3 lines of code)
2. **ALWAYS report totals** (X out of Y found / checked)
3. **NEVER make up code** (if NOT FOUND, say so explicitly)
4. **ALWAYS follow scoring tables exactly** (do not interpret or guess)
5. **ALWAYS justify N/A** (one sentence explaining why not applicable)
6. **NEVER score a criterion if required file is missing** (use FAIL or skip that criterion)
7. **ALWAYS verify context** (don't match on substrings alone)
8. **ALWAYS scan entire files** (report line counts / totals scanned)
