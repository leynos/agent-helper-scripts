# Zod Mini API mapping

`zod/mini` is a tree-shakable functional API that produces the same runtime schemas as
classic `zod`. Core bundle ~1.88 KB gzipped (vs ~5.36 KB classic, ~12.47 KB Zod 3).

**When to use:** edge functions, serverless, mobile web, or any context with strict
bundle size constraints.

**When not to use:** if bundle size is not a hard constraint, classic `zod` provides a
more ergonomic method-chaining API.

Both APIs are fully interoperable — a schema created with `zod/mini` can be used anywhere
a `zod` schema is expected, and vice versa.

```ts
import * as z from "zod/mini";
```

## Method → function mapping

| Classic `zod`                        | `zod/mini`                                       |
|--------------------------------------|--------------------------------------------------|
| `z.string().optional()`              | `z.optional(z.string())`                         |
| `z.string().nullable()`              | `z.nullable(z.string())`                         |
| `z.string().array()`                 | `z.array(z.string())`                            |
| `z.string().or(z.number())`          | `z.union([z.string(), z.number()])`              |
| `z.string().and(other)`              | `z.intersection(z.string(), other)`              |
| `z.string().default("hello")`        | `z.default(z.string(), "hello")`                 |
| `z.string().catch("fallback")`       | `z.catch(z.string(), "fallback")`                |
| `schema.pipe(other)`                 | `z.pipe(schema, other)`                          |
| `obj.extend({ age: z.number() })`    | `z.extend(obj, { age: z.number() })`             |
| `obj.pick({ name: true })`           | `z.pick(obj, { name: true })`                    |
| `obj.omit({ age: true })`            | `z.omit(obj, { age: true })`                     |
| `obj.partial()`                      | `z.partial(obj)`                                 |
| `obj.required()`                     | `z.required(obj)`                                |
| `obj.keyof()`                        | `z.keyof(obj)`                                   |


## Checks via `.check()`

Instead of chaining methods like `.min()`, `.max()`, `.email()`, Mini schemas use
`.check()` with top-level check constructors:

```ts
z.array(z.number()).check(
  z.minLength(5),
  z.maxLength(10),
  z.refine(arr => arr.includes(42))
);

z.string().check(
  z.minLength(1),
  z.maxLength(255),
  z.regex(/^[a-z]+$/i)
);

z.number().check(
  z.gt(0),
  z.lte(100),
  z.multipleOf(5)
);
```

### Available check constructors

**Custom:** `z.refine()`

**Numeric:** `z.lt()`, `z.lte()` (alias: `z.maximum()`), `z.gt()`, `z.gte()` (alias:
`z.minimum()`), `z.positive()`, `z.negative()`, `z.nonpositive()`, `z.nonnegative()`,
`z.multipleOf()`

**Size/length:** `z.maxSize()`, `z.minSize()`, `z.size()`, `z.maxLength()`,
`z.minLength()`, `z.length()`

**String:** `z.regex()`, `z.lowercase()`, `z.uppercase()`, `z.includes()`,
`z.startsWith()`, `z.endsWith()`

**Object property:** `z.property(key, schema)`

**File:** `z.mime()`

**Overwrites (mutate value, don't change type):** `z.overwrite()`, `z.normalize()`,
`z.trim()`, `z.toLowerCase()`, `z.toUpperCase()`


## Parsing — identical API

```ts
schema.parse(data);
schema.safeParse(data);
await schema.parseAsync(data);
await schema.safeParseAsync(data);
```


## Codecs in Mini

The `.decode()` / `.encode()` instance methods are not available on Mini schemas. Use the
equivalent top-level functions:

```ts
import * as z from "zod/mini";

const isoDate = z.codec(z.string(), z.date(), {
  decode: (s) => new Date(s),
  encode: (d) => d.toISOString(),
});

z.decode(isoDate, "2025-01-15T10:30:00.000Z"); // → Date
z.encode(isoDate, new Date());                   // → string
```


## Metadata in Mini (4.3+)

Mini exports `z.meta()` and `z.describe()` as check-style functions used with `.with()`:

```ts
z.string().with(z.describe("A user name"));
z.number().with(z.meta({ deprecated: true }));
```


## Slugify in Mini (4.3+)

```ts
z.string().with(z.slugify()).parse("Hello World"); // "hello-world"
```
