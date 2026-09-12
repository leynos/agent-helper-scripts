# Don't panic: a hitchhiker’s guide to building an error-recovering parser with **Chumsky**

> *A completely remarkable book. Probably the most remarkable, certainly the
> most successful book ever to come out of the great publishing corporations of
> Ursa Minor.*

## 1 Know where the towel (and grammar) is

Before summoning Chumsky’s combinators, capture the grammar — preferably in
Extended Backus–Naur Form, biro on a napkin, or etched into the side of a Vogon
constructor fleet. Chumsky mirrors whatever it receives; revise the napkin
later, and the team will be spelunking inside recursive lambdas at 2 a.m.

### Checklist

- A complete token list
- Precedence rules in plain English (“multiply before add, semicolons end
  statements, tea before Arthur, etc.”)
- Examples of legal *and* illegal programmes.

## 2 Feed it tokens, not breadcrumbs

Chumsky is much happier when it’s nibbling on a neat `Vec<TokenSpan>` than on
raw characters. Use the `logos` crate (or a favourite lexical life-form) to
slice the source first. This yields:

- Cleaner error messages (“unexpected `KwIf`”)
- Simple span maths: every token already knows its start & end byte
- The freedom to invent helpful token kinds (e.g. “Indent”, “Dedent”, “Unified
  Field Theory Symbol”)

## 3 Dealing with left-recursion, infinite loops, and other things that ate Betelgeuse

Left-recursive rules make top-down parsers seize up like Marvin’s shoulder
joints. Rewrite them with repetition combinators (`many()`, `foldl()`), or use
a precedence-climbing expression parser.

Forward references? Wrap them in `recursive(|expr| { … })`, so Chumsky can see
round corners.

Ambiguity? Break overlapping prefixes into separate branches *first* and only
then hand the survivors to `choice()`.

## 4 Panic? No. Recovery? Yes

Error recovery is what turns the parser from Vogon poetry into a Babel fish.

1. **Anchors:** Tell Chumsky that `;`, `}`, `]`, and other setters of cosmic
   balance are “hard delimiters”. Use `recover_with(skip_until([]))`.
2. **Labels:** Tag sub-parsers with `.labelled("expression")` so the diagnostics
   mention something friendlier than “expected `Unknown(42)`”.
3. **Tri-state nodes:** Return `Option<AstNode>`; missing bits propagate, but
   the parser soldiers on.

In practice, it is common to compose the built-ins via
`recover_with(nested_delimiters())` and `recover_with(skip_until(…))`,
threading in a couple of bespoke closures, and quickly look like the local
authority on parser resilience.

## 5 Getting the Codex to behave (or: how to babysit a 2-metre tall neural net)

Codex is a marvellous companion so long as the operator observes a few rules:

- **Constrain its universe.** Include the token enums, abstract syntax tree
  structures, and the precise combinators in the prompt.
- **Ask for one production at a time.** Whole-grammar requests invite
  hallucinations of alternate dimensions.
- **Round-trip ruthlessly.** Generate random abstract syntax trees →
  pretty-print → reparse → assert equality. Failures mean Codex (or the prompt
  author) has misremembered the Restaurant at the End of the File.

## 6 Linting: the first sip of the semantic analyser

Treat the linter as the pre-solver phase of the semantic analyser:

1. Build symbol tables and scope graphs.
2. Run the cheap local checks (duplicates, arity, type holes).
3. Emit a constraint set and immediately feed it to the solver; conflicts become
   diagnostics.

Because an incremental solver can recheck only what changed, teams can deliver
editor feedback faster than a hyperspace bypass.

## 7 Keeping the whole show flying

- **Continuous Integration (CI) pipeline:** `cargo insta test`,
  `cargo clippy --deny warnings`, and the round-trip parser tests on every push.
- **Editor integration:** Convert Chumsky’s `Rich` errors into Language Server
  Protocol (LSP) diagnostics; line/column already sorted.
- **Performance guardrails:** Benchmark on a representative large input. If a
  commit slows parsing or solving by > 20 %, trigger the Heart of Gold and
  revert reality.

______________________________________________________________________

## Too long; didn’t read (because life is short and full of Thursdays)

Write the grammar first, lex separately, tame left-recursion, anchor recovery
on hard delimiters, keep Codex on a tight leash, and let the linter double as
the solver’s warm-up act.

And always keep the towel handy. It’s the most massively useful thing an
interstellar parser hacker can carry.
