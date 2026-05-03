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
1. Context Gathering     ← Catalogue ALL modules → classify → deep-review → derive standard
2. Provider Docs         ← Retrieve resource schema from Terraform Registry
3. Threat Model Review   ← Map security controls to code constraints
4. Code Generation       ← Write compliant .tf files grounded in schema + standard
5. Validation            ← terraform validate → fmt → security scan
6. Registry Publication  ← Tag release → TFC private registry auto-indexes
```

---

## Phase 1 — Module Catalogue Review

Phase 1 is a structured audit of the entire private module catalogue. It has four stages:
catalogue all modules → classify into buckets → deep-review each Azure service module →
derive the canonical standard. The full review is designed to run using low-cost Copilot
models following the instructions in
[`docs/phase1-catalogue-review.md`](phase1-catalogue-review.md).

### 1a. Catalogue All azurerm Modules

Do **not** sample a subset. Retrieve the complete list of modules from the private TFC
registry before doing anything else:

```
@terraform-expert search_private_modules org=<your-org> provider=azurerm
```

For each module returned, record:

| Field | Source |
|-------|--------|
| Module name | TFC registry response |
| Latest version | TFC registry response |
| GitHub repo URL | TFC registry metadata (VCS link) |
| Description | TFC registry response |
| Published by | TFC registry response |

This becomes the **master catalogue** — every subsequent step operates on this list.

### 1b. Classify: Utility vs Azure Service

For each module in the catalogue, classify it as one of:

| Bucket | Criteria |
|--------|---------|
| **Azure Service** | Wraps a specific Azure resource type (e.g. storage account, Key Vault, AKS). The primary output is one or more `azurerm_*` resources. |
| **Utility** | Provides shared logic, naming helpers, tag generators, policy assignments, or composes multiple Azure Service modules. Does not directly create a single Azure service. |

Modules in the **Utility** bucket are recorded but not deep-reviewed in Phase 1. Only
**Azure Service** modules proceed to Phase 1c.

### 1c. Deep Review — Azure Service Modules

Each Azure Service module must be reviewed against **two sets of criteria**: security
controls and code quality. The review requires reading the actual module source code from
GitHub — the TFC registry metadata alone is insufficient.

For each module:
1. Retrieve the GitHub repo URL from the TFC registry record
2. Clone or fetch the repository contents (or use the GitHub API to read files)
3. Score the module against every criterion below

#### Security Controls Scorecard

| # | Control | Pass condition | Fail condition |
|---|---------|---------------|---------------|
| S1 | **Network isolation** | Module creates or requires a subnet/VNet integration, NSG, or service endpoint. Network access is not unrestricted by default. | No network configuration. Public access defaults to open with no variable to restrict it. |
| S2 | **Private endpoints** | Module includes an `azurerm_private_endpoint` resource or accepts a `private_endpoint_subnet_id` variable that is used to create one. | No private endpoint support. Service is reachable over public internet with no mitigation. |
| S3 | **Public access blocked** | Public network access is disabled by default (`public_network_access_enabled = false` or equivalent). If public access is optional, it must be `false` by default with security exception requirements documented in the variable description. | Public access is enabled by default or there is no variable to control it. |
| S4 | **Managed identity** | Module configures a system-assigned or user-assigned managed identity (`identity` block) for the resource. Cross-service authentication uses managed identity, not connection strings or API keys stored in config. | No identity block. Authentication to dependent services relies on shared secrets or connection strings passed as variables. |
| S5 | **Key Vault integration** | Secrets (connection strings, keys, passwords) are stored in Azure Key Vault. Module either writes secrets to Key Vault or accepts Key Vault references (`@Microsoft.KeyVault(...)`) rather than plaintext values. | Secrets are passed as plaintext Terraform variables or hardcoded. No Key Vault reference pattern. |
| S6 | **Provider usage coverage & maintenance** | Module implements major supported resource capabilities (or explicitly documents why omissions exist in README). Provider version is current (within 3 minor releases of latest). | Major capabilities missing without README justification. Provider version is 4+ minor releases outdated. Uses unsupported provider attributes. |
| S7 | **Account keys & connection strings restricted** | Account keys and connection strings are disabled by default. If configurable, must default to `false` with security exception requirements documented in variable description. Any outputs exposing secrets marked `sensitive = true`. | Account keys/connection strings enabled by default or configurable without exception documentation. Secrets exposed in outputs without `sensitive = true`. |

Score each control: **Pass / Partial / Fail / N/A** (N/A only when the control is
architecturally irrelevant to the service, e.g. S2 for a purely internal service mesh).

#### Code Quality Scorecard

| # | Dimension | Pass condition | Fail condition |
|---|-----------|---------------|---------------|
| Q1 | **Variable naming** | Consistent snake_case. Boolean toggles use `enable_` prefix. No unexplained abbreviations. | Mixed conventions, camelCase, or single-letter variables. |
| Q2 | **Variable completeness** | Every variable has `type`, `description`, and either a `default` or is explicitly required. | Variables missing `description` or `type`. |
| Q3 | **Validation blocks** | All string variables accepting enum values have `validation` blocks with meaningful `error_message`. | Enum-accepting variables lack validation. Invalid values would only be caught at plan time with cryptic provider errors. |
| Q4 | **Output completeness** | Exports `id` and `name` of every primary resource. Connection endpoints exported where applicable. No sensitive values exported in plaintext. | Missing `id` or `name`. Sensitive values (keys, passwords) exported without `sensitive = true`. |
| Q5 | **File layout** | `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf` all present and used correctly. No logic mixed into `outputs.tf`. | Files missing or responsibilities mixed (e.g. variables defined in `main.tf`). |
| Q6 | **Provider version pin** | `required_providers` block present with azurerm pinned to at least a minor version (e.g. `~> 3.90`). | No version pin, or pinned only to a major (`~> 3.0`), allowing unexpected breaking changes. |
| Q7 | **Tagging** | `tags` variable of `type = map(string)` present. Module merges caller tags with required internal tags (e.g. `managed_by`, `module`). | No `tags` variable, or tags not merged with required internal tags. |
| Q8 | **`for_each` / `dynamic` usage** | Optional sub-resources use `dynamic` blocks or `for_each`. No use of `count` for boolean optional resources. | `count = var.enable_X ? 1 : 0` pattern used for optional resources. |

#### README and Examples Scorecard

| # | Dimension | Pass condition | Fail condition |
|---|-----------|---------------|---------------|
| R1 | **README present** | `README.md` exists at the module root. | No README. |
| R2 | **Description accurate** | The description matches what the module actually creates. No stale copy-paste from another module. | Description refers to a different service or is generic/empty. |
| R3 | **Inputs table** | All variables listed with correct types, descriptions, and whether required or optional. | Inputs table missing, incomplete, or shows wrong types/descriptions compared to `variables.tf`. |
| R4 | **Outputs table** | All outputs listed with descriptions. | Outputs table missing or lists outputs that do not exist in `outputs.tf`. |
| R5 | **Usage example present** | At least one `module` block example in README showing minimum required variables. | No usage example. |
| R6 | **Usage example accurate** | The example uses the correct module source path, correct variable names, and would work without modification (excluding real values). | Example uses wrong variable names, missing required variables, or references a module path that does not match the registry entry. |
| R7 | **Security controls documented** | README has a section explaining what security controls the module enforces and what the caller must provide. | No mention of security posture, private endpoints, managed identity, or network controls. |

### 1d. Derive the Canonical Standard

After completing all individual module reviews, aggregate the results to produce the
**canonical standard** used when generating new modules.

The process:

1. **Identify consensus patterns** — where ≥ 75% of modules use the same pattern, that
   pattern is adopted as standard
2. **Select the best non-consensus pattern** — where patterns differ, choose the most
   correct implementation (not the most common), documenting why
3. **Fill remaining gaps** from HashiCorp Module Standards and the Azure CAF naming guide
4. **Record failures as anti-patterns** — explicitly list the patterns that were found and
   rejected, so new module generation avoids them

The output of Phase 1 is a structured document with two sections:

**Section A — Catalogue Summary**: table of all modules with their bucket classification
and scorecard results (pass/partial/fail per criterion).

**Section B — Canonical Standard**: the normalised coding and security standard derived
from the best patterns observed, with explicit anti-pattern list.

> See [`docs/phase1-catalogue-review.md`](phase1-catalogue-review.md) for the detailed
> step-by-step instructions designed for execution by low-cost Copilot models.

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
@terraform-expert Execute Phase 1 of the module acceleration process for org=<your-org>.

Step 1: Catalogue all azurerm modules in the private TFC registry.
Step 2: Classify each module as "Azure Service" or "Utility".
Step 3: For each Azure Service module, retrieve the GitHub repo and evaluate it
        against the full scorecard in docs/phase1-catalogue-review.md.
Step 4: Produce Section A (catalogue summary with scores) and Section B (canonical standard).

Follow the detailed instructions in docs/phase1-catalogue-review.md exactly.
Output the results as structured markdown.
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

## 🎯 TODO: Company-Specific Standards & Guides

This document provides a framework for module acceleration. To tailor it to your organisation, update it with:

**Development Standards:**
- [ ] Company naming conventions for resources, variables, locals, and outputs (e.g. CAF prefix, department tags)
- [ ] Approved Azure services and resource types (allowlist/blocklist by team)
- [ ] Tagging strategy — required tags, key formats, enforcement mechanism
- [ ] Provider version pinning policy (e.g. "must pin azurerm ~> 3.90")
- [ ] Module source structure requirements (e.g. modules/ directory layout, private registry naming)

**Security & Compliance Standards:**
- [ ] Mandatory security controls (e.g. encryption-at-rest, network isolation, managed identity requirements)
- [ ] Network architecture standards (e.g. private endpoints mandatory, public access blocked)
- [ ] Authentication/authorization patterns (e.g. RBAC, managed identities, Key Vault integration)
- [ ] Audit logging requirements (e.g. diagnostics settings, monitoring expectations)
- [ ] Compliance frameworks (e.g. CIS, PCI DSS, internal policies)
- [ ] Data residency / sovereignty constraints

**Code Quality Standards:**
- [ ] Linter / formatter enforcement (e.g. checkov, tfsec rules, terraform fmt)
- [ ] Documentation requirements beyond README (e.g. architecture diagrams, threat models)
- [ ] Testing strategy (e.g. terratest, unit tests, integration tests)
- [ ] Code review process and approval requirements
- [ ] Version control workflow (e.g. branch naming, PR template, release process)

**Operational Standards:**
- [ ] State management requirements (remote state, locking, backup policy)
- [ ] Workspace naming conventions and access control
- [ ] Deployment pipeline workflow (e.g. plan approval, automated apply conditions)
- [ ] Change management requirements (e.g. CAB approval, change windows)
- [ ] Runbook / documentation standards for module troubleshooting

**Links to Company Resources:**
- [ ] Internal architecture decision records (ADRs)
- [ ] Security policy documentation
- [ ] Network design standards
- [ ] Tagging taxonomy document
- [ ] Approved provider versions (with EOL dates)

---

## 🎯 TODO: Central Registry & Repository Locations

To make this framework actionable, document where modules, repos, and workspaces are centrally managed:

**Module Registry:**
- [ ] TFC Private Registry URL or hostname
- [ ] Module source naming convention (e.g. `company/service-name/azurerm`)
- [ ] Module repository root directory (e.g. `terraform-modules/` or `modules/`)
- [ ] Module versioning strategy (semantic versioning rules, tag naming pattern)
- [ ] Module release process (who approves, approval SLA, changelog requirements)
- [ ] Module deprecation process (sunset timeline, migration guidance)

**Repository Locations:**
- [ ] GitHub organization or Org URL (e.g. `github.com/company-terraform`)
- [ ] Module repositories pattern/location (e.g. `terraform-{service}-module` naming)
- [ ] Monorepo vs poly-repo strategy (all modules in one repo or separate repos per module?)
- [ ] Default branch naming convention (e.g. `main`, `master`)
- [ ] Branch protection rules and required reviews
- [ ] Release tag format (e.g. `v1.2.3`, `release-1.2.3`)
- [ ] GitHub teams with module maintenance permissions
- [ ] Automated release/tagging workflow (if applicable)

**HCP Terraform / Terraform Cloud:**
- [ ] Organization name(s)
- [ ] Workspace naming conventions (e.g. `{environment}-{service}`, `prod-storage-001`)
- [ ] Default workspace structure (VCS integration, working directory, state backend)
- [ ] HCP Terraform team structure and permissions model
- [ ] Variable set locations (global vs workspace-scoped)
- [ ] Policy-as-code (Sentinel) policy set repository location
- [ ] Cost estimation and governance thresholds
- [ ] Run triggers and auto-apply conditions

**Artifact Management:**
- [ ] Terraform lock file (.terraform.lock.hcl) — version controlled or generated?
- [ ] State file backup strategy and location (S3, GCS, Azure Blob Storage)
- [ ] State file retention and audit logging requirements
- [ ] Plan artifacts storage (if captured for auditing)
- [ ] Change log / audit trail for all module releases

**Documentation & Knowledge Base:**
- [ ] Central documentation site or wiki (Confluence, GitHub Pages, internal wiki)
- [ ] Module usage examples repository location
- [ ] Architecture decision records (ADRs) repository
- [ ] Module troubleshooting runbook location
- [ ] On-call escalation path for production incidents
- [ ] Training/onboarding materials for new developers

**Integration Points:**
- [ ] Module validation/scanning tools (checkov, tfsec) enforcement location
- [ ] CI/CD pipeline configuration repository
- [ ] Secrets management backend (HashiCorp Vault, Azure Key Vault, AWS Secrets Manager)
- [ ] Compliance scanning results dashboard or reporting location
- [ ] Cost optimization alerts and reports location
- [ ] Change notification channels (Slack, email, etc.)

---

## 🎯 TODO: GitHub Actions & CI/CD Pipeline

Pre-configured GitHub Actions enforce code quality, validation, and integration testing for all module repositories:

**Linting & Validation Actions:**
- [ ] `terraform validate` step in CI pipeline
- [ ] `terraform fmt` check (fail on unformatted code)
- [ ] `checkov` security scanning configuration (rules, severity thresholds)
- [ ] `tfsec` static analysis configuration (rules, exclusions)
- [ ] Provider schema validation (prevent breaking changes to outputs)
- [ ] Documentation validation (README updates required with code changes)
- [ ] Commit message linting (enforce conventional commits pattern)

**Integration Testing with Chef InSpec:**
- [ ] Chef InSpec test framework setup and location (`test/`, `inspec/`, or `spec/`)
- [ ] InSpec profile structure and naming conventions
- [ ] Integration test runner in GitHub Actions CI (trigger after `terraform apply`)
- [ ] Test environment provisioning strategy (ephemeral Azure resources for testing)
- [ ] Test data and fixtures management (secrets, test resource IDs)
- [ ] InSpec test coverage expectations (% of resources covered)
- [ ] Failure handling — rollback strategy if tests fail post-apply
- [ ] Integration test duration target (timeout thresholds)
- [ ] Test results reporting (GitHub Check Runs, test summary in PR)

**CI/CD Workflow:**
- [ ] Workflow trigger rules (on PR, on merge to main, on release tag)
- [ ] Approval gates (manual approval before `terraform apply` in CI)
- [ ] Notification on failure (Slack, email, GitHub teams)
- [ ] Artifact retention (plan logs, test reports, state snapshots)
- [ ] Automated version bumping and release tagging
- [ ] Registry publication workflow (auto-publish on tag)
- [ ] Status badge for CI/CD health on README

**Module Creation Requirements:**
- [ ] New modules MUST include skeleton InSpec test profile
- [ ] Integration tests MUST cover all resource types created
- [ ] Test controls MUST validate resource attributes (names, tags, settings)
- [ ] Destructive tests (cleanup after verify) documented in test code
- [ ] Test fixture data or seed files included in module repo
- [ ] CI pipeline template available for quick module repo setup

**Future Enhancement — Module Evaluation:**
- [ ] Phase 2+ evaluation: InSpec test coverage assessment (Q9 code quality criterion)
- [ ] Coverage metric: % of Azure resources with test controls
- [ ] Evaluation criteria:
  - [ ] All resources have at least one control assertion
  - [ ] Critical attributes verified (tags, encryption, network settings)
  - [ ] Controls properly structured and maintainable
  - [ ] Test documentation included (test intent comments)
- [ ] Failure scenarios: module review flags if:
  - [ ] Integration tests missing or empty
  - [ ] Tests are not maintained with code changes
  - [ ] Test coverage < 80% of resources
  - [ ] Test controls too generic or trivial

---

## Related Resources

- [HashiCorp Module Development Standards](https://developer.hashicorp.com/terraform/language/modules/develop)
- [Azure Resource Naming Convention (CAF)](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming)
- [TFC Private Registry Docs](https://developer.hashicorp.com/terraform/cloud-docs/registry)
- [checkov](https://www.checkov.io/) / [tfsec](https://aquasecurity.github.io/tfsec/)
- Agent instructions: `agent/instructions.md`
- [docs/phase1-catalogue-review.md](phase1-catalogue-review.md) — detailed Phase 1 review instructions (low-cost model ready)
