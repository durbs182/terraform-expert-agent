# Accelerating Azure Terraform Module Creation with Copilot

## Overview

This document describes the process for accelerating the creation of new, security-hardened
Azure Terraform modules using the `@terraform-expert` Copilot agent.

The company maintains a catalogue of `azurerm`-backed modules in a private TFC registry.
Each module wraps a single Azure service, enforces company security requirements, and is
accompanied by a threat model. Creating a new module from scratch is time-consuming —
this process reduces that effort while producing consistent, standards-compliant code.

---

## Why Modules Vary in Quality

The existing module catalogue was built by multiple teams over time. As a result:

- Variable naming conventions differ (e.g. `resource_group` vs `rg_name` vs `resource_group_name`)
- Some modules use `count`, others `for_each` for optional resources
- Output naming is inconsistent across modules
- Variable descriptions and validation blocks are missing in older modules
- `required_providers` version pins vary in specificity (`~> 3.0` vs `~> 3.90`)
- Tag enforcement is inconsistent — some modules accept a `tags` map, others hard-code partial tags
- Some modules expose security-sensitive attributes as optional variables without validation

Before generating new modules, the agent must **derive a normalised canonical standard** by
analysing a representative cross-section of existing modules. This prevents inheriting bad
patterns from any one team.

---

## Process Overview

```
1. Context Gathering     ← Analyse existing modules; derive canonical standard
2. Provider Docs         ← Retrieve resource schema from Terraform Registry
3. Threat Model Review   ← Map security controls to code constraints
4. Code Generation       ← Write compliant .tf files grounded in schema + standard
5. Validation            ← terraform validate → fmt → security scan
6. Registry Publication  ← Tag release → TFC private registry auto-indexes
```

---

## Phase 1 — Context Gathering

### 1a. Sample Existing Modules

Use `search_private_modules` to list the catalogue, then retrieve details for
**3–5 representative modules** spanning different teams and services:

```
@terraform-expert search_private_modules org=<your-org>
@terraform-expert get_private_module_details name=<module-name> org=<your-org>
```

Select modules that cover different resource types (networking, storage, compute) and
that were authored by different teams where possible. The goal is to capture the full
range of styles present in the catalogue.

### 1b. Analyse and Compare

For each retrieved module, extract and compare:

| Dimension | What to look for |
|-----------|-----------------|
| **Variable naming** | snake_case, abbreviations used, prefixes (e.g. `enable_`, `is_`) |
| **Variable structure** | Types used (`string`, `object`, `map(string)`), nullable, optional |
| **Validation blocks** | Presence, regex patterns, error message quality |
| **Output naming** | Suffixes (`_id`, `_name`, `_connection_string`) |
| **File layout** | Whether `versions.tf` is separate, README format, example presence |
| **Tagging** | `tags` variable type, merge strategy, required vs optional tags |
| **`required_providers`** | Version constraint style and azurerm version pinned |
| **Optional resources** | `count`-based vs `for_each`-based vs `dynamic` blocks |
| **Lifecycle rules** | `prevent_destroy`, `ignore_changes` usage |

### 1c. Derive the Canonical Standard

From the analysis, produce a normalised standard that:

