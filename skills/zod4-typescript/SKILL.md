---
name: zod4-typescript
description: >
  Use Zod 4 idiomatically in TypeScript projects for schema validation, type inference,
  serialization/deserialization, JSON Schema interop, and error handling. Trigger whenever
  the user mentions Zod, schema validation in TypeScript, runtime type checking, form
  validation, API contract validation, z.object, z.string, z.infer, z.parse, or is writing
  TypeScript code that involves parsing, validating, or transforming untrusted data. Also
  trigger when migrating from Zod 3 to Zod 4, or when the user references Zod schemas in
  the context of OpenAPI, JSON Schema, tRPC, React Hook Form, or similar integrations.
  This skill covers Zod 4.x (including 4.1 codecs, 4.3 features) and explicitly flags
  Zod 3 assumptions that no longer hold.
---

# Zod 4 for TypeScript

Zod 4 is the current stable release (latest: 4.3.x). It ships three packages from a single
`zod` install: `zod` (classic), `zod/mini` (tree-shakable), and `zod/v4/core` (for library
authors). TypeScript ≥5.5 and `strict: true` in tsconfig are hard requirements.

```
npm install zod@^4.0.0
```

Import the classic API throughout unless bundle size constraints demand `zod/mini`:

```ts
import * as z from "zod";
```

> **Navigating this skill**
>
> §1–§4 cover daily usage: schemas, parsing, error handling, type inference.
> §5 covers the Zod 3 → 4 migration traps — **read this if porting existing code**.
> §6–§8 cover powerful but less frequently needed features:
>   - §6 **Codecs** — bidirectional serialization (API boundaries, date handling)
>   - §7 **Metadata, registries, and JSON Schema** — OpenAPI generation, schema documentation
>   - §8 **Advanced patterns** — recursive types, template literals, discriminated unions,
>     `z.xor`, branded types, `zod/mini`, library authoring via `zod/v4/core`
>
> For codec recipes, JSON Schema options, and `zod/mini` API mappings, see the
> `references/` directory.


## §1 Defining schemas

Prefer top-level format constructors over the deprecated method chain. This is both more
tree-shakable and the direction of the API going forward (method equivalents will be removed
in Zod 5).

```ts
// ✅ Zod 4 idiomatic
z.email()
z.uuidv4()
z.url()
z.ipv4()
z.iso.datetime()

// ❌ Deprecated — still works, will be removed in next major
z.string().email()
z.string().uuid()
```

### Primitives and literals

All standard primitives: `z.string()`, `z.number()`, `z.bigint()`, `z.boolean()`,
`z.date()`, `z.null()`, `z.undefined()`, `z.void()`, `z.symbol()`, `z.never()`,
`z.any()`, `z.unknown()`. Note: `z.literal()` no longer accepts symbols.

`z.literal()` now accepts arrays for multi-value literals:

```ts
const HttpOk = z.literal([200, 201, 204]); // 200 | 201 | 204
```

### Numeric formats

Fixed-width types with built-in range constraints:

```ts
z.int()      // safe integers only
z.int32()    // [-2^31, 2^31-1]
z.uint32()   // [0, 2^32-1]
z.float32()  // single-precision range
z.float64()  // double-precision range
z.int64()    // ZodBigInt — exceeds safe integer range
z.uint64()   // ZodBigInt
```

### Objects

```ts
const User = z.object({
  name: z.string(),
  age: z.int(),
  email: z.email(),
});

type User = z.infer<typeof User>;
```

For strict (reject unknown keys) or loose (pass-through unknown keys) objects, use the
top-level constructors rather than the deprecated `.strict()` / `.passthrough()` methods:

```ts
z.strictObject({ name: z.string() });   // rejects unrecognized keys
z.looseObject({ name: z.string() });    // passes through unrecognized keys
z.object({ name: z.string() });         // strips unrecognized keys (default)
```

#### Extending and composing objects

Use `.extend()` or shape spread. `.merge()` is deprecated.

```ts
const WithName = Base.extend({ name: z.string() });
// best tsc performance — use shape spread:
const WithName2 = z.object({ ...Base.shape, name: z.string() });
// .safeExtend() — preserves refinements and enforces extends constraint (4.1+)
const WithAge = Base.safeExtend({ age: z.int() });
```

