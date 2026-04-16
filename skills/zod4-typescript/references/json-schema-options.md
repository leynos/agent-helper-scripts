# JSON Schema conversion options

## Zod → JSON Schema (`z.toJSONSchema()`)

```ts
z.toJSONSchema(schema, options?)
```

### Options

| Option               | Type                                     | Description                                              |
|----------------------|------------------------------------------|----------------------------------------------------------|
| `name`               | `string`                                 | Root schema title                                         |
| `$refStrategy`       | `"root"` \| `"relative"` \| `"none"`    | How to generate `$ref` pointers for reused schemas       |
| `effectStrategy`     | `"input"` \| `"output"` \| `"any"`      | Which side of transforms/pipes to represent               |
| `definitions`        | `Record<string, ZodTypeAny>`             | Named schemas to emit as `$defs`                         |
| `errorMessages`      | `boolean`                                | Embed Zod error messages as `errorMessage`               |
| `markdownDescription`| `boolean`                                | Emit `markdownDescription` alongside `description`       |

### Metadata propagation

Any metadata stored in `z.globalRegistry` (via `.meta()` or `.describe()`) is
automatically included in the JSON Schema output.

```ts
const schema = z.object({
  name: z.string().meta({ title: "User name", examples: ["alice"] }),
  age: z.int().meta({ description: "Age in years" }),
});

z.toJSONSchema(schema);
// {
//   type: "object",
//   properties: {
//     name: { type: "string", title: "User name", examples: ["alice"] },
//     age: { type: "integer", description: "Age in years", minimum: ..., maximum: ... },
//   },
//   required: ["name", "age"],
//   additionalProperties: false,
// }
```

### Named definitions via `definitions`

Provide a definitions map to emit reusable `$defs` and `$ref` pointers:

```ts
const Address = z.object({ street: z.string(), city: z.string() });
const User = z.object({ name: z.string(), address: Address });

z.toJSONSchema(User, {
  definitions: { Address },
});
// properties.address → { "$ref": "#/$defs/Address" }
```

### Effect strategy

Controls how transforms and pipes appear in the generated schema:

- `"input"` (default): uses the input side of transforms
- `"output"`: uses the output side
- `"any"`: uses `{}` (any) for transformed schemas

### Schema type mapping

Zod 4 maps schemas to JSON Schema as follows (non-exhaustive):

| Zod schema               | JSON Schema                              |
|--------------------------|------------------------------------------|
| `z.string()`             | `{ type: "string" }`                     |
| `z.email()`              | `{ type: "string", format: "email" }`    |
| `z.int()`                | `{ type: "integer", ... }`               |
| `z.number()`             | `{ type: "number" }`                     |
| `z.boolean()`            | `{ type: "boolean" }`                    |
| `z.null()`               | `{ type: "null" }`                       |
| `z.array()`              | `{ type: "array", items: ... }`          |
| `z.object()`             | `{ type: "object", ... }`                |
| `z.union()`              | `{ anyOf: [...] }`                       |
| `z.xor()`                | `{ oneOf: [...] }`                       |
| `z.discriminatedUnion()` | `{ anyOf: [...] }` with discriminator    |
| `z.literal()`            | `{ const: ... }` or `{ enum: [...] }`    |
| `z.optional()`           | removes from `required`                  |
| `z.nullable()`           | adds `null` to type                      |

### `additionalProperties`

By default, `z.object()` produces `additionalProperties: false`.
`z.looseObject()` produces `additionalProperties: true`.
`z.strictObject()` produces `additionalProperties: false`.


## JSON Schema → Zod (`z.fromJSONSchema()`)

**Experimental** (4.3+). May change in minor releases. No guarantee of round-trip fidelity.

```ts
const zodSchema = z.fromJSONSchema(jsonSchema, options?);
```

### Supported drafts

- JSON Schema draft-2020-12
- JSON Schema draft-7
- JSON Schema draft-4
- OpenAPI 3.0

### Options

| Option     | Type          | Description                    |
|------------|---------------|--------------------------------|
| `errorMap` | `ZodErrorMap`  | Custom error map for the schema |

### Limitations

- No 1:1 round-trip soundness: `schema → toJSONSchema → fromJSONSchema` may not produce
  an equivalent schema, because some Zod features (refinements, transforms, codecs) have
  no JSON Schema representation, and vice versa.
- Complex JSON Schema features like `$dynamicRef`, `if/then/else`, and certain
  `patternProperties` combinations may not convert faithfully.
- The returned schema is loosely typed (`ZodTypeAny`) — you lose the compile-time type
  information that hand-authored Zod schemas provide.

### Practical use case

Useful for consuming external JSON Schema definitions (e.g. from a schema registry or
OpenAPI spec) and applying Zod's runtime validation:

```ts
const externalSchema = await fetch("/api/schema/user").then(r => r.json());
const validator = z.fromJSONSchema(externalSchema);

const result = validator.safeParse(untrustedData);
```