1. **Takes the best pattern** for each dimension — not the most common, but the most correct
2. **Fills gaps** using [HashiCorp Module Standards](https://developer.hashicorp.com/terraform/language/modules/develop/structure)
   and the [Azure Naming Convention](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming)
3. **Rejects inconsistent patterns** that would conflict across modules (e.g. if only one module
   uses `count`, standardise on `for_each` or `dynamic` blocks for optional resources)

Document the derived standard at the top of your working context before proceeding. Example:

```
Canonical standard (derived from 4 modules):
- Variable names: snake_case, no abbreviations for clarity, enable_ prefix for bool toggles
- Tags: var.tags = map(string), merged with local required_tags (cost_centre, environment)
- Outputs: always suffix _id, _name, _fqdn as applicable — never expose secrets directly
- required_providers: azurerm ~> 3.90, exact minor pin
- Optional resources: dynamic blocks preferred over count for readability
- Validation: all string vars that accept enum values must have validation block
```

---

## Phase 2 — Provider Docs Retrieval

Use the MCP registry tools to pull the full resource schema for the target Azure service.

```
@terraform-expert search_providers query="azurerm" namespace=hashicorp
@terraform-expert get_provider_details name=azurerm namespace=hashicorp resource=<resource_type>
```

From the returned schema, identify and categorise all attributes:

| Category | Handling |
|----------|---------|
| **Security-critical** (encryption, network rules, identity, private endpoint) | Enforce as required or hardcoded defaults — review against threat model |
| **Service-identifying** (name, location, resource group) | Expose as required variables |
| **Operational tunables** (SKU, capacity, tier) | Expose as optional variables with safe defaults |
| **Diagnostics / logging** | Expose as optional with `enable_diagnostic_settings` toggle |
| **Deprecated attributes** | Exclude entirely |

---

## Phase 3 — Threat Model Integration

Each module should be accompanied by a threat model (STRIDE or equivalent). Before generating
code, review the threat model for the target service to identify:

1. **Hard-enforced controls**: attributes that MUST be set to a specific value
   (e.g. `min_tls_version = "TLS1_2"`, `https_only = true`)
2. **User-configurable with guardrails**: attributes where the user picks a value but it must
   fall within an approved range (use `validation` blocks with clear error messages)
3. **Explicitly disabled features**: attributes that must never be enabled by users
   (omit from variables; hardcode to `false` or `null`)
4. **Audit requirements**: outputs or tags required for compliance tracking

Map each threat model control to either a hardcoded value or a `validation` block:

```hcl
# Hardcoded enforcement (from threat model: TLS downgrade attack)
min_tls_version = "TLS1_2"

# Validation guardrail (from threat model: unrestricted network access)
variable "allowed_ip_ranges" {
  type        = list(string)
  description = "IP ranges permitted to access the service. Must be specified — empty list is not allowed."
  validation {
    condition     = length(var.allowed_ip_ranges) > 0
    error_message = "At least one IP range must be specified. Open access is not permitted by policy."
  }
}
```

---

## Phase 4 — Code Generation

Generate the following files, grounded in the canonical standard (Phase 1) and provider schema
(Phase 2) with security controls from the threat model (Phase 3).

### File Structure

```
modules/<service-name>/
├── main.tf          ← resource blocks with security defaults enforced
├── variables.tf     ← typed variables, descriptions, defaults, validation
├── outputs.tf       ← IDs, names, endpoints — never raw secrets
├── versions.tf      ← required_version + required_providers with pinned azurerm
└── README.md        ← inputs table, outputs table, security notes, usage example
```

### `versions.tf`

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
  }
}
```

### `variables.tf` Standards

- Every variable must have a `description`
- Use `type` constraints — avoid bare `any`
- `string` variables accepting enum values require `validation` blocks
- Boolean toggles use `enable_` prefix and default to the secure value
- Include a `tags` variable of `type = map(string)` with `default = {}`

### `main.tf` Standards

- One resource per file for complex resources; multiple tightly-coupled resources (e.g. resource + diagnostic setting) may co-exist
- Use `locals` for computed values and tag merging:
  ```hcl
  locals {
    required_tags = {
      managed_by   = "terraform"
      module       = "<module-name>"
      environment  = var.environment
    }
    tags = merge(local.required_tags, var.tags)
  }
  ```
- Security-critical attributes (from threat model) placed at the **top** of resource blocks with a comment citing the control
- `dynamic` blocks for optional sub-resources (not `count`)

### `outputs.tf` Standards

- Export `id` and `name` for every primary resource
- Export connection-oriented outputs (`fqdn`, `endpoint`, `connection_string`) but **never** export sensitive values directly — use `sensitive = true` if unavoidable
- Output names follow the pattern: `<resource>_<attribute>` (e.g. `storage_account_id`, `storage_account_name`)

### `README.md` Standards

Use a standard template:

```markdown
# <Module Name>

Brief description of what this module creates and what security controls it enforces.

