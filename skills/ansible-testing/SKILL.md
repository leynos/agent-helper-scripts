---
name: ansible-testing
description: >
  Local-first Ansible testing for roles and modules within collections. Use
  whenever the user wants to add, run, scaffold, or debug tests for an Ansible
  collection, role, or module. Triggers include: "test my Ansible role",
  "add Molecule tests", "run ansible-test", "set up integration tests",
  "scaffold a test scenario", "run sanity checks", "write unit tests for a
  module", "test a collection locally". Always prefer this skill over ad hoc
  shell suggestions when Ansible testing is the subject. The skill covers the
  full testing stack: Molecule + Podman for roles, ansible-test for modules
  and collections (sanity, unit, integration). Python 3.12+, collections
  layout, and Podman are assumed throughout.
---

# Ansible Testing Skill

Local-first testing for Ansible collections, roles, and modules.

## Governing assumptions

- **Python**: `/usr/bin/python` is CPython 3.12. All virtual environments
  target 3.12 unless the user specifies otherwise.
- **Container runtime**: Podman. Never suggest Docker unless the user asks.
  Set `ANSIBLE_TEST_PREFER_PODMAN=1` in the environment when running
  `ansible-test`.
- **Layout**: All work lives inside a collection. Standalone roles are an
  anti-pattern for new code; if the user has one, migrate it into a collection
  first (see Phase 0).
- **Molecule**: Primary harness for roles. Use the `molecule-plugins[podman]`
  driver. Never use the legacy `molecule-docker` driver. For end-to-end
  scenarios that exercise a role or collection workflow against a managed
  system, recommend Molecule with Podman first.
- **ansible-test**: Primary harness for modules, plugins, and collection-level
  sanity/unit/integration. Run locally via
  `--controller origin:python=venv/3.12` and
  `--target controller:python=venv/3.12` unless the user needs a separate
  managed node, in which case prefer SSH over Docker.
- **Base container image**: `registry.access.redhat.com/ubi9/ubi-init` for
  systemd-capable tests; `registry.access.redhat.com/ubi9/ubi` for stateless
  tests. Prefer UBI9 over CentOS 7 / Fedora images from the docs.

---

## Phase 0 — Context discovery

Before writing any files, determine:

1. **Collection or standalone role?**
   - Run `ls` and check for `galaxy.yml` or `MANIFEST.json` in the current
     directory, or for the path pattern
     `~/ansible_collections/<namespace>/<collection>`.
   - If standalone role: create a minimal collection wrapper (see
     "Wrapping a standalone role" below).

2. **What kind of test is needed?**
   - Role behaviour → Molecule
   - End-to-end role or collection workflow → Molecule with Podman
   - Module / plugin logic → `ansible-test units`
   - Module / plugin integration contract → `ansible-test integration`
   - Code quality → `ansible-test sanity`
   - All of the above → all of the above

3. **Does Molecule already exist?**
   - Check for `molecule/` inside the role directory.
   - If yes, read `molecule/default/molecule.yml` before proceeding.

4. **Does the collection namespace path exist?**
   - The collection must live at
     `~/ansible_collections/<namespace>/<collection_name>`.
   - If not, set it up with a symlink or move before running `ansible-test`.

---

## Phase 1 — Collection layout

A correct collection layout is a prerequisite for `ansible-test`. Scaffold
or verify this structure before doing anything else:

```text
ansible_collections/
└── <namespace>/
    └── <collection>/
        ├── galaxy.yml          # namespace, name, version, description
        ├── README.md
        ├── roles/
        │   └── <role_name>/
        │       ├── defaults/main.yml
        │       ├── handlers/main.yml
        │       ├── meta/main.yml
        │       ├── molecule/       # Molecule lives here, inside the role
        │       │   └── default/
        │       ├── tasks/main.yml
        │       └── vars/main.yml
        ├── plugins/
        │   ├── modules/
        │   └── module_utils/
        └── tests/
            ├── integration/
            │   └── targets/
            └── unit/
```

