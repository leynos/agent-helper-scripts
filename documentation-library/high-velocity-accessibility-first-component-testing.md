# An Architectural Blueprint for High-Velocity, Accessibility-First Testing

## I. Strategic Framework: A Multi-Layered Approach to Accessible Testing

Achieving an **accessibility-first** testing strategy at high velocity requires
a test architecture that is both **fast** and **thorough**. We must embed
accessibility into everyday development without creating a slow feedback loop.
The proposed framework adopts a multi-layered approach: a rapid inner loop for
component tests and a comprehensive outer loop for end-to-end (E2E) validation.

This architecture reflects recent tooling decisions. Notably, we leverage the
speed of the **Bun** runtime for most unit and integration tests, while
compensating for its limitations with a parallel **Node.js** harness for
accessibility scans. On top of this, we employ **Playwright** as an outer test
loop to cover all aspects of the user experience. Each layer has a distinct
role, ensuring that accessibility is verified at every stage without
compromising developer productivity.

### 1.1 Deconstructing the Happy-DOM Deadlock: Bun vs. `axe-core`

Initial experiments exposed a fundamental deadlock between Bun's default DOM
simulation and the industry-standard accessibility engine, **`axe-core`**.
Bun’s test runner is engineered for extreme speed and recommends using **Happy
DOM** for simulating the browser environment. **Happy DOM** is a lightweight,
fast implementation of browser APIs – but its quest for speed comes at a cost.
It diverges from web standards in subtle ways that clash with `axe-core`.

The most critical incompatibility lies in Happy DOM’s handling of the **
`Node.isConnected`** property. This DOM API indicates if a node is attached to
the document. `axe-core` relies on modifying `isConnected` during its DOM
traversal. In Happy DOM, `isConnected` is implemented as a read-only property
(and not fully standard), causing `axe-core` to throw runtime errors when it
attempts to set it. In practice, this means any accessibility scan using
`axe-core` fails outright under Happy DOM in the versions we tested.[^1]
Community reports and library documentation confirm this issue: the
maintainers of `vitest-axe` (a Vitest/Jest integration for axe) explicitly
warn that their matcher is **incompatible** with the Happy DOM versions they
tested against. Confirm the current compatibility of the Happy DOM, `axe-core`
and `vitest-axe` versions selected for a given project before relying on this
warning.

At the time this strategy was adopted, Bun’s test runner did not support the
more standards-compliant **JSDOM** environment (the de facto choice for
Node-based DOM testing) as a drop-in replacement.[^2] Whether that remains
true depends on the Bun version in use: compatibility between Bun, JSDOM and
`axe-core` should be validated against the versions selected for the target
project rather than assumed. With the Bun version available when this
document was written, the combination presented a catch-22:

- Bun’s recommended path for DOM tests is Happy DOM (for speed).

- `axe-core` cannot operate under Happy DOM due to fundamental API mismatch.

- The only viable alternative (JSDOM) was not supported in Bun’s native
  runner.

In summary, with the dependency versions evaluated here, **Bun alone could not
run component-level accessibility scans**. This was not a matter of
configuration or a minor bug; it was a limitation of that particular Bun +
Happy DOM pairing, and it should be re-verified against the versions in use
before being treated as still applicable. We must therefore adjust our
strategy to retain Bun’s performance benefits _and_ enable `axe-core` scans
through other means. The solution is a **hybrid testing approach**: run most
tests in Bun for speed, but outsource accessibility-specific tests to a Node.js
environment that supports JSDOM.

### 1.2 A Hybrid Solution: Node.js + JSDOM for A11y Scans

To resolve the deadlock observed with the evaluated versions, we introduce a
**parallel Node.js test harness** dedicated to accessibility checks. This is a
version-dependent design choice rather than a universal or permanent Bun
limitation, and it should be revisited whenever the Bun, JSDOM or `axe-core`
versions in use change. Rather than abandoning Bun entirely (and its
performance gains), we isolate the `axe-core` scans into their own test suite
running on Node.js. In practice, this means writing our accessibility tests in
separate files – for example, naming them `*.a11y.test.tsx` – and executing
them with a Node-based runner that uses JSDOM. All other unit and integration
tests continue to run with `bun test` using Happy DOM as usual.

Under this hybrid model, **Bun** remains the primary test engine for the vast
majority of tests (ensuring fast feedback), and **Node+JSDOM** is invoked as
needed for the specific cases that require `axe-core`. This dual setup gives us
the “best of both worlds”:

- **Fast feedback for logic and UI structure:** Bun’s test runner with Happy
  DOM provides near-instant execution for tests that verify component
  behaviour, state management, and basic rendering structure. Developers get
  immediate feedback in their inner loop without waiting on a heavy browser
  simulation.

- **Standards-compliant DOM for accessibility rules:** A Node environment can
  host JSDOM, a more complete DOM implementation that `axe-core` supports. By
  running `axe` in this context, we can catch semantic and structural
  accessibility issues that Bun/Happy DOM would miss or error on.

To keep the Node-based tests efficient, we can use **tsgo** (TypeScript’s new
fast compiler) to type-check or transpile the tests. A separate runner, such as
Vitest using its Node pool, loads and executes the `*.a11y.test.tsx` files. The
tests set up JSDOM, render components, run `axe-core`, and report results.

Crucially, the separation of test files by naming convention means we can run
the two suites independently. A typical workflow might include two NPM scripts:
one for the **fast tests** (`npm run test:unit` using Bun) and one for the
**a11y tests** (`npm run test:a11y` using Node). In continuous integration,
these can run in parallel or in sequence, but they are logically isolated. This
prevents any slow-down of the primary suite; if accessibility scans are a bit
slower due to JSDOM’s overhead, they won’t make the core test run (which
developers execute frequently) any slower. It also provides flexibility – for
example, a developer in rapid prototyping mode can run just the Bun tests, and
only run the axe checks when needed or in a pre-commit hook.

By introducing a Node+JSDOM harness for `axe-core`, we unblock our
accessibility-first strategy without sacrificing performance. Bun remains at
the centre of our testing, but we now have a reliable secondary path to perform
**automated accessibility audits** at the component level.

### 1.3 Acknowledging Limits: What JSDOM **Can’t** Catch

Even with JSDOM enabling `axe-core` scans, it’s important to set realistic
expectations. **No simulated DOM environment (Happy DOM or JSDOM) can replace a
real browser for certain accessibility validations.** JSDOM is purely a DOM
parser and engine; it does **not** perform visual rendering, apply CSS layout,
or run the browser’s accessibility tree computations. This means some
accessibility rules are beyond its scope.

The official Axe documentation notes "limited support for JSDOM" and advises
disabling rules that are known to yield false results in a headless DOM.[^3]
The most prominent example is the **colour contrast** rule. Verifying colour
contrast requires computing rendered text colours against background pixels –
something impossible without an actual rendering engine (JSDOM has no concept
of pixels or CSS cascade in effect). Any `axe-core` rule that depends on actual
rendering or CSS will fail or produce irrelevant results under JSDOM. Besides
`color-contrast`, other rules in this category include:

- **Target size** (minimum touch target dimensions)

- **Scrollable region focusable** (requires knowing if overflow renders
  scrollbars)