**⚠ Zod 3 trap:** `.extend()` on a refined schema now throws if you overwrite existing
properties. Use `.safeExtend()` to add new properties preserving refinements, or rebuild
from `.shape`.

### Enums

`z.nativeEnum()` is deprecated. `z.enum()` now handles both string arrays and TypeScript
enums:

```ts
const Status = z.enum(["active", "inactive", "suspended"]);

// TypeScript enum (not recommended, but supported)
enum Direction { Up = "UP", Down = "DOWN" }
const Dir = z.enum(Direction);
```

Access values via `.enum` (`.Enum` and `.Values` are removed):

```ts
Status.enum.active; // "active"
```

### Records

`z.record()` now requires two arguments (key schema, value schema). The single-argument
form is removed.

```ts
z.record(z.string(), z.number()); // Record<string, number>
```

When the key schema is a `z.enum()`, Zod 4 exhaustively checks all enum members exist as
keys. For partial records, use `z.partialRecord()`. For pass-through of non-matching keys,
use `z.looseRecord()`.

### Arrays and tuples

```ts
z.array(z.string()).min(1).max(10);

// nonempty — ⚠ Zod 4 infers string[], not [string, ...string[]]
z.array(z.string()).nonempty();

// For the old tuple-style nonempty, use z.tuple with rest:
z.tuple([z.string()], z.string()); // [string, ...string[]]
```

### File validation

```ts
z.file().min(10_000).max(1_000_000).mime(["image/png", "image/jpeg"]);
```


## §2 Parsing and safe parsing

```ts
const result = User.safeParse(untrustedInput);
if (result.success) {
  result.data; // fully typed User
} else {
  result.error; // ZodError
}

// Throwing variant
const user = User.parse(untrustedInput);
```

Async variants (`parseAsync`, `safeParseAsync`) exist for schemas with async refinements
or transforms.


## §3 Error handling

### Pretty printing

```ts
const err = User.safeParse(bad).error!;
console.log(z.prettifyError(err));
// ✖ Invalid input: expected string, received number
//   → at name
```

### Structured error trees

`.format()` and `.flatten()` are deprecated. Use `z.treeifyError()`:

```ts
const tree = z.treeifyError(err);
// tree.name?.errors  → string[]
// tree.age?.errors   → string[]
```

### Customizing error messages

A single unified `error` parameter replaces `message`, `invalid_type_error`,
`required_error`, and `errorMap`:

```ts
z.string().min(5, { error: "Too short" });

// Function form — replaces errorMap, invalid_type_error, required_error
z.string({
  error: (issue) =>
    issue.input === undefined ? "Required" : "Expected a string",
});

// Returning undefined yields to the next error map in the chain
z.string().min(5, {
  error: (issue) => issue.code === "too_small" ? `Need >${issue.minimum} chars` : undefined,
});
```

### Internationalization

```ts
z.config(z.locales.en()); // or z.locales.de(), z.locales.ja(), etc.
```

### Issue types

Zod 4 consolidated issue types. The base interface remains stable:

```ts
interface $ZodIssueBase {
  readonly code?: string;
  readonly input?: unknown;
  readonly path: PropertyKey[];
  readonly message: string;
}
```

Notable merges: `invalid_enum_value`/`invalid_literal` → `invalid_value`;
`invalid_date`/`not_finite` → `invalid_type`. Infinities always rejected by `z.number()`.


## §4 Type inference

```ts
type UserInput = z.input<typeof User>;   // type before transforms
type UserOutput = z.output<typeof User>;  // type after transforms (= z.infer)
type User = z.infer<typeof User>;         // alias for z.output
```

**⚠ Zod 3 trap:** `z.any()` and `z.unknown()` properties in objects are no longer
optional in the inferred type. `{ a: z.any() }` infers `{ a: any }`, not `{ a?: any }`.


## §5 Migration traps (Zod 3 → 4)

This section is a **concise** checklist. For the full migration guide, see
https://zod.dev/v4/changelog. A community codemod `zod-v3-to-v4` is available.

### High impact

1. **`message` → `error`** in all refinement / check options. `message` still works but is
   deprecated.
2. **`invalid_type_error` / `required_error`** — dropped entirely. Use `error` function
   form.