Minimum viable `galaxy.yml`:

```yaml
namespace: <namespace>
name: <collection>
version: 1.0.0
readme: README.md
description: ""
license:
  - GPL-2.0-or-later
```

### Wrapping a standalone role

If the user has a standalone role at `./my_role/`, create the collection
wrapper and symlink or copy the role in:

```bash
mkdir -p ~/ansible_collections/acme/platform/roles
cp -r ./my_role ~/ansible_collections/acme/platform/roles/my_role
cd ~/ansible_collections/acme/platform
cat > galaxy.yml <<'EOF'
namespace: acme
name: platform
version: 1.0.0
readme: README.md
description: ""
license:
  - GPL-2.0-or-later
EOF
```

---

## Phase 2 — Python environment

All tools run inside a virtual environment. Create one per project, not
system-wide.

```bash
python3.12 -m venv ~/.venv/ansible-dev
source ~/.venv/ansible-dev/bin/activate

pip install --upgrade pip
pip install \
  ansible-core \
  molecule \
  "molecule-plugins[podman]" \
  ansible-lint \
  pytest \
  pytest-mock \
  "pytest-ansible>=4.0"
```

Verify:

```bash
molecule --version
ansible-test --version
python --version   # must be 3.12.x
```

Export the Podman preference before running `ansible-test`:

```bash
export ANSIBLE_TEST_PREFER_PODMAN=1
```

---

## Phase 3 — Molecule setup (roles)

### 3a. Initialise a new Molecule scenario

Run from inside the role directory
(`~/ansible_collections/<ns>/<col>/roles/<role>/`):

```bash
molecule init scenario default --driver-name podman
```

If the role directory does not yet exist, initialise it first:

```bash
cd ~/ansible_collections/<ns>/<col>
ansible-galaxy role init roles/<role_name>
cd roles/<role_name>
molecule init scenario default --driver-name podman
```

### 3b. molecule.yml

Replace the generated `molecule/default/molecule.yml` with this template.
Adjust the image and command for the target OS.

```yaml
---
dependency:
  name: galaxy
  # Add options only when the scenario has requirements files. Keep
  # `force: false` so local dependency caches can be reused.
  # options:
  #   requirements-file: ${MOLECULE_SCENARIO_DIRECTORY}/requirements.yml
  #   role-file: ${MOLECULE_SCENARIO_DIRECTORY}/requirements.yml
  #   force: false

driver:
  name: podman

scenario:
  test_sequence:
    - dependency
    - destroy
    - create
    - prepare
    - converge
    - idempotence
    - verify
    - destroy

platforms:
  # Systemd-capable UBI9 — use for roles that manage services
  - name: ubi9-init-${MOLECULE_INSTANCE_SUFFIX}
    image: registry.access.redhat.com/ubi9/ubi-init:latest
    pre_build_image: true
    command: /usr/sbin/init
    systemd: always
    tmpfs:
      - /run
      - /tmp
    volumes:
      - /sys/fs/cgroup:/sys/fs/cgroup:ro
    capabilities:
      - SYS_ADMIN

  # Stateless UBI9 — use for roles that only manage files / packages
  # Uncomment and remove the entry above if systemd is not needed.
  # - name: ubi9-${MOLECULE_INSTANCE_SUFFIX}
  #   image: registry.access.redhat.com/ubi9/ubi:latest
  #   pre_build_image: true

provisioner:
  name: ansible
  env:
    ANSIBLE_COLLECTIONS_PATH: ${MOLECULE_PROJECT_DIRECTORY}/.cache/collections
    ANSIBLE_ROLES_PATH: ${MOLECULE_PROJECT_DIRECTORY}/.cache/roles
    PROFILE_TASKS_SORT_ORDER: descending
    PROFILE_TASKS_TASK_OUTPUT_LIMIT: "20"
  config_options:
    defaults:
      interpreter_python: /usr/bin/python3
      # python3 must be present in the container image; add a prepare step
      # if the image does not ship it.
      gathering: smart
      fact_caching: jsonfile
      fact_caching_connection: ${MOLECULE_PROJECT_DIRECTORY}/.cache/facts-${MOLECULE_INSTANCE_SUFFIX}
      fact_caching_timeout: 3600
      callbacks_enabled: timer, profile_tasks
      retry_files_enabled: false
    connection:
      pipelining: false   # required for Podman

verifier:
  name: ansible

lint: |
  set -e
  yamllint .
  ansible-lint .
```