- **Visual focus indicators** (CSS outline or highlight on focusable elements)

- Etc.

We address this by **disabling such rules in the component-layer tests** and
deferring their verification to the Playwright E2E layer. In practice, our
Node-based axe test harness will load `axe-core` with a configuration that
turns off rules like `color-contrast` and any others that rely on styles or
layout. For example, we globally disable `color-contrast` in these tests and
explicitly document that **contrast must be checked in the browser**.
Similarly, a rule like `scrollable-region-focusable` (which might flag an
element for not being keyboard-focusable if it’s scrollable) is unreliable
without actual CSS overflow calculations; we’ll ignore it in JSDOM scans and
instead have a keyboard navigation test cover it in the E2E suite.

Understanding these limits reinforces our need for the **outer test loop**. The
inner loop (Bun + Node/axe tests) catches semantic issues (like missing ARIA
labels, improper roles, missing alt text, etc.), but it **cannot fully
guarantee** things like proper colour contrast, focus order on actual UI, or
dynamic content announcements. We explicitly rely on **real browser testing
with Playwright** to cover those. This separation of concerns ensures we don’t
develop a false sense of security from our fast tests – we know exactly which
checks happen later in the pipeline.

With the strategic foundation laid, we can now delve into each layer of the
architecture: the fast feedback inner loop powered by Bun (augmented with
Node-based axe scans), and the comprehensive outer loop powered by Playwright.

## II. The Inner Loop: Fast, Accessible Component Testing with Bun & JSDOM

The “inner loop” is where developers spend most of their time. It encompasses
the rapid unit and component tests run during active development – often on
every file save or commit. Our goal for this layer is to **make accessibility a
built-in aspect of these fast tests**. Every time a developer tests a
component’s logic or rendering, we want accessibility checks to happen
automatically and with minimal overhead.

To achieve this, we structure the inner loop into two synergistic parts:

- **2.1 Bun Test Runner + Happy DOM for Core Tests** – ultra-fast execution of
  component tests for logic, state, and basic rendering using Bun’s native test
  framework.

- **2.2 Node + JSDOM Axe Tests for Accessibility** – focused tests that
  specifically scan components with `axe-core` to catch semantic issues,
  running in a Node environment in parallel to the Bun tests.

- **2.3 Accessible-First Test Practices** – a set of conventions for writing
  tests (in both parts above) that ensure we’re using accessible selectors and
  asserting on meaningful output, effectively doubling as accessibility
  verification.

Together, these ensure that by the time a component leaves the inner loop, it
isn’t just functionally correct – it’s also **accessible by design**.

### 2.1 Ultra-Fast Execution with Bun and Happy DOM

Bun’s built-in test runner serves as our default for all standard tests. We
configure `bun test` with Happy DOM as the global DOM
(`--preload ./tests/setup-happy-dom.ts` in our NPM script) so that each test
file can create `document` and `window` as if running in a browser. The payoff
is speed: Bun’s runtime and Happy DOM allow most tests to run in
**milliseconds**, keeping the feedback loop extremely tight.

In these Bun-driven tests, we cover things like:

- **Component Rendering and Props:** Does the component render the right output
  given certain props or state?

- **State Transitions:** When we simulate a user action or change a context
  value, does the component update correctly?

- **Basic Accessibility attributes:** If a component is supposed to have
  certain ARIA attributes or roles, are they present in the rendered output?

For example, suppose we have a `<ThemeProvider>` context and an `<AppShell>`
layout component. A Bun test might verify that when the theme context is
applied, the DOM gets a `data-theme` attribute on the `<html>` element:

```tsx
import { describe, it, expect } from 'bun:test';
import { createRoot } from 'react-dom/client';
import { act } from 'react';

// ... import our ThemeProvider and a test component

describe('ThemeProvider integration', () => {
  it('applies the default theme to <html> and <body>', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(<ThemeProvider><span id="probe" /></ThemeProvider>);
    });

    const probe = container.querySelector('#probe');
    expect(probe).toBeTruthy();
    // Check that the theme data attribute was applied globally
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.body.getAttribute('data-theme')).toBe('dark');

    root.unmount();
  });
});
```

In this snippet, the Bun test quickly sets up a React root in a fake DOM,
renders a component, and makes assertions. The usage of
`document.querySelector` and standard DOM APIs is possible thanks to Happy DOM.
Tests like this run blazingly fast (no real browser, no JSDOM overhead) and can
be run hundreds of times a minute during development.

**Happy DOM Caveat:** As discussed, Happy DOM isn’t fully standards-compliant.
We **limit our usage of Happy DOM to tests that do not require full fidelity**.
That typically means we avoid deep CSS or canvas-related testing here. For most
React component output and event simulation, Happy DOM is sufficient and
incredibly fast. Whenever we bump into a limitation (like an API not
implemented or a discrepancy), we document it. In many cases, simple polyfills
or slight test adjustments can work around minor differences.

### 2.2 Automated Accessibility Scans via Node + JSDOM

To complement Bun’s lightning-fast tests, we run a parallel suite of
**accessibility-focused tests** in Node. These tests are responsible for running
`axe-core` against our components. They ensure that from a semantic
standpoint, components meet WCAG guidelines (no missing labels, correct roles,
valid ARIA attributes, etc.) before we even integrate them into pages.

**Test Structure and Naming:** We suffix these files with `.a11y.test.tsx` (for
example, `Button.a11y.test.tsx`, `Modal.a11y.test.tsx`) to clearly distinguish
them. This naming serves two purposes: it signals their purpose, and it allows
us to target them specifically in our test scripts. We might configure our
package scripts such that `npm run test:a11y` only picks up files matching
`*.a11y.test.tsx`. In CI, this makes it trivial to run the accessibility suite
separately from (and possibly in parallel with) the main Bun test suite.

**JSDOM Setup:** Each a11y test file uses **JSDOM** as its DOM environment. We
can either initialize JSDOM manually within the test, or use a Node test runner
that supports JSDOM globally. One lightweight approach is writing a small
harness script that, for each `.a11y.test.tsx` file:

- Spins up a JSDOM instance (e.g. using
  `new JSDOM('<!DOCTYPE html><html><body></body></html>')` and setting global
  `window` and `document`).

- Mounts the React component into that JSDOM document (likely using ReactDOM or
  Testing Library’s `render`).

- Runs `axe-core` on the JSDOM’s DOM tree.

- Asserts that there are no violations.

We can automate this using familiar libraries. For instance, **React Testing
Library** can be used to render components into the JSDOM document easily, and
the **axe-core API** (via something like `jest-axe` or `vitest-axe` utilities)
can perform the scan. The following illustrates a typical pattern, written in a
Jest/Vitest style (which is similar to what our custom harness would do):

```tsx
// Button.a11y.test.tsx
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import Button from './Button';

// Extend expect for the axe matcher (if using jest-axe)
expect.extend(toHaveNoViolations);

test('Button has no accessibility violations and is properly labelled', async () => {
  const { container } = render(<Button>Click Me</Button>);

  const results = await axe(container);
  expect(results).toHaveNoViolations();  // Custom matcher asserts zero axe issues

  // Also verify accessible name and role are correct as a sanity check:
  const btn = screen.getByRole('button', { name: /click me/i });
  expect(btn).toBeInTheDocument();
});
```

