# Mocking services with Simulacrum, actors, and stable keyset connections

A useful service mock does not merely answer requests. It remembers, enforces
rules, and exposes the same little world through every protocol surface. The
goal is not a papier-mâché endpoint that returns JSON-shaped confetti. The goal
is a simulator: a compact, deterministic model of a service with state,
identity, permissions, pagination, latency, failure modes, and scenario control.

For experienced TypeScript developers, the core architecture should look like
this:

```text
fixtures
  -> canonical store
  -> selectors and domain actions
  -> actor-aware views
  -> REST / GraphQL / webhooks / scenario routes
```

The most important design constraint is that REST handlers, GraphQL resolvers,
scenario routes, webhook emitters, and inspection tools must all read from and
write to the same canonical state. If each route carries its own miniature
reality, tests will eventually discover that one endpoint lives in springtime
while another endpoint reports a snowstorm.

## 1. Treat Simulacrum as a simulator substrate

Simulacrum provides the bones of a service simulator: an Express-based server,
OpenAPI-backed handlers, static JSON route support, store extension, route
extension, request logging, optional response delay, and a simulation
inspection surface.

Start with Simulacrum when any of these are needed:

A fake HTTP service that a production client can call through a configurable
base URL.

A mock that can move beyond static fixtures into stateful behaviour.

An OpenAPI description that can provide shallow default behaviour while teams
progressively replace important endpoints with scripted handlers.

A local development service that behaves closely enough to exercise UI states,
retry code, auth flows, and edge cases.

A CI-safe simulator that starts on a dynamic port and shuts down cleanly.

A minimal service might look like this:

```typescript
import {
  createFoundationSimulationServer,
  type Document
} from '@simulacrum/foundation-simulator';

import type { Request, Response } from 'express';

type TicketStatus = 'open' | 'closed';

type Ticket = {
  id: string;
  title: string;
  status: TicketStatus;
  createdAt: string;
  updatedAt: string;
};

const initialTickets: Record<string, Ticket> = {
  'TCK-1': {
    id: 'TCK-1',
    title: 'Replace the cardboard dragon',
    status: 'open',
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z'
  }
};

export const createTicketSimulator = (openApiDocument: Document) =>
  createFoundationSimulationServer({
    port: 0,
    simulationContextPage: '/simulation',

    extendStore: {
      schema: ({ slice }) => ({
        tickets: slice.table({ initialState: initialTickets })
      }),

      selectors: ({ schema, createSelector }) => ({
        openTickets: createSelector(
          schema.tickets.selectTableAsList,
          tickets => tickets.filter(ticket => ticket.status === 'open')
        ),

        ticketById(state: unknown, id: string): Ticket | undefined {
          return schema.tickets.selectById(state, { id });
        }
      }),

      actions: ({ thunks, schema }) => ({
        closeTicket: thunks.create<{ id: string; now: string }>(
          'tickets/close',
          function* (ctx, next) {
            yield* schema.update(
              schema.tickets.patch({
                [ctx.payload.id]: {
                  status: 'closed',
                  updatedAt: ctx.payload.now
                }
              })
            );

            yield* next();
          }
        )
      })
    },

    openapi: [
      {
        document: openApiDocument,
        apiRoot: '/',

        handlers: simulationStore => ({
          'tickets/list': async () => ({
            status: 200,
            json: simulationStore.schema.tickets.selectTableAsList(
              simulationStore.store.getState()
            )
          }),

          'tickets/get': async (context, _request, response) => {
            const { id } = context.request.params as { id: string };

            const ticket = simulationStore.selectors.ticketById(
              simulationStore.store.getState(),
              id
            );

            if (!ticket) {
              return response.status(404).json({ message: 'Not Found' });
            }

            return response.status(200).json(ticket);
          }
        })
      }
    ],

    extendRouter(router, simulationStore) {
      router.get('/health', (_request: Request, response: Response) => {
        response.json({ status: 'ok' });
      });

      router.post('/__scenario__/tickets/:id/close', (request, response) => {
        simulationStore.store.dispatch(
          simulationStore.actions.closeTicket({
            id: request.params.id,
            now: new Date().toISOString()
          })
        );

        response.sendStatus(204);
      });
    }
  });
```

This example already contains the most important pieces: canonical state,
selectors, domain actions, API adapters, and scenario routes. None of those
pieces should know that a test expects a specific assertion. They should model
the simulated service’s behaviour.

## 2. Use static JSON only as the first rung

Static JSON routes help when fast scaffolding is needed:

```text
GET /account -> account.json
GET /products -> products.json
GET /plans -> plans.json
```

That works for early UI wiring, contract exploration, and smoke tests. It fails
as soon as an application needs to perform a write, list a changed entity,
enforce visibility, paginate consistently, retry a transient failure, or
observe a webhook.

Use static JSON for shape.

Use store-backed handlers for behaviour.

A simple maturity ladder helps:

```text
static fixture
  -> OpenAPI example response
  -> store-backed read
  -> store-backed mutation
  -> actor-aware mutation
  -> cross-protocol behaviour
  -> latency / failure / concurrency scenario
```

Do not skip the middle rungs. A simulator grows best when each endpoint earns
its complexity.

## 3. Keep production clients configurable, not simulator-aware

Production code should not contain `isSimulator`, `isLocal`, or
`useMockService` branches. Configuration should choose the service base URL and
credentials.

```typescript
type ServiceClientOptions = {
  baseUrl: string;
  accessToken: string;
  fetch?: typeof fetch;
};

export class ServiceClient {
  readonly #baseUrl: string;
  readonly #accessToken: string;
  readonly #fetch: typeof fetch;

  constructor(options: ServiceClientOptions) {
    this.#baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.#accessToken = options.accessToken;
    this.#fetch = options.fetch ?? fetch;
  }

  async getTicket(id: string): Promise<Ticket> {
    const response = await this.#fetch(`${this.#baseUrl}/tickets/${id}`, {
      headers: {
        Authorization: `Bearer ${this.#accessToken}`
      }
    });

    if (!response.ok) {
      throw new Error(`failed to fetch ticket ${id}: ${response.status}`);
    }

    return response.json() as Promise<Ticket>;
  }
}
```

Then tests point the same client at the simulator:

```typescript
import { afterEach, beforeEach, expect, test } from 'vitest';

let running: {
  port: number;
  ensureClose(): Promise<void>;
};

beforeEach(async () => {
  const simulator = createTicketSimulator(openApiDocument);
  running = await simulator.listen(0);
});

afterEach(async () => {
  await running.ensureClose();
});

test('reads a seeded ticket', async () => {
  const client = new ServiceClient({
    baseUrl: `http://127.0.0.1:${running.port}`,
    accessToken: 'user:alice'
  });

  await expect(client.getTicket('TCK-1')).resolves.toMatchObject({
    id: 'TCK-1',
    status: 'open'
  });
});
```

The simulator and production service now share a single client contract. The
test changes coordinates, not code paths.

## 4. Model identity with actors

The actor model gives every request a principal. The actor can be anonymous, a
user, a machine token, a service account, an installation, a tenant
administrator, or any other identity the simulated service needs.

Do not sprinkle token parsing across handlers. Resolve the actor once and pass
it down.

```typescript
type Permission = 'read' | 'write' | 'admin';

type ResourceKey = `${string}:${string}`;

