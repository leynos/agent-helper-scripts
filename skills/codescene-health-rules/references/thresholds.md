# CodeScene Threshold Keys

Threshold overrides go in the `"thresholds"` array inside a `rule_set`:

```json
"thresholds": [
  { "name": "function_cyclomatic_complexity_warning", "value": 12 }
]
```

The full template is available from **Project Configuration → Hotspots → Download
template**. That template is authoritative; the values below are confirmed from
documentation and known examples, but CodeScene may add or rename thresholds across
versions.

---

## Confirmed Threshold Keys

| Key | What it Controls | Typical Default | Notes |
|-----|-----------------|-----------------|-------|
| `function_cyclomatic_complexity_warning` | Cyclomatic complexity at which a function is flagged by the Complex Method rule. | ~8–10 (language-dependent) | Raise to 15–20 for test code where complex parametrised setups are common. |
| `function_nesting_depth_warning` | Maximum nesting depth before Nested Complexity fires. | ~3–4 | Lowering to 2 is strict; useful for safety-critical code. Raising above 4 is rarely advisable. |

---

## Inferred / Likely Threshold Keys

These names follow CodeScene's documented naming conventions and correspond to
compound rule components described in the docs. **Verify against your downloaded
template before committing**, as CodeScene does not document all threshold keys
publicly and ignores unknown keys silently.

| Key (likely) | Corresponding Rule | Description |
|-------------|-------------------|-------------|
| `function_lines_of_code_warning` | Large Method, Brain Method | LoC threshold for a function to be considered large. |
| `module_lines_of_code_warning` | Lines of Code, Brain Class | LoC threshold at module/file level. |
| `assertion_block_size_warning` | Large Assertion Blocks | Number of consecutive asserts before the smell fires. |
| `duplication_block_size_warning` | DRY Violations | Minimum block size for duplication detection. |

---

## Language Defaults

Default values vary by language — Python and Ruby tend to have higher LoC thresholds
than C++ or Java because idiomatic code is denser. The authoritative per-language
defaults are in the `default-rules.zip` downloadable from:

> https://helpcenter.codescene.com/articles/6084507-what-are-the-default-threshold-values-for-different-programming-languages

Languages with documented defaults in that zip:
C#, C++, JavaScript, Python, Ruby, PHP, Clojure, Groovy, Swift, Kotlin, Rust, Scala,
TensorFlow, MatLab, Go, Euphoria, Dart, Tcl, Visual Basic, Perl, Erlang.

---

## Override Strategy

Thresholds are scalpels; use them when a rule weight override is too blunt. For example:

- You want "Complex Method" to still fire, but your team is comfortable with
  cyclomatic complexity up to 12 → raise `function_cyclomatic_complexity_warning`
  rather than lowering the rule weight.
- You want to allow deeper nesting in generated code → raise
  `function_nesting_depth_warning` scoped to `src/generated/**` rather than globally.

Overridden thresholds appear in the virtual code review for each affected file, so
developers always know non-default values are in effect.