In this example, when run in a Node+JSDOM environment, the `Button` component
is rendered off-screen and scanned. The test will fail if, for instance, the
`<Button>` component is missing an accessible name or has ARIA attributes
misused. By including a Testing Library query
(`getByRole('button', { name: /click me/i })`), we double-verify that the
component is not only _free of axe-detectable violations_ but also that it
adheres to expected accessibility APIs (here, that a button with text "Click
Me" indeed yields an element with role `button` and that label).

We apply this pattern to all interactive components. A more complex example is
a **Modal** component which might be hidden or shown based on props:

```tsx
// Modal.a11y.test.tsx
import { render } from '@testing-library/react';
import { axe } from 'jest-axe';
import Modal from './Modal';

describe('Modal component accessibility', () => {
  test('has no violations when closed', async () => {
    const { container } = render(<Modal open={false} title="Sample Modal" />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
    // Even though modal is closed (perhaps rendered off-screen or not at all),
    // we ensure no stray violations like missing landmarks.
  });

  test('has no violations when open', async () => {
    const { container } = render(<Modal open={true} title="Sample Modal"><p>Content</p></Modal>);
    // Temporarily disable a page-level rule that is irrelevant in isolation:
    const results = await axe(container, {
      rules: {
        region: { enabled: false }  // disable landmark rule since modal isn't wrapped in <main> here
      }
    });
    expect(results).toHaveNoViolations();
  });
});
```

In the second test, we demonstrate **contextual rule configuration**: the
`region` rule (which requires content be within landmarks like `<main>`) is not
applicable when testing a Modal in isolation, so we disable it. This ability to
tweak axe’s rules per test helps avoid false positives and keeps our test
signal clean. Every axe violation we see in this suite should correspond to a
genuine issue that a user might encounter.

**Execution and Performance:** Running these Node/JSDOM tests is slower than
the Bun tests – JSDOM startup and axe analysis take time – but they are still
relatively fast. A simple component scan might take on the order of tens of
milliseconds to a couple hundred milliseconds. We mitigate performance concerns
by a) running these tests in parallel (Node can leverage multiple processes or
threads if we use a test runner), and b) keeping each test focused on a single
component or state to avoid heavy DOMs. In CI, we could further parallelize by
splitting the accessibility tests across multiple machines if needed (though
likely not necessary unless the suite grows very large).

The key outcome of this inner-loop accessibility suite is **immediate feedback
on semantic issues**. If a developer forgets an `aria-label` on a button, a
test fails right when they run `npm test`. This is far better than catching it
days later in a manual audit or in a slow E2E test. It turns accessibility into
a daily concern rather than a QA afterthought.

### 2.3 Accessible-First Test Practices: Enforcing Good Habits

Having the right tools is only half the battle. We also enforce **strict
conventions in how tests are written**, to ensure our test code itself
encourages accessible implementation. Two key practices are:

- **Use of Accessible Queries:** Tests must interact with the rendered DOM the
  same way a user or assistive technology would – i.e. by using accessible
  labels, roles, and text content. We forbid selecting elements by obscure
  hooks or internal IDs whenever a semantic alternative exists. In practice,
  this means favouring Testing Library queries like `getByRole`,
  `getByLabelText`, or `getByText` over queries like
  `querySelector('[data-testid="..."]')`. If our tests cannot find an element
  by a meaningful label or role, that’s a red flag that the component might not
  be accessible.

_Policy:_ The use of `data-testid` (or similar testing-only attributes) is
considered a last resort. In code review, any test that uses a test ID must
justify why a role or label could not be used instead. Often, the remedy is to
improve the component (e.g. add an `aria-label` or proper text) such that a
more user-centric query becomes possible. This policy creates a virtuous cycle:
it pushes developers to build components with accessibility in mind (so they
are easily testable), and it makes the tests more robust by tying them to
user-visible strings and roles.

_Automation:_ Biome loads the `tools/grit/rule-testing-*.grit` patterns, which
emit the `test/no-testid-selectors`, `test/no-queryselector`,
`test/prefer-byrole-for-actions`, and `test/no-raw-dom-lookup` diagnostics for
test files. These rules error on any `*ByTestId` lookup (or raw
`querySelector*`), warn when `getByText` is clicked, and therefore keep our
tests aligned with the role-first guidance from Testing Library and Playwright.
If a semantic selector is genuinely impossible, add an `ACCESSIBILITY:`
justification next to a targeted
`// biome-ignore lint/test/no-testid-selectors` suppression so reviewers can
see the trade-off.

_Example:_ In the `SettingsPanel` component test, instead of selecting a
toggle button by an ID or class, we query it by its accessible name:

```tsx
const themeToggle = mountNode.querySelector("button[aria-label='Switch to dark theme']");
expect(themeToggle).toBeTruthy();
```

Here we rely on the presence of `aria-label="Switch to dark theme"` on the
button. If that label were missing or changed, the test would fail – which is
good, because the accessible contract of the UI changed. In a future refactor,
we might rewrite such a query using Testing Library’s
`getByRole('button', { name: 'Switch to dark theme' })` for clarity. Either
way, the test asserts something a screen reader user would care about: that
there is a button with that label.

#### 2.3.1 Exemplars awaiting refactor

We still have a handful of high-visibility suites leaning on test IDs and DOM
structure hooks. They are valuable targets when socializing the upcoming lint
rule:

- `tests/order-history.test.tsx` (list and delete flows) uses selectors such
  as `[data-testid='order-list-panel']` and `delete-order-button`. The fix is
  to surface accessible names – for example, ensure the list panel owns an
  `aria-labelledby`, label the delete buttons “Delete order {order number}”,
  and then switch the tests to `getByRole('tabpanel', { name: /orders/i })`
  or `getAllByRole('button', { name: /delete order .*/i })`.
- `tests/settings-panel.test.tsx` relies on a hidden
  `<span data-testid="mode-probe">` shim to assert state transitions. Replace
  this with assertions against the real control’s `aria-pressed` state and
  visible label (`getByRole('button', { name: /display mode/i })`).
- `tests/dashboard-widget.test.tsx` queries widget panels via
  `[data-testid='dashboard-widget-container']`. Once the container has a
  sensible label (for example `aria-label="Sales summary widget"`), the test
  can use `getByRole('region', { name: /sales summary widget/i })` and remain
  resilient.

Documenting these specific call sites gives reviewers a short list of “fix me
next” examples and shows what the accessible alternative should look like.

- **Assertions on Accessibility Outcomes:** In addition to low-level assertions
  (like “this state toggled” or “this element exists”), we add assertions
  specifically for accessibility expectations. For instance, after clicking a
  button that opens a modal, we might assert that focus moved to the modal
  dialog element (using `expect(dialog).toHaveFocus()` or checking
  `document.activeElement`). Or after toggling a theme, we assert that the
  `<html lang>` or `data-theme` attributes are correctly set. By writing these
  into tests, we ensure that accessibility features (focus management, ARIA
  attributes, language attributes, etc.) aren’t accidentally broken. It’s far
  easier to debug an automated test failure pointing to a missing `lang`
  attribute than to wait for a manual audit.