type Actor =
  | {
      kind: 'anonymous';
      cacheKey: 'anonymous';
    }
  | {
      kind: 'user';
      id: string;
      displayName: string;
      scopes: ReadonlySet<string>;
      cacheKey: `user:${string}`;
    }
  | {
      kind: 'service';
      id: string;
      scopes: ReadonlySet<string>;
      cacheKey: `service:${string}`;
    }
  | {
      kind: 'installation';
      id: string;
      tenantId: string;
      resources: ReadonlySet<ResourceKey>;
      permissions: ReadonlyMap<ResourceKey, Permission>;
      cacheKey: `installation:${string}`;
    };

const anonymousActor: Actor = {
  kind: 'anonymous',
  cacheKey: 'anonymous'
};

type ActorTokenRecord = {
  token: string;
  actor: Exclude<Actor, { kind: 'anonymous' }>;
  expiresAt?: string;
};

const bearerToken = (authorization: string | undefined): string | undefined => {
  if (!authorization) return undefined;

  const [scheme, token] = authorization.split(/\s+/, 2);

  if (scheme?.toLowerCase() !== 'bearer') return undefined;
  if (!token) return undefined;

  return token;
};
```

Keep token records in simulator state:

```typescript
type ActorStoreExtensionInput = {
  tokens: readonly ActorTokenRecord[];
};

export const actorStoreExtension = ({ tokens }: ActorStoreExtensionInput) => ({
  schema: ({ slice }) => ({
    actorTokens: slice.table({
      initialState: Object.fromEntries(
        tokens.map(record => [record.token, record])
      )
    })
  }),

  selectors: ({ schema }) => ({
    actorForToken(state: unknown, token: string | undefined): Actor {
      if (!token) return anonymousActor;

      const record = schema.actorTokens.selectById(state, { id: token });

      if (!record) return anonymousActor;

      if (record.expiresAt && Date.parse(record.expiresAt) <= Date.now()) {
        return anonymousActor;
      }

      return record.actor;
    }
  })
});
```

Resolve actors from HTTP requests at the boundary:

```typescript
import type { Request } from 'express';

type SimulationStoreWithActors = {
  store: { getState(): unknown };
  selectors: {
    actorForToken(state: unknown, token: string | undefined): Actor;
  };
};

export const resolveActorFromExpressRequest = (
  request: Request,
  simulationStore: SimulationStoreWithActors
): Actor => {
  const token =
    bearerToken(request.get('authorization')) ??
    request.get('x-simulator-token');

  return simulationStore.selectors.actorForToken(
    simulationStore.store.getState(),
    token
  );
};
```

A simulator does not need to validate real cryptographic credentials unless the
credential protocol itself forms part of the test target. Fake tokens work
beautifully when the simulator models the consequences of identity: visibility,
scopes, expiry, ownership, rate limits, and permissions.

The boundary may be fake. The rules inside should be crisp.

## 5. Define canonical keys before defining routes

Stateful mocks rot fastest when entities lack stable identity. Define canonical
keys for every entity type before writing REST handlers or GraphQL resolvers.

For a generic multi-tenant service, this could be:

```typescript
type TenantKey = string;
type ProjectKey = `${TenantKey}/${string}`;
type TicketKey = `${ProjectKey}#${string}`;
type CommentKey = `${TicketKey}/comments/${string}`;
type AttachmentKey = `${TicketKey}/attachments/${string}`;
type UserKey = `user:${string}`;

type ProjectScoped = {
  tenantId: string;
  projectId: string;
};

const projectKey = (value: ProjectScoped): ProjectKey =>
  `${value.tenantId}/${value.projectId}`;

const ticketKey = (value: ProjectScoped & { ticketId: string }): TicketKey =>
  `${value.tenantId}/${value.projectId}#${value.ticketId}`;
```

A good canonical key has these properties:

It includes all namespace components needed to avoid collisions.

It uses stable identifiers, not display names that users can edit.

It round-trips easily through logs and diagnostics.

It can serve as a table key.

It can participate in sort keys and cursor payloads.

It does not depend on array position.

Canonical keys also provide better diagnostics:

```typescript
throw new Error(`duplicate ticket key in seed data: ${ticketKey(ticket)}`);
```

A duplicate-key failure at simulator startup beats a phantom pagination bug
three hours later. Tiny dragon, caught early.

## 6. Validate seed state aggressively

Seed fixtures should feel pleasant to write but strict to load. Use Zod,
Valibot, TypeBox, or another schema system to validate fixture shape and
relationships.

```typescript
import { z } from 'zod';

const IsoDateTime = z.string().datetime();

const TicketSeed = z.object({
  tenantId: z.string().min(1),
  projectId: z.string().min(1),
  ticketId: z.string().min(1),
  title: z.string().min(1),
  status: z.enum(['open', 'closed']),
  createdAt: IsoDateTime,
  updatedAt: IsoDateTime,
  assigneeId: z.string().optional()
});

type TicketSeed = z.infer<typeof TicketSeed>;

const InitialState = z.object({
  tickets: z.array(TicketSeed),
  actors: z.array(
    z.object({
      token: z.string().min(1),
      actorId: z.string().min(1)
    })
  )
});

type InitialState = z.infer<typeof InitialState>;
```

During conversion, check relationships and duplicates:

```typescript
type Ticket = TicketSeed & {
  key: TicketKey;
};

const toTicketTable = (seeds: readonly TicketSeed[]): Record<TicketKey, Ticket> => {
  const table: Record<TicketKey, Ticket> = {};

  for (const seed of seeds) {
    const key = ticketKey(seed);

    if (table[key]) {
      throw new Error(`duplicate ticket key: ${key}`);
    }

    if (Date.parse(seed.updatedAt) < Date.parse(seed.createdAt)) {
      throw new Error(`ticket ${key} has updatedAt before createdAt`);
    }

    table[key] = {
      ...seed,
      key
    };
  }

  return table;
};
```

Prefer explicit seed data for identifiers, timestamps, sort fields, and
ownership. Generate harmless defaults only when they cannot affect test
behaviour.

Good builders help:

```typescript
const ticket = (overrides: Partial<TicketSeed> = {}): TicketSeed => ({
  tenantId: 'tenant-a',
  projectId: 'project-a',
  ticketId: 'TCK-1',
  title: 'Default ticket',
  status: 'open',
  createdAt: '2026-01-01T00:00:00.000Z',
  updatedAt: '2026-01-01T00:00:00.000Z',
  ...overrides
});
```

Avoid hidden randomness unless the test explicitly controls the seed. A random
UUID inside a cursor or snapshot assertion is a tiny ferret with bolt cutters.

## 7. Build selectors and indexes as the simulator’s nervous system

Handlers should not scan entire tables repeatedly. Keep traversal logic in
selectors and build memoized indexes for hot paths.

```typescript
type Ticket = {
  key: TicketKey;
  tenantId: string;
  projectId: string;
  ticketId: string;
  title: string;
  status: 'open' | 'closed';
  createdAt: string;
  updatedAt: string;
};

