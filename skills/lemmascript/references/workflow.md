# LemmaScript workflow: backends, edit loop, CI, brownfield strategy

## Choosing a backend

**Dafny is the primary backend** and the default. It has the fuller feature set
(classes, `havoc`, `assume`, `perm`, most string/sequence helpers), the `regen`
merge workflow, and is currently the easier target for LLM-assisted proof
completion. **Lean** (via the Velvet and Loom forks) is stronger for inductive
proofs and offers a richer proof language, but automation is harder and several
features are absent. Gate backend-specific files with a file-level
`//@ backend dafny` directive. Several case studies prove the same annotated
source in both.

## CLI

```sh
npx lsc gen   --backend=dafny src/foo.ts   # generate artefacts
npx lsc check --backend=dafny src/foo.ts   # gen + additions-only check + dafny verify
npx lsc regen --backend=dafny src/foo.ts   # regenerate with three-way merge (Dafny only)
npx lsc extract src/foo.ts                 # dump Raw IR JSON (debugging)
npx lsc info    src/foo.ts                 # JSON summary of verified functions
```

Useful flags: `--time-limit=<s>` (per-verification-condition limit) and
`--extra-flags=...` (passed to the prover verbatim). When working against a
source checkout (recommended for brownfield work), replace `npx lsc` with
`npx tsx ../LemmaScript/tools/src/lsc.ts`; `tsx` picks up toolchain edits with
no build step.

## File structure

### Dafny (two files per source)

| File          | Generated?  | Purpose                                                                                                                                    |
| ------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `foo.ts`      | —           | TypeScript source with `//@` annotations                                                                                                   |
| `foo.dfy.gen` | Yes         | Generated Dafny; merge base. **Never edit.**                                                                                               |
| `foo.dfy`     | Seeded once | Source of truth: the generated code plus your proof additions (helper lemmas, ghost predicates, asserts, `modifies` clauses, spec bodies). |

The diff `foo.dfy.gen` → `foo.dfy` must be **additions only**; `lsc check`
enforces it. Large proof developments often move the bulk of lemmas to a
separate hand-written file (`domain.proofs.dfy`).

### Lean (four files per source)

| File             | Generated? | Purpose                                    |
| ---------------- | ---------- | ------------------------------------------ |
| `foo.types.lean` | Yes        | Type definitions and `Pure` namespace defs |
| `foo.def.lean`   | Yes        | Velvet `method` definitions                |
| `foo.spec.lean`  | No         | Ghost definitions and helper lemmas        |
| `foo.proof.lean` | No         | `prove_correct` with proof tactics         |

Regenerating the generated pair never destroys work in the hand-written pair.
Verify with `lake build`.

## The edit loop (Dafny)

1. Annotate the function (`//@ verify`, `requires`, `ensures`) and run
   `lsc regen --backend=dafny src/foo.ts`.
2. Run `dafny verify src/foo.dfy`.
3. On failure, decide where the fix belongs:
   - **In the `.ts`**: tighten a `requires`, weaken an `ensures`, add
     a missing `//@ invariant` or `//@ decreases`. Then `regen` —
     never delete the `.dfy` and `gen` fresh; the three-way merge
     preserves every proof addition.
   - **In the `.dfy`**: add a helper lemma, a ghost predicate, or a
     nudging `assert`. Purely additive.
4. For stubborn obligations, narrow the search:

   ```sh
   dafny verify --filter-symbol=myFunction_ensures src/foo.dfy
   dafny verify --isolate-assertions src/foo.dfy
   dafny verify --isolate-assertions --verification-time-limit 180 src/foo.dfy
   ```

An LLM may propose tactics, lemmas, and asserts — the prover checks them, so
the LLM is untrusted. What it cannot supply is a missing loop invariant: that
lives in the TypeScript and requires a regen.

## Proof techniques that recur across case studies

- **Refinement**: write a pure recursive spec that mirrors the loop
  one branch per case, prove `method == spec` once, then prove properties of
  the spec — everything transfers.
- **Snapshot ghost state**: `//@ ghost let original = xs` before a
  mutating loop turns invariant preservation into frame reasoning against a
  constant instead of set-subtraction over mutating state.
- **Permutation invariance**: prove a fold is a homomorphism from
  concatenation to addition, then lift order-independence with `perm(a, b)`.
- **In-place over parallel models**: prefer annotating the real
  function. Where a type resists import, shadow it with `//@ declare-type`
  (e.g. replace a function-valued field with plain data) so the shipped
  function remains the proof target.
- **Composition proofs**: encode ordering requirements (decode
  *before* check) as a single obligation over the composed pipeline so a
  reordered implementation fails the proof.

## Brownfield strategy

- Start with small pure functions: string helpers, predicates,
  parsers without I/O. Security predicates and CVE-shaped checks are high-value
  early targets.
- Clone LemmaScript as a sibling directory and start any coding agent
  in the **parent** directory so it can edit both trees; point it at the
  repository's AGENTS.md.
- Expect toolchain gaps (tech preview): unsupported methods, missed
  narrowing, generated Dafny that fails to typecheck. Fixes usually land in
  `tools/src/transform.ts`, `peephole.ts`, `dafny-emit.ts`, or `types.ts` — in
  a separate PR from the project change.
- Keep existing tests green; the annotations are comments, so the
  production build is untouched by construction.

## CI

`tools/check.sh dafny` reads `LemmaScript-files.txt` — one verified file per
line, optionally followed by a Dafny timeout and extra flags:

```text
src/utils/cookie.ts
src/middleware/ip-restriction/verified.ts 120
src/utils/ipaddr.verified.ts 30 --isolate-assertions
```

Add every newly verified file to it. Copy hono-lemmascript's GitHub Actions
workflow as the template: it clones LemmaScript as a sibling, installs Dafny,
runs `check.sh dafny`, and fails when generated files are out of date.

## Incremental adoption boundary

Verification does not need to cover the codebase. The `@lemmafit/contracts`
layer enforces, at runtime, that unverified TypeScript interacts correctly with
verified modules: proofs inside (zero runtime cost), contracts at the boundary,
plain TypeScript outside. State the trust boundary explicitly — UI, I/O, auth,
clock, and adapter code are trusted, not proved.