3. **`errorMap`** — renamed to `error`. Can now return a plain string or undefined.
4. **`.format()` / `.flatten()`** — deprecated. Use `z.treeifyError()`.
5. **`.merge()`** — deprecated. Use `.extend(other.shape)` or shape spread.
6. **`z.nativeEnum()`** — deprecated. `z.enum()` handles TS enums directly.
7. **`z.record(valueSchema)`** — single-arg form removed. Always pass key + value schemas.
8. **`z.string().email()`** etc — deprecated. Use `z.email()`, `z.url()`, `z.uuidv4()`.
9. **`.strict()` / `.passthrough()`** — deprecated. Use `z.strictObject()` /
   `z.looseObject()`.
10. **`z.function()`** — no longer a schema. New factory API with `input`/`output` params.

### Semantic changes (silent breakage risk)

11. **`z.number()` rejects `Infinity`/`-Infinity`.**
12. **`.int()` rejects unsafe integers** (outside `Number.MIN_SAFE_INTEGER` ..
    `MAX_SAFE_INTEGER`).
13. **`.default()` now short-circuits.** The default value must match the *output* type,
    not the input type. For pre-parse defaults, use `.prefault()`.
14. **Defaults inside optional fields are applied:** `z.string().default("x").optional()`
    yields `"x"` when the key is missing, not `undefined`.
15. **`z.unknown()` / `z.any()` object properties are required** in the inferred type.
16. **`.nonempty()` on arrays infers `T[]`**, not `[T, ...T[]]`.
17. **Refinements via type predicates no longer narrow** in `.refine()` (restored in 4.3
    — see §8).
18. **Error map precedence changed:** schema-level `error` now takes priority over
    parse-time `error`.
19. **`z.record()` with enum keys is now exhaustive** — all enum members must be present.
    Use `z.partialRecord()` for the old behavior.
20. **`.pick()` / `.omit()` on refined schemas now throws** (4.3+) — previously silently
    dropped refinements.


## §6 Codecs (4.1+)

Codecs solve the serialization boundary problem. Where `.transform()` is unidirectional,
a codec defines both directions, enabling `.encode()` to round-trip data.

```ts
const isoDate = z.codec(z.iso.datetime(), z.date(), {
  decode: (iso) => new Date(iso),
  encode: (date) => date.toISOString(),
});

isoDate.decode("2025-01-15T10:30:00.000Z"); // → Date
isoDate.encode(new Date());                  // → "2025-01-15T..."
isoDate.parse("2025-01-15T10:30:00.000Z");  // → Date (same as decode)
```

**Key constraint:** `.transform()` is incompatible with `.encode()` — calling `.encode()`
on a pipeline containing `.transform()` throws. Refactor to codecs when you need
round-tripping.

Codecs compose via `.pipe()`:

```ts
const JsonParams = jsonCodec.pipe(z.object({ name: z.string(), age: z.number() }));
JsonParams.decode('{"name":"Alice","age":30}'); // → { name: "Alice", age: 30 }
JsonParams.encode({ name: "Bob", age: 25 });    // → JSON string
```

Most non-transforming schemas behave identically under `.decode()` and `.encode()`. The
behaviour diverges for codecs, `.default()` (short-circuits on decode, rejects `undefined`
on encode), `.catch()` (decode only), and `z.stringbool()` (a codec internally).

For a full library of codec implementations (JSON, hex, base64, URL, epoch, etc.), see
`references/codec-recipes.md`.


## §7 Metadata, registries, and JSON Schema

### Registries

Store strongly typed metadata *outside* the schema itself, in a registry:

```ts
const apiRegistry = z.registry<{
  title: string;
  description: string;
  deprecated?: boolean;
}>();

const Email = z.email();
apiRegistry.add(Email, { title: "Email", description: "User email address" });
apiRegistry.get(Email); // → { title: "Email", ... }
```

### Global registry and `.meta()`

```ts
z.string().meta({
  id: "user_name",
  title: "Username",
  description: "Unique handle",
  examples: ["alice42"],
});

// Shorthand for description only (.describe() still works but .meta() is preferred)
z.string().meta({ description: "A username" });
```

### JSON Schema conversion

```ts
// Zod → JSON Schema
const jsonSchema = z.toJSONSchema(User);

// JSON Schema → Zod (experimental, 4.3+)
const zodSchema = z.fromJSONSchema({
  type: "object",
  properties: { name: { type: "string" } },
  required: ["name"],
});
```