const buildTicketsByProject = (
  tickets: readonly Ticket[]
): ReadonlyMap<ProjectKey, readonly Ticket[]> => {
  const index = new Map<ProjectKey, Ticket[]>();

  for (const ticket of tickets) {
    const key = projectKey(ticket);
    const bucket = index.get(key);

    if (bucket) {
      bucket.push(ticket);
    } else {
      index.set(key, [ticket]);
    }
  }

  return index;
};
```

In a Simulacrum store extension:

```typescript
selectors: ({ schema, createSelector }) => {
  const ticketsByProject = createSelector(
    schema.tickets.selectTableAsList,
    buildTicketsByProject
  );

  return {
    getTicket(
      state: unknown,
      coordinates: ProjectScoped & { ticketId: string }
    ): Ticket | undefined {
      return schema.tickets.selectById(state, {
        id: ticketKey(coordinates)
      });
    },

    listTicketsForProject(
      state: unknown,
      coordinates: ProjectScoped
    ): readonly Ticket[] {
      return ticketsByProject(state).get(projectKey(coordinates)) ?? [];
    }
  };
}
```

Use indexes for every common relationship:

```text
tenant -> projects
project -> tickets
ticket -> comments
actor -> visible resources
resource -> permissions
event type -> domain events
foreign id -> canonical key
```

The rule is simple: if a resolver can run once per parent row, it must not
perform a full table scan. That is where innocent mocks grow quadratic teeth.

## 8. Separate domain rules from protocol adapters

A REST handler should not contain business logic. A GraphQL resolver should not
mutate tables directly. Keep domain rules in pure functions and actions.

```typescript
const canReadTicket = (actor: Actor, ticket: Ticket): boolean => {
  if (actor.kind === 'anonymous') return false;

  if (actor.kind === 'user' || actor.kind === 'service') {
    return actor.scopes.has('tickets:read');
  }

  if (actor.kind === 'installation') {
    const resource = projectKey(ticket);
    return actor.resources.has(resource);
  }

  return false;
};

const canCloseTicket = (actor: Actor, ticket: Ticket): boolean => {
  if (!canReadTicket(actor, ticket)) return false;

  if (actor.kind === 'user' || actor.kind === 'service') {
    return actor.scopes.has('tickets:write');
  }

  if (actor.kind === 'installation') {
    const permission = actor.permissions.get(projectKey(ticket));
    return permission === 'write' || permission === 'admin';
  }

  return false;
};
```

Then build a domain view:

```typescript
type TicketViewInput = {
  state: unknown;
  actor: Actor;
  coordinates: ProjectScoped & { ticketId: string };
  simulationStore: {
    selectors: {
      getTicket(
        state: unknown,
        coordinates: ProjectScoped & { ticketId: string }
      ): Ticket | undefined;
    };
  };
};

const getReadableTicket = ({
  state,
  actor,
  coordinates,
  simulationStore
}: TicketViewInput): Ticket | undefined => {
  const ticket = simulationStore.selectors.getTicket(state, coordinates);

  if (!ticket) return undefined;
  if (!canReadTicket(actor, ticket)) return undefined;

  return ticket;
};
```

Now protocols become thin adapters:

```typescript
const restGetTicket = simulationStore => async (context, request, response) => {
  const actor = resolveActorFromExpressRequest(request, simulationStore);
  const state = simulationStore.store.getState();

  const ticket = getReadableTicket({
    state,
    actor,
    coordinates: {
      tenantId: String(context.request.params.tenantId),
      projectId: String(context.request.params.projectId),
      ticketId: String(context.request.params.ticketId)
    },
    simulationStore
  });

  if (!ticket) {
    return response.status(404).json({ message: 'Not Found' });
  }

  return response.status(200).json(toRestTicket(ticket));
};
```

The same domain view can serve GraphQL, webhooks, and inspection routes. One
lawbook, many windows.

## 9. Centralize mutations as actions

Every write should pass through a domain action. Do not let a REST handler
patch one table while a GraphQL mutation patches another table differently.

```typescript
type DomainEvent =
  | {
      type: 'ticket.closed';
      actorCacheKey: string;
      ticketKey: TicketKey;
      occurredAt: string;
    }
  | {
      type: 'ticket.assigned';
      actorCacheKey: string;
      ticketKey: TicketKey;
      assigneeId: string;
      occurredAt: string;
    };

type CloseTicketPayload = {
  actor: Actor;
  coordinates: ProjectScoped & { ticketId: string };
  now: string;
};

const createTicketActions = ({ thunks, schema, selectors }) => ({
  closeTicket: thunks.create<CloseTicketPayload>(
    'tickets/close',
    function* (ctx, next) {
      const { actor, coordinates, now } = ctx.payload;
      const state = yield* select();

      const ticket = selectors.getTicket(state, coordinates);

      if (!ticket) {
        throw new Error(`ticket not found: ${ticketKey(coordinates)}`);
      }

      if (!canCloseTicket(actor, ticket)) {
        throw new Error(`actor cannot close ticket: ${actor.cacheKey}`);
      }

      const key = ticketKey(coordinates);
      const eventKey = `${now}:ticket.closed:${key}`;

      yield* schema.update(
        schema.tickets.patch({
          [key]: {
            status: 'closed',
            updatedAt: now
          }
        })
      );

      yield* schema.update(
        schema.domainEvents.patch({
          [eventKey]: {
            type: 'ticket.closed',
            actorCacheKey: actor.cacheKey,
            ticketKey: key,
            occurredAt: now
          } satisfies DomainEvent
        })
      );

      yield* next();
    }
  )
});
```

REST can call the action:

```typescript
const restCloseTicket = simulationStore => async (context, request, response) => {
  const actor = resolveActorFromExpressRequest(request, simulationStore);

  simulationStore.store.dispatch(
    simulationStore.actions.closeTicket({
      actor,
      coordinates: {
        tenantId: String(context.request.params.tenantId),
        projectId: String(context.request.params.projectId),
        ticketId: String(context.request.params.ticketId)
      },
      now: new Date().toISOString()
    })
  );

  return response.sendStatus(204);
};
```

GraphQL can call the same action. Scenario routes can call the same action.
Webhook emitters can read the domain event written by the same action. That
shared path eliminates a whole shelf of “REST says yes, GraphQL says no”
insects.

## 10. Expose collections as connections, not raw arrays

A service simulator should resist returning raw arrays once the real service
supports pagination, sorting, filtering, or visibility.

Use a connection shape:

```typescript
type PageInfo = {
  hasPreviousPage: boolean;
  hasNextPage: boolean;
  startCursor?: string;
  endCursor?: string;
};

type Edge<Node> = {
  cursor: string;
  node: Node;
};

type Connection<Node> = {
  totalCount: number;
  edges: Array<Edge<Node>>;
  nodes: Node[];
  pageInfo: PageInfo;
};
```

A connection does four useful things in simulations:

It forces stable ordering to be defined.

It makes pagination behaviour explicit and testable.

It lets REST and GraphQL share the same collection semantics.

It gives actor-specific visibility a proper home.

Even if a REST endpoint returns this shape:

```json
{
  "items": [],
  "next_cursor": null
}
```

the simulator can still build it internally from a generic connection helper.
Adapt the final wire shape at the edge.

## 11. Use stable keyset cursors inside simulations

Array-index cursors look tempting:

```typescript
const cursor = String(index);
```

They work only when the result set never changes, the actor never changes, no
filtering changes, and no items appear or disappear between page requests. That
describes a museum display, not a service simulation.

A robust simulator should use stable keyset cursors. A keyset cursor encodes
the last item’s stable sort key, plus enough scope to prove that the cursor
belongs to this exact connection view.

For example:

```typescript
type SortPart = string | number | boolean | null;
type SortKey = readonly [SortPart, ...SortPart[]];

type CursorPayload = {
  version: 1;
  scope: string;
  direction: 'forward' | 'backward';
  key: SortKey;
};
```

The cursor should encode:

A version, so cursor format can change later.

A connection scope, so callers cannot reuse a cursor from another collection.

A direction, if the API distinguishes forward and backward traversal.

A stable sort key, not an array index.

The key should include a tie-breaker that uniquely identifies the row. For
example:

```typescript
const ticketSortKey = (ticket: Ticket): SortKey => [
  ticket.updatedAt,
  ticket.key
];
```

If two tickets share the same `updatedAt`, the canonical key breaks the tie.
Without the tie-breaker, pagination can skip or duplicate rows when sort values
collide.

## 12. Define cursor scope as part of the contract

Cursor scope protects the simulator from category errors.

This cursor:

```text
tenant-a/project-a tickets visible to user:alice sorted by updatedAt desc
```

must not work against:

```text
tenant-a/project-a tickets visible to user:bob sorted by updatedAt desc
```

or:

```text
tenant-a/project-a tickets visible to user:alice sorted by createdAt asc
```

or:

```text
tenant-b/project-z tickets visible to user:alice sorted by updatedAt desc
```

Build scope from every component that affects membership or ordering:

```typescript
type ConnectionScopeInput = {
  connectionName: string;
  actor: Actor;
  tenantId: string;
  projectId: string;
  filters: Record<string, string | number | boolean | null | undefined>;
  orderBy: string;
};