> **SELinux note**: On a host with SELinux enforcing, run once:
>
> ```bash
> sudo setsebool -P container_manage_cgroup 1
> ```

### 3c. converge.yml

`molecule/default/converge.yml` applies the role under test:

```yaml
---
- name: Converge
  hosts: all
  gather_facts: true
  gather_subset:
    - min

  pre_tasks:
    # Ensure Python 3 is available in the UBI image
    - name: Install python3 (UBI9 minimal image)
      ansible.builtin.raw: >
        rpm -q python3 || dnf install -y python3
      changed_when: false

  roles:
    - role: <namespace>.<collection>.<role_name>
```

### 3d. verify.yml

Write assertions using `ansible.builtin.assert` and `check_mode`:

```yaml
---
- name: Verify
  hosts: all
  gather_facts: false

  tasks:
    - name: Check that <thing> is installed
      ansible.builtin.package:
        name: <package>
        state: present
      check_mode: true
      register: pkg_check

    - name: Fail if package was not installed by the role
      ansible.builtin.assert:
        that:
          - not pkg_check.changed
        fail_msg: "<package> was not installed — role did not converge correctly"
        success_msg: "<package> is present"

    - name: Gather service status
      ansible.builtin.service_facts:

    - name: Assert service is running and enabled
      ansible.builtin.assert:
        that:
          - ansible_facts.services['<service>.service'].state == 'running'
          - ansible_facts.services['<service>.service'].status == 'enabled'
```

### 3e. Running Molecule

```bash
# Full test cycle (lint → create → converge → verify → destroy)
MOLECULE_INSTANCE_SUFFIX="$(id -un)-$(git branch --show-current)-manual-$$" \
  molecule test

# Iterative development
export MOLECULE_INSTANCE_SUFFIX="$(id -un)-$(git branch --show-current)-manual-$$"
molecule create          # start containers
molecule converge        # apply the role
molecule verify          # run assertions
molecule login           # drop into the container for inspection
molecule destroy         # tear down

# Idempotence check
molecule idempotence

# Lint only
molecule lint
```

### 3f. Molecule test isolation on shared hosts

When multiple agents may test different branches or repositories on the same
VM, make Podman resource names unique per run. Unsuffixed Molecule platform
names become Podman container names, so two branches with `name: ubi9-init`
can collide, reuse the wrong container, or destroy each other's test instance.

Use the pattern from `dev-env-rocky`: generate a short
`MOLECULE_INSTANCE_SUFFIX` from the user, current branch or directory, and PID
in the Makefile, pass it to every scenario invocation, and append it to every
Podman-backed platform name and shared cache path.

```make
.RECIPEPREFIX := >
MOLECULE_BRANCH := $(shell git branch --show-current 2>/dev/null || basename "$$PWD")
MOLECULE_INSTANCE_SUFFIX_GENERATED := $(shell \
  printf '%s-%s-%s' "$$(id -un)" "$(MOLECULE_BRANCH)" "$$$$" | \
  tr -c '[:alnum:]_.-' '-' | cut -c 1-48)
MOLECULE_INSTANCE_SUFFIX ?= $(MOLECULE_INSTANCE_SUFFIX_GENERATED)

.PHONY: molecule
molecule:
> cd roles/<role_name> && \
>   MOLECULE_INSTANCE_SUFFIX=$(MOLECULE_INSTANCE_SUFFIX) \
>   molecule test -s default
```

