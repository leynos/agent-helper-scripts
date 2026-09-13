# Using Cloudflare DNS with OpenTofu

## 1. Set up the Cloudflare provider

Pin the Cloudflare provider to a v5 release from the `cloudflare/cloudflare`
source:

```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}
```

The `provider "cloudflare"` block configures authentication and connects
OpenTofu to Cloudflare. Declare the token as a sensitive variable and supply
it via an environment variable to avoid leaking secrets:

```hcl
variable "cloudflare_api_token" {
  description = "Cloudflare API token with DNS edit permissions"
  type        = string
  sensitive   = true
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
```

Set credentials securely:

```bash
export CLOUDFLARE_API_TOKEN="example-token"
export TF_VAR_cloudflare_api_token="$CLOUDFLARE_API_TOKEN"
```

This ensures that sensitive data never lands in the repository.

## 2. Define and manage DNS zones

Create or reference a Cloudflare DNS zone with a `cloudflare_zone` resource:

```hcl
resource "cloudflare_zone" "example" {
  name = "example.com"
  type = "full"
}
```

This exposes the `zone_id` required for record management.

## 3. Configure DNS records

Use `cloudflare_dns_record` resources to define DNS entries:

```hcl
resource "cloudflare_dns_record" "www" {
  zone_id = cloudflare_zone.example.id
  name    = "www"
  type    = "A"
  content = "203.0.113.10"
  ttl     = 1
  proxied = true
}
```

This creates a proxied A record pointing to `203.0.113.10`. Cloudflare
requires automatic TTL (`ttl = 1`) on proxied records.

## 4. Automate bulk records with variables

For repeated or multiple record definitions, leverage `for_each` or `count`
with a structured variable:

```hcl
variable "dns_records" {
  type = map(object({
    name    = string
    type    = string
    content = string
    ttl     = number
    proxied = optional(bool, false)
  }))
}

resource "cloudflare_dns_record" "bulk" {
  for_each = var.dns_records

  zone_id = var.cloudflare_zone_id
  name    = each.value.name
  type    = each.value.type
  content = each.value.content
  ttl     = each.value.ttl
  proxied = each.value.proxied
}
```

`dns_records` is a map keyed by a caller-supplied, stable identifier, so
several records can share a hostname (for example round-robin `A` records)
without colliding. Define `dns_records` in `terraform.tfvars`:

```hcl
dns_records = {
  app      = { name = "app.example.com", type = "A", content = "192.168.1.1", ttl = 1, proxied = true }
  api      = { name = "api.example.com", type = "CNAME", content = "example.com", ttl = 300 }
  app_rr_a = { name = "app-rr.example.com", type = "A", content = "203.0.113.11", ttl = 300 }
  app_rr_b = { name = "app-rr.example.com", type = "A", content = "203.0.113.12", ttl = 300 }
}
```

The `app_rr_a` and `app_rr_b` entries are round-robin `A` records that share
the `app-rr.example.com` hostname under different map keys.

This keeps the configuration "don't repeat yourself" (DRY) and maintainable.

## 5. Import existing DNS records

When onboarding existing DNS infrastructure into OpenTofu, Cloudflare record
IDs (not just names) are required for import:

1. Retrieve via API:

   ```bash
   export CLOUDFLARE_API_TOKEN="…"
   ZONE_ID=$(curl -s -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
     https://api.cloudflare.com/client/v4/zones?name=example.com | jq -r '.result[0].id')

   DNS_ID=$(curl -s -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
     "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?name=www.example.com&type=A" | jq -r '.result[0].id')
   ```

2. Then import using the composite `<zone_id>/<dns_record_id>` identifier
   that the `cloudflare/cloudflare` provider v5 (and later) expects for
   `cloudflare_dns_record`:

   ```bash
   tofu import cloudflare_dns_record.example "${ZONE_ID}/${DNS_ID}"
   ```

This aligns existing records with the Infrastructure as Code (IaC) workflow.

## 6. Example project structure

```plaintext
infra/
├── main.tf
├── variables.tf
├── terraform.tfvars
├── outputs.tf
├── provider.tf
```

- **`provider.tf`** – Sets Cloudflare provider and auth via variables.
- **`variables.tf`** – Defines `dns_records`, `cloudflare_zone_id`, etc.
- **`main.tf`** – Contains `cloudflare_zone` and `cloudflare_dns_record`
  blocks (static or dynamic).
- **`outputs.tf`** – Outputs useful values like `name_servers`.
- **`terraform.tfvars`** – Specifies non-secret concrete values: zone name
  and record definitions. Credentials come from an environment variable or
  secret manager, never from this file.

## 7. Workflow quick-hit list

1. **Init**: `tofu init`
2. **Preview**: `tofu plan`
3. **Apply**: `tofu apply -auto-approve`
4. **Observe**: Check state changes and dashboard results
5. **Import** (if migrating): Use the API to find record IDs, then
   `tofu import`
6. **Version Control**: Store in Git, exclude secrets

## Additional levers and advanced practices

The [Filador blog](https://filador.com) demonstrates integrating DNS, WAF,
mTLS, and Pages with OpenTofu and Cloudflare. Provider documentation is
available via the
[OpenTofu registry (Cloudflare provider)](https://registry.opentofu.org/providers/opentofu/cloudflare/latest)
and the
[Terraform Registry](https://registry.terraform.io/providers/cloudflare/cloudflare/latest);
modules remain discoverable on the
[Terraform Module Registry](https://registry.terraform.io/browse/modules),
with example repositories supporting modular design.

### Summary table

| Step      | Description                                      |
| --------- | ------------------------------------------------ |
| Provider  | Set up securely via environment variables        |
| Zone      | Define or reference Cloudflare DNS zone          |
| Record    | Create DNS entries, dynamic via `for_each`       |
| Import    | Migrate existing records using API + import      |
| Structure | Organize by Terraform files, use version control |
| Advanced  | Extend with WAF, mTLS, modules as needed         |
