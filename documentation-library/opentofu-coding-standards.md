# OpenTofu HashiCorp Configuration Language (HCL) coding standards

## Purpose

This guide defines house rules for writing OpenTofu HashiCorp Configuration
Language (HCL). The guidance complements the HCL syntax reference and the
module testing guide.

## Core principles

- Prefer declarative, idempotent plans; review every `tofu plan` before
  apply.
- Keep modules focused; expose only the inputs and outputs a caller needs.
- Surface intent through validation, tagging, and meaningful naming.
- Optimize for offline workflows; avoid resources that need live lookups.

## File layout

- Keep `main.tf` for orchestration and cross-resource wiring.
- Group related resources in dedicated files (e.g. `acm.tf`, `dns.tf`).
- Define module interfaces in `variables.tf` and `outputs.tf`.
- Pin providers in `terraform.tf`; declare aliases like `aws.useast1`.

Example module structure:

```plaintext
modules/
├── static_site/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── tests/
├── deploy/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── tests/
└── monitoring/
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    └── tests/
```

## Formatting

- Run `tofu fmt -check`, `tofu validate`, and `tofu test` before submitting.
- Indent with two spaces; avoid tabs and trailing whitespace.
- Keep argument lines under 120 characters; break expressions with
  parentheses.
- Place blank lines between top-level blocks and logical sections.

## Naming conventions

- Name resources `aws_service_purpose` (e.g. `aws_s3_bucket.site`).
- Use snake_case for locals and variables; keep tags as hyphenated slugs.
- Tag resources with Name patterns like `"${var.project_name}-site"` to aid
  tracing.
- Match output names to the value intent, not the implementation detail.

## Variables and outputs

- Provide `description`, `type`, and `nullable = false` for required
  inputs.
- Put `default` below `type` and explain it in the description.
- Use `validation` blocks to catch misuse with precise error messages.
- Mark secrets with `sensitive = true` and avoid real default values.
- Add `description` fields to outputs so module intent stays discoverable.

```hcl
variable "bucket_name" {
  description = "Name of the S3 bucket hosting the site"
  type        = string
  nullable    = false

  validation {
    condition     = trimspace(var.bucket_name) != ""
    error_message = "Bucket name must not be empty."
  }
}
```

## Expressions and control flow

- Prefer `for_each` over `count` so resource identities stay stable.
- Store reusable snippets in `locals` blocks, as done for deploy scripts.
- Guard `null` paths with ternaries or `try` rather than sentinel defaults.
- Comment on any `depends_on` usage that encodes hidden relationships.

## Providers and backends

- Pin provider versions with pessimistic ranges in `terraform.tf`.
- Declare required aliases, such as `aws.useast1`, near the provider block.
- Stub remote calls with `mock_provider` or test doubles so validation
  stays offline.
- Treat backend configuration as immutable once a state file is in use.

## Testing and validation

- Add module tests under `modules/<name>/tests` with the native framework.
- Assert on outputs, resource counts, and critical arguments.
- Use generated fixtures only within the test directory; clean temporary
  files.
- Ensure `tofu test` passes alongside `tofu validate` for every change set.

## Security and secrets

- Mark secrets as sensitive and keep them out of logs and outputs.
- Pass tokens such as `github_token` via environment or continuous
  integration (CI) secrets.
- Clean up temporary artefacts in provisioners using `trap`.
- Grant Identity and Access Management (IAM) permissions on the narrowest
  scope; prefer data sources for Amazon Resource Names (ARNs).

## Documentation and comments

- Explain non-obvious logic above the block using complete sentences.
- Reference follow-up docs or tickets only when they add real context.
- Update module READMEs and docs whenever the interface or behaviour
  shifts.

## Workflow expectations

- Run `tofu init`, `tofu plan`, and `tofu apply` in clean environments.
- Share plan output or a summary in pull requests touching infrastructure.
- Follow Conventional Commits; mention the affected module in the body
  when useful.
- Coordinate state changes to avoid parallel applies across environments.