const stableJson = (value: unknown): string => {
  if (
    value === null ||
    typeof value !== 'object' ||
    Array.isArray(value)
  ) {
    return JSON.stringify(value);
  }

  const object = value as Record<string, unknown>;

  return JSON.stringify(
    Object.fromEntries(
      Object.keys(object)
        .sort()
        .map(key => [key, stableJson(object[key])])
    )
  );
};

const connectionScope = ({
  connectionName,
  actor,
  tenantId,
  projectId,
  filters,
  orderBy
}: ConnectionScopeInput): string =>
  [
    connectionName,
    `actor=${actor.cacheKey}`,
    `tenant=${tenantId}`,
    `project=${projectId}`,
    `filters=${stableJson(filters)}`,
    `order=${orderBy}`
  ].join('|');
```

For a public, anonymous collection, include `actor=anonymous`. For a
tenant-wide administrator, include the administrator’s actor cache key unless
every administrator sees exactly the same rows. Be conservative: if actor
identity can affect visibility, put it in the scope.

## 13. Encode cursors opaquely

Clients should treat cursors as opaque strings. That does not mean they need
cryptographic secrecy in a simulator, but they should not invite application
code to depend on their internals.

A simple base64url JSON cursor works well:

```typescript
const encodeCursor = (payload: CursorPayload): string =>
  Buffer.from(JSON.stringify(payload), 'utf8').toString('base64url');

const decodeCursorPayload = (cursor: string): CursorPayload => {
  let parsed: unknown;

  try {
    parsed = JSON.parse(Buffer.from(cursor, 'base64url').toString('utf8'));
  } catch {
    throw new CursorError('invalid cursor encoding');
  }

  if (!isCursorPayload(parsed)) {
    throw new CursorError('invalid cursor payload');
  }

  return parsed;
};

const isCursorPayload = (value: unknown): value is CursorPayload => {
  if (!value || typeof value !== 'object') return false;

  const candidate = value as Partial<CursorPayload>;

  return (
    candidate.version === 1 &&
    typeof candidate.scope === 'string' &&
    (candidate.direction === 'forward' || candidate.direction === 'backward') &&
    Array.isArray(candidate.key) &&
    candidate.key.length > 0
  );
};

class CursorError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CursorError';
  }
}
```

If a simulator handles sensitive test data, sign cursor payloads with an HMAC.
For most local and CI simulation, scope validation and opaque encoding suffice.

## 14. Compare sort keys precisely

A stable keyset cursor needs a deterministic comparator. Avoid locale-dependent
surprises unless the simulated service genuinely sorts by locale collation.

```typescript
const compareSortPart = (left: SortPart, right: SortPart): number => {
  if (left === right) return 0;

  if (left === null) return -1;
  if (right === null) return 1;

  if (typeof left === 'number' && typeof right === 'number') {
    return left - right;
  }

  if (typeof left === 'boolean' && typeof right === 'boolean') {
    return Number(left) - Number(right);
  }

  return String(left) < String(right) ? -1 : 1;
};

const compareSortKey = (left: SortKey, right: SortKey): number => {
  const length = Math.max(left.length, right.length);

  for (let index = 0; index < length; index += 1) {
    const result = compareSortPart(left[index] ?? null, right[index] ?? null);

    if (result !== 0) return result;
  }

  return 0;
};

const invertComparison = (value: number): number =>
  value === 0 ? 0 : -value;
```

For descending order, either invert the comparator or normalize descending
fields into ascending-compatible values. In a simulator, inverting the
comparator usually reads better:

```typescript
type SortDirection = 'asc' | 'desc';

type SortSpec<Row> = {
  keyOf(row: Row): SortKey;
  direction: SortDirection;
};

const compareRows = <Row>(sort: SortSpec<Row>, left: Row, right: Row): number => {
  const result = compareSortKey(sort.keyOf(left), sort.keyOf(right));

  return sort.direction === 'asc' ? result : invertComparison(result);
};
```

Always include a unique tie-breaker at the end of the key. The tie-breaker
should follow the same direction as the rest of the key unless the target
service defines otherwise.

```typescript
const ticketUpdatedDescending: SortSpec<Ticket> = {
  direction: 'desc',
  keyOf: ticket => [ticket.updatedAt, ticket.key]
};
```

## 15. Implement a generic keyset connection helper

A reusable helper lets REST and GraphQL share pagination semantics.

```typescript
type PageArgs = {
  first?: number | null;
  after?: string | null;
  last?: number | null;
  before?: string | null;
};

type KeysetConnectionOptions<Row, Node> = {
  scope: string;
  rows: readonly Row[];
  sort: SortSpec<Row>;
  nodeOf(row: Row): Node;
  defaultPageSize?: number;
  maxPageSize?: number;
  direction?: 'forward' | 'backward';
};

const assertPageArgs = (
  args: PageArgs,
  maxPageSize: number,
  defaultPageSize: number
): number => {
  if (args.first != null && args.last != null) {
    throw new CursorError("do not combine 'first' and 'last'");
  }

  if (args.after && args.before) {
    throw new CursorError("do not combine 'after' and 'before'");
  }

  if (args.first != null && args.first < 0) {
    throw new CursorError("'first' must be non-negative");
  }

  if (args.last != null && args.last < 0) {
    throw new CursorError("'last' must be non-negative");
  }

  const requested = args.first ?? args.last ?? defaultPageSize;

  return Math.min(requested, maxPageSize);
};

const decodeCursor = (
  cursor: string,
  expectedScope: string
): CursorPayload => {
  const payload = decodeCursorPayload(cursor);

  if (payload.scope !== expectedScope) {
    throw new CursorError('cursor does not belong to this connection');
  }

  return payload;
};

const makeCursor = (
  scope: string,
  direction: CursorPayload['direction'],
  key: SortKey
): string =>
  encodeCursor({
    version: 1,
    scope,
    direction,
    key
  });