## Security Controls

List the key security decisions enforced by this module with references to the threat model.

## Usage

\`\`\`hcl
module "<service>" {
  source  = "<org>/<module>/<provider>"
  version = "~> 1.0"
  # required variables
}
\`\`\`

## Inputs

<!-- Auto-generated or manually maintained inputs table -->

## Outputs

<!-- Auto-generated or manually maintained outputs table -->

## Threat Model

Link to the associated threat model document.
```

---

## Phase 5 — Validation

Run the following in order. Fix all issues before proceeding to publication.

```bash
# 1. Syntax and semantic validation
terraform init -backend=false
terraform validate

# 2. Canonical formatting
terraform fmt -recursive -check
terraform fmt -recursive   # apply if check fails

# 3. Security scan (choose one or both)
checkov -d . --framework terraform
tfsec .

# 4. Documentation generation (optional but recommended)
terraform-docs markdown table . > README_generated.md
```

All `checkov` / `tfsec` failures must be either:
- **Fixed** (preferred), or
- **Suppressed with a justification comment** inline citing the threat model decision

No unreviewed suppressions.

---

## Phase 6 — Registry Publication

The private TFC registry auto-indexes modules from VCS-connected repositories when a
semver tag is pushed.

```bash
# 1. Commit all module files
git add modules/<service-name>/
git commit -m "feat: add <service-name> module v1.0.0"

# 2. Tag the release
git tag v1.0.0
git push origin main --tags
```

TFC will detect the tag and index the new module version. It will appear in the private
registry within a few minutes under `<org>/<module-name>/azurerm`.

### Versioning Policy

| Change type | Version bump |
|-------------|-------------|
| New required variable or breaking output change | Major (`v2.0.0`) |
| New optional variable, new output, backward-compatible change | Minor (`v1.1.0`) |
| Bug fix, security patch, doc update | Patch (`v1.0.1`) |

---

## Prompt Templates

Use these prompts when invoking `@terraform-expert` for each phase.

### Phase 1 — Context Gathering

```
@terraform-expert Retrieve the following modules from the private registry and analyse
them for naming conventions, variable patterns, output patterns, and tagging strategy:
<list module names>

Identify inconsistencies across modules and derive a canonical standard we will use
for all new modules going forward. Document the standard explicitly.
```

### Phase 2 — Provider Docs

```
@terraform-expert Retrieve the full resource schema for azurerm_<resource_type> from
the public Terraform Registry. Categorise all attributes as:
- Security-critical (must be enforced)
- Required for service identity (expose as required variables)
- Operational tunables (expose as optional with defaults)
- Deprecated (exclude)
```

### Phase 4 — Code Generation

```
@terraform-expert Generate a Terraform module for Azure <service> following this canonical
standard: <paste standard from Phase 1>

Apply these security controls from the threat model: <paste controls>

Ground the implementation in the azurerm_<resource_type> schema retrieved above.
Generate: main.tf, variables.tf, outputs.tf, versions.tf, README.md
```

---

## Quality Checklist

Before opening a PR for a new module:

- [ ] All variables have descriptions
- [ ] All security-critical attributes from threat model are enforced
- [ ] `validation` blocks present on all enum-type string variables
- [ ] `tags` variable present and merged with required module tags
- [ ] `versions.tf` pins azurerm at the canonical minor version
- [ ] `terraform validate` passes
- [ ] `terraform fmt` produces no diff
- [ ] `checkov` / `tfsec` scan clean (or suppressions justified)
- [ ] README includes usage example and security controls section
- [ ] Module reviewed against canonical standard from Phase 1

---

## Related Resources

- [HashiCorp Module Development Standards](https://developer.hashicorp.com/terraform/language/modules/develop)
- [Azure Resource Naming Convention (CAF)](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming)
- [TFC Private Registry Docs](https://developer.hashicorp.com/terraform/cloud-docs/registry)
- [checkov](https://www.checkov.io/) / [tfsec](https://aquasecurity.github.io/tfsec/)
- Agent instructions: `agent/instructions.md`
