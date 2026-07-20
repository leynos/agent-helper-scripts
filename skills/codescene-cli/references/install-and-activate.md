# Installing and Activating the CodeScene CLI

## Install (Linux, macOS, Windows via WSL)

The install script downloads the binary, moves it to `~/.local/bin`, makes it
executable, and adds `~/.local/bin` to `PATH` if needed. Works with bash, zsh,
or fish:

```bash
curl https://downloads.codescene.io/enterprise/cli/install-cs-tool.sh | sh
```

## Manual installation

Download the binary for your platform and make it executable:

- Linux amd64:
  `https://downloads.codescene.io/enterprise/cli/cs-linux-amd64-latest.zip`
- Linux aarch64:
  `https://downloads.codescene.io/enterprise/cli/cs-linux-aarch64-latest.zip`
- Windows amd64:
  `https://downloads.codescene.io/enterprise/cli/cs-windows-amd64-latest.zip`
- macOS amd64:
  `https://downloads.codescene.io/enterprise/cli/cs-macos-amd64-latest.zip`
- macOS aarch64:
  `https://downloads.codescene.io/enterprise/cli/cs-macos-aarch64-latest.zip`

Platform-specific notes:

- macOS binaries are not signed; move them out of quarantine with
  `xattr -dr com.apple.quarantine <binary>`.
- Windows users might have to set the script execution policy manually:
  `Set-ExecutionPolicy RemoteSigned`.

## Updating

Re-run the install script, or repeat the manual installation. Check the
installed version with `cs version` (prints build date and SHA).

## Activation (licensing)

The CLI requires an access token for licensing. Use a **Personal Access Token**
generated from your CodeScene user settings — the older "CodeScene CLI" /
devtools tokens are **deprecated** and have been replaced by Personal Access
Tokens. Then:

```bash
export CS_ACCESS_TOKEN=<your-personal-access-token>
```

Windows PowerShell:

```powershell
$env:CS_ACCESS_TOKEN = '<your-personal-access-token>'
```

Windows Command Prompt:

```bat
SET CS_ACCESS_TOKEN=<token>   :: temporary, current session only
SETX CS_ACCESS_TOKEN <token>  :: persistent; takes effect in NEW terminals
```

Variables can also be set via System Properties → Advanced → Environment
Variables (shortcut: `Windows + R`, run `sysdm.cpl`, Advanced tab).

## OAuth login (Cloud)

For browser-based OAuth login, set `CS_ACCOUNT_ID` to a positive account ID
before running `cs auth login` to select that Cloud account:

```bash
CS_ACCOUNT_ID=123 cs auth login
```

- The signed-in user must be a member of the requested account.
- OAuth credentials are stored separately for each selected account.
- `CS_ACCOUNT_ID` does not affect `CS_ACCESS_TOKEN` authentication.

## Enterprise

Point the CLI at a CodeScene Enterprise instance with:

```bash
export CS_ONPREM_URL=<base-url>
```

Additional trusted certificates can be supplied via `CS_CERTS` (DER, PEM, or
PKCS12 paths, comma or semicolon separated) and `CS_CERTS_PASSWORD` for PKCS12
files.