In `molecule.yml`, suffix every platform and any persistent test cache with
that variable:

```yaml
platforms:
  - name: ubi9-init-${MOLECULE_INSTANCE_SUFFIX}
    image: registry.access.redhat.com/ubi9/ubi-init:latest
    pre_build_image: true

provisioner:
  name: ansible
  config_options:
    defaults:
      fact_caching: jsonfile
      fact_caching_connection: >-
        ${MOLECULE_PROJECT_DIRECTORY}/.cache/facts-${MOLECULE_INSTANCE_SUFFIX}
```

For focused manual runs, set the suffix explicitly:

```bash
MOLECULE_INSTANCE_SUFFIX="$(id -un)-$(git branch --show-current)-manual-$$" \
  molecule converge -s default
MOLECULE_INSTANCE_SUFFIX="$(id -un)-$(git branch --show-current)-manual-$$" \
  molecule verify -s default
```

Rules for new scenarios:

- Never use static Podman platform names such as `instance`, `ubi9`, or
  `rocky10` on shared developer hosts.
- Keep `MOLECULE_INSTANCE_SUFFIX` generation in the project test wrapper or
  Makefile so normal gate commands are isolated by default.
- Do not use shell-style default expansion in platform names, such as
  `${MOLECULE_INSTANCE_SUFFIX:-local}`. Molecule interpolates environment
  variables; it does not run platform names through a shell.
- Include the suffix in fact-cache directories, temporary host paths, and any
  other shared resource that can survive across Molecule steps.
- Run Molecule scenarios sequentially in shared agent workspaces. Throughput
  comes from per-agent suffix isolation, not from one agent spawning several
  Podman scenarios at once.

### 3g. Molecule performance guidance

Molecule should be the default end-to-end test harness, but keep it fast
enough that developers will actually run it. Optimise in this order:

1. **Use Podman with pre-built, Python-enabled images**
   - Keep `pre_build_image: true` for pulled or locally built images that
     already contain Python, systemd support when needed, and common packages.
   - Prefer `registry.access.redhat.com/ubi9/ubi-init` for service roles and
     `registry.access.redhat.com/ubi9/ubi` for stateless roles.
   - If a role needs heavy prerequisites, create a local `Containerfile` for
     the Molecule image and build it outside the test loop:

     ```bash
     podman build -f Containerfile.molecule-ubi9 -t molecule-ubi9:latest .
     ```

     Then use:

     ```yaml
     platforms:
       - name: ubi9-init
         image: localhost/molecule-ubi9:latest
         pre_build_image: true
     ```

2. **Cache Galaxy dependencies and facts**
   - Keep Molecule dependency `force: false`.
   - Set `ANSIBLE_COLLECTIONS_PATH`, `ANSIBLE_ROLES_PATH`, and
     `fact_caching_connection` under a project-local `.cache/` directory.
   - Include `MOLECULE_INSTANCE_SUFFIX` in `fact_caching_connection` on shared
     hosts so concurrent branch runs do not reuse each other's facts.
   - Add `.cache/` to `.gitignore`; the cache is local state, not source.
   - Do not write playbooks that depend on cache files existing. A cache miss
     must only make the run slower, not change behaviour.

3. **Use the shortest useful Molecule command while developing**
   - Fast role iteration: `molecule converge`
   - Check assertions after a converge: `molecule verify`
   - Check idempotence after behaviour stabilises:
     `molecule converge && molecule idempotence`
   - Commit gate: `molecule test`
   - Keep containers during a focused local debugging loop with
     `molecule test --destroy=never`, then run `molecule destroy` when done.

4. **Limit fact gathering deliberately**
   - Use `gather_facts: false` for verify plays that only inspect files,
     commands, package state, or service state via explicit modules.
   - When facts are needed, prefer a small `gather_subset` such as `min`, then
     add only the subsets the role actually consumes.