To enforce these practices, we integrate ESLint rules and testing guidelines:

- We enable **ESLint plugins like Testing Library’s `prefer-user-event` and
  `no-test-id-queries`** which warn if a test uses `getByTestId` when a
  role query is available, or if it calls low-level DOM methods instead of
  simulating real user events.

- In pull request reviews, the team is instructed to flag any test code that
  doesn’t adhere to accessible-first querying. Over time this becomes second
  nature.

By combining tooling (axe scans, proper libraries) with conventions (only use
accessible queries, assert on ARIA/focus behaviours), our inner loop becomes a
strong quality gate. A developer cannot merge a component that is functionally
perfect but accessibly flawed – the tests would catch it.

## III. The Outer Loop: Comprehensive E2E Validation with Playwright

While the inner loop verifies individual components in isolation, the **outer
loop** ensures that the application works as a cohesive, accessible whole. Here
we use **Playwright** to run end-to-end tests in real browsers. The outer loop
addresses everything that a simulated environment cannot: actual rendering,
styling, user interactions across components, and integration of features like
routing and dynamic content. It is our final safety net and a place to conduct
more intensive audits, including visual and internationalization checks.

Playwright was chosen for its robust multi-browser support (Chromium, Firefox,
WebKit), its powerful automation APIs, and built-in test runner that integrates
assertions, parallelization, and rich reporting. This section outlines how we
leverage Playwright for various accessibility-focused E2E tasks:

- **3.1 In-Browser Axe Scans:** Running `axe-core` in a **real browser**
  context to catch issues like colour contrast, focus order, and other things
  JSDOM can’t detect.

- **3.2 Advanced Interaction Tests:** Simulating keyboard navigation, verifying
  focus management (e.g., modals trapping focus, return focus on close), and
  other workflow-oriented checks.

- **3.3 Accessibility Tree Snapshots:** Capturing and diffing the browser’s
  accessibility tree to detect unintended semantic changes over time.

- **3.4 Visual Regression across Viewports/Themes:** Taking screenshots of
  pages/components in various layouts to catch visual bugs that could affect
  usability or clarity.

- **3.5 Localization and Language Verification:** Testing the app under
  different locale settings to ensure language-specific attributes and content
  appear correctly.

This battery of tests runs less frequently (e.g., on pull request or nightly
builds) due to being heavier, but it is exhaustive in ensuring real-world
accessibility compliance.

### 3.1 Strategic Axe Scans in the Browser

We integrate `axe-core` into Playwright tests via the `@axe-core/playwright`
utility. This allows us to inject the axe script into pages and analyse the
rendered output for violations. The **advantage** here is that in a real
browser, axe can evaluate everything – including CSS, canvas, and the actual
computed tree. For example, the colour contrast rule will now produce
meaningful results because it can compute actual colours on the page.

However, we must be strategic to avoid slowing down the suite. Running a full
axe scan after every action would turn our E2E tests into a slog. Instead, we
treat accessibility scans as **targeted assertions** at critical checkpoints of
a user flow:

- **After initial page load:** We often scan the fully loaded page to ensure no
  glaring issues on the baseline UI.

- **After major UI transitions:** For example, after opening a modal, after
  navigating to a new page, after triggering a form validation that reveals
  errors, etc. These are points where new content appears or state
  significantly changes, warranting a re-check.

- **Scope the scan to changed regions:** Using `AxeBuilder.include(selector)`
  we can limit analysis to specific parts of the DOM. For instance, after
  opening a modal, we can scan _only_ the modal dialog element instead of the
  entire page (which saves time and focuses results).

**Example – Modal Workflow:** Consider a test of an e-commerce flow where
clicking "Add to Cart" opens a dialog. We can write:

```ts
import { test, expect } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';

test.describe('Add to Cart Modal Flow', () => {
  test('main page has no axe violations on load', async ({ page }) => {
    await page.goto('/products');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('modal dialog is accessible after opening', async ({ page }) => {
    await page.goto('/products');
    // Trigger the modal
    await page.getByRole('button', { name: 'Add to Cart' }).click();
    // Ensure modal is visible
    const modal = page.locator('#add-to-cart-modal');
    await expect(modal).toBeVisible();
    // Run axe only inside the modal
    const modalResults = await new AxeBuilder({ page }).include('#add-to-cart-modal').analyze();
    expect(modalResults.violations).toEqual([]);
  });
});
```

In this snippet, the first test scans the full page and expects zero violations
(meaning our base page structure is solid). The second test specifically clicks
the "Add to Cart" button (again, using an **accessible query** by role and
name, ensuring the button is labelled properly) and then waits for the modal.
We then scan just the modal content for violations. If, say, the modal was
missing an `aria-label` on its header or had a form control without a label,
`axe-core` would catch it here.

By **scoping axe scans and using them sparingly**, we avoid a performance hit.
Each scan might take a second or two on a large page, so we do it only where it
yields new information. The principle is: **treat accessibility scans as
assertions, not as a blanket afterthought**. This way, our E2E tests remain
fast enough to run in CI while still covering critical scenarios.

### 3.2 Interactive Behaviour and Focus Management

Automated accessibility testing must extend beyond static analysis. Many
accessibility issues are only apparent when users actually interact with the
UI. With Playwright’s control of the browser, we can simulate these
interactions and validate the application’s response. Two major areas we
concentrate on are **keyboard navigation** and **focus handling**.

#### 3.2.1 Keyboard Navigation Flow Tests

A core WCAG principle is that **all functionality should be operable via
keyboard** (no mouse required). We write E2E tests that mimic a user pressing
`Tab`, `Shift+Tab`, `Enter`, and `Escape` keys to navigate and activate
components.

For example, consider verifying the navigation menu and search input in a
header:

```ts
test('Home page header is fully keyboard-navigable', async ({ page }) => {
  await page.goto('/');

  // Press Tab repeatedly and check focus moves in the expected order
  await page.keyboard.press('Tab');
  let focused = await page.evaluate(() => document.activeElement?.textContent);
  expect(focused).toMatch(/Products/i);  // focus on "Products" link

  await page.keyboard.press('Tab');
  focused = await page.evaluate(() => document.activeElement?.getAttribute('aria-label'));
  expect(focused).toBe('Search');  // now search box is focused (identified by its aria-label)

  await page.keyboard.press('Tab');
  focused = await page.evaluate(() => document.activeElement?.textContent);
  expect(focused).toMatch(/My Account/i);  // now "My Account" button is focused

  // Reverse navigation
  await page.keyboard.down('Shift');
  await page.keyboard.press('Tab');
  await page.keyboard.up('Shift');
  focused = await page.evaluate(() => document.activeElement?.getAttribute('aria-label'));
  expect(focused).toBe('Search');
});
```

This script tabs through the interactive elements of the header and uses the
`document.activeElement` to check which element is currently focused. We verify
that focus cycles through **Products link → Search input → My Account button**
in order, and that it can go backwards as well. If an element was not reachable
via Tab (e.g., missing a `tabindex` or not a natural focusable element), this
test would catch it.

We do similar tests for menus, dialogs, and other composite components:

- Ensuring that pressing **Enter** on a focused button triggers the expected
  action (Playwright’s `page.keyboard.press('Enter')` can be used).