export const toKeysetConnection = <Row, Node>(
  args: PageArgs,
  options: KeysetConnectionOptions<Row, Node>
): Connection<Node> => {
  const defaultPageSize = options.defaultPageSize ?? 50;
  const maxPageSize = options.maxPageSize ?? 100;
  const direction = options.direction ?? (args.last != null ? 'backward' : 'forward');

  const limit = assertPageArgs(args, maxPageSize, defaultPageSize);

  const sorted = [...options.rows].sort((left, right) =>
    compareRows(options.sort, left, right)
  );

  const afterPayload = args.after
    ? decodeCursor(args.after, options.scope)
    : undefined;

  const beforePayload = args.before
    ? decodeCursor(args.before, options.scope)
    : undefined;

  const afterKey = afterPayload?.key;
  const beforeKey = beforePayload?.key;

  const filtered = sorted.filter(row => {
    const rowKey = options.sort.keyOf(row);
    const compareAfter =
      afterKey ? compareSortKey(rowKey, afterKey) : undefined;
    const compareBefore =
      beforeKey ? compareSortKey(rowKey, beforeKey) : undefined;

    if (options.sort.direction === 'asc') {
      if (compareAfter != null && compareAfter <= 0) return false;
      if (compareBefore != null && compareBefore >= 0) return false;
    } else {
      if (compareAfter != null && compareAfter >= 0) return false;
      if (compareBefore != null && compareBefore <= 0) return false;
    }

    return true;
  });

  const pageRows =
    args.last != null
      ? filtered.slice(Math.max(0, filtered.length - limit))
      : filtered.slice(0, limit);

  const edges = pageRows.map(row => ({
    cursor: makeCursor(options.scope, direction, options.sort.keyOf(row)),
    node: options.nodeOf(row)
  }));

  const firstPageRow = pageRows[0];
  const lastPageRow = pageRows.at(-1);

  const firstPageKey = firstPageRow ? options.sort.keyOf(firstPageRow) : undefined;
  const lastPageKey = lastPageRow ? options.sort.keyOf(lastPageRow) : undefined;

  const firstPageIndex = firstPageKey
    ? filtered.findIndex(row => compareSortKey(options.sort.keyOf(row), firstPageKey) === 0)
    : -1;

  const lastPageIndex = lastPageKey
    ? filtered.findIndex(row => compareSortKey(options.sort.keyOf(row), lastPageKey) === 0)
    : -1;

  return {
    totalCount: sorted.length,
    edges,
    nodes: edges.map(edge => edge.node),
    pageInfo: {
      hasPreviousPage: firstPageIndex > 0,
      hasNextPage: lastPageIndex >= 0 && lastPageIndex < filtered.length - 1,
      startCursor: edges[0]?.cursor,
      endCursor: edges.at(-1)?.cursor
    }
  };
};
```

That helper implements the essential simulation semantics:

It sorts by a stable key.

It filters relative to `after` or `before` using the sort key.

It validates cursor scope.

It enforces page-size limits.

It exposes `edges`, `nodes`, `totalCount`, and `pageInfo`.

It works for REST and GraphQL adapters.

For very large fixtures, replace `findIndex` with a binary search over sorted
keys. In most service simulations, the clearer implementation above wins until
benchmarks prove otherwise.

## 16. Make keyset cursors actor-aware

Actor filtering must happen before pagination. Otherwise, users can observe
phantom gaps, infer hidden resources, or receive unstable pages.

Do this:

```typescript
const visibleTickets = allTickets.filter(ticket =>
  canReadTicket(actor, ticket)
);

const connection = toKeysetConnection(args, {
  scope,
  rows: visibleTickets,
  sort: ticketUpdatedDescending,
  nodeOf: toGraphqlTicket
});
```

Do not do this:

```typescript
const connection = toKeysetConnection(args, {
  scope,
  rows: allTickets,
  sort: ticketUpdatedDescending,
  nodeOf: ticket => canReadTicket(actor, ticket) ? toGraphqlTicket(ticket) : null
});
```

Membership comes first. Pagination comes second. Projection comes third.

For a generic project ticket connection:

```typescript
type TicketConnectionArgs = PageArgs & {
  status?: 'open' | 'closed' | null;
  orderBy?: 'UPDATED_AT_DESC' | 'CREATED_AT_ASC' | null;
};