5. **Reduce package-manager work**
   - Put package prerequisites in the image when they are stable test
     dependencies.
   - In the role, install package lists in one task instead of many single
     package tasks.
   - For apt-based images, use `cache_valid_time` when updating the cache:

     ```yaml
     - name: Install packages
       ansible.builtin.apt:
         name:
           - curl
           - git
           - python3
         state: present
         update_cache: true
         cache_valid_time: 3600
     ```

6. **Profile before guessing**
   - Keep `callbacks_enabled: timer, profile_tasks` in Molecule when
     investigating slow roles.
   - Review the slowest tasks, then remove profiling callbacks from normal CI
     output if they become noisy.

7. **Parallelise scenarios only on suitable runners**
   - Prefer Molecule's native worker mode over background shell jobs:

     ```bash
     molecule test --all --workers cpus-1
     ```

   - `--workers` requires collection mode with `galaxy.yml`.
   - Use `shared_state: true` in scenario configs when using the native
     worker mode so the default scenario owns shared create/destroy lifecycle.
   - Treat this as a CI or dedicated-runner optimisation. In shared agent
     workspaces, follow the host instructions and run gates sequentially.
   - Do not combine `--workers > 1` with `--destroy=never`.

8. **Use Mitogen only as an explicit compatibility choice**
   - Mitogen can speed task execution for compatible Ansible versions, but it
     is an extra strategy plugin and must be validated against the project's
     ansible-core version before becoming the default.
   - Do not add it to a generated scenario unless the user asks for it or the
     collection already standardises on it.

When improving a slow suite, time the baseline and each change:

```bash
time molecule create
time molecule converge
time molecule idempotence
time molecule verify
time molecule destroy
time molecule test
```

---

## Phase 4 — ansible-test: sanity

Sanity tests enforce coding standards. Run them from the collection root.

```bash
cd ~/ansible_collections/<namespace>/<collection>

# All sanity tests, local Python 3.12, no container
ansible-test sanity --python 3.12 --local

# Specific test
ansible-test sanity --python 3.12 --local --test validate-modules

# List available tests
ansible-test sanity --list-tests
```

Common failures and fixes:

| Test | Typical cause | Fix |
| --- | --- | --- |
| `validate-modules` | Missing `DOCUMENTATION`, `EXAMPLES`, or `RETURN` | Add the YAML documentation block |
| `pep8` | PEP 8 violations | `autopep8 --in-place` or fix manually |
| `pylint` | Linting errors | Fix or add `# pylint: disable=...` with justification |
| `ignore` | New test added to ignore list incorrectly | Remove from `tests/sanity/ignore-*.txt` |

---

## Phase 5 — ansible-test: unit tests

Unit tests live at `tests/unit/` and mirror the plugin structure.

```text
tests/unit/
└── plugins/
    └── modules/
        └── test_<module_name>.py
```

### 5a. Minimal unit test skeleton

```python
# tests/unit/plugins/modules/test_my_module.py
from __future__ import annotations

import json
import pytest

from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes

# Import the module under test
from ansible_collections.<namespace>.<collection>.plugins.modules import my_module


def set_module_args(args: dict) -> None:
    """Inject module arguments as if they arrived on STDIN."""
    args = json.dumps({"ANSIBLE_MODULE_ARGS": args})
    basic._ANSIBLE_ARGS = to_bytes(args)


class AnsibleExitJson(Exception):
    pass


class AnsibleFailJson(Exception):
    pass


def exit_json(*args, **kwargs):
    if "changed" not in kwargs:
        kwargs["changed"] = False
    raise AnsibleExitJson(kwargs)


def fail_json(*args, **kwargs):
    kwargs["failed"] = True
    raise AnsibleFailJson(kwargs)


@pytest.fixture(autouse=True)
def patch_ansible_module(monkeypatch):
    monkeypatch.setattr(basic.AnsibleModule, "exit_json", exit_json)
    monkeypatch.setattr(basic.AnsibleModule, "fail_json", fail_json)


class TestMyModule:
    def test_required_args_missing(self):
        set_module_args({})
        with pytest.raises(AnsibleFailJson) as exc:
            my_module.main()
        assert exc.value.args[0]["failed"] is True

    def test_state_present_creates_resource(self, mocker):
        set_module_args({
            "name": "test-resource",
            "state": "present",
        })
        mocker.patch.object(
            my_module,
            "_create_resource",
            return_value={"id": "abc123"},
        )
        with pytest.raises(AnsibleExitJson) as exc:
            my_module.main()
        result = exc.value.args[0]
        assert result["changed"] is True
        assert result["resource"]["id"] == "abc123"
```

