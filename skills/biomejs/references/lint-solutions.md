# Lint Solutions Reference

Solutions for non-obvious Biome lint errors. Organised by rule category.

## Suspicious Category

### noExplicitAny

**Error:** `Unexpected any. Specify a different type.`

**Lazy fix to avoid:** `// biome-ignore` without proper typing.

**Proper solutions:**

```typescript
// Instead of: function parse(data: any)

// Use unknown for truly unknown data
function parse(data: unknown): ParsedResult {
  if (typeof data === 'object' && data !== null) {
    // Type narrowing
  }
}

// Use generics for flexible typing
function parse<T>(data: T): ParsedResult<T> { }

// Use specific union types
function parse(data: string | number | Record<string, unknown>): ParsedResult { }

// For external untyped libraries, create declaration files
// types/legacy-lib.d.ts
declare module 'legacy-lib' {
  export function doThing(input: string): Promise<unknown>;
}
```

**Acceptable suppression cases:**
- FFI boundaries with C/Rust libraries lacking type definitions
- Dynamic metaprogramming (proxies, decorators)
- Test mocks requiring deliberate type escape hatches

### noArrayIndexKey

**Error:** `Avoid using array index as key.`

**Why it matters:** React uses keys for reconciliation. Index keys cause incorrect component reuse when arrays reorder.

**Proper solutions:**

```typescript
// BAD
items.map((item, index) => <Item key={index} />)

// GOOD: Use stable identifier
items.map((item) => <Item key={item.id} />)

// GOOD: Derive key from content (when no ID exists)
items.map((item) => <Item key={`${item.name}-${item.createdAt}`} />)

// GOOD: Generate IDs at data creation time
const itemsWithIds = rawItems.map((item, i) => ({
  ...item,
  _key: crypto.randomUUID()  // or nanoid()
}));
```

**Acceptable suppression:** Static lists that never reorder (rare).

### noConsoleLog

**Error:** `Don't use console.log`

**Proper solutions:**

```typescript
// Use a logger abstraction
import { logger } from './logger';
logger.debug('Processing', { itemCount: items.length });

// For development-only logging
if (import.meta.env.DEV) {
  console.log('Debug:', value);
}

// Use console.info/warn/error for intentional output
console.error('Fatal error:', err);  // Allowed by default
```

**Configuration to allow specific console methods:**

```json
{
  "linter": {
    "rules": {
      "suspicious": {
        "noConsole": {
          "level": "error",
          "options": {
            "allow": ["error", "warn", "info"]
          }
        }
      }
    }
  }
}
```

### noDoubleEquals

**Error:** `Use === instead of ==`

**Proper solutions:**

```typescript
// BAD
if (value == null)

// GOOD: Explicit checks
if (value === null || value === undefined)

// GOOD: Use nullish patterns
if (value ?? defaultValue)

// EXCEPTION: == null is a deliberate pattern for null|undefined
// If you want this pattern, suppress with reason:
// biome-ignore lint/suspicious/noDoubleEquals: intentional null|undefined check
if (value == null)
```

### noAsyncPromiseExecutor

**Error:** `Async executor function in Promise constructor`

**Why it matters:** Errors in async executors won't reject the promise—they'll be unhandled.

```typescript
// BAD
new Promise(async (resolve) => {
  const data = await fetch(url);
  resolve(data);
});

// GOOD: Use async function directly
async function getData() {
  return await fetch(url);
}

// GOOD: If you need Promise constructor, don't use async
new Promise((resolve, reject) => {
  fetch(url).then(resolve).catch(reject);
});
```

## Style Category

### noNonNullAssertion

**Error:** `Forbidden non-null assertion`

**Proper solutions:**

```typescript
// BAD
const el = document.getElementById('root')!;

// GOOD: Throw on null
const el = document.getElementById('root');
if (!el) throw new Error('Root element not found');

// GOOD: Type guard
function assertElement(el: HTMLElement | null): asserts el is HTMLElement {
  if (!el) throw new Error('Element required');
}
const el = document.getElementById('root');
assertElement(el);

// GOOD: Optional chaining when null is acceptable
document.getElementById('root')?.addEventListener('click', handler);
```

### noDefaultExport

**Error:** `Avoid default exports`

**Why it matters:** Named exports improve refactoring, IDE support, and tree-shaking.

```typescript
// BAD
export default function handler() {}

// GOOD
export function handler() {}

// In consuming file:
import { handler } from './handler';  // Clear what's imported
```

**Override for config files** (which often require default exports):