const ticketConnectionForProject = (
  coordinates: ProjectScoped,
  args: TicketConnectionArgs,
  context: {
    actor: Actor;
    state: unknown;
    simulationStore: {
      selectors: {
        listTicketsForProject(
          state: unknown,
          coordinates: ProjectScoped
        ): readonly Ticket[];
      };
    };
  }
): Connection<GraphqlTicket> => {
  const orderBy = args.orderBy ?? 'UPDATED_AT_DESC';

  const filters = {
    status: args.status ?? null
  };

  const scope = connectionScope({
    connectionName: 'Project.tickets',
    actor: context.actor,
    tenantId: coordinates.tenantId,
    projectId: coordinates.projectId,
    filters,
    orderBy
  });

  const rows = context.simulationStore.selectors
    .listTicketsForProject(context.state, coordinates)
    .filter(ticket => canReadTicket(context.actor, ticket))
    .filter(ticket => !args.status || ticket.status === args.status);

  const sort =
    orderBy === 'CREATED_AT_ASC'
      ? {
          direction: 'asc' as const,
          keyOf: (ticket: Ticket): SortKey => [ticket.createdAt, ticket.key]
        }
      : {
          direction: 'desc' as const,
          keyOf: (ticket: Ticket): SortKey => [ticket.updatedAt, ticket.key]
        };

  return toKeysetConnection(args, {
    scope,
    rows,
    sort,
    nodeOf: toGraphqlTicket,
    defaultPageSize: 50,
    maxPageSize: 100
  });
};
```

This connection remains stable across protocol surfaces and honest about actor
visibility.

## 17. Handle writes between pages deliberately

Stable keyset cursors give simulations sane behaviour when data changes between
page requests, but they do not make changing data magically static. Decide
which semantics are wanted.

Most simulated services should use live keyset semantics:

First request:

```text
GET /tickets?first=2
```

returns tickets updated at:

```text
10:00 TCK-5
09:00 TCK-4
```

The cursor stores:

```text
[09:00, tenant-a/project-a#TCK-4]
```

Then another action updates `TCK-2` to `09:30`.

Second request:

```text
GET /tickets?first=2&after=<cursor for TCK-4>
```

With descending `updatedAt`, `TCK-2` now sits before the cursor, so the second
page will not include it. That matches many real keyset-paginated APIs. The
cursor means “continue after this key in the current ordered view”, not
“continue from a frozen snapshot”.

If snapshot semantics are required, include a snapshot identifier in scope and
store the snapshot membership:

```typescript
type Snapshot = {
  id: string;
  createdAt: string;
  actorCacheKey: string;
  connectionScopeWithoutSnapshot: string;
  rowKeys: readonly string[];
};

type SnapshotCursorPayload = CursorPayload & {
  snapshotId: string;
};
```

Snapshot pagination costs more memory and state management. Use it only when an
application or target protocol requires frozen list traversal. Live keyset
semantics usually offer the best balance for simulations because they match the
behaviour of many operational systems and keep the simulator lean.

## 18. Convert connections to REST wire formats

Internal connection helpers do not force GraphQL-only output. REST can adapt
the same connection to its own shape.

```typescript
type RestListResponse<Item> = {
  items: Item[];
  next_cursor: string | null;
  previous_cursor: string | null;
  total_count: number;
};

const toRestListResponse = <Node, Item>(
  connection: Connection<Node>,
  itemOf: (node: Node) => Item
): RestListResponse<Item> => ({
  items: connection.nodes.map(itemOf),
  next_cursor: connection.pageInfo.hasNextPage
    ? connection.pageInfo.endCursor ?? null
    : null,
  previous_cursor: connection.pageInfo.hasPreviousPage
    ? connection.pageInfo.startCursor ?? null
    : null,
  total_count: connection.totalCount
});
```

A REST handler then stays thin:

```typescript
const restListTickets = simulationStore => async (context, request, response) => {
  const actor = resolveActorFromExpressRequest(request, simulationStore);
  const state = simulationStore.store.getState();
  const rawLimit = request.query.limit;
  const limit = typeof rawLimit === 'string' && /^\d+$/.test(rawLimit)
    ? Number(rawLimit)
    : undefined;

  if (rawLimit !== undefined && limit === undefined) {
    response.status(400).json({message: 'limit must be a non-negative integer'});
    return;
  }

  const args: TicketConnectionArgs = {
    first: limit,
    after: typeof request.query.cursor === 'string'
      ? request.query.cursor
      : undefined,
    status:
      request.query.status === 'open' || request.query.status === 'closed'
        ? request.query.status
        : undefined,
    orderBy: 'UPDATED_AT_DESC'
  };

  try {
    const connection = ticketConnectionForProject(
      {
        tenantId: String(context.request.params.tenantId),
        projectId: String(context.request.params.projectId)
      },
      args,
      {
        actor,
        state,
        simulationStore
      }
    );

    return response.status(200).json(
      toRestListResponse(connection, toRestTicket)
    );
  } catch (error) {
    if (error instanceof CursorError) {
      return response.status(400).json({ message: error.message });
    }

    throw error;
  }
};
```

REST and GraphQL now share ordering, cursor validation, visibility, and
page-size limits. The adapters only reshape the packet.

## 19. Convert connections to GraphQL fields

GraphQL resolvers should reuse the same connection factory:

```typescript
const resolvers = {
  Project: {
    tickets(
      project: { tenantId: string; projectId: string },
      args: TicketConnectionArgs,
      context: GraphQLContext
    ) {
      return ticketConnectionForProject(
        {
          tenantId: project.tenantId,
          projectId: project.projectId
        },
        args,
        context
      );
    }
  }
};
```

Keep GraphQL context actor-aware:

```typescript
type GraphQLContext = {
  actor: Actor;
  state: unknown;
  simulationStore: ExtendedSimulationStore;
};

export const createGraphQLContext = (
  request: Request,
  simulationStore: ExtendedSimulationStore
): GraphQLContext => {
  const token = bearerToken(
    request.headers.get('authorization') ?? undefined
  );

  const state = simulationStore.store.getState();

  return {
    actor: simulationStore.selectors.actorForToken(state, token),
    state,
    simulationStore
  };
};
```

For mutations, call the same actions that REST calls:

```typescript
const mutationResolvers = {
  Mutation: {
    closeTicket(
      _root: unknown,
      args: {
        input: {
          tenantId: string;
          projectId: string;
          ticketId: string;
        };
      },
      context: GraphQLContext
    ) {
      context.simulationStore.store.dispatch(
        context.simulationStore.actions.closeTicket({
          actor: context.actor,
          coordinates: args.input,
          now: new Date().toISOString()
        })
      );

      const ticket = getReadableTicket({
        state: context.simulationStore.store.getState(),
        actor: context.actor,
        coordinates: args.input,
        simulationStore: context.simulationStore
      });

      return {
        ticket: ticket ? toGraphqlTicket(ticket) : null
      };
    }
  }
};
```

This keeps mutation effects observable through every read path.

## 20. Make unsupported behaviour explicit

A simulator should not silently pretend to support everything. Use a capability
matrix:

```typescript
type Capability =
  | 'fully-scriptable'
  | 'partially-scriptable'
  | 'schema-stubbed'
  | 'placeholder'
  | 'unsupported';

type CapabilityRecord = {
  surface: 'rest' | 'graphql' | 'webhook' | 'scenario';
  name: string;
  capability: Capability;
  notes?: string;
};

const capabilities: readonly CapabilityRecord[] = [
  {
    surface: 'rest',
    name: 'GET /tenants/:tenantId/projects/:projectId/tickets',
    capability: 'fully-scriptable',
    notes: 'Actor-aware; supports status filter and keyset cursor pagination.'
  },
  {
    surface: 'graphql',
    name: 'Project.tickets',
    capability: 'fully-scriptable',
    notes: 'Shares connection helper with REST.'
  },
  {
    surface: 'webhook',
    name: 'ticket.closed',
    capability: 'partially-scriptable',
    notes: 'Domain event exists; delivery retries are scenario-controlled.'
  }
];
```

Expose capabilities through an inspection route:

```typescript
router.get('/__simulator__/capabilities', (_request, response) => {
  response.json({ capabilities });
});
```

This pays for itself when a test fails because an endpoint returns a plausible
example response but not stateful behaviour. Plausible falsehoods wear good
shoes. They get far.

## 21. Use OpenAPI as scaffolding

OpenAPI-backed mocks stand up a broad surface quickly. Keep that broad surface
honest by promoting important operations into store-backed handlers.

A healthy progression:

```text
Operation exists in schema
  -> returns example response
  -> validates request shape
  -> reads canonical store
  -> applies actor visibility
  -> supports stable pagination
  -> supports writes through domain actions
  -> emits domain events
```

For operations that remain schema-stubbed, document that fact. Example
responses work well for shallow integration tests, but they do not prove that
the simulator models service behaviour.

## 22. Model errors as carefully as successes

Error semantics deserve first-class treatment. The simulator should help client
code practise failure.

Use these defaults:

Malformed request shape: `400`.

Invalid cursor encoding, mismatched cursor scope, negative page size, or
incompatible pagination arguments: `400`.

Missing credentials where credentials are required: `401`.

Authenticated actor lacks permission for a visible operation: `403`.

Private or hidden resource should not reveal existence: `404`.

Unknown resource: `404`.

Conflict with current state, such as closing an already closed item when the
real service rejects it: `409`.

Unsupported operation: `501` or a documented stub response, depending on the
simulator contract.

Impossible simulator invariant: throw loudly or return `500`.

Cursor errors should not leak implementation internals:

```typescript
const toCursorErrorResponse = (error: CursorError): { message: string } => ({
  message: error.message
});
```

Avoid returning the decoded cursor payload to clients unless the route belongs
to the simulator inspection namespace.

## 23. Add scenario routes for orchestration

Scenario routes let tests change simulator conditions without pretending those
routes exist in the real service.

Keep them under an unmistakable namespace:

```typescript
extendRouter(router, simulationStore) {
  router.post('/__scenario__/reset', (_request, response) => {
    simulationStore.store.dispatch(
      simulationStore.actions.resetToInitialState()
    );

    response.sendStatus(204);
  });

  router.post('/__scenario__/actors/:actorId/expire', (request, response) => {
    simulationStore.store.dispatch(
      simulationStore.actions.expireActor({
        actorId: request.params.actorId
      })
    );

    response.sendStatus(204);
  });

  router.post('/__scenario__/tickets/:tenantId/:projectId/:ticketId/touch', (request, response) => {
    const actor = resolveActorFromExpressRequest(request, simulationStore);

    simulationStore.store.dispatch(
      simulationStore.actions.touchTicket({
        actor,
        coordinates: {
          tenantId: request.params.tenantId,
          projectId: request.params.projectId,
          ticketId: request.params.ticketId
        },
        now: new Date().toISOString()
      })
    );

    response.sendStatus(204);
  });
}
```

Scenario routes should call the same domain actions as real routes unless they
intentionally set up impossible state for resilience testing. If they create
impossible state, name them accordingly:

```text
/__scenario__/corrupt/...
/__scenario__/force/...
/__scenario__/network/...
```

No velvet curtains. Make the trapdoor visible.

## 24. Simulate latency and faults deterministically

Random latency can expose UI assumptions, but deterministic scenarios make
reliable tests.

For local development:

```typescript
const delayResponses =
  process.env.SIMULATOR_LATENCY === 'slow'
    ? { minimum: 250, maximum: 750 }
    : 0;
```

For CI, prefer scripted conditions:

```typescript
type FaultRule = {
  id: string;
  method: string;
  pathPattern: string;
  remainingMatches: number;
  response: {
    status: number;
    body: unknown;
  };
};

const shouldApplyFault = (
  rule: FaultRule,
  request: Request
): boolean =>
  rule.remainingMatches > 0 &&
  rule.method === request.method &&
  new RegExp(rule.pathPattern).test(request.path);
```

Scenario route:

```typescript
router.post('/__scenario__/faults', (request, response) => {
  simulationStore.store.dispatch(
    simulationStore.actions.addFaultRule(request.body)
  );

  response.sendStatus(204);
});
```

Middleware:

```typescript
router.use((request, response, next) => {
  const state = simulationStore.store.getState();
  const fault = simulationStore.selectors.nextFaultForRequest(state, request);

  if (!fault) {
    next();
    return;
  }

  simulationStore.store.dispatch(
    simulationStore.actions.consumeFaultRule({ id: fault.id })
  );

  response.status(fault.response.status).json(fault.response.body);
});
```

This lets tests say “the next matching request fails with `503`” rather than
“sometimes the gremlin sneezes”.

## 25. Keep time injectable

Time affects cursors, ordering, expiry, rate limits, retries, and event
emission. Do not scatter `new Date()` across domain code. Inject a clock.

```typescript
type Clock = {
  now(): string;
};

const systemClock: Clock = {
  now: () => new Date().toISOString()
};

const fixedClock = (now: string): Clock => ({
  now: () => now
});
```

Use it in actions:

```typescript
type ActionContext = {
  clock: Clock;
};

const createActions = ({ clock }: ActionContext) => ({
  closeTicket(payload: Omit<CloseTicketPayload, 'now'>): CloseTicketPayload {
    return {
      ...payload,
      now: clock.now()
    };
  }
});
```

Or put the current simulated time in the store:

```typescript
type SimulatedClockState = {
  now: string;
};

router.post('/__scenario__/time', (request, response) => {
  simulationStore.store.dispatch(
    simulationStore.actions.setSimulatedTime({
      now: request.body.now
    })
  );

  response.sendStatus(204);
});
```

If time can move, cursor tests become far easier. You can touch one entity,
advance time by one minute, and assert the new keyset order without praying to
the millisecond pixies.

## 26. Add domain events and optional webhook delivery

A good simulator records what happened. A great simulator lets tests inspect or
deliver those events.

```typescript
type DomainEventBase = {
  id: string;
  type: string;
  actorCacheKey: string;
  occurredAt: string;
};

type TicketClosedEvent = DomainEventBase & {
  type: 'ticket.closed';
  ticketKey: TicketKey;
};

type AnyDomainEvent = TicketClosedEvent;
```

Store domain events as append-only rows:

```typescript
const eventId = (event: Pick<AnyDomainEvent, 'occurredAt' | 'type'>): string =>
  `${event.occurredAt}:${event.type}:${crypto.randomUUID()}`;
```

Expose inspection:

```typescript
router.get('/__simulator__/events', (request, response) => {
  const state = simulationStore.store.getState();

  const events = simulationStore.schema.domainEvents
    .selectTableAsList(state)
    .filter(event =>
      typeof request.query.type === 'string'
        ? event.type === request.query.type
        : true
    );

  response.json({ events });
});
```

Deliver webhooks through a controlled queue if an application consumes them:

```typescript
type WebhookDelivery = {
  id: string;
  eventId: string;
  targetUrl: string;
  status: 'pending' | 'delivered' | 'failed';
  attempts: number;
  nextAttemptAt: string;
};
```

For most test suites, polling `/__simulator__/events` gives more deterministic
assertions than real outbound HTTP delivery. Use full webhook delivery when the
product’s webhook receiver forms part of the behaviour under test.

## 27. Test the simulator itself

Treat the simulator as infrastructure with its own test suite. Otherwise, every
downstream test inherits its false assumptions.

Prioritize these tests:

Actor resolution:

```text
missing token -> anonymous
unknown token -> anonymous or 401, according to the contract
expired token -> anonymous or 401
user token -> user actor
service token -> service actor
installation token -> installation actor
```

Visibility:

```text
anonymous cannot read private resource
actor can read assigned resource
actor cannot read unassigned resource
admin can read tenant-wide resource
hidden resources return 404 where appropriate
```

Connections:

```text
stable order with duplicate timestamps
first page returns correct endCursor
after endCursor returns next rows
last page returns correct startCursor
before startCursor returns previous rows
invalid base64 cursor returns 400
valid cursor with wrong scope returns 400
cursor from different actor returns 400
cursor from different filter returns 400
cursor from different sort order returns 400
insert before cursor does not appear on later page under live semantics
insert after cursor can appear on later page under live semantics
delete cursor row still allows continuation by key
```

Cross-protocol consistency:

```text
mutate through REST, read through GraphQL
mutate through GraphQL, read through REST
mutate through scenario route, observe event log
close ticket, then list connection observes new sort order
```

Performance:

```text
listing one project does not scan unrelated tenant-heavy fixtures per parent row
nested GraphQL query does not perform N full table scans
connection helper handles thousands of rows within a small budget
```

Capability:

```text
documented unsupported endpoint fails in documented way
schema-stubbed endpoint does not claim stateful behaviour
inspection route reports capability matrix
```

## 28. Benchmark selectors before optimizing everything else

Most simulator slowness comes from repeated filtering and nested resolver
scans, not from JSON serialization or cursor encoding.

A simple micro-benchmark can smoke out the goblins:

```typescript
import { performance } from 'node:perf_hooks';

const measure = <T>(label: string, fn: () => T): T => {
  const startedAt = performance.now();

  try {
    return fn();
  } finally {
    const duration = performance.now() - startedAt;
    console.log(`${label}: ${duration.toFixed(2)}ms`);
  }
};

measure('list tickets for project', () => {
  for (let index = 0; index < 1_000; index += 1) {
    simulationStore.selectors.listTicketsForProject(state, {
      tenantId: 'tenant-a',
      projectId: 'project-a'
    });
  }
});
```

Build indexes where the same query shape repeats. Keep raw table scans for rare
administrative or inspection routes.

Useful indexes include:

```text
by canonical key
by parent key
by actor cache key
by tenant
by status
by event type
by external id
```

For connection-heavy fixtures, sorted lists can be cached per scope:

```typescript
type SortedConnectionCache<Row> = ReadonlyMap<string, readonly Row[]>;

const sortTicketsForConnection = (
  rows: readonly Ticket[],
  sort: SortSpec<Ticket>
): readonly Ticket[] =>
  [...rows].sort((left, right) => compareRows(sort, left, right));
```

Only cache sorted lists when profiling says it helps. Sorting a few hundred
rows per request often costs less than maintaining elaborate cache invalidation
machinery. Avoid building machinery that does not need to exist.

## 29. Keep concurrency realistic but bounded

Node’s request handling can interleave asynchronous work. Simulator
implementations should avoid accidental race bugs, especially if scenario
routes introduce waits, faults, or webhook delivery.

Keep store mutations synchronous where possible.

Avoid reading state, awaiting, then writing based on stale assumptions unless
the simulated service has that race.

For deterministic concurrency scenarios, add explicit gates:

```typescript
type Gate = {
  id: string;
  status: 'closed' | 'open';
};

router.post('/__scenario__/gates/:id/open', (request, response) => {
  simulationStore.store.dispatch(
    simulationStore.actions.openGate({ id: request.params.id })
  );

  response.sendStatus(204);
});

const waitForGate = async (
  simulationStore: ExtendedSimulationStore,
  gateId: string,
  timeoutMs: number
): Promise<void> => {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const state = simulationStore.store.getState();

    if (simulationStore.selectors.gateIsOpen(state, gateId)) {
      return;
    }

    await new Promise(resolve => setTimeout(resolve, 10));
  }

  throw new Error(`timed out waiting for gate ${gateId}`);
};
```

Then a handler can pause at a known point:

```typescript
router.post('/dangerous-operation', async (request, response) => {
  await waitForGate(simulationStore, 'dangerous-operation', 5_000);

  response.json({ ok: true });
});
```

This gives precise tests for cancellation, retry storms, duplicate submission,
and out-of-order completion.

## 30. Organize the simulator package by responsibility

A maintainable simulator usually wants this shape:

```text
src/
  domain/
    actors.ts
    permissions.ts
    keys.ts
    events.ts
    time.ts
  store/
    schema.ts
    selectors.ts
    actions.ts
    seed.ts
  connections/
    cursor.ts
    keyset.ts
    scopes.ts
  rest/
    handlers.ts
    serializers.ts
    errors.ts
  graphql/
    schema.graphql
    resolvers.ts
    context.ts
    serializers.ts
  scenario/
    routes.ts
    faults.ts
    gates.ts
  inspection/
    routes.ts
    capabilities.ts
  simulator.ts