### 5b. Running unit tests

```bash
cd ~/ansible_collections/<namespace>/<collection>

# All unit tests, local Python 3.12
ansible-test units --python 3.12 --local

# Specific module
ansible-test units --python 3.12 --local plugins/modules/my_module.py

# With coverage
ansible-test units --python 3.12 --local --coverage
ansible-test coverage report
```

---

## Phase 6 — ansible-test: integration tests

Use `ansible-test integration` for module and plugin integration contracts:
argument handling, idempotent module behaviour, return values, failure paths,
and collection-level integration targets.

For end-to-end role or workflow tests, prefer Molecule with Podman instead of
`ansible-test integration`. Molecule gives the scenario lifecycle that e2e
tests usually need: create, prepare, converge, idempotence, verify, cleanup,
and destroy against disposable Podman-managed systems.

`ansible-test integration` targets live here:

```text
tests/integration/
└── targets/
    └── <target_name>/
        ├── aliases          # marks: e.g. "posix/ci/group1"
        └── tasks/
            └── main.yml
```

### 6a. aliases file

```text
# tests/integration/targets/<target_name>/aliases
posix/ci/group1
```

Mark tests that cannot run in CI:

```text
unsupported
```

### 6b. tasks/main.yml skeleton

```yaml
---
# Integration test for <module_name>
- name: Test <module_name> — state=present creates resource
  <namespace>.<collection>.<module_name>:
    name: test-resource
    state: present
  register: result

- name: Assert resource was created
  ansible.builtin.assert:
    that:
      - result.changed
      - result.resource.name == "test-resource"

- name: Test idempotence — state=present on existing resource
  <namespace>.<collection>.<module_name>:
    name: test-resource
    state: present
  register: result_idem

- name: Assert no change on second run
  ansible.builtin.assert:
    that:
      - not result_idem.changed

- name: Test cleanup — state=absent removes resource
  <namespace>.<collection>.<module_name>:
    name: test-resource
    state: absent
  register: result_absent

- name: Assert resource was removed
  ansible.builtin.assert:
    that:
      - result_absent.changed
```

### 6c. Running integration tests locally

**Fully local** (controller = target = local Python 3.12 venv):

```bash
cd ~/ansible_collections/<namespace>/<collection>
export ANSIBLE_TEST_PREFER_PODMAN=1

ansible-test integration \
  --controller "origin:python=venv/3.12" \
  --target "controller:python=venv/3.12" \
  <target_name>
```

**Local controller, Podman-based managed node** (use when the test modifies
system state that would be unsafe on the host):

```bash
ansible-test integration \
  --controller "origin:python=venv/3.12" \
  --target "docker:registry.access.redhat.com/ubi9/ubi,python=3.12" \
  <target_name>
```

> The `docker:` key works for Podman when `ANSIBLE_TEST_PREFER_PODMAN=1` is
> set; the flag is internal to `ansible-test`.

**Local controller, SSH target** (use when tests require a persistent host,
e.g. testing against a VM):

```bash
ansible-test integration \
  --controller "origin:python=venv/3.12" \
  --target "ssh:user@192.168.1.10,python=3.12" \
  <target_name>
```

