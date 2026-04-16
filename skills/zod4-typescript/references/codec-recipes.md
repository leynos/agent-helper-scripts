# Codec recipes

Codecs encapsulate bidirectional transformations. Unlike `.transform()` (decode only),
codecs support `.encode()` for round-tripping data across serialization boundaries.

Introduced in Zod 4.1. Available on classic `zod` schemas via `.decode()` / `.encode()`
methods. On `zod/mini` schemas, use `z.decode(schema, value)` and
`z.encode(schema, value)` top-level functions.

## Core rules

1. `.transform()` is incompatible with `.encode()` — mixing them throws at runtime.
2. `.default()` short-circuits on decode (returns default for `undefined`), rejects
   `undefined` on encode.
3. `.catch()` applies on decode only.
4. Codecs compose via `.pipe()` — the pipe reverses direction during encode.


## ISO datetime → Date

```ts
const isoDate = z.codec(z.iso.datetime(), z.date(), {
  decode: (iso) => new Date(iso),
  encode: (date) => date.toISOString(),
});
```

## Unix epoch (seconds) → Date

```ts
const epochDate = z.codec(z.int().min(0), z.date(), {
  decode: (secs) => new Date(secs * 1000),
  encode: (date) => Math.floor(date.getTime() / 1000),
});
```

## JSON string → typed object

```ts
const jsonCodec = <T extends z.ZodType>(schema: T) =>
  z.codec(z.string(), schema, {
    decode: (s, ctx) => {
      try {
        return JSON.parse(s);
      } catch (err: any) {
        ctx.issues.push({
          code: "invalid_format",
          format: "json",
          input: s,
          message: err.message,
        });
        return z.NEVER;
      }
    },
    encode: (v) => JSON.stringify(v),
  });

// Compose with an object schema:
const UserJson = jsonCodec(z.object({ name: z.string(), age: z.int() }));
UserJson.decode('{"name":"Alice","age":30}'); // → { name: "Alice", age: 30 }
UserJson.encode({ name: "Bob", age: 25 });    // → '{"name":"Bob","age":25}'
```

## String ↔ number

```ts
const stringToNumber = z.codec(
  z.string().regex(z.regexes.number),
  z.number(),
  {
    decode: (s) => Number.parseFloat(s),
    encode: (n) => n.toString(),
  }
);
```

## String ↔ integer

```ts
const stringToInt = z.codec(
  z.string().regex(/^-?\d+$/),
  z.int(),
  {
    decode: (s) => Number.parseInt(s, 10),
    encode: (n) => n.toString(),
  }
);
```

## Hex string ↔ Uint8Array

```ts
const hexToBytes = z.codec(z.hex(), z.instanceof(Uint8Array), {
  decode: (hex) => z.util.hexToUint8Array(hex),
  encode: (bytes) => z.util.uint8ArrayToHex(bytes),
});
```

## Base64 ↔ Uint8Array

```ts
const base64ToBytes = z.codec(z.base64(), z.instanceof(Uint8Array), {
  decode: (b64) => z.core.util.base64ToUint8Array(b64),
  encode: (bytes) => z.core.util.uint8ArrayToBase64(bytes),
});
```

## Base64url ↔ Uint8Array

```ts
const base64urlToBytes = z.codec(z.base64url(), z.instanceof(Uint8Array), {
  decode: (b64url) => z.util.base64urlToUint8Array(b64url),
  encode: (bytes) => z.util.uint8ArrayToBase64url(bytes),
});
```

## URL string ↔ URL object

```ts
const stringToURL = z.codec(z.url(), z.instanceof(URL), {
  decode: (s) => new URL(s),
  encode: (url) => url.href,
});
```

## Number ↔ BigInt

```ts
const numToBigInt = z.codec(z.int(), z.bigint(), {
  decode: (n) => BigInt(n),
  encode: (bi) => Number(bi),
});
```

## Composing codecs with `.pipe()`

Codecs and schemas compose via `.pipe()`. During `.encode()`, the pipe runs in reverse.

```ts
// Base64url string → bytes → UTF-8 string → JSON → typed object
const base64urlToBytes = z.codec(z.base64url(), z.instanceof(Uint8Array), {
  decode: (s) => z.util.base64urlToUint8Array(s),
  encode: (b) => z.util.uint8ArrayToBase64url(b),
});

const bytesToUtf8 = z.codec(z.instanceof(Uint8Array), z.string(), {
  decode: (b) => new TextDecoder().decode(b),
  encode: (s) => new TextEncoder().encode(s),
});

const UserSchema = z.object({ name: z.string(), age: z.number() });
const pipeline = base64urlToBytes.pipe(bytesToUtf8).pipe(jsonCodec(UserSchema));

pipeline.decode("eyJuYW1lIjoiQWxpY2UiLCJhZ2UiOjMwfQ");
// → { name: "Alice", age: 30 }
```


## stringbool as codec

`z.stringbool()` is internally a codec since 4.1:

```ts
const sb = z.stringbool();
sb.decode("true");    // true
sb.encode(false);     // "false"

// Custom truthy/falsy — first element is the encode target:
z.stringbool({ truthy: ["yes", "y"], falsy: ["no", "n"] });
// encode(true)  → "yes"
// encode(false) → "no"
```