- Ensuring **Escape** closes dialogs or dropdowns when focused inside them.

- Verifying there are no **keyboard traps**: focus should never get stuck in a
  loop or lost off-screen. For modals, we _want_ focus trap within the modal
  while it’s open (so Tab doesn’t go behind the modal), but when the modal
  closes, focus should return to a sensible place (often the button that opened
  it).

These tests give us confidence that a sighted keyboard user or a visually
impaired user using keyboard + screen reader can navigate and operate the app
fully.

#### 3.2.2 Focus Handling in Dialogs and Overlays

Building on keyboard tests, we specifically check **modal dialogs, popovers,
and other overlays** for proper focus management:

- When a modal opens, the first interactive element inside it should receive
  focus (or the modal container itself, if it has `tabindex="-1"` to catch
  focus).

- Tab should wrap within the modal (since modals typically trap focus until
  closed).

- When the modal closes, focus should restore to the element that opened it (or
  another logical location).

Playwright makes it straightforward to test these conditions:

```ts
// Assume the "Add to Cart" modal from earlier tests
await page.getByRole('button', { name: 'Add to Cart' }).click();
const modalDialog = page.locator('#add-to-cart-modal');
await expect(modalDialog).toBeVisible();

// The first focusable element in modal should be focused.
const firstFocusable = modalDialog.locator('button').first();
await expect(firstFocusable).toBeFocused();

// Press Tab repeatedly within modal and ensure focus stays in modal
for (let i = 0; i < 5; i++) {
  await page.keyboard.press('Tab');
  const activeId = await page.evaluate(() => document.activeElement?.closest('#add-to-cart-modal')?.id);
  expect(activeId).toBe('add-to-cart-modal');
}

// Close modal (press Escape or click close button)
await page.keyboard.press('Escape');
await expect(modalDialog).toBeHidden();

// After closing, focus should return to the "Add to Cart" button
const triggerButton = page.getByRole('button', { name: 'Add to Cart' });
await expect(triggerButton).toBeFocused();
```

This sequence rigorously checks focus containment and restoration. If any step
fails (focus leaves the modal, or doesn’t return after closing), we know we
have a bug in our focus management logic (perhaps a missing call to `.focus()`
or incorrect `tabindex` attributes).

Such tests ensure **operability** – one of the four principles of accessibility
(POUR: Perceivable, Operable, Understandable, Robust). They catch issues that
static analysis never could (for example, `axe-core` might not tell you that
focus got lost when a dialog closed).

### 3.3 Accessibility Tree Snapshots for Semantic Regression

In a complex UI, it’s possible to inadvertently change or break semantic
structure while refactoring, even if everything “looks” fine visually. To guard
against this, we use **accessibility tree snapshots** in Playwright. The
accessibility tree is what assistive technologies actually interact with –
essentially a computed structure derived from the DOM, listing elements with
roles, names, and properties as a screen reader would perceive them.

Playwright's `page.ariaSnapshot()` API returns a raw, YAML-like textual
representation of the page's accessible roles, names, and structure. The test
suite preserves that text without a custom normalizer so Playwright remains the
authority for the snapshot format.

Each route snapshot stores the raw text under `accessibilityTree` in a JSON
envelope, alongside any focused computed-style samples. Playwright's generic
`toMatchSnapshot()` matcher owns the file boundary and reports differences on
subsequent runs.

```typescript
const accessibilityTree = await page.ariaSnapshot();
const snapshotPayload = `${JSON.stringify({ accessibilityTree }, null, 2)}\n`;

expect(snapshotPayload).toMatchSnapshot("product-card-aria-tree.json");
```

Regenerate only the affected route snapshots after an intentional semantic
change, then audit the resulting roles and accessible names before accepting
the new baseline.

If a developer accidentally changed the `h2` in `ProductCard` to an `h3` or
removed an aria-label on the image, the next test run would produce a different
snapshot and cause a failure. This kind of regression test is **highly
sensitive to meaningful changes** but **robust to cosmetic ones**. Unlike raw
HTML snapshots (which would break on any minor markup change), the
accessibility snapshot ignores irrelevant container `<div>`s or styling hooks
and focuses purely on roles, names, and structure. If an extra `<div>` is added
for layout but doesn’t affect roles or names, the snapshot remains the same.
But if, say, a heading level changes or a label is lost, the difference is
caught immediately.

This technique gives us confidence that as we refactor or iterate on
components, we’re not silently altering the user’s accessible experience. It’s
especially useful for ensuring things like:

- Headings hierarchy remains correct (no suddenly skipping from h2 to h4, etc.).

- Buttons and links retain their names.

- Images keep their alt text or accessible name.

- Regions and landmarks (like nav, main, footer) remain in place.

We incorporate accessibility snapshot tests for all major composite components
and pages. They serve as a guardrail for semantic consistency.

### 3.4 Visual Regression Testing across Breakpoints and Themes

Accessibility isn’t just about screen readers and keyboard nav – visual
presentation matters too. Issues like text getting cut off, colour contrast in
different themes, or layout breakage on small screens can dramatically affect
usability. To catch these, we include **visual regression tests** in our
Playwright suite.

Using Playwright’s screenshot capabilities, we generate snapshots of pages or
components under various conditions and compare them to baselines. Key
dimensions we cover:

- **Different screen sizes (responsive breakpoints):** We test layouts on a
  small mobile viewport (e.g. 375×667) vs a desktop viewport (e.g. 1280×800).
  This ensures our responsive design doesn’t introduce inaccessible overflow or
  hiding of content on small screens.

- **Light and Dark themes:** Where an application supports theme switching
  (e.g., `light` vs `dark` themes), we capture each in
  screenshots. This helps verify colour contrast in each theme and catches any
  colour-specific asset issues (like an icon that’s not visible on a dark
  background).

- **Critical pages/components:** We focus on pages like the home dashboard,
  forms, and any component with complex styling (e.g., data visualization or
  maps in our context) for visual snapshots.

**Example – Responsive Header Snapshot:**

```ts
test.describe('Header visual regression', () => {
  // Test at two breakpoints
  const viewports = { mobile: { width: 360, height: 740 }, desktop: { width: 1280, height: 800 } };
  for (const [label, size] of Object.entries(viewports)) {
    test(`header looks correct in ${label} view`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.goto('/');  // go to homepage which includes the header
      // If theme defaults to dark, ensure it’s set for consistency
      await expect(page).toHaveScreenshot(`header-${label}.png`);
    });
  }
});
```

The first run will save `header-mobile.png` and `header-desktop.png`.
Subsequent runs will compare screenshots pixel-by-pixel. If a CSS change
accidentally pushed the header’s menu off-screen on mobile, the diff will flag
it. We have to manage the usual challenges of visual testing (ensuring
consistent fonts, ignoring dynamic content), but Playwright has mechanisms for
that (like disabling animations, using a standard font/locale).

For theme variations, we might have a test that explicitly toggles the theme:

```ts
test('Settings panel visual regression in dark and light mode', async ({ page }) => {
  await page.goto('/settings');
  // Dark theme (default)
  await expect(page.locator('#settings-panel')).toHaveScreenshot('settings-dark.png');
  // Toggle theme button
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  await expect(page.locator('#settings-panel')).toHaveScreenshot('settings-light.png');
});
```