```

That structure keeps the service model independent of protocol machinery. It
also helps expose when a REST handler starts hoarding business logic like a
raccoon with a jewellery box.

## 31. Use TypeScript to make invalid states inconvenient

TypeScript cannot prove a simulator correct, but it can make sloppy states
annoying.

Brand canonical keys:

```typescript
type Brand<T, Name extends string> = T & { readonly __brand: Name };

type TenantId = Brand<string, 'TenantId'>;
type ProjectId = Brand<string, 'ProjectId'>;
type TicketId = Brand<string, 'TicketId'>;
type TicketKey = Brand<string, 'TicketKey'>;

const asTenantId = (value: string): TenantId => value as TenantId;
const asProjectId = (value: string): ProjectId => value as ProjectId;
const asTicketId = (value: string): TicketId => value as TicketId;

const makeTicketKey = (
  tenantId: TenantId,
  projectId: ProjectId,
  ticketId: TicketId
): TicketKey =>
  `${tenantId}/${projectId}#${ticketId}` as TicketKey;
```

Use discriminated unions for actor and event variants:

```typescript
type ActorKind = Actor['kind'];

const assertNever = (value: never): never => {
  throw new Error(`unexpected value: ${JSON.stringify(value)}`);
};

const actorLabel = (actor: Actor): string => {
  switch (actor.kind) {
    case 'anonymous':
      return 'anonymous';

    case 'user':
      return actor.displayName;

    case 'service':
      return `service:${actor.id}`;

    case 'installation':
      return `installation:${actor.id}`;

    default:
      return assertNever(actor);
  }
};
```

Use readonly arrays and maps in selectors to discourage accidental mutation:

```typescript
const listVisibleTickets = (
  actor: Actor,
  tickets: readonly Ticket[]
): readonly Ticket[] =>
  tickets.filter(ticket => canReadTicket(actor, ticket));