**All integration targets at once**:

```bash
ansible-test integration \
  --controller "origin:python=venv/3.12" \
  --target "controller:python=venv/3.12"
```

---

## Phase 7 — CI/CD integration (GitHub Actions reference)

A minimal workflow that runs sanity, units, and integration in sequence using
Podman:

```yaml
# .github/workflows/test.yml
name: CI
on: [push, pull_request]

jobs:
  sanity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          path: ansible_collections/<namespace>/<collection>

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install ansible-core
        run: pip install ansible-core

      - name: Sanity tests
        run: ansible-test sanity --python 3.12 --local
        working-directory: ansible_collections/<namespace>/<collection>

  units:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          path: ansible_collections/<namespace>/<collection>

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install ansible-core pytest pytest-mock

      - name: Unit tests
        run: ansible-test units --python 3.12 --local
        working-directory: ansible_collections/<namespace>/<collection>

  molecule:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Molecule + Podman driver
        run: pip install ansible-core molecule "molecule-plugins[podman]" ansible-lint

      - name: Run Molecule
        run: molecule test
        working-directory: roles/<role_name>
        env:
          ANSIBLE_TEST_PREFER_PODMAN: "1"
```

---

## Quick-reference command table

| Goal | Command |
| --- | --- |
| Full Molecule cycle | `molecule test` |
| E2E role/workflow test | `molecule test` with `driver.name: podman` |
| Apply role only | `molecule converge` |
| Run assertions only | `molecule verify` |
| Time slow Molecule step | `time molecule converge` |
| All Molecule scenarios on dedicated runner | `molecule test --all --workers cpus-1` |
| Shell into container | `molecule login` |
| Lint YAML + Ansible | `molecule lint` |
| Sanity (local) | `ansible-test sanity --python 3.12 --local` |
| Sanity (specific) | `ansible-test sanity --python 3.12 --local --test validate-modules` |
| Unit tests (local) | `ansible-test units --python 3.12 --local` |
| Unit tests (specific) | `ansible-test units --python 3.12 --local plugins/modules/my_module.py` |
| Integration (local) | `ansible-test integration --controller "origin:python=venv/3.12" --target "controller:python=venv/3.12" <target>` |
| Integration (Podman target) | `ansible-test integration --controller "origin:python=venv/3.12" --target "docker:registry.access.redhat.com/ubi9/ubi,python=3.12" <target>` |
| Integration (SSH target) | `ansible-test integration --controller "origin:python=venv/3.12" --target "ssh:user@host,python=3.12" <target>` |
| Coverage report | `ansible-test coverage report` |
| List integration targets | `ansible-test integration --list-targets` |

---

## Common pitfalls

**`ansible-test` cannot find the collection**
The collection must be at `~/ansible_collections/<ns>/<col>` and `ansible-test`
must be run from within that directory. A symlink from your checkout to that
path is fine.

**Podman containers fail to start systemd**
Ensure `container_manage_cgroup` SELinux boolean is set and that the
`molecule.yml` mounts `/sys/fs/cgroup` and sets `systemd: always`. Use
`ubi9/ubi-init`, not `ubi9/ubi`, for systemd-dependent roles.

**`pipelining` errors with Podman**
Set `pipelining: false` under `provisioner.config_options.connection` in
`molecule.yml`.

**`python3` not found inside UBI container**
Add a `pre_tasks` block in `converge.yml` that runs
`ansible.builtin.raw: rpm -q python3 || dnf install -y python3` before
gathering facts.

**`ansible-test integration` says `--docker` image not found**
Do not use the legacy `--docker` flag. Use the composite `--target
"docker:<image>,python=<version>"` form and ensure
`ANSIBLE_TEST_PREFER_PODMAN=1` is exported.

**Module documentation fails `validate-modules`**
Every module needs `DOCUMENTATION`, `EXAMPLES`, and `RETURN` as module-level
string variables, formatted as YAML inside triple-quoted strings.
