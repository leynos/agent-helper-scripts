# Using Cloudflare DNS with OpenTofu

## 1. Set up the Cloudflare provider

The `provider "cloudflare"` block configures authentication and connects
OpenTofu to Cloudflare. Use environment variables for credentials to avoid
leaking secrets:

```hcl
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

Use `cloudflare_record` resources to define DNS entries:

```hcl
resource "cloudflare_record" "www" {
  zone_id = cloudflare_zone.example.id
  name    = "www"
  type    = "A"
  content = "203.0.113.10"
  ttl     = 3600
  proxied = true
}
```

This creates a proxied A record pointing to `203.0.113.10`.

## 4. Automate bulk records with variables

For repeated or multiple record definitions, leverage `for_each` or `count`
with a structured variable:

```hcl
variable "dns_records" {
  type = list(object({
    name    = string
    type    = string
    content = string
    ttl     = number
    proxied = optional(bool, false)
  }))
}

resource "cloudflare_record" "bulk" {
  for_each = { for r in var.dns_records : r.name => r }

  zone_id = var.cloudflare_zone_id
  name    = each.value.name
  type    = each.value.type
  content = each.value.content
  ttl     = each.value.ttl
  proxied = each.value.proxied
}
```

Define `dns_records` in `terraform.tfvars`:

```hcl
dns_records = [
  { name = "app.example.com", type = "A", content = "192.168.1.1", ttl = 3600, proxied = true },
  { name = "api.example.com", type = "CNAME", content = "example.com", ttl = 300 }
]
```

This keeps the configuration "don't repeat yourself" (DRY) and maintainable.

## 5. Import existing DNS records

When onboarding existing DNS infrastructure into OpenTofu, Cloudflare record
IDs (not just names) are required for import:

1. Retrieve via API:

   ```bash
   export CLOUDFLARE_API_TOKEN="…"
   ZONE_ID=$(curl -s -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
     https://api.cloudflare.com/client/v4/zones?name=example.com | jq -r '.result[0].id')

   curl -s -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
     "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?name=www.example.com&type=A" | jq -r '.result[0].id'
   ```

2. Then import:

   ```bash
   tofu import cloudflare_record.example DNS_ID
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
- **`main.tf`** – Contains `cloudflare_zone` and `cloudflare_record`
  blocks (static or dynamic).
- **`outputs.tf`** – Outputs useful values like `name_servers`.
- **`terraform.tfvars`** – Specifies concrete values: zone name, token,
  and record definitions.

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