```

Avoid `any` in simulator domain code. If `unknown` is needed at the boundary,
parse it immediately.

## 32. Design for reset and isolation

Every test should receive a clean simulator or an intentional scenario state.

The most robust approach starts a fresh simulator on a dynamic port per test
file or per test case:

```typescript
let running: {
  port: number;
  ensureClose(): Promise<void>;
};

beforeEach(async () => {
  running = await createSimulator({ initialState }).listen(0);
});

afterEach(async () => {
  await running.ensureClose();
});
```

If startup cost becomes too high, use reset routes:

```typescript
router.post('/__scenario__/reset', (_request, response) => {
  simulationStore.store.dispatch(
    simulationStore.actions.replaceState({
      state: createStoreStateFromInitialSeed(initialState)
    })
  );

  response.sendStatus(204);
});
```

Reset must clear:

```text
entity tables
domain events
webhook queues
fault rules
gates
rate-limit buckets
actor token expiry mutations
simulated clock changes
connection snapshots, if used
```

Partial reset produces haunted tests. Full reset shuts the crypt door.

## 33. Keep logs useful

A simulator should log enough to diagnose a failing test without drowning CI
output.

Record:

```text
request id
method
path
actor cache key
status code
duration
matched operation name, where available
scenario fault id, where applicable
domain events emitted
cursor error class, not full sensitive payload
```

A simple request log entry:

```typescript
type RequestLogEntry = {
  id: string;
  method: string;
  path: string;
  actorCacheKey: string;
  statusCode: number;
  durationMs: number;
  operationName?: string;
  faultRuleId?: string;
  emittedEventIds: readonly string[];
};
```

Expose recent logs through inspection:

```typescript
router.get('/__simulator__/requests', (_request, response) => {
  const state = simulationStore.store.getState();

  response.json({
    requests: simulationStore.schema.requestLogs.selectTableAsList(state)
  });
});
```

When a connection test fails, include cursor diagnostics in simulator logs, not
in public responses:

```typescript
type CursorDiagnostic = {
  scope: string;
  error: string;
  receivedCursorHash: string;
};
```

Hash the cursor rather than logging the whole thing if fixtures contain
sensitive data.

## 34. Decide how realistic the simulator should be

Realism costs. Spend it where the product makes decisions.

High-value realism:

```text
identity and permissions
read-after-write state
pagination and ordering
error codes
rate limits, if client handles them
webhook events, if the product consumes them
latency and retry scenarios
```

Low-value realism, unless directly under test:

```text
full cryptographic token verification
perfect wire-level parity for unused fields
every obscure endpoint in a large public API
random production-like timing
undocumented provider quirks
```

The simulator should model the slice of service behaviour an application
depends on. Avoid building an empire when a border checkpoint is enough, but
make that checkpoint extremely convincing.

## 35. A practical build sequence

Start with a narrow slice:

```text
one entity type
one list endpoint
one get endpoint
one actor type
one permission rule
one mutation
one connection helper
one scenario route
```

Then expand in this order:

1. Canonical keys and seed validation.

2. Store tables and selectors.

3. Actor resolution.

4. Permission functions.

5. Store-backed reads.

6. Stable keyset connection helper.

7. Store-backed mutations.

8. Domain events.

9. REST adapters.

10. GraphQL adapters, if needed.

11. Scenario routes.

12. Faults, gates, and latency.

13. Capability inspection.

14. Simulator self-tests.

A minimal vertical slice beats a broad fake surface. Once the first slice works
properly, every later feature has a place to live.

## 36. Checklist for stable keyset cursor simulations

Use this list when reviewing a paginated simulator endpoint:

The connection sorts by stable fields.

The final sort field uniquely identifies the row.

The cursor stores the sort key, not an array index.

The cursor includes a version.

The cursor includes a scope.

The scope includes actor identity when visibility can differ by actor.

The scope includes filters.

The scope includes sort order.

The scope includes parent resource identity.

Actor visibility applies before pagination.

Filters apply before pagination.

Projection to REST or GraphQL shape happens after pagination.

Invalid cursor encoding returns `400`.

Wrong-scope cursor returns `400`.

Negative page size returns `400`.

The endpoint enforces a maximum page size.

The endpoint has deterministic behaviour when rows share timestamps.

Tests cover insertion, update, and deletion between page requests.

The simulator documents whether the connection uses live or snapshot semantics.

That list is where pagination bugs go to lose their tiny hats.

## 37. The design mantra

Make the simulator boringly truthful.

A strong Simulacrum-based simulator does not need to mirror an entire external
service. It needs to model the behaviour a client application actually relies
on, with stable identity, actor-aware visibility, deterministic state
transitions, honest capability boundaries, fast selectors, scenario control,
and stable keyset cursors.

The reward is a test harness that does not merely return expected JSON. It
hosts a small pocket universe with laws. Client applications can poke it, page
through it, mutate it, authenticate to it, retry against it, and still receive
answers that make sense.