```json
{
  "overrides": [{
    "include": ["*.config.ts", "*.config.js"],
    "linter": {
      "rules": {
        "style": { "noDefaultExport": "off" }
      }
    }
  }]
}
```

### useConst

**Error:** `Use const instead of let`

```typescript
// BAD
let config = loadConfig();

// GOOD
const config = loadConfig();

// If you genuinely need mutation, that's fine—Biome only flags
// variables that are never reassigned
```

### useTemplate

**Error:** `Use template literals instead of string concatenation`

```typescript
// BAD
const msg = 'Hello ' + name + '!';

// GOOD
const msg = `Hello ${name}!`;
```

## Complexity Category

### noForEach

**Error:** `Prefer for...of instead of forEach`

**Why it matters:** `forEach` can't be broken out of, doesn't work with async/await properly, and has performance overhead.

```typescript
// BAD
items.forEach(item => process(item));

// GOOD
for (const item of items) {
  process(item);
}

// GOOD: When you need index
for (const [index, item] of items.entries()) {
  process(item, index);
}

// GOOD: Functional transforms (map/filter/reduce are fine)
const processed = items.map(item => transform(item));
```

### noUselessFragments

**Error:** `Avoid useless fragments`

```typescript
// BAD
return <><Component /></>;

// GOOD
return <Component />;

// Fragments are useful when returning multiple elements
return (
  <>
    <Header />
    <Main />
  </>
);
```

### noBannedTypes

**Error:** `Don't use Object as a type`

```typescript
// BAD
function process(obj: Object) {}
function process(obj: {}) {}

// GOOD: For any object
function process(obj: Record<string, unknown>) {}

// GOOD: For specific shape
function process(obj: { id: string; name: string }) {}

// GOOD: For truly any value
function process(obj: unknown) {}
```

## Correctness Category

### noUnusedVariables

**Error:** `Variable is declared but never used`

```typescript
// For intentionally unused variables, prefix with underscore
const [_first, second] = tuple;

// For unused function parameters
function handler(_event: Event, data: Data) {
  return process(data);
}

// For unused imports in type-only contexts
import type { Config } from './config';  // Use 'import type'
```

### useExhaustiveDependencies

**Error:** `Missing dependency in useEffect/useCallback/useMemo`

This is one of the most commonly suppressed rules. **Don't suppress it blindly.**

```typescript
// BAD: Missing dependency
useEffect(() => {
  fetchData(userId);
}, []);  // userId missing!

// GOOD: Include all dependencies
useEffect(() => {
  fetchData(userId);
}, [userId]);

// GOOD: If you want to run only on mount, move the value outside
const userIdRef = useRef(userId);
useEffect(() => {
  fetchData(userIdRef.current);
}, []);

// GOOD: For event handlers that shouldn't re-run
const fetchDataRef = useRef(fetchData);
useEffect(() => {
  fetchDataRef.current = fetchData;
});

useEffect(() => {
  fetchDataRef.current(userId);
}, [userId]);
```

**Acceptable suppression:** When you genuinely need stale closure behaviour (rare, document thoroughly).

## A11y Category

### useButtonType

**Error:** `Provide explicit type attribute for button`

```typescript
// BAD
<button onClick={handleClick}>Submit</button>

// GOOD
<button type="submit" onClick={handleClick}>Submit</button>
<button type="button" onClick={handleClick}>Cancel</button>
```

Browsers default to `type="submit"`, which can cause unintended form submissions.

### noSvgWithoutTitle

**Error:** `SVG elements must have a title for accessibility`

```typescript
// BAD
<svg><path d="..." /></svg>

// GOOD: Decorative SVG
<svg aria-hidden="true"><path d="..." /></svg>

// GOOD: Meaningful SVG
<svg role="img" aria-labelledby="title">
  <title id="title">Loading spinner</title>
  <path d="..." />
</svg>
```

## Performance Category

### noAccumulatingSpread

**Error:** `Avoid spreading in accumulators`

**Why it matters:** Each spread creates a new object. In loops, this is O(n²).

```typescript
// BAD: O(n²) complexity
const result = items.reduce((acc, item) => ({
  ...acc,
  [item.id]: item
}), {});

// GOOD: Mutate the accumulator
const result = items.reduce((acc, item) => {
  acc[item.id] = item;
  return acc;
}, {} as Record<string, Item>);

// GOOD: Use Object.fromEntries
const result = Object.fromEntries(
  items.map(item => [item.id, item])
);

// GOOD: Use a Map
const result = new Map(items.map(item => [item.id, item]));
```