`z.toJSONSchema()` pulls metadata from `z.globalRegistry` automatically. For full options
(including `$refStrategy`, `effectStrategy`, named definitions), see
`references/json-schema-options.md`.

`z.fromJSONSchema()` supports JSON Schema draft-2020-12, draft-7, draft-4, and OpenAPI 3.0.
Consider it experimental — no guarantee of round-trip soundness through
`toJSONSchema → fromJSONSchema`.


## §8 Advanced patterns

### Recursive types (native — no casts needed)

Use getter syntax. Unlike Zod 3's `z.lazy()` pattern, no type assertion required, and the
result is a full `ZodObject` with `.pick()`, `.partial()`, etc.

```ts
const Category = z.object({
  name: z.string(),
  get subcategories() { return z.array(Category); },
});
type Category = z.infer<typeof Category>;
// { name: string; subcategories: Category[] }
```

Mutual recursion works identically via cross-referencing getters.

### Template literal types

Represent TypeScript template literal types with validated parsing. String format schemas
(e.g. `z.email()`) work inside — their internal regexes are concatenated. Custom
refinements are **not** enforced.

```ts
const CssValue = z.templateLiteral([z.number(), z.enum(["px", "em", "rem", "%"])]);
CssValue.parse("16px"); // ✅
```

### Discriminated unions (upgraded)

Now support union/pipe discriminators and compose — a discriminated union can be a member
of another. See the `z.discriminatedUnion()` docs for examples.

### `z.xor()` (4.3+)

Exclusive union — requires exactly one match. Produces `oneOf` in JSON Schema.

```ts
const schema = z.xor([
  z.object({ type: z.literal("user"), name: z.string() }),
  z.object({ type: z.literal("admin"), role: z.string() }),
]);
```

### Type predicate refinements (restored in 4.3)

```ts
const isString = z.unknown().refine((v): v is string => typeof v === "string");
type T = z.output<typeof isString>; // string
```

### Branded types (enhanced in 4.3)

```ts
z.string().brand<"UserId">();           // output only (default)
z.string().brand<"UserId", "in">();     // input only
z.string().brand<"UserId", "inout">(); // both
```

### `.apply()` (4.3+) — factor out reusable check pipelines

```ts
const clamp = <T extends z.ZodNumber>(s: T) => s.min(0).max(100);
z.number().apply(clamp).nullable();
```

### `z.stringbool()` — env var booleans

Truthy: "true", "1", "yes", "on", "y", "enabled". Falsy: "false", "0", "no", "off", "n",
"disabled". Customizable via `{ truthy: [...], falsy: [...] }`.

### Zod Mini and library authoring

Zod Mini (`zod/mini`): functional, tree-shakable API (~1.88 KB gzipped). See
`references/zod-mini-mapping.md` for the full method→function mapping.

For library authors: depend on `zod/v4/core` for compatibility with both Classic and Mini.
It exports `$ZodType`, `$ZodCheck`, `$ZodError` and top-level parsing functions. The
`"zod/v4/core"` subpath is a permanent, stable permalink.


## Best practices

1. **Top-level format constructors** (`z.email()`, not `z.string().email()`).
2. **`z.strictObject()` at API boundaries** to catch unexpected fields.
3. **Codecs for serialization boundaries** — API responses, form data, env vars.
4. **`.meta()` and registries** to drive JSON Schema / OpenAPI generation.
5. **Shape spread over `.extend()`** for best tsc performance in large schemas.
6. **`.safeParse()` over `.parse()`** in user-facing paths — avoid try/catch for expected
   validation failures.
7. **`z.prettifyError()` for humans; `z.treeifyError()` for programmatic access.**
8. **`z.int()` / `z.int32()`** over `z.number().int()` for clarity and built-in ranges.
9. **`z.xor()` when exactly one variant must match** — correct `oneOf` in JSON Schema.
10. **`z.stringbool()` for env vars** instead of hand-rolled coercion.

## Forward compatibility

- Method-form string formats (`.email()`, `.uuid()`) will be removed in Zod 5.
- `.strict()`, `.passthrough()`, `.merge()`, `.describe()` — deprecated but retained.
- `z.fromJSONSchema()` is experimental and may change in minor releases.
- `zod/v4/core` is the stable contract for library authors — prefer it over internals.