Now we have baseline images for both dark and light modes of the settings
panel. If in light mode some text becomes illegible (e.g., if we accidentally
had white text on a light background), the screenshot difference will alert us.
This is effectively an automated **contrast check** across themes,
complementing what axe does. Axe will catch low contrast if configured, but
visual snapshots give a human-verifiable artefact to review if something
changes.

Visual regression tests are run sparingly because they can be
resource-intensive and occasionally flaky (due to antialiasing differences,
etc.). We mitigate flakiness by:

- Freezing dynamic data (e.g., use test accounts or stubbed dates so that
  today’s date or random data doesn’t spoil the snapshot).

- Using tolerances or masking for known nondeterministic regions if needed.

- Running on consistent infrastructure (same browser versions, etc., via
  Playwright’s Docker or the cloud workers).

The payoff is worthwhile: we get an assurance that the UI looks as intended and
remains usable at a glance. Many accessibility issues manifest visually (like
an off-screen element or overlapping text), so these tests catch problems that
neither axe nor unit tests would.

### 3.5 Localization and Internationalization Checks

Finally, accessibility extends to supporting users from different locales and
languages. An often overlooked aspect is ensuring that our app properly handles
localization – both in terms of content and technical attributes like the
page’s language. We add E2E tests to validate internationalization (i18n)
features:

- **Locale-specific content loading:** If our app is translated or supports
  multiple languages, we verify that switching to a locale yields the correct
  text. For example, toggling the language setting to French should cause the
  UI text to change to French.

- **Language attributes:** We ensure the `<html lang="">` attribute is set
  correctly whenever the locale changes, and that any region-specific sub-tags
  (like `en-GB` vs `en-US`) are handled if needed. The `lang` attribute is
  critical for screen readers to switch voice profiles.

- **Directionality:** If we ever support right-to-left (RTL) languages, tests
  would verify that the `dir="rtl"` attribute is applied and that layout flips
  appropriately. (For now, assume LTR only, but the tests are structured to
  accommodate this if needed.)

Playwright allows us to simulate different locales by launching contexts with a
specific locale. For example, `browser.newContext({ locale: 'fr-FR' })` would
make `navigator.language` report French. Alternatively, if our app has a UI
control for language, we use that.

**Example – Language Toggle:**

```ts
test('app supports English and Spanish locales', async ({ page }) => {
  await page.goto('/');
  // Default is English
  expect(await page.locator('html').getAttribute('lang')).toBe('en');
  await expect(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();

  // Switch locale via UI control (assuming a button or menu)
  await page.getByRole('button', { name: 'Español' }).click();
  // Now the page should be in Spanish
  expect(await page.locator('html').getAttribute('lang')).toBe('es');
  await expect(page.getByRole('heading', { name: 'Bienvenido' })).toBeVisible();
});
```

In this test, we verify two things: the `<html lang>` attribute changes from
"en" to "es", and the content of a heading changed from "Welcome" to
"Bienvenido". If either fails, it indicates a localization issue (either
content didn’t load, or we forgot to update the lang attribute in the code).

For more thorough coverage, we can run an entire suite in a non-default locale
using Playwright’s test config. For instance, duplicate some critical E2E tests
under a fixture where the context is launched with `{ locale: 'es-ES' }`. That
way, we are not only testing the toggle, but also that the Spanish version of
various flows has no axe violations and passes the same checks as English. This
ensures no translation accidentally introduces an accessibility issue (e.g., a
Spanish string that’s extremely long might cause a layout overflow which our
visual tests would catch).

By treating localization as a first-class aspect of testing, we safeguard the
**understandability** aspect of accessibility for all our supported audiences.
It also has practical benefits: we catch missing translation keys or formatting
issues early.

## IV. Performance Strategy and CI Integration

Having a comprehensive test suite is great, but it must run efficiently to be
viable in a fast-paced development setting. Our strategy layers the tests in
such a way that we **fail fast** on the cheapest tests and defer the heavier
tests to later, possibly parallelized, stages. We also integrate these layers
into our Continuous Integration pipeline so that accessibility is continuously
enforced.

### 4.1 Layered Test Execution for Speed

The test architecture naturally splits into tiers which we can execute
separately:

- **Layer 1: Bun Unit/Integration Tests** – Extremely fast, should be run on
  every commit and even every file change in watch mode. These catch basic
  regressions immediately. If any of these fail, there’s no need to proceed
  further until fixed.

- **Layer 2: Node/JSDOM Axe Tests** – These are a bit slower but still
  relatively quick. They can run in parallel to Layer 1. In a local dev flow, a
  developer might not run these on every save, but certainly before pushing
  code. In CI, we run them on each PR. If an accessibility rule fails here, we
  fail the build (for serious issues) or at least flag it for fixing.

- **Layer 3: Playwright E2E Tests** – This is the slowest layer, involving real
  browsers and possibly multiple iterations (various viewports, etc.). We
  execute this layer less frequently, typically on pull request validation and
  nightly full runs. Within this layer, we can configure Playwright to shard
  tests across multiple workers (it automatically runs tests in parallel across
  CPU cores, and can run across browser types concurrently if configured). So
  even though each test is heavy, the suite can still complete in a reasonable
  time.

In CI, we take advantage of parallel jobs:

- We run the **Bun tests** in one job. Given Bun’s speed, this job might finish
  in, say, 30 seconds.

- Simultaneously, run the **axe a11y tests** in another job. This might also
  take on the order of seconds to a minute, depending on how many components we
  scan.

- In parallel, run the **Playwright E2E tests** in another job. This could take
  a few minutes, especially if running on 3 browsers or doing visual
  comparisons, but often Playwright can keep it around 2-5 minutes by
  parallelizing internally.

By splitting these, the overall CI time is roughly the max of these, not the
sum. The **longest** will be the Playwright job. If that is, say, 4 minutes,
and the others finish in 1 minute, our total CI test time is ~4 minutes. This
is acceptable for a PR gate in exchange for the thorough coverage we get.

We configure our GitHub Actions (or equivalent CI) to reflect this structure:

- Job “Test: Bun” – runs `bun test` on all non-a11y tests.

- Job “Test: Accessibility (Node)” – runs our Node script for axe tests.

- Job “Test: E2E” – runs `npx playwright test` (possibly with some flags for
  trace or report).

- An overall workflow that depends on all three finishing. We can set fail-fast
  for certain jobs if desired (for instance, if Bun tests fail, maybe abort
  others to save resources).

This way, a quick failure (like a unit test failing or a basic axe rule
failing) doesn’t require waiting for the whole E2E suite to complete –
developers get immediate feedback on what broke.

Additionally, if test runtime ever becomes a concern (say our component count
triples and Node axe tests slow down), we can further partition those tests.
For example, run axe tests in parallel shards (maybe split by test file name
across two processes). But at our current scope, this likely isn’t necessary.

### 4.2 CI Reporting and Failure Triage

Integrating into CI also means handling results smartly. We treat any
**accessibility violation of high severity as a build failure**. For instance:

- If axe reports a **critical or serious** violation in either the component
  tests or E2E scans, the CI job fails. This prevents merging code that would
  introduce major accessibility regressions.

