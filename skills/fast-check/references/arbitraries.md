# Arbitraries: composition and the filtering-trap fix

All examples assume fast-check 4.x and `import fc from "fast-check"`.

## Everyday arbitraries

| Need                     | Arbitrary                                                    |
| ------------------------ | ------------------------------------------------------------ |
| Integers                 | `fc.integer({ min, max })`, `fc.nat({ max })`                |
| Floats/doubles           | `fc.float(...)`, `fc.double({ noNaN: true })`                |
| BigInts                  | `fc.bigInt({ min, max })`                                    |
| Strings                  | `fc.string({ minLength, maxLength, unit })`                  |
| Full Unicode strings     | `fc.string({ unit: "binary" })`                              |
| ASCII strings            | `fc.string({ unit: "binary-ascii" })`                        |
| Grapheme-aware strings   | `fc.string({ unit: "grapheme" })`                            |
| Booleans                 | `fc.boolean()`                                               |
| Dates                    | `fc.date({ noInvalidDate: true })`                           |
| Arrays                   | `fc.array(arb, { minLength, maxLength })`                    |
| Non-empty arrays         | `fc.array(arb, { minLength: 1 })`                            |
| Unique arrays            | `fc.uniqueArray(arb, { selector })`                          |
| Tuples                   | `fc.tuple(arbA, arbB)`                                       |
| Objects with known shape | `fc.record({ a: arbA, b: arbB })`                            |
| Optional keys            | `fc.record(model, { requiredKeys: [] })`                     |
| Dictionaries             | `fc.dictionary(keyArb, valueArb)`                            |
| One of several shapes    | `fc.oneof(arbA, arbB)` (weighted variant available)          |
| Fixed alternatives       | `fc.constant(v)`, `fc.constantFrom(a, b, c)`                 |
| JSON                     | `fc.json()`, `fc.jsonValue()`                                |
| Anything                 | `fc.anything()` (adversarial: symbols, null protos)          |
| Sub-sequences            | `fc.subarray(items)`, `fc.shuffledSubarray(items)`           |
| Functions                | `fc.func(outArb)`, `fc.compareFunc()`                        |
| IP/UUID/email/URL        | `fc.ipV4()`, `fc.uuid()`, `fc.emailAddress()`, `fc.webUrl()` |

In 4.x, `fc.constant("a")` infers `Arbitrary<"a">` and
`fc.constantFrom("a", "b")` infers `Arbitrary<"a" | "b">`; widen explicitly
(`fc.constant<string>("a")`) when the literal type is unwanted.

## Composition

### map — derive a valid value from a simpler seed

```typescript
// Even integers, without filtering
const even = fc.integer({ min: -500_000, max: 500_000 }).map((n) => n * 2);

// ISO date strings that always parse
const isoDate = fc
  .tuple(
    fc.integer({ min: 0, max: 9999 }),
    fc.integer({ min: 1, max: 12 }),
    fc.integer({ min: 1, max: 28 }),
  )
  .map(
    ([y, m, d]) =>
      `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
  );
```

Pass a second *unmapper* argument to `map` when the arbitrary must also shrink
values injected via examples: `arb.map(mapper, unmapper)`.

### chain — let one draw shape the next

```typescript
// An array plus a valid index into it
const arrayWithIndex = fc
  .array(fc.integer(), { minLength: 1 })
  .chain((arr) =>
    fc.tuple(fc.constant(arr), fc.nat({ max: arr.length - 1 })),
  );
```

`chain` weakens shrinking across the boundary (the second draw is regenerated
when the first shrinks), so prefer `map` over `chain` whenever the dependency
can be expressed as a pure transformation.

### record + map — domain builders

```typescript
interface Order {
  id: string;
  lines: Array<{ sku: string; qty: number }>;
  total: number;
}

const orderArb: fc.Arbitrary<Order> = fc
  .record({
    id: fc.uuid(),
    lines: fc.array(
      fc.record({
        sku: fc.string({ minLength: 1, maxLength: 12 }),
        qty: fc.integer({ min: 1, max: 999 }),
      }),
      { minLength: 1, maxLength: 20 },
    ),
  })
  .map(({ id, lines }) => ({
    id,
    lines,
    // Derive the invariant instead of asserting it later
    total: lines.reduce((s, l) => s + l.qty, 0),
  }));
```

### letrec — recursive structures

```typescript
const { tree } = fc.letrec((tie) => ({
  tree: fc.oneof(
    { depthSize: "small" },
    tie("leaf"),
    fc.record({ left: tie("tree"), right: tie("tree") }),
  ),
  leaf: fc.integer(),
}));
```

Always pass a depth control (`depthSize` or `maxDepth`) on the recursive
`oneof`, or generation may blow the stack.

## The filtering trap: before and after

Rejection sampling (`.filter`, `fc.pre`) wastes the run budget and starves the
shrinker. Construct validity instead.

```typescript
// BAD: ~50% rejection, shrinker fights the filter
const evenBad = fc.integer().filter((n) => n % 2 === 0);

// GOOD: every draw valid, shrinks cleanly
const evenGood = fc.integer({ min: -500_000, max: 500_000 }).map((n) => n * 2);

// BAD: rejects half of all pairs
const orderedBad = fc
  .tuple(fc.nat(), fc.nat())
  .filter(([a, b]) => a < b);

// GOOD: draw the bound, then map into it
const orderedGood = fc
  .tuple(fc.nat({ max: 999_999 }), fc.nat({ max: 999_998 }))
  .map(([b, a]) => [Math.min(a, b), Math.max(a, b) + 1] as const);
```

A thin filter that rejects rarely (say, excluding one sentinel value) is fine;
a filter that rejects a constant fraction of the space is the trap.

## Global and per-test configuration

```typescript
// Once, in test setup
fc.configureGlobal({ numRuns: 200 });

// Per property
fc.assert(fc.property(arb, predicate), {
  numRuns: 1000,
  seed: 42,          // reproduce a specific run
  path: "25:2:0",    // jump straight to a counter-example
  endOnFailure: true,
  verbose: 2,        // show the full shrink trail
});
```

Failure reports print `{ seed, path }`; pin them to replay, then remove the pin
once fixed and add the shrunk input as a named unit test.