- **Minor** or **moderate** issues also block merging unless an explicit,
  time-limited allow-list entry covers them. Each entry must identify an
  owner, link to a tracking issue, record an expiry date, and pass CI
  validation. Creating an automated task alone does not permit a finding to
  pass; missing, invalid, or expired entries fail the gate.

We use Playwright and our Node tests’ reporting capabilities to output
machine-readable results (like JSON). A post-processing step in CI could parse
the axe results and summarize any violations. We also generate **HTML reports**
for easier debugging:

- The Node axe tests can produce an HTML report of all violations, with links
  to relevant DOM nodes and suggestions (using the output from `axe-core`).

- Playwright, by default, can produce an HTML report that includes screenshots,
  failing test traces, etc. We enable this and have the CI upload it as an
  artefact on failure.

Our team’s workflow is then: if a test fails, especially an accessibility one,
the engineer can download the report artefact and see exactly what failed – for
example, a Playwright trace showing that after clicking a button, the focus did
not move as expected, or an axe report highlighting a missing form label.

Finally, we maintain a **culture of accessibility ownership**. Failing tests
are not just turned green by updating the tests – the expectation is to _fix
the underlying issue_. Because the tests are designed to catch real problems,
the correct response to a failure is usually to correct the component or page
(e.g., add the missing `aria-label`, adjust the colour contrast in CSS, fix the
focus logic in JavaScript).

To help manage this, we integrate severity tagging:

- Tests or checks can be annotated with severity levels (for example, using
  axe’s impact ratings). Our CI parser can distinguish and perhaps post a
  comment on the PR: “⚠️ Accessibility issue detected: **low contrast on button
  text** (critical). This must be resolved before merge.”

- For less critical issues that slip through, we create backlog tickets
  automatically. But ideally, our gating ensures everything important is caught
  and fixed in the same development cycle.

## V. Synthesis and Implementation Roadmap

The proposed testing framework delivers a **holistic, layered approach** to
accessibility testing without sacrificing development speed. We combine fast
component-level checks with full browser validation to ensure that every new UI
piece is both **rapidly verified** and **truly accessible** in practice. Below
is a summary of the two major layers and their roles:

| Dimension   | Component layer               | E2E layer                  |
| ----------- | ----------------------------- | -------------------------- |
| Tools       | Bun, Node, JSDOM and axe      | Playwright and Axe         |
| Environment | Simulated DOM                 | Real browser               |
| Scope       | Components                    | Pages and user flows       |
| Speed       | Milliseconds                  | Seconds; minutes per suite |
| Defects     | Structure and semantics       | Visuals and interaction    |
| Schedule    | Every change and pull request | Merge gate and nightly     |
| CI role     | Early failure                 | Integrated-product gate    |

The table summarizes these distinctions:

- **Tools:** Bun runs unit tests in Happy DOM. Node and JSDOM run component axe
  scans. Playwright runs Axe in Chromium, Firefox and WebKit for E2E tests.
- **Environment:** the component layer uses Happy DOM for speed and JSDOM for
  standards support. The E2E layer uses a real browser, headless or headed.
- **Scope:** the component layer checks isolated components and small in-memory
  integrations. The E2E layer checks full pages and user flows in the deployed
  application.
- **Speed:** Bun usually takes milliseconds per test file, with some overhead
  for axe. Browser tests take seconds each and minutes for the whole suite.
- **Defects:** component tests find missing labels, incorrect roles, improper
  ARIA, form-association errors and basic functional bugs. Browser tests find
  colour contrast failures, focus order errors, keyboard traps, missing focus
  outlines, responsive layout breakages, incorrect `lang` attributes and
  integration errors in flows such as modals and navigation. Visual and style
  defects remain outside the Happy DOM and JSDOM scope.
- **Schedule:** component tests run on every change and pull request. Browser
  tests run as a merge gate, nightly and locally before major releases.
- **CI role:** component tests fail the build quickly when a core test or axe
  rule fails. Browser tests validate the integrated product and provide
  artefacts such as screenshots and traces.

This model ensures **accessibility is woven into every stage**: a developer
gets immediate feedback in their IDE or terminal for obvious issues, and the CI
catches anything that requires a real browser to detect.

### 5.1 Implementation Plan

To adopt this framework, a phased rollout is advisable:

#### Phase 1: Setup Bun and Basic Testing (Day 0-1)

- **Install/Verify Bun** in the project. Ensure the `bun:test` script is
  working with Happy DOM. Add a `tests/setup-happy-dom.ts` to configure any
  globals or polyfills (for example, setting `document.doctype` if needed, or
  configuring `window.fetch` if used in tests).

- **Establish Test Structure:** Decide on a directory convention (e.g., all
  tests in `tests/` folder, mirroring src structure). Ensure naming for a11y
  tests is in place (e.g., `*.a11y.test.tsx`).

- **Sample Bun Tests:** Write a couple of simple Bun tests for existing
  components to validate that the framework is running and fast. For example,
  test a context provider or a presentational component. This lays groundwork
  and confidence in Bun’s runner.

#### Phase 2: Integrate Node A11y Testing (Day 1-2)

- **Add Dependencies:** Install `axe-core` (or `jest-axe`) and
  `@testing-library/react` as devDependencies for the Node tests. Also install
  `jsdom` if not already included (though some testing libraries bring it in).
  Optionally, add `tsgo` or configure `tsc` for quick compilation of tests.

- **Node Test Script:** Create an NPM script, e.g.,
  `"test:a11y": "node scripts/run-a11y-tests.js"`. This script can discover
  `*.a11y.test.tsx` files (via glob), compile them (using tsgo or esbuild), and
  execute them. As an interim, one could use a tool like Mocha or Vitest in
  Node just for these tests – but a lightweight custom runner might suffice.

- **First Axe Test:** Write an a11y test for a simple component (like a
  `<Button>` or a form input) and deliberately introduce a violation (e.g.,
  remove an aria-label) to see that it catches it. Then fix the violation and
  see tests pass. This validates the Node axe pipeline.

- **Disable Incompatible Rules:** Configure the axe wrapper to disable
  `color-contrast` and other problematic rules globally for JSDOM. This can be
  done in a setup portion of the Node tests (for example, using `axe.configure`
  to turn off certain checks). Document these disabled rules clearly,
  referencing that Playwright will cover them.

#### Phase 3: Expand Coverage in Inner Loop (Week 1 ongoing)

- **Write Tests for Key Components:** Start adding tests (both Bun and a11y)
  for all crucial components in the codebase. Prioritize components that are
  reused often or have complex accessibility considerations (dialogs, menus,
  inputs, etc.). Leverage the patterns illustrated (render, axe scan, role/name
  assertions).

- **Enforce Query Convention:** Introduce the ESLint rules for Testing Library
  to ensure no one slips in a `getByTestId`. Add this to the CI lint step.
  Also, communicate the guideline to the team: test as a user, not via
  implementation details.

- **Team Training:** Host a short workshop or provide docs on how to write
  these new tests. Show examples of good patterns. This will help scale the
  effort as multiple developers contribute tests.

#### Phase 4: Playwright Setup (Week 2)

- **Install Playwright and Config:** Add Playwright test runner
  (`@playwright/test`) and run `npx playwright install` to get browser
  binaries. Create `playwright.config.ts` with proper settings: use a base URL
  (if running against a dev server or Storybook), configure timeouts, and set
  test directory (e.g., `tests/e2e`). Also enable trace on failure and
  screenshot on failure for debugging.

- **Axe in Playwright:** Import `@axe-core/playwright` in a test to ensure it
  works. Write a basic test that navigates to a page and runs an axe scan. This
  is to validate that our environment can do in-browser scans (and to fine-tune
  any needed delays/wait-fors to stabilize the page).

- **Visual Baseline:** Write a simple visual test for a static page and
  generate the baseline screenshot. Commit this baseline image to the repo (we
  generally commit reference snapshots to track changes over time). Ensure that
  small pixel differences don’t cause noise – adjust threshold or screenshot
  options if needed (like disabling anti-aliasing via CSS in test).

- **Accessibility Snapshots:** Capture the raw text returned by
  `page.ariaSnapshot()`, store it in the snapshot JSON envelope, and compare
  the payload through Playwright's generic `toMatchSnapshot()` boundary. Start
  by snapshotting a simple component or page to test the flow before expanding
  route coverage.

#### Phase 5: Full E2E Test Development (Week 2-3)

- **Implement Scenario Tests:** Begin writing tests for critical user flows:
  e.g., “user can navigate through main menu with keyboard,” “opening and
  closing modals manages focus correctly,” “form error messages are announced
  or present in DOM,” etc. Use the patterns from 3.2.1 and 3.2.2. These tests
  might require building out some test fixture data or using a staging
  environment if working with real backend – ensure they are deterministic.

- **Implement Visual & I18n Tests:** Add tests for visual snapshots of key
  pages in both themes, and for switching language as described. Mark these as
  either part of the main Playwright suite or a separate suite if we want to
  run them less frequently (Playwright can tag tests, e.g., `@visual` tag, to
  filter runs).

- **Parallelize where possible:** Playwright will parallelize by default;
  confirm that our tests are isolated (avoid tests interfering with each other
  by using fresh page/context for each, which Playwright does by default per
  test). Use test fixtures for different viewport sizes or locales to run those
  in parallel threads.

#### Phase 6: CI Integration (Week 3)

- **Set up CI jobs:** Modify the pipeline to include the three jobs (Bun tests,
  Node a11y, Playwright). Use caching where possible (cache `node_modules` or
  Playwright browsers for speed). If using GitHub Actions, ensure runners have
  necessary dependencies (or use the official Playwright action).

- **Artefact & Reporting:** Configure each job to output results. For Bun/Node
  tests, a simple console output might suffice, but we can also output JUnit or
  HTML reports using tools like `bun test --reporter junit` or a custom format.
  For Playwright, enable the HTML report and artefacts (videos, traces on
  failure). Upload these in the CI (Actions artefacts).

- **Failure Criteria:** Any failing test fails the job. Axe tests assert zero
  violations, so any violation fails unless a valid, time-limited allow-list
  entry with an owner, issue link, expiry date, and CI validation covers a
  legacy issue.

- **Notification:** Update PR template or guidelines to mention that a PR will
  not be merged if accessibility tests fail. Possibly integrate a status check
  that specifically surfaces “Accessibility Checks” vs “Unit Tests” so it’s
  clear where an issue lies.

#### Phase 7: Ongoing Maintenance and Coverage (Week 4+)

- **Backfill Tests:** Gradually increase coverage by adding tests for remaining
  components and pages. Our goal is not 100% coverage for coverage’s sake, but
  rather covering all **accessibility aspects** of each element. Use the a11y
  test suite as a checklist for components – if a component has an interactive
  role, ensure it has at least one axe test verifying its basics.

- **Update Snapshots Intentionally:** When a legitimate UI change occurs (e.g.,
  we redesign a component’s structure or text), update the corresponding
  accessibility and visual snapshots. Treat these updates as code changes
  requiring review – double-check that the new output is correct (e.g., if a
  heading level changed, is that semantically acceptable?).

- **Monitor Flakiness:** Keep an eye on E2E test stability. If a test is flaky
  (randomly failing), investigate and fix it promptly, as flaky tests can erode
  team trust in the suite. Playwright’s trace viewer can help debug
  intermittent failures. It might be a timing issue or a test that needs a
  slight adjustment (like waiting for an animation to finish).

- **Continuous Improvement:** As new accessibility best practices or tools
  emerge, integrate them. For example, if a library for detecting screen reader
  announcements becomes available, we could add tests for live region updates.
  Or if Bun adds support for JSDOM in the future, we might simplify the Node
  harness and run axe directly in Bun (dropping the complexity). Remain
  adaptable to improve the framework.

By following this roadmap, we incrementally build up a robust testing regimen.
Each phase delivers tangible benefits (immediate bug catching, new coverage)
without overwhelming the team. Within a few weeks, accessibility testing moves
from an abstract concern to an everyday part of development, with developers
empowered by quick feedback and protected by comprehensive end-to-end checks.

### 5.2 Outcomes and Benefits

In conclusion, this accessibility-first testing architecture embeds the mantra
“**shift left** on accessibility” into our development lifecycle. Fast Bun
tests and Node axe checks mean issues are caught at the earliest possible
moment. Playwright E2E ensures that nothing slips through the cracks when it
comes to real user experience. We no longer rely solely on periodic manual
audits or the diligence of individual developers remembering every ARIA rule –
the system has our back.

**Key benefits we expect:**

- **Higher Quality UIs:** Fewer accessibility bugs reach production, resulting
  in an inclusive product by default.

- **Developer Efficiency:** Quick inner loop tests prevent context-switching;
  developers fix issues while the code is fresh in mind. The outer loop, while
  slower, is automated and saves QA effort by catching issues that would be
  hard to find manually.

- **Documentation by Tests:** The tests themselves serve as living
  documentation of our accessibility expectations. New team members can read
  tests to understand how components should behave (e.g., “Modal should return
  focus to opener on close – see test X”). This knowledge sharing is invaluable.

- **Compliance and Confidence:** We can confidently assert conformance to
  standards (like WCAG 2.1 AA) because we have automated checks for many
  criteria (contrast, focus order, semantics, etc.). This mitigates risk from a
  legal/compliance standpoint and broadens our user reach.

By modernizing the original design to use **Bun for speed** and a **Node assist
for axe**, we preserve the core philosophy: accessibility testing should
enhance, not hinder, our development velocity. Every layer of testing
reinforces the other, and together they create a safety net where accessibility
regressions simply cannot survive unnoticed. This is the essence of
high-velocity, accessibility-first development – moving fast **without breaking
things** for our users.

## Footnotes

[^1]: Happy DOM issue tracker – documented incompatibility of
    `Node.isConnected` implementation with axe-core's expectations.
[^2]: Bun GitHub issue #3554 – tracking request for JSDOM support in Bun's
    test runner. The issue is closed, and Bun v1.1.41 brought JSDOM
    compatibility improvements.
[^3]: Deque `axe-core` documentation – notes on JSDOM support and rules like
    `color-contrast` being inapplicable in headless DOM.
