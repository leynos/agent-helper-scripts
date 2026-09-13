# Architecting Resilient Local-First Applications in React: An Expert Guide to Zustand, Tanstack Query, and Real-Time Synchronization

## The Local-First Paradigm for Modern Web Applications

### Defining Local-First: A Paradigm Shift from Cloud-Centric to User-Centric

The dominant architectural pattern for web applications over the past two
decades has been the cloud-first, or "thin-client," model. In this paradigm,
the server holds the primary, authoritative copy of all data, and the
client-side application is merely a subordinate cache, a window through which
users interact with this central source of truth.[^1] Every significant data
modification must be sent to the server to be validated and persisted;
otherwise, from the system's perspective, it "didn't happen".[^1] While this
model has enabled unprecedented levels of real-time collaboration and
multi-device access, it is fundamentally constrained by the physics of network
communication. Latency is an unavoidable reality, leading to user interfaces
filled with loading spinners and a user experience that is entirely dependent
on a stable internet connection.

In response to these limitations, a new architectural philosophy has emerged:
**local-first software**. This paradigm inverts the traditional model. It
treats the copy of the data on the user's local device—their laptop, tablet, or
phone—as the primary copy.[^1] Servers are relegated to a secondary role,
acting as a backup and a rendezvous point for synchronizing data between a
user's devices or with other collaborators.[^2] This fundamental shift is not
merely a technical implementation detail; it is a re-evaluation of the
relationship between the user, their data, and the network. The motivation is
to create applications that are inherently faster, more reliable, and that
grant users true ownership and control over their digital artefacts.[^1] The
ultimate goal is to achieve the best of both worlds: the rich, real-time
collaboration of modern cloud applications combined with the performance,
longevity, and data sovereignty of traditional, offline-capable desktop
software.[^1] This architectural approach redefines the server's role from a
gatekeeper of data to a facilitator of synchronization, prioritizing the user's
immediate experience above all else.

### The Seven Ideals of Local-First Software

The principles of local-first software can be distilled into seven distinct
ideals, as articulated by the research group Ink & Switch. These ideals serve
as a guiding philosophy and a benchmark for the architecture detailed in this
report, outlining the tangible user-facing benefits that this approach aims to
deliver.[^1]

1. **No spinners: work at the user's fingertips.** The most immediate and
   perceptible benefit of a local-first architecture is its speed. Because all
   operations read from and write to a local database on the device, the user
   interface can respond instantly to user input. There is no need to wait for
   a network round-trip to complete before reflecting a change. This eliminates
   the ubiquitous loading spinners and progress bars that characterize
   cloud-centric applications, creating a fluid and responsive user
   experience.[^1] Data synchronization with other devices or collaborators
   occurs quietly and asynchronously in the background.
2. **Users' work is not trapped on one device.** While the primary copy of the
   data resides locally, a core tenet of modern computing is the ability to
   access information from multiple devices. Local-first applications achieve
   this by ensuring that data is seamlessly synchronized across all of a user's
   devices, providing the convenience of multi-device access without being
   solely dependent on a central server.[^1]
3. **The network is optional.** In a local-first model, an internet connection
   is treated as an enhancement, not a requirement. The application must be
   fully functional offline, allowing users to create, read, update, and delete
   data without interruption. When a network connection becomes available, the
   application opportunistically synchronizes any local changes with the server
   and pulls down updates from other clients.[^1]
4. **Seamless collaboration with colleagues.** Local-first architecture
   does not sacrifice the collaborative capabilities that have made cloud
   applications indispensable. The goal is to support real-time, multi-user
   collaboration that is on par with, or even superior to, existing cloud-based
   tools. This is often achieved through advanced data structures and
   algorithms that allow for the automatic merging of changes from multiple
   users, even when those changes are made concurrently while offline.[^1]
5. **The Long Now.** By storing both the application's data and the software
   required to interpret it on the user's device, local-first applications
   offer greater longevity. Users are not dependent on a company's continued
   operation to access their data. Even if the service provider were to shut
   down its servers, the user would retain their local data and the ability to
   use the application, safeguarding their work against the volatility of the
   tech industry.[^1]
6. **Security and privacy by default.** Centralized servers that store
   unencrypted data for thousands or millions of users are high-value targets
   for attackers. Local-first applications enhance security and privacy by
   design. Data is stored on the user's own device, and when it is synchronized
   via a server, it can be end-to-end encrypted. This ensures that the server
   operator cannot access the content of the user's data, only store the
   encrypted blobs.[^1]
7. **Users retain ultimate ownership and control.** Perhaps the most profound
   philosophical shift is the restoration of data ownership to the user.
   Because the data resides in files on their local device, users have ultimate
   agency. They can back it up, move it, manipulate it with other tools, or
   delete it permanently, all without needing permission from a service
   provider. This model empowers users with full control and sovereignty over
   their own data.[^1]

### Acknowledging the Core Challenge: Eventual Consistency

The profound benefits of the local-first paradigm come with a significant
architectural trade-off: the abandonment of strong consistency in favour of
**eventual consistency**.[^2] In a traditional cloud-first model, the server
acts as a single, authoritative source of truth, ensuring that all users see a
consistent view of the data at all times. In a local-first system, however,
there are multiple sources of truth—one on each user's device, and potentially
another on the server.

This distributed nature means that at any given moment, the data on different
devices may be temporarily out of sync. This leads to the most complex
challenge in local-first development: **data conflict resolution**. Conflicts
arise when two or more users (or the same user on different devices) modify the
same piece of data independently while offline. When these devices later
reconnect and attempt to synchronize their changes, the system must have a
strategy for reconciling the conflicting versions into a single, coherent
state.[^2] This is not a problem that can be solved by a single library or
framework; it is a fundamental business logic challenge that requires careful
design and consideration, a topic that will be explored in depth in Section 8
of this report.

## Architectural Foundations: Delineating Client and Server State

### The Two Categories of Application State

At the heart of any modern, complex web application lie two fundamentally
different categories of state. A failure to recognize and properly manage this
distinction is a primary source of complexity, bugs, and performance issues.
The entire architecture presented in this report is predicated on a clear and
disciplined separation of these two state types.

- **Client State:** This category encompasses all data that is owned
  exclusively by the client-side application. It is typically synchronous,
  ephemeral, and directly related to the user interface and its current
  condition. Examples of client state include the open or closed status of a
  dialog box, the current values in a multi-step form before submission, the
  application's theme (e.g., light or dark mode), or the selection state of
  items in a list.[^6] This state is not persisted remotely and is generally
  not expected to survive a browser refresh unless explicitly saved to local
  storage for user convenience.
- **Server State:** This refers to data that is persisted remotely on a server
  and is considered the authoritative source of truth for the application's
  core domain entities. From the client's perspective, server state is a local
  cache of this remote data. It is inherently asynchronous, as it must be
  fetched over a network. It is also shared, meaning other users or processes
  can change it without the client's direct knowledge, causing the local cache
  to become "stale".[^3] In the context of this local-first architecture, this
  "server state" is mirrored and persisted on the client's device, becoming the
  primary data source that the application interacts with, but its lifecycle
  and synchronization challenges remain.

### Why a Single State Manager is an Anti-Pattern

A common architectural mistake, particularly in applications that have grown
organically, is the attempt to manage both client and server state within a
single global state management library, such as Redux or even a simple
implementation using Zustand alone.[^7] This approach inevitably leads to what
can be described as a "state management soup," where the distinct lifecycles of
the two state types become entangled, creating a host of problems.

When a client state library is used to store server state, the developer is
forced to manually re-implement a vast amount of complex logic that is required
to manage the asynchronous nature of that data. This includes manually tracking
loading and error states for every network request, implementing caching logic
to avoid redundant fetches, devising strategies for background data refetching
to prevent staleness, and handling request deduplication.[^3] This results in a
significant amount of boilerplate code and introduces numerous opportunities
for bugs, such as displaying stale data or creating race conditions. The core
issue is that libraries designed for managing simple, synchronous client state
are not equipped with the specialized tools needed to handle the complex,
asynchronous lifecycle of server state.[^8]

### Introducing the Specialists: Zustand and Tanstack Query

The most robust and maintainable architecture is one that embraces the
principle of separation of concerns by using specialized tools for each
category of state. This report advocates for a combination of two best-in-class
libraries that are purpose-built for their respective domains.

- **Zustand for Client State:** Zustand is a small, fast, and scalable state
  management solution designed for managing client state with minimal
  boilerplate.[^10] Its API is based on hooks, making it feel native to the
  React ecosystem. It is unopinionated, performant by default due to its
  selective subscription model, and does not require wrapping the application
  in a context provider.[^13] These characteristics make it the ideal tool for
  managing the ephemeral, UI-related state that is owned by the client.
- **Tanstack Query for Server State:** Tanstack Query (formerly React Query) is
  a powerful library for managing server state.[^3] It is more accurately
  described as a server-state synchronization engine rather than a simple
  data-fetching library.[^3] It provides a declarative, hook-based API that
  automates the difficult challenges of server state management, including
  caching, background updates, request deduplication, and handling loading and
  error states.[^3] By offloading these responsibilities to Tanstack Query,
  developers can drastically simplify their component logic and build more
  resilient applications. Adopting a dedicated server-state tool like Tanstack
  Query has the profound effect of simplifying and shrinking the amount of
  global client state an application needs, often reducing it to just a few UI
  flags.[^6]

This deliberate separation forms the cornerstone of this local-first
architecture. It allows each library to perform the task for which it was
designed, resulting in a system that is more performant, less complex, and
easier to maintain at scale.

| Feature                   | Zustand                                                            | Tanstack Query                                                                                             |
| ------------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| **Primary Use Case**      | Client State Management                                            | Server State Management & Synchronization                                                                  |
| **State Characteristics** | Synchronous, ephemeral, UI-related state owned by the client.      | Asynchronous, cached remote data that can become stale.                                                    |
| **Core Features**         | Simple store creation, actions, performant selectors via hooks.    | Declarative data fetching, automatic caching, background refetching, mutations, offline support, devtools. |
| **Boilerplate**           | Minimal to none. No providers, reducers, or action types required. | Low. A declarative hook (`useQuery`) replaces complex manual state management logic.                       |
| **Data Flow**             | Direct, synchronous state updates via `set()` function.            | Manages the entire asynchronous lifecycle: `pending`, `error`, `success`.                                  |

## Mastering Client State with Zustand

### Core Concepts: The `create` API

Zustand's API is intentionally minimalist, centred around a single function:
`create`. This function takes a "creator" function as an argument, which
defines the initial state and the actions that can modify it.[^10] The
`create` function returns a custom hook that can be used to access the store
from any component in the application.

A key feature of Zustand is its developer-friendly approach to state updates.
The `set` function, which is provided to the creator function, handles state
merging by default. This means developers can update a single property of an
object without needing to manually spread the rest of the state (`{...state}`),
reducing boilerplate and a common source of errors.[^10] Furthermore, the
creator function also receives a
`get` function, which allows actions to access the current state, enabling
complex logic where the next state depends on the current one.[^10]

```javascript
// src/stores/uiStore.js
import { create } from 'zustand';

const useUIStore = create((set, get) => ({
  isSidebarOpen: false,
  theme: 'light',
  
  // Action to toggle the sidebar
  toggleSidebar: () => set((state) => ({ isSidebarOpen:!state.isSidebarOpen })),
  
  // Action to set the theme
  setTheme: (newTheme) => set({ theme: newTheme }),
  
  // Example of an action using get()
  resetToDefault: () => {
    const currentTheme = get().theme;
    console.log(`Resetting UI state. Current theme was: ${currentTheme}`);
    set({ isSidebarOpen: false, theme: 'light' });
  },
}));

export default useUIStore;

```

### Consuming State in Components: The Selector Pattern

Connecting a React component to a Zustand store is as simple as calling the
custom hook returned by `create`. However, the key to achieving optimal
performance with Zustand lies in the use of the **selector pattern**.[^11]

Instead of subscribing to the entire state object, which would cause the
component to re-render whenever _any_ part of the state changes, a selector
function is passed to the hook. This function "selects" only the specific piece
of state that the component needs. Zustand then tracks this selected value and
will only trigger a re-render in the component if that specific value
changes.[^11] This granular subscription model is the foundation of Zustand's
performance and prevents the unnecessary re-renders that can plague other state
management solutions.

```javascript
// src/components/Header.jsx
import React from 'react';
import useUIStore from '../stores/uiStore';

function Header() {
  // Selector for a single state property.
  // This component will ONLY re-render when `isSidebarOpen` changes.
  const isSidebarOpen = useUIStore((state) => state.isSidebarOpen);
  
  // Selector for an action. Actions are stable, so this won't cause re-renders.
  const toggleSidebar = useUIStore((state) => state.toggleSidebar);

  return (
    <header>
      <h1>My App</h1>
      <button onClick={toggleSidebar}>
        {isSidebarOpen? 'Close Menu' : 'Open Menu'}
      </button>
    </header>
  );
}

// src/components/ThemeSwitcher.jsx
import React from 'react';
import useUIStore from '../stores/uiStore';

function ThemeSwitcher() {
  // This component subscribes to a different piece of state.
  // It will ONLY re-render when `theme` changes.
  const theme = useUIStore((state) => state.theme);
  const setTheme = useUIStore((state) => state.setTheme);

  const handleThemeChange = (e) => {
    setTheme(e.target.value);
  };

  return (
    <div>
      <label>Theme:</label>
      <select value={theme} onChange={handleThemeChange}>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </div>
  );
}

```

In the example above, the `Header` component and the `ThemeSwitcher` component
are completely decoupled in their rendering cycles. A change to the `theme`
will not cause the `Header` to re-render, and vice-versa. This is a powerful
demonstration of how Zustand's design naturally guides developers toward
building performant applications.

### Extending Functionality with Middleware

Zustand's core is minimal, but it can be extended with powerful functionality
through middleware. Middleware are functions that wrap the creator function,
augmenting the store's capabilities. One of the most commonly used is the
`persist` middleware, which provides a simple way to save the store's state to
a persistent storage layer like `localStorage` or `AsyncStorage` in React
Native.[^11]

This is particularly useful for client state that should be remembered across
sessions, such as user preferences or UI settings. The `persist` middleware
automatically handles the serialization and hydration of the state, making it
trivial to implement.

```javascript
// src/stores/settingsStore.js
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const useSettingsStore = create(
  persist(
    (set) => ({
      notificationsEnabled: true,
      language: 'en',
      
      toggleNotifications: () => set((state) => ({ notificationsEnabled:!state.notificationsEnabled })),
      setLanguage: (lang) => set({ language: lang }),
    }),
    {
      name: 'app-settings-storage', // The key to use in localStorage
    }
  )
);

export default useSettingsStore;

```

This simple example provides a gentle introduction to the concept of state
persistence, which is explored in much greater depth when this report
discusses persisting the server state cache in Section 6.

## Server State Synchronization with Tanstack Query

### Beyond Data Fetching: Tanstack Query as a Synchronization Engine

It is a common misconception to view Tanstack Query as merely a data-fetching
library. While it does manage the process of fetching data, its true power and
purpose lie in its role as a **server-state synchronization engine**.[^3] Its
primary responsibility is to manage the client-side cache of server state,
ensuring that it remains as synchronized as possible with the remote source of
truth.

Tanstack Query automates a wide range of complex tasks that are otherwise left
to the developer to handle manually. These include[^3]:

- **Caching:** Storing the results of successful requests in memory to avoid
  redundant network calls for the same data.
- **Request Deduping:** If multiple components request the same data at the
  same time, Tanstack Query will automatically deduplicate these requests into
  a single network call.
- **Background Updates:** Intelligently refetching stale data in the background
  to keep the UI up-to-date without disruptive loading indicators.
- **Staleness Management:** Providing a sophisticated mechanism to determine
  when cached data is "out of date" and needs to be refreshed.

By abstracting these concerns away, Tanstack Query allows developers to focus
on what data their components need, rather than the complex mechanics of how to
fetch and maintain it.

### The Query Lifecycle: ,`staleTime`, vs. ,`gcTime`

Understanding the distinction between `staleTime` and `gcTime` (garbage
collection time) is the absolute key to mastering Tanstack Query's caching
behaviour. These two configuration options govern the entire lifecycle of a
cached query and are often a point of confusion.

- `staleTime`**:** This option determines the duration, in milliseconds, for
  which fetched data is considered "fresh." By default, `staleTime` is `0`,
  meaning data is considered stale immediately after it is fetched.[^16] When a
  query's data is fresh, Tanstack Query will serve it directly from the cache
  without making a network request. When a new component mounts that uses a
  query with stale data, Tanstack Query will return the stale data from the
  cache _and_ trigger a background refetch to get the latest version. Setting a
  longer `staleTime` (e.g., `5` minutes) is useful for data that does not
  change frequently, as it will prevent unnecessary background refetches.
- `gcTime`**:** This option, formerly known as `cacheTime`, determines the
  duration, in milliseconds, that data for an **inactive** query is kept in the
  cache before being garbage collected.[^16] A query becomes inactive when
  there are no longer any mounted components subscribing to it (i.e., no active

`useQuery` hooks for that query key). The default `gcTime` is 5 minutes
(300,000 ms). This means that if a user navigates away from a page, the data
for that page will be kept in the cache for 5 minutes. If they navigate back
within that window, the data will be instantly available. After 5 minutes of
inactivity, the data is deleted from the cache. As Section 6 shows,
this setting has critical implications for building a local-first application,
as the default value is insufficient for offline persistence.

### The Power of Query Keys: The Cache's Primary Identifier

The entire mechanism of Tanstack Query is built upon **query keys**. A query
key is an array that uniquely identifies a piece of data in the cache.[^16]
Tanstack Query uses a deterministic hash of this array to manage caching,
refetching, and invalidation.

The structure of these keys is crucial for building a scalable and maintainable
application. A best practice is to use a hierarchical structure that allows for
both specific and broad targeting of cache operations.

- **List Query:** `['todos', 'list']`
- **Filtered List Query:** `['todos', 'list', { status: 'completed', page: 2 }]`
- **Detail Query:** `['todos', 'detail', 123]`

This structure allows for powerful and targeted cache invalidations. For
example, calling `queryClient.invalidateQueries({ queryKey: ['todos'] })` will
invalidate all queries whose keys start with `'todos'`, including all list and
detail queries. This is essential for keeping the UI consistent after a
mutation.[^20]

### Implementing Queries and Mutations

The primary interface for interacting with Tanstack Query is through its hooks,
`useQuery` and `useMutation`.

- `useQuery`**:** This hook is used for fetching and subscribing to data. It
  takes an object with a `queryKey` and a `queryFn` (an async function that
  returns the data) as its primary arguments. It returns an object containing
  the query's state, including derived flags like `isPending`, `isError`, and
  the `data` itself.[^3]

```javascript
// src/hooks/useTodos.js
import { useQuery } from '@tanstack/react-query';
import { fetchTodos } from '../api/todosApi';

export function useTodos(filters) {
  return useQuery({
    queryKey: ['todos', 'list', filters], // The query key includes the filters
    queryFn: () => fetchTodos(filters),   // The query function passes the filters to the API
  });
}

// In a component:
// const { data: todos, isPending, isError } = useTodos({ status: 'active' });

```

- `useMutation`**:** This hook is used for creating, updating, or deleting
  data. It takes a `mutationFn` as its argument. The returned `mutate` function
  is called to trigger the mutation. A common and powerful pattern is to use the
  `onSuccess` callback to invalidate related queries, which prompts Tanstack
  Query to automatically refetch the data and keep the UI in sync.[^15]

```javascript
// src/hooks/useAddTodo.js
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createTodo } from '../api/todosApi';

export function useAddTodo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createTodo, // e.g., (newTodo) => axios.post('/todos', newTodo)
    onSuccess: () => {
      // Invalidate all queries that start with ['todos']
      // This will cause the todo list to refetch with the new item.
      queryClient.invalidateQueries({ queryKey: ['todos'] });
    },
  });
}

// In a component:
// const { mutate: addTodo } = useAddTodo();
// const handleAdd = () => addTodo({ title: 'New Todo' });

```

The relationship between `staleTime` and `gcTime` is the central mechanism that
governs Tanstack Query's behaviour. In a standard online application, these
defaults provide a sensible balance of responsiveness and network efficiency.
However, the decision to build a local-first application with offline
persistence fundamentally alters the operational context. Data for an offline
application is often "inactive" from Tanstack Query's perspective, yet it must
not be garbage collected. This reveals a critical, non-obvious dependency: the
architectural goal of offline persistence _requires_ a deliberate override of
the default `gcTime` setting. Failure to recognize this will result in a broken
offline experience, as the persisted data will be silently deleted from the
cache.

## The Core Integration Strategy: A Symbiotic Architecture

### The Guiding Principle: Single Source of Truth

The foundational principle for integrating Zustand and Tanstack Query is the
strict enforcement of a **single source of truth** for every piece of data in
the application. This means:

- **Server state lives exclusively in Tanstack Query's cache.** This includes
  all data fetched from APIs, its loading and error states, and its caching
  metadata.
- **Client state lives exclusively in a Zustand store.** This includes UI
  state, form inputs, and other ephemeral data owned by the client.

Under no circumstances should server state be duplicated by storing it in a
Zustand store.[^7] Adhering to this principle prevents a wide range of bugs
related to data synchronization, stale UIs, and conflicting states.

### A Layered Architectural Pattern

To enforce this separation of concerns and create a scalable, maintainable
codebase, a layered architecture is highly recommended. This pattern, inspired
by clean architecture principles, decouples the various parts of the
application, making them easier to reason about, test, and modify.[^8]

1. **API Layer:** This layer contains simple, reusable functions responsible
   for the raw communication with the backend. These functions typically use
   `fetch` or a library like `axios` to make HTTP requests and return promises
   that resolve with the response data. This layer knows nothing about state
   management.
2. **Server State Layer (Queries/Mutations):** This layer consists of custom
   React hooks that wrap `useQuery` and `useMutation`. These hooks use the
   functions from the API Layer as their `queryFn` or `mutationFn`. This is the
   exclusive home of Tanstack Query within the application. All query keys and
   caching configurations are defined here.
3. **Client State Layer (Stores):** This layer contains the Zustand stores that
   manage all client-specific state. Each store should be focused on a specific
   domain of the UI (e.g., `useUIStore`, `useFormStore`).
4. **Controller Layer (Hooks):** This is an optional but powerful abstraction
   layer. It contains custom hooks that compose logic from both the Server
   State Layer and the Client State Layer. For example, a controller hook might
   retrieve a filter value from a Zustand store and pass it to a server state
   hook. This layer acts as a mediator, keeping the presentation layer clean
   and free of complex business logic.
5. **Presentation Layer (Views):** This layer consists of the React components
   that make up the UI. These components should be as "dumb" as possible. Their
   primary responsibility is to render data and delegate user interactions to
   functions provided by the Controller or State layers. They should not
   contain any direct API calls or complex state manipulation logic.

### Data Flow Pattern: Client State Driving Server State

The most elegant and robust pattern for making these two libraries work
together is a reactive, unidirectional data flow where **client state drives
server state**. A common and illustrative example is implementing a search or
filtering feature.

In this pattern, the user's interaction (e.g., typing in a search box) updates
a simple, synchronous value in a Zustand store. A `useQuery` hook in the server
state layer subscribes to this value from the Zustand store and, crucially,
includes it in its `queryKey`.

Because the `queryKey` is reactive, any change to the search term in the
Zustand store will cause the `queryKey` to change. Tanstack Query detects this
change and automatically triggers a refetch of the data with the new search
term. This creates a seamless, declarative data flow that leverages the
strengths of both libraries without any manual synchronization or effect
hooks.[^7]

```javascript
// 1. Client State Layer (Zustand)
// src/stores/filterStore.js
import { create } from 'zustand';

export const useFilterStore = create((set) => ({
  searchTerm: '',
  setSearchTerm: (term) => set({ searchTerm: term }),
}));

// 2. Server State Layer (Tanstack Query)
// src/hooks/useProducts.js
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchProducts } from '../api/productsApi';
import { useFilterStore } from '../stores/filterStore';

export function useProducts() {
  // Read the search term directly from the Zustand store
  const searchTerm = useFilterStore((state) => state.searchTerm);

  return useQuery({
    // The search term is part of the query key.
    // When it changes, Tanstack Query will automatically refetch.
    queryKey: ['products', 'list', { search: searchTerm }],
    queryFn: () => fetchProducts({ search: searchTerm }),
    // placeholderData prevents UI flashes while new data loads
    placeholderData: keepPreviousData,
  });
}

// 5. Presentation Layer (View)
// src/components/ProductSearch.jsx
import React from 'react';
import { useFilterStore } from '../stores/filterStore';
import { useProducts } from '../hooks/useProducts';

function ProductSearch() {
  const searchTerm = useFilterStore((state) => state.searchTerm);
  const setSearchTerm = useFilterStore((state) => state.setSearchTerm);
  const { data: products, isPending } = useProducts();

  return (
    <div>
      <input
        type="text"
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        placeholder="Search products..."
      />
      {isPending && <p>Loading...</p>}
      <ul>
        {products?.map(product => <li key={product.id}>{product.name}</li>)}
      </ul>
    </div>
  );
}

```

### The Anti-Pattern: Storing Server State in Zustand

A common but flawed approach is to use Tanstack Query solely as a data-fetching
mechanism and then manually push the fetched data into a Zustand store. This is
typically done using a `useEffect` hook that watches the `data` returned from
`useQuery` or via the now-deprecated `onSuccess` callback.[^8]

```javascript
// ANTI-PATTERN: DO NOT DO THIS
import { useEffect } from 'react';

const useProductStore = create((set) => ({
  products: [],
  setProducts: (data) => set({ products: data }),
}));

function ProductComponent() {
  const setProducts = useProductStore((state) => state.setProducts);
  const { data } = useQuery({ queryKey: ['products'], queryFn: fetchProducts });

  // This creates a second source of truth and breaks Tanstack Query's features.
  useEffect(() => {
    if (data) {
      setProducts(data);
    }
  }, [data, setProducts]);

  //... render products from the Zustand store
}

```

This pattern should be avoided for several critical reasons[^7]:

- **It creates two sources of truth:** The data now exists in both Tanstack
  Query's cache and the Zustand store, which will inevitably lead to
  synchronization bugs.
- **It breaks Tanstack Query's lifecycle:** By moving the data out of Tanstack
  Query's control, the application loses all of its powerful features, such as
  automatic background refetches on window focus or reconnect, which will not
  be reflected in the Zustand store.
- **It leads to stale data:** The Zustand store will not be aware of updates
  happening in the Tanstack Query cache, resulting in the UI displaying
  out-of-date information.

The correct pattern is declarative and reactive: let components read server
state directly from Tanstack Query's hooks. The data flow where client state
updates drive reactive query keys is far more robust and maintainable than an
imperative approach that manually synchronizes two separate state containers.

## Implementing Offline Persistence for True Local-First Capability

A core ideal of local-first software is that the network is optional. To
achieve this, the application's state must be persisted locally on the user's
device. For this architecture, this means persisting the in-memory cache managed
by Tanstack Query to a durable storage layer. This transforms the cache from a
transient, session-based optimization into a robust, local database that
enables full offline functionality.

### Enabling Offline Mode with ,`persistQueryClient`

The Tanstack ecosystem provides a dedicated utility for this purpose: the
`@tanstack/react-query-persist-client` package. Its primary export, the
`persistQueryClient` function, orchestrates the process of saving the
`QueryClient`'s state to a chosen storage mechanism and rehydrating it when the
application loads.[^25] This utility works in conjunction with a "persister"
object, which provides the specific logic for reading from and writing to the
storage layer.

### Choosing the Right Storage: Why IndexedDB is Superior

While `localStorage` is a common choice for simple web storage, it has
significant limitations that make it unsuitable for a serious local-first
application. It has a small storage limit (typically around 5 MB), operates
synchronously (which can block the main thread), and can only store strings,
requiring manual serialization and deserialization of complex JavaScript
objects.[^27]

**IndexedDB** is a far superior choice for this task. It is a low-level,
asynchronous API for client-side storage of large amounts of structured data.
Its key advantages include[^25]:

- **Large Storage Capacity:** IndexedDB allows for significantly more storage
  than `localStorage`, often hundreds of megabytes or more, depending on the
  browser and user permissions.
- **Asynchronous API:** Its non-blocking nature ensures that storage operations
  do not freeze the user interface.
- **Rich Data Support:** It can store complex JavaScript objects, including
  `File`, `Blob`, and `Date` objects, without the need for manual JSON
  serialization.

While the native IndexedDB API can be verbose, a lightweight wrapper library
like `idb-keyval` simplifies it to a `get`/`set`/`del` promise-based API,
making it easy to create a custom persister for Tanstack Query.

```javascript
// src/lib/idbPersister.js
import { get, set, del } from 'idb-keyval';

export function createIDBPersister(idbValidKey = 'reactQuery') {
  return {
    persistClient: async (client) => {
      await set(idbValidKey, client);
    },
    restoreClient: async () => {
      return await get(idbValidKey);
    },
    removeClient: async () => {
      await del(idbValidKey);
    },
  };
}

```

### Configuration Deep Dive: Preventing Race Conditions and Data Loss

Simply adding a persister is not enough. To ensure a robust offline
implementation, two critical configuration changes are required. Neglecting
these will lead to a broken or unreliable offline experience.

1. **Setting **`gcTime`** to Prevent Premature Data Loss:** As discussed in
   Section 4, `gcTime` controls when inactive data is removed from the cache.
   The default is 5 minutes. In an offline context, a query can easily become
   "inactive" for longer than this period. If `gcTime` is not increased,
   Tanstack Query's garbage collector will remove the data from the in-memory
   cache, and because the persister maintains a 1:1 mirror of the cache, it
   will also be removed from IndexedDB.[^28] To prevent this,

`gcTime` must be set to a much higher value, such as 24 hours or even
`Infinity`, to ensure that offline data is preserved indefinitely.[^25]

1. **Using **`PersistQueryClientProvider`** to Prevent Race Conditions:**
   Restoring the cache from an asynchronous storage like IndexedDB takes a
   small amount of time. During this hydration process, components may mount
   and trigger `useQuery` hooks, initiating new network requests before the
   persisted offline data has been loaded into the cache. This creates a race
   condition. The `PersistQueryClientProvider` component from the persistence
   library solves this problem. It should be used in place of the standard
   `QueryClientProvider`. It intelligently pauses all queries, holding them in
   an `idle` state until the asynchronous restoration from storage is complete,
   thereby ensuring that the application always starts with its persisted
   state.[^25]

```javascript
// src/App.jsx
import { QueryClient } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { createIDBPersister } from './lib/idbPersister';

// 1. Create a QueryClient with a long gcTime
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      gcTime: Infinity, // preserve offline data indefinitely
    },
  },
});

// 2. Create the IndexedDB persister
const persister = createIDBPersister();

// 3. Register a default mutationFn so paused mutations can be resumed
//    after a page reload, when the in-memory function reference is lost
queryClient.setMutationDefaults(['todos', 'mutate'], {
  mutationFn: ({ id, data }) => api.updateTodo(id, data),
});

function App() {
  return (
    // 4. Use PersistQueryClientProvider
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{ persister, maxAge: Infinity }}
      onSuccess={() => queryClient.resumePausedMutations()}
    >
      {/* The rest of the application */}
    </PersistQueryClientProvider>
  );
}

```

### Handling Offline Mutations

Tanstack Query has a built-in `onlineManager` that tracks the network status of
the application. By default, it operates in an "online" mode. If the
application goes offline, any attempt to execute a mutation will be paused. The
mutation will be held in a pending state and will automatically be fired as
soon as network connectivity is restored.[^29] This works seamlessly with the
persistence layer for mutations that resume within the same page session. A
user can perform multiple actions while offline; these actions are queued up
as paused mutations, and the UI can be updated optimistically (as described in
the next section). When the user comes back online, Tanstack Query will
automatically execute the queued mutations, synchronizing the local changes
with the server.[^26] If the page is reloaded while mutations are still
paused, resumption is not automatic: the mutation must have a default
`mutationFn` registered via `setMutationDefaults`, and
`queryClient.resumePausedMutations()` must be called explicitly, typically
from the persister's `onSuccess` callback.

______________________________________________________________________

## Handling Large Offline Assets: Offline Bundles, Tiles, and "Stuff That Isn't JSON"

The patterns above work extremely well for "JSON-ish" domain data: records,
user notes, progress, favourites, and so on. However, media-heavy PWAs usually
have a second problem domain: **large, binary-ish assets** (map tiles, images,
sprites, fonts, large geometry blobs, audio, etc.). They arrive in many small
requests, they add up to hundreds of megabytes, and they do not fit neatly into
"React state".

A pragmatic approach is to keep the same mental model—**Zustand for UI state,
TanStack Query for server state**—and add one extra concept: an **offline
bundle** that describes what has been downloaded, while a dedicated storage
layer holds the bytes. This is a "tile/asset store alongside Query" approach.

### Modelling an Offline Bundle as First-Class Data

Treat the _bundle manifest_ as a normal domain entity that TanStack Query owns
and persists:

```ts
export type OfflineBundle = {
  id: string; // e.g. a region id, such as "downtown_walk_2025_11"
  regionId: string;

  // Coverage
  bounds: [minLng: number, minLat: number, maxLng: number, maxLat: number];
  zoomRange: [minZoom: number, maxZoom: number];

  // Asset addressing
  tileKeyPrefix: string; // e.g. "offline/downtown-walk"
  sizeBytes: number;

  // Lifecycle
  createdAt: string; // ISO-8601
  updatedAt?: string;
};
```

A simple Query key scheme usually does the job:

- `['offline-bundles', userId]` → list bundles
- `['offline-bundles', userId, bundleId]` → bundle detail
- mutations: `createOfflineBundle(...)`, `deleteOfflineBundle(...)`

Now the UI can answer "is this region available offline?" without needing to
understand storage internals.

### Where the Tile Bytes Live: Two Sane Options

#### Option A (default): Service Worker + Cache Storage API

Use Cache Storage as a content-addressable HTTP cache, with a service worker
(SW) as the traffic cop:

- The app computes the list of tile URLs it wants to prefetch (bounds + zoom
  range).
- The app sends the SW a message: "prefetch these URLs, associate them with
  bundle X".
- The SW fetches and stores responses in Cache Storage.
- The map library requests tiles by URL as usual; the SW serves cached
  responses while offline.

This keeps MapLibre/Leaflet blissfully unaware that “offline mode” exists.

A minimal SW sketch:

```ts
// sw.ts (illustrative)
self.addEventListener('message', (event: MessageEvent) => {
  const msg = event.data;
  if (msg?.type !== 'PRECACHE_TILES') return;

  const { cacheName, urls } = msg as { cacheName: string; urls: string[] };

  event.waitUntil((async () => {
    const cache = await caches.open(cacheName);
    await Promise.all(urls.map(async (url) => {
      const req = new Request(url, { cache: 'reload' });
      const res = await fetch(req);
      if (res.ok) await cache.put(req, res);
    }));
  })());
});

self.addEventListener('fetch', (event: FetchEvent) => {
  const url = new URL(event.request.url);

  // Keep this predicate tight: it must not hijack the entire site.
  const isTile = url.pathname.includes('/tiles/');
  if (!isTile) return;

  event.respondWith((async () => {
    const cache = await caches.open('tiles-v1');
    const cached = await cache.match(event.request);
    if (cached) return cached;

    try {
      const fresh = await fetch(event.request);
      if (fresh.ok) await cache.put(event.request, fresh.clone());
      return fresh;
    } catch {
      // Offline and not cached: choose an appropriate failure mode (empty tile, 404, etc.)
      return new Response('', { status: 503 });
    }
  })());
});
```

To purge bundle X, either:

- delete a whole cache by name, or
- track per-URL membership in IndexedDB (metadata only) and selectively delete
  entries.

#### Option B (control-first): IndexedDB / Dexie for Tiles

IndexedDB is useful when explicit control over eviction, accounting, or
non-HTTP sources is needed. Dexie makes this approach ergonomic, providing a
"small SQLite" mental model over IndexedDB.

Tile blobs are stored keyed by `{bundleId, z, x, y}` (or a compound key), and
the map library is taught to read from that store before falling back to the
network.

An illustrative Dexie schema:

```ts
import Dexie, { type Table } from 'dexie';

type TileRow = {
  bundleId: string;
  z: number;
  x: number;
  y: number;
  mime: string;
  blob: Blob;
  etag?: string;
  updatedAt: number;
};

class AppDB extends Dexie {
  tiles!: Table<TileRow, [string, number, number, number]>;

  constructor() {
    super('app');
    this.version(1).stores({
      tiles: '[bundleId+z+x+y],bundleId,z,x,y,updatedAt',
    });
  }
}
```

MapLibre in particular supports custom protocols; `app://bundle/z/x/y` can be
wired to an IndexedDB lookup that returns an `ArrayBuffer`. This route
provides deterministic storage and predictable purging, at the cost of
more bespoke integration code.

### Computing Tile URLs from Bounds

Bundle creation usually boils down to "given a bounding box, enumerate tile
coordinates for zoom levels Zmin..Zmax".

For slippy-map/WebMercator tiles:

```ts
const lon2tileX = (lon: number, z: number) =>
  Math.floor(((lon + 180) / 360) * (2 ** z));

const lat2tileY = (lat: number, z: number) => {
  const rad = (lat * Math.PI) / 180;
  const n = Math.log(Math.tan(Math.PI / 4 + rad / 2));
  return Math.floor((1 - n / Math.PI) / 2 * (2 ** z));
};

export function enumerateTiles(
  bounds: [number, number, number, number],
  zMin: number,
  zMax: number
) {
  if (!Number.isInteger(zMin) || !Number.isInteger(zMax)) {
    throw new RangeError('zMin and zMax must be integers');
  }
  if (zMin < 0 || zMax < zMin) {
    throw new RangeError('zMin must be >= 0 and zMax must be >= zMin');
  }

  const [minLng, minLat, maxLng, maxLat] = bounds;

  const tiles: Array<{ z: number; x: number; y: number }> = [];
  for (let z = zMin; z <= zMax; z++) {
    const xMin = lon2tileX(minLng, z);
    const xMax = lon2tileX(maxLng, z);
    const yMin = lat2tileY(maxLat, z); // note: lat decreases as y increases
    const yMax = lat2tileY(minLat, z);

    for (let x = xMin; x <= xMax; x++) {
      for (let y = yMin; y <= yMax; y++) {
        tiles.push({ z, x, y });
      }
    }
  }
  return tiles;
}
```

In practice, it is also necessary to:

- cap bundle size (hard limits, user-configured limits, "Wi-Fi only" toggles),
- download with bounded concurrency and cancellation,
- show progress based on tiles completed / bytes completed,
- handle quota errors and "persistent storage" requests
  (`navigator.storage.persist()`), and
- version bundles so old caches can be invalidated cleanly when the basemap
  style changes.

______________________________________________________________________

## Durable Offline Writes: An Outbox (Because Reality Dislikes Perfect Networks)

TanStack Query's paused-offline-mutation behaviour covers a surprising amount
of ground. However, an explicit **durable outbox** is often still wanted when:

- pending writes need to survive refreshes and restarts,
- richer retry/backoff logic than "try again when online" is wanted,
- multiple client actions need to be grouped into a single server transaction,
  or
- an audit trail of "what was attempted?" is wanted.

This is the "Query as the authoritative local view, outbox as sync
bookkeeping" approach.

### Outbox Data Model

```ts
export type OutboxItem = {
  id: string; // client-generated UUID; also works as an idempotency key
  type: 'CREATE_ITEM' | 'UPDATE_ITEM' | 'DELETE_ITEM' | 'RATE_ITEM';
  entityId: string;

  payload: unknown;

  createdAt: string; // ISO-8601
  lastAttemptAt?: string;
  attemptCount: number;

  status: 'pending' | 'in-flight' | 'failed' | 'done';
  error?: string;
};
```

### Write Path: Optimistic UI + Append to Outbox

When the user performs an action while offline (or on a flaky link):

1. Apply the optimistic update to the relevant Query cache (`setQueryData` in
   `onMutate`).
2. Append an `OutboxItem` to IndexedDB (Dexie works nicely here).
3. Return control to the user immediately.

The UI reads from Query, so it stays responsive even though the server has not
seen the change yet.

### Sync Path: Drain the Outbox When Online

A straightforward sync loop:

- Watch connectivity (`onlineManager` or `navigator.onLine`).
- On reconnect, read `pending` items in order.
- For each item:
  - mark `in-flight`,
  - POST/PUT to the server with an **Idempotency-Key** header derived from
    `id`,
  - on success: mark `done`, invalidate/refresh relevant queries,
  - on failure: increment attempt count, mark `failed` or requeue with backoff.

Because the outbox uses durable storage, this loop can run from:

- the app runtime,
- a service worker (Background Sync when supported), or
- a dedicated "sync worker" in a Web Worker.

The important invariant stays the same: **Query drives the UI; the outbox
drives the synchronizer**.

## Real-Time Data Flow: Integrating REST and WebSockets

### Understanding the Communication Protocols

A robust local-first application often needs to support different modes of
communication with its backend services. The two most prevalent protocols for
this are REST and WebSockets. They are not mutually exclusive; rather, they are
complementary tools that are suited for different tasks. Understanding their
distinct characteristics is essential for designing an efficient and responsive
data synchronization layer.

- **REST (Representational State Transfer):** Built on top of HTTP, REST is a
  stateless, request-response protocol. Each interaction is a discrete
  request-response exchange, although the underlying connection may remain
  open and be reused for later requests (as with HTTP keep-alive). This model
  is simple, scalable, and well-supported by web infrastructure. It is ideal
  for standard CRUD (Create, Read, Update, Delete) operations, such as
  fetching the initial state of a resource or submitting a form.[^31]
- **WebSockets:** The WebSocket protocol provides a stateful, persistent, and
  bidirectional (full-duplex) communication channel over a single TCP
  connection. Once the initial handshake is complete, the connection remains
  open, allowing both the client and the server to send messages to each other
  at any time with very low latency. This makes WebSockets the ideal choice for
  features that require real-time updates, such as chat applications, live
  notifications, and collaborative editing environments.[^31]

| Characteristic          | REST (HTTP)                                                                  | WebSocket                                                                                         |
| ----------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **Communication Model** | Request-Response (client initiates)                                          | Full-Duplex (bidirectional messages)                                                              |
| **Connection**          | Stateless, short-lived (a new connection per request)                        | Stateful, persistent (a single connection is kept open)                                           |
| **Statefulness**        | Stateless; each request is self-contained.                                   | Stateful; the server and client are aware of the connection state.                                |
| **Latency/Overhead**    | Higher overhead per request due to connection setup and HTTP headers.        | Very low latency and minimal overhead after the initial handshake.                                |
| **Directionality**      | Unidirectional (client requests, server responds).                           | Bidirectional (client and server can send data independently).                                    |
| **Scalability**         | Highly scalable due to its stateless nature.                                 | More complex to scale due to persistent connections.                                              |
| **Ideal Use Cases**     | Initial data loads, CRUD operations, transactions (e.g., submitting a form). | Real-time chat, live notifications, collaborative editing, financial data streams, online gaming. |

### Part A: The Request-Response Model with REST and Optimistic Updates

Even when using a stateless protocol like REST, it is possible to create a user
experience that feels instantaneous and aligns with the "no spinners" ideal of
local-first design. The key technique for achieving this is **optimistic
updates**.[^36]

An optimistic update involves updating the client-side UI immediately, _before_
the server has confirmed that the operation was successful. The application
"optimistically" assumes the mutation will succeed. If it does, the UI is
already in the correct state. If it fails, the application must roll back the
change and inform the user. Tanstack Query provides a powerful and robust API
for implementing this pattern within the `useMutation` hook.

The process involves using the `onMutate` lifecycle callback, which runs before
the `mutationFn` is executed:

1. `onMutate`**:** Inside this `async` function, the first step is to cancel
   any ongoing refetches for the data being mutated using
   `queryClient.cancelQueries`. This prevents a background refetch from
   overwriting the optimistic update.
2. **Snapshot Previous State:** The current state of the data is read from the
   cache using `queryClient.getQueryData`. This snapshot is crucial for rolling
   back the change if the mutation fails.
3. **Optimistically Update Cache:** The cache is then immediately updated with
   the new, optimistic data using `queryClient.setQueryData`.
4. **Return Context:** The `onMutate` function returns a context object
   containing the snapshotted previous state.
5. `onError`**:** If the `mutationFn` throws an error, the `onError` callback
   is triggered. It receives the context object from `onMutate` and uses it to
   restore the cache to its original state with `queryClient.setQueryData`,
   thus rolling back the optimistic update.
6. `onSettled`**:** This callback runs after the mutation is complete,
   regardless of whether it succeeded or failed. It is used to invalidate the
   relevant query (`queryClient.invalidateQueries`), ensuring that the client's
   cache is eventually synchronized with the true, authoritative state from the
   server.

```javascript
// src/hooks/useUpdateTodo.js
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { updateTodo } from '../api/todosApi';

export function useUpdateTodo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateTodo, // (updatedTodo) => axios.put(`/todos/${updatedTodo.id}`, updatedTodo)
    
    onMutate: async (updatedTodo) => {
      const queryKey = ['todos', 'list'];
      
      // 1. Cancel ongoing refetches
      await queryClient.cancelQueries({ queryKey });

      // 2. Snapshot the previous value
      const previousTodos = queryClient.getQueryData(queryKey);

      // 3. Optimistically update to the new value
      queryClient.setQueryData(queryKey, (old) => {
        if (!Array.isArray(old)) {
          return old;
        }

        return old.map(todo => (todo.id === updatedTodo.id ? updatedTodo : todo));
      });

      // 4. Return a context object with the snapshotted value
      return { previousTodos };
    },

    // 5. If the mutation fails, roll back
    onError: (err, updatedTodo, context) => {
      queryClient.setQueryData(['todos', 'list'], context.previousTodos);
    },

    // 6. Always refetch after error or success
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['todos', 'list'] });
    },
  });
}

```

### Part B: The Persistent Connection Model with WebSockets

For features that require true real-time updates pushed from the server,
WebSockets are the superior choice. Integrating WebSocket messages into the
Tanstack Query cache can be achieved by establishing a single, application-wide
WebSocket connection (typically within a top-level component's `useEffect`
hook) and then using the `queryClient` to update the cache when messages are
received.[^37]

There are two primary strategies for how the server should communicate updates
and how the client should apply them to the cache. The choice between them
involves a trade-off between network bandwidth, client-side complexity, and
update latency.

| Strategy              | Query Invalidation (`invalidateQueries`)                                                                                                                                   | Direct Cache Update (`setQueryData`)                                                                                                                                  |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Mechanism**         | The client receives a small notification, marks the relevant data as stale, and triggers a background refetch via HTTP to get the latest data.                             | The client receives the new data directly in the WebSocket message and manually writes it into the Tanstack Query cache.                                              |
| **WebSocket Payload** | A small, lightweight event object, e.g., `{ "event": "todo_updated", "id": 123 }`.                                                                                         | The full or partial data object, e.g., `{ "id": 123, "title": "New Title", "completed": true }`.                                                                      |
| **Network Usage**     | Two network calls: one lightweight WebSocket message from the server, followed by one standard HTTP request from the client to refetch the data.                           | One network call: a single WebSocket message from the server, which may have a larger payload containing the actual data.                                             |
| **Pros**              | - Simple to implement on the client. - Leverages Tanstack Query's existing `queryFn` and refetching logic. - Ensures the client always has the authoritative server state. | - Lowest possible latency (no second round-trip). - Reduces load on HTTP API endpoints. - Highly efficient for frequent, small updates.                               |
| **Cons**              | - Higher latency due to the second HTTP round-trip. - Can lead to more HTTP requests if updates are very frequent.                                                         | - More complex client-side logic to manually update the cache. - Bypasses the `queryFn`, potentially leading to inconsistencies if transformation logic exists there. |
| **Ideal Use Case**    | Infrequent but important updates where eventual consistency is acceptable (e.g., a project's status changing, a new comment being added).                                  | High-frequency, low-latency updates where immediate reflection is critical (e.g., real-time chat messages, live stock tickers, collaborative cursor positions).       |

### Strategy 1: Event-Driven Query Invalidation

This is often the simplest and most robust approach. The server sends a small
message indicating what has changed, not the new data itself. The client
receives this event and uses `queryClient.invalidateQueries` to tell Tanstack
Query that the relevant data is now stale. If there is an active `useQuery`
hook for that data, a background refetch will be triggered automatically.

```javascript
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

function TodoSocketBridge() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const socket = new WebSocket('wss://your-server.com');

    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);

      if (message.event === 'todo_updated') {
        // Invalidate the specific todo detail query and all todo lists
        queryClient.invalidateQueries({ queryKey: ['todos', 'detail', message.id] });
        queryClient.invalidateQueries({ queryKey: ['todos', 'list'] });
      }
    };

    return () => socket.close();
  }, [queryClient]);

  return null;
}

```

### Strategy 2: Direct Cache Updates

For applications requiring the lowest possible latency, such as a chat app, the
server can push the entire data object over the WebSocket. The client then
directly injects this data into the cache using `queryClient.setQueryData`.
This avoids the second HTTP request, making the UI update feel instantaneous.

```javascript
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

function TodoSocketBridge() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const socket = new WebSocket('wss://your-server.com');

    socket.onmessage = (event) => {
      const newTodo = JSON.parse(event.data);

      // Directly update the cache for the specific todo
      queryClient.setQueryData(['todos', 'detail', newTodo.id], newTodo);

      // Also update every cached list variant (e.g. filtered views) that
      // shares the 'todos', 'list' prefix, not just the unfiltered key
      queryClient.setQueriesData({ queryKey: ['todos', 'list'] }, (oldData = []) => {
        const exists = oldData.some(todo => todo.id === newTodo.id);
        if (exists) {
          return oldData.map(todo => (todo.id === newTodo.id ? newTodo : todo));
        }

        return [...oldData, newTodo];
      });
    };

    return () => socket.close();
  }, [queryClient]);

  return null;
}

```

## Orchestrating Complex Client-Side Logic with XState

While Zustand excels at managing simple, discrete pieces of client state, some
application features involve complex, multi-step processes, intricate user
flows, or behaviours with a finite number of well-defined states. For these
scenarios, a more robust solution is needed to prevent bugs and manage
complexity. This is where XState, a library for creating and managing state
machines and statecharts, becomes an invaluable addition to this
architecture.[^44]

### Introducing XState: Beyond State Management to State Orchestration

XState is not just another state management library; it is a state
_orchestration_ solution.[^46] It uses the formal concepts of

**finite state machines (FSMs)** and **statecharts** to model application
logic.[^47] This approach provides a declarative and predictable way to handle
complex behaviour.[^47]

The core concepts include[^47]:

- **States:** A finite set of explicit conditions an application or component
  can be in (e.g., `idle`, `loading`, `success`, `error`). A machine can only
  be in one state at a time, which eliminates impossible states and reduces
  bugs.[^48]
- **Events:** Plain objects that describe something that has happened, which
  can trigger a state change (e.g., `{ type: 'FETCH' }`).
- **Transitions:** Rules that define how the machine moves from one state to
  another in response to an event.
- **Context:** Quantitative data that is stored alongside the qualitative state
  (e.g., a list of items, an error message).
- **Actors:** Long-running processes or side effects that can be invoked by the
  machine.[^47]

By modelling logic this way, XState makes complex flows visualizable, easier to
reason about, and more robust, especially for features like multi-step forms,
onboarding flows, or intricate UI interactions.[^49]

### The Division of Labour: XState vs. Zustand

At first glance, XState and Zustand seem to overlap as they both manage client
state. However, they are designed to solve different classes of problems, and
understanding their distinct roles is key to using them effectively.[^51]

- **Zustand is for storing _state values_.** It is ideal for simple,
  independent pieces of UI state that don't have complex transition logic.
  Think of it as a lightweight, global key-value store. Examples include the
  status of a modal (`isOpen`), the content of a search input, or a theme
  preference.[^52]
- **XState is for modelling _state flows_.** It excels at managing
  complex, interdependent states where the sequence of operations and the
  transitions between states are critical. It defines the _behaviour_ of a
  system, ensuring that only valid transitions can occur.[^50]

The primary impedance mismatch arises when one tool is used for the other's
job. Using Zustand to manage a complex wizard can lead to a "boolean
explosion"—a confusing web of `isLoading`, `isSuccess`, `isError`, `isStepOne`,
`isStepTwo` flags that can easily result in invalid or impossible states.[^53]
Conversely, using XState for a simple theme toggle is overly verbose and adds
unnecessary complexity.[^50]

The best practice is to use them together, not as mutually exclusive options.
Use Zustand for simple, global UI state, and introduce XState for specific,
complex components or features that benefit from the rigour of a state machine.

### Best Practices for Seamless Integration with Tanstack Query

Integrating XState into this architecture with Tanstack Query follows the same
core principle: **Tanstack Query owns the server state**.[^54] The state
machine should not duplicate this state but rather react to it.

The most effective pattern is to have the XState machine manage the UI and
interaction flow, while treating the status of a Tanstack Query hook as a
source of events.

1. **Let Tanstack Query Handle Fetching:** The `useQuery` hook remains the
   single source of truth for the data itself, as well as its asynchronous
   lifecycle (`isPending`, `isSuccess`, `isError`).
2. **Feed Query State into the Machine:** Use a `useEffect` hook to observe the
   state of `useQuery` and send corresponding events to the XState machine.
3. **Machine Manages UI State:** The machine transitions based on these events,
   controlling what the user sees (e.g., a loading spinner, the data, or an
   error message with a retry button).

```javascript
// Example of a component using XState with Tanstack Query
import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useMachine } from '@xstate/react';
import { createMachine, assign } from 'xstate';

// 1. Define the state machine for the UI flow
const fetchMachine = createMachine({
  id: 'fetcher',
  initial: 'idle',
  context: {
    data: null,
    error: null,
  },
  states: {
    idle: {
      on: { FETCH: 'loading' },
    },
    loading: {
      on: {
        FETCH_SUCCESS: {
          target: 'success',
          actions: assign({ data: ({ event }) => event.data }),
        },
        FETCH_ERROR: {
          target: 'failure',
          actions: assign({ error: ({ event }) => event.error }),
        },
      },
    },
    success: {
      on: { FETCH: 'loading' }, // Allow refetching
    },
    failure: {
      on: { RETRY: 'loading' },
    },
  },
});

function MyComponent() {
  const [state, send] = useMachine(fetchMachine);

  // 2. Tanstack Query owns the server state
  const { isPending, isError, data, error, refetch } = useQuery({
    queryKey: ['my-data'],
    queryFn: fetchData,
    enabled: state.matches('loading'), // Only fetch when the machine is in the loading state
  });

  // 3. Feed query state changes into the machine as events
  useEffect(() => {
    if (isPending) return; // The machine is already in 'loading'

    if (isError) {
      send({ type: 'FETCH_ERROR', error });
    } else {
      send({ type: 'FETCH_SUCCESS', data });
    }
  }, [isPending, isError, data, error, send]);

  // 4. The machine's state drives the UI
  return (
    <div>
      {state.matches('idle') && (
        <button onClick={() => send({ type: 'FETCH' })}>Fetch Data</button>
      )}
      {state.matches('loading') && <p>Loading...</p>}
      {state.matches('failure') && (
        <div>
          <p>Error: {state.context.error.message}</p>
          <button onClick={() => send({ type: 'RETRY' })}>Retry</button>
        </div>
      )}
      {state.matches('success') && (
        <div>
          <h2>Data Loaded:</h2>
          <pre>{JSON.stringify(state.context.data, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

```

This pattern creates a clear separation of concerns. Tanstack Query is
responsible for the mechanics of data fetching and caching, while XState is
responsible for orchestrating the user-facing flow, making the component's
logic explicit and robust. For even tighter integration, the
`zustand-middleware-xstate` package allows an XState machine to be embedded
directly within a Zustand store, offering a hybrid approach.[^55]

## Advanced Considerations and Future Frontiers

### The Unsolved Problem: Data Conflict Resolution

The architecture detailed thus far provides a powerful foundation for building
offline-capable, resilient applications. However, it is crucial to recognize
that it does not, by itself, solve the most difficult challenge of local-first
development: **data conflict resolution**.[^2]

Conflicts are an inevitable consequence of eventual consistency. They occur
when the same piece of data is modified on two different clients while they are
offline. When these clients reconnect and attempt to sync their changes, the
system is faced with two or more conflicting versions of the truth. For example:

- User A, while offline on their laptop, renames a shared document from
  "Project Plan" to "Q3 Strategy."
- User B, also offline on their tablet, renames the _same_ document from
  "Project Plan" to "Marketing Brief."

When both users come back online, the synchronization server will receive two
valid but contradictory updates for the same document. The combination of
Zustand and Tanstack Query does not provide a built-in mechanism to resolve
this. Conflict resolution is fundamentally an application-level, business logic
problem that requires a deliberate strategy. Common strategies include:

- **Last-Write-Wins (LWW):** This is the simplest strategy, where the server
  simply accepts the last update it receives and discards all others. While
  easy to implement, it is often destructive, as it can lead to unintentional
  data loss.
- **Application-Specific Merging:** The application can implement custom logic
  to merge conflicting changes. For example, if two users add different items
  to the same list, the resolution could be to create a new list containing all
  items from both versions. This requires domain-specific code.
- **Conflict-Free Replicated Data Types (CRDTs):** These are advanced data
  structures mathematically designed to merge concurrent changes in a way that
  is guaranteed to converge to the same result on all clients, without
  conflicts. While powerful, implementing CRDTs can be complex.[^5]
- **User-Driven Resolution:** In many cases, the only way to correctly resolve
  a conflict is to ask the user. The application's UI can be designed to detect
  and present the conflicting versions to the user, allowing them to manually
  choose the correct version or merge the changes themselves.[^5]

The choice of strategy is highly dependent on the nature of the data and the
application's requirements. It is a critical design decision that must be
addressed when building any non-trivial local-first application.

### When to Reach for Something Heavier Than "Query + Persistence + Outbox"

The stack in this guide intentionally stays "in the family": Zustand for UI
state, TanStack Query for server state, and IndexedDB for persistence. It
scales further than people expect, especially for single-user or
mostly-single-user apps where conflicts stay rare.

However, some requirements change the game:

- **Multi-writer collaboration on the same entities**, including concurrent
  edits while offline.
- **Bidirectional sync as a product feature**, not a background convenience.
- **Strong guarantees about convergence** (every replica ends up identical)
  without user mediation.

When those show up, purpose-built local-first databases and
sync engines:

- **RxDB:** a browser/Node database on top of IndexedDB/SQLite with
  replication and conflict handling. It can integrate with Query, but in
  practice it starts to _own_ the application's server state lifecycle.
- **ElectricSQL (+ local SQLite):** a Postgres-centric approach that syncs
  into a local replica (often with CRDT-based merge semantics). It pushes
  applications towards a database-first architecture.
- **Replicache / CRDT toolkits (Automerge, Yjs):** best suited to
  collaborative editing. They can feel like overkill until the day they are not.

These tools are excellent, but they also shift the centre of gravity: the
database and sync engine become the main abstraction, and TanStack Query
becomes an accessory rather than the backbone.

### The Future is Purpose-Built: The Emergence of Tanstack DB

The complexities of manually implementing offline persistence, synchronization,
and conflict resolution have highlighted the need for more integrated,
purpose-built tools. Recognizing this gap, the Tanstack ecosystem is evolving.
The emergence of **Tanstack DB** represents the logical next step in this
evolution, providing a higher-level abstraction specifically designed for
local-first and real-time applications.[^17]

Tanstack DB builds directly on top of Tanstack Query, extending it with a set
of primitives that formalize the patterns manually constructed earlier in this
guide[^43]:

- **Collections:** A formal local store primitive that acts as the client-side
  database. Collections can be populated by Tanstack Query, a real-time sync
  engine, or local-only data, providing a unified interface for all application
  data.[^42]
- **Live Queries:** These are reactive queries that run directly against the
  local collections. When the data in a collection changes (whether from a user
  action or a background sync), any component using a live query on that
  collection will automatically and efficiently re-render. This abstracts away
  the need for manual cache invalidation or updates.[^42]
- **Transactional Mutations:** Tanstack DB introduces mutations that are
  transactional, meaning they can be applied atomically across multiple
  collections. They are also more tightly integrated with the lifecycle of a
  sync engine, providing better support for managing optimistic state and
  rollbacks.[^42]

The patterns documented in this report are powerful and effective, but they
require significant manual implementation and a deep understanding of the
underlying libraries. The development of Tanstack DB signals a broader industry
trend towards higher-level abstractions that aim to automate and formalize
these patterns. For teams embarking on complex local-first projects, Tanstack
DB represents a promising future where the intricate mechanics of data
synchronization are handled by the framework, allowing developers to focus more
on application logic and user experience.

## Conclusion: Synthesizing a Robust Local-First Architecture

### Recapitulation of Core Principles

This report has detailed a comprehensive architecture for building resilient,
high-performance, local-first applications in React. The success of this
architecture hinges on a set of core principles that guide every implementation
decision:

- **Strict Separation of State:** The most critical principle is the
  disciplined separation of client state and server state. Client state, which
  is ephemeral and UI-related, is best managed by a minimalist library like
  Zustand. Server state, which is an asynchronous and persistent cache of
  remote data, requires a specialized synchronization engine like Tanstack
  Query.
- **Specialized Tooling:** Using the right tool for the right job avoids
  anti-patterns like state duplication and the manual re-implementation of
  complex caching and synchronization logic.
- **Layered Architecture:** Organizing the codebase into distinct layers—API,
  Server State, Client State, Controller, and Presentation—enforces separation
  of concerns, enhances testability, and improves long-term maintainability.
- **Reactive Data Flow:** The optimal integration pattern involves a
  unidirectional, reactive data flow where simple, synchronous updates to
  client state (in Zustand) drive the powerful, asynchronous data
  synchronization capabilities of Tanstack Query via reactive query keys.

### The Benefits Realized

By adhering to these principles and implementing the patterns detailed—from
offline persistence with IndexedDB to real-time updates with optimistic REST
and WebSockets—this architecture directly achieves the seven ideals of
local-first software. The technical implementations translate directly into
tangible user benefits:

- **No Spinners:** Optimistic updates and local data access provide
  instantaneous UI feedback.
- **Network Optionality:** Persisting the Tanstack Query cache enables full
  application functionality without an internet connection.
- **Seamless Collaboration:** The integration of WebSockets allows for
  real-time, multi-user experiences.
- **Data Ownership and Longevity:** Storing data on the user's device empowers
  them with control and ensures long-term access.

### Final Recommendations and Path Forward

The architectural patterns presented here are not for every project. They
represent a significant investment in building a superior user experience, one
that is exceptionally fast, reliable, and respectful of the user's data and
context. This approach is highly recommended for applications where these
qualities are paramount: collaborative tools, productivity software, and any
application intended for use in environments with unreliable network
connectivity.

As the web development ecosystem continues to evolve, the principles of
local-first design are becoming increasingly relevant. The challenges of
network latency and data privacy are not going away. For development teams and
architects looking to build the next generation of web applications, mastering
these patterns is a crucial step. Furthermore, it is essential to keep an eye
on emerging, purpose-built tools like Tanstack DB. As they mature, these
higher-level abstractions promise to simplify the implementation of these
advanced concepts, making the power of local-first architecture accessible to
an even broader range of applications.

## Works cited

[^1] Local-first software: You own your data, in spite of the cloud, accessed
on August 20, 2025,
[https://www.inkandswitch.com/essay/local-first/](https://www.inkandswitch.com/essay/local-first/)

[^2] Why Local-First Software Is the Future and its Limitations | RxDB -
JavaScript Database, accessed on August 20, 2025,
[https://rxdb.info/articles/local-first-future.html](https://rxdb.info/articles/local-first-future.html)

[^3] Overview | TanStack Query React Docs, accessed on August 20, 2025,
[https://tanstack.com/query/v5/docs/react/overview](https://tanstack.com/query/v5/docs/react/overview)

[^4] Mastering Local-First Apps: The Ultimate Guide to Offline-First
Development with Seamless Cloud Sync | by M Mahdi Ramadhan, M. Si | Medium,
accessed on August 20, 2025,
[https://medium.com/@Mahdi_ramadhan/mastering-local-first-apps-the-ultimate-guide-to-offline-first-development-with-seamless-cloud-be656167f43f](https://medium.com/@Mahdi_ramadhan/mastering-local-first-apps-the-ultimate-guide-to-offline-first-development-with-seamless-cloud-be656167f43f)

[^5] Downsides of Local First / Offline First | RxDB - JavaScript Database,
accessed on August 20, 2025,
[https://rxdb.info/downsides-of-offline-first.html](https://rxdb.info/downsides-of-offline-first.html)

[^6] Does TanStack Query replace Redux, MobX or other global state managers?,
accessed on August 20, 2025,
[https://tanstack.com/query/v5/docs/react/guides/does-this-replace-client-state](https://tanstack.com/query/v5/docs/react/guides/does-this-replace-client-state)

[^7] Zustand vs tanstack query : r/reactjs - Reddit, accessed on
August 20, 2025,
[https://www.reddit.com/r/reactjs/comments/1mugweq/zustand_vs_tanstack_query/](https://www.reddit.com/r/reactjs/comments/1mugweq/zustand_vs_tanstack_query/)

[^8] How to structure Next.js project with Zustand and React Query | by …,
accessed on August 20, 2025,
[https://medium.com/@zerebkov.artjom/how-to-structure-next-js-project-with-zustand-and-react-query-c4949544b0fe](https://medium.com/@zerebkov.artjom/how-to-structure-next-js-project-with-zustand-and-react-query-c4949544b0fe)

[^9] Separating Concerns with Zustand and TanStack Query, accessed on
August 20, 2025,
[https://volodymyrrudyi.com/blog/separating-concerns-with-zustand-and-tanstack-query/](https://volodymyrrudyi.com/blog/separating-concerns-with-zustand-and-tanstack-query/)

[^10] React State Management — using Zustand | by Chikku George | Globant -
Medium, accessed on August 20, 2025,
[https://medium.com/globant/react-state-management-b0c81e0cbbf3](https://medium.com/globant/react-state-management-b0c81e0cbbf3)

[^11] Managing React state with Zustand | by Dzmitry Ihnatovich - Medium,
accessed on August 20, 2025,
[https://medium.com/@ignatovich.dm/managing-react-state-with-zustand-4e4d6bb50722](https://medium.com/@ignatovich.dm/managing-react-state-with-zustand-4e4d6bb50722)

[^12] Modernizing Your React Applications: From Redux to Zustand, TanStack
Query, and Redux Toolkit - Makepath, accessed on August 20, 2025,
[https://makepath.com/modernizing-your-react-applications-from-redux-to-zustand-tanstack-query-and-redux-toolkit/](https://makepath.com/modernizing-your-react-applications-from-redux-to-zustand-tanstack-query-and-redux-toolkit/)

[^13] Introduction - Zustand, accessed on August 20, 2025,
[https://zustand.docs.pmnd.rs/getting-started/introduction](https://zustand.docs.pmnd.rs/getting-started/introduction)

[^14] Zustand vs. RTK Query vs. TanStack Query: Unpacking the React State
Management Toolbox | by Imran Rafeek | Medium, accessed on August 20, 2025,
[https://medium.com/@imranrafeek/zustand-vs-rtk-query-vs-tanstack-query-unpacking-the-react-state-management-toolbox-d47893479742](https://medium.com/@imranrafeek/zustand-vs-rtk-query-vs-tanstack-query-unpacking-the-react-state-management-toolbox-d47893479742)

[^15] TanStack Query: A Powerful Tool for Data Management in React - Medium,
accessed on August 20, 2025,
[https://medium.com/@ignatovich.dm/tanstack-query-a-powerful-tool-for-data-management-in-react-0c5ae6ef037c](https://medium.com/@ignatovich.dm/tanstack-query-a-powerful-tool-for-data-management-in-react-0c5ae6ef037c)

[^16] Asynchronous State Management with TanStack Query - Atlantbh Sarajevo,
accessed on August 20, 2025,
[https://www.atlantbh.com/asynchronous-state-management-with-tanstack-query/](https://www.atlantbh.com/asynchronous-state-management-with-tanstack-query/)

[^17] TanStack | High Quality Open-Source Software for Web Developers, accessed
on August 20, 2025, [https://tanstack.com/](https://tanstack.com/)

[^18] useQuery | TanStack Query React Docs, accessed on August 20, 2025,
[https://tanstack.com/query/v4/docs/react/reference/useQuery](https://tanstack.com/query/v4/docs/react/reference/useQuery)

[^19] Cache storage in Tanstack query. Introduction | by Akilesh Rao -
JavaScript in Plain English, accessed on August 20, 2025,
[https://javascript.plainenglish.io/cache-storage-in-tanstack-query-bdfd89fa4705](https://javascript.plainenglish.io/cache-storage-in-tanstack-query-bdfd89fa4705)

[^20] Query Invalidation | TanStack Query React Docs, accessed on
August 20, 2025,
[https://tanstack.com/query/v5/docs/react/guides/query-invalidation](https://tanstack.com/query/v5/docs/react/guides/query-invalidation)

[^21] React Query Cache Invalidation: Why Your Mutations Work But Your UI
Doesn't Update, accessed on August 20, 2025,
[https://medium.com/@kennediowusu/react-query-cache-invalidation-why-your-mutations-work-but-your-ui-doesnt-update-a1ad23bc7ef1](https://medium.com/@kennediowusu/react-query-cache-invalidation-why-your-mutations-work-but-your-ui-doesnt-update-a1ad23bc7ef1)

[^22] Managing Query Keys for Cache Invalidation in React Query - Wisp CMS,
accessed on August 20, 2025,
[https://www.wisp.blog/blog/managing-query-keys-for-cache-invalidation-in-react-query](https://www.wisp.blog/blog/managing-query-keys-for-cache-invalidation-in-react-query)

[^23] How to use zustand to store the result of a query - Stack Overflow,
accessed on August 20, 2025,
[https://stackoverflow.com/questions/68690221/how-to-use-zustand-to-store-the-result-of-a-query](https://stackoverflow.com/questions/68690221/how-to-use-zustand-to-store-the-result-of-a-query)

[^24] Behaviour of onSuccess and idea for callbacks · TanStack query - GitHub,
accessed on August 20, 2025,
[https://github.com/TanStack/query/discussions/5034](https://github.com/TanStack/query/discussions/5034)

[^25] persistQueryClient | TanStack Query React Docs, accessed on
August 20, 2025,
[https://tanstack.com/query/v4/docs/react/plugins/persistQueryClient](https://tanstack.com/query/v4/docs/react/plugins/persistQueryClient)

[^26] Building Offline-First React Native Apps with React Query and …, accessed
on August 20, 2025,
[https://www.whitespectre.com/ideas/how-to-build-offline-first-react-native-apps-with-react-query-and-typescript/](https://www.whitespectre.com/ideas/how-to-build-offline-first-react-native-apps-with-react-query-and-typescript/)

[^27] Cache Persistence in IndexedDB · TanStack query · Discussion #1638 -
GitHub, accessed on August 20, 2025,
[https://github.com/TanStack/query/discussions/1638](https://github.com/TanStack/query/discussions/1638)

[^28] Understanding offline example · TanStack query · Discussion #4296 -
GitHub, accessed on August 20, 2025,
[https://github.com/TanStack/query/discussions/4296](https://github.com/TanStack/query/discussions/4296)

[^29] Offline caching with AWS Amplify, Tanstack, AppSync and MongoDB Atlas,
accessed on August 20, 2025,
[https://aws.amazon.com/blogs/mobile/offline-caching-with-aws-amplify-tanstack-appsync-and-mongodb-atlas/](https://aws.amazon.com/blogs/mobile/offline-caching-with-aws-amplify-tanstack-appsync-and-mongodb-atlas/)

[^30] Adding Offline Capabilities to React Native Apps with TanStack Query
Benoit Paul, accessed on August 20, 2025,
[https://www.benoitpaul.com/blog/react-native/offline-first-tanstack-query/](https://www.benoitpaul.com/blog/react-native/offline-first-tanstack-query/)

[^31] WebSocket vs REST: Key differences and which to use - Ably, accessed on
August 20, 2025,
[https://ably.com/topic/websocket-vs-rest](https://ably.com/topic/websocket-vs-rest)

[^32] Websocket vs REST when sending data to server - Stack Overflow, accessed
on August 20, 2025,
[https://stackoverflow.com/questions/45460734/websocket-vs-rest-when-sending-data-to-server](https://stackoverflow.com/questions/45460734/websocket-vs-rest-when-sending-data-to-server)

[^33] REST API vs. WebSocket API - JDoodle Blog | Latest Updates, Industry News
& more, accessed on August 20, 2025,
[https://www.jdoodle.com/blog/rest-vs-websocket](https://www.jdoodle.com/blog/rest-vs-websocket)

[^34] What is the difference between RESTful APIs and WebSockets? -
[Polygon.io](http://Polygon.io), accessed on August 20, 2025,
[https://polygon.io/knowledge-base/article/what-is-the-difference-between-restful-apis-and-websockets](https://polygon.io/knowledge-base/article/what-is-the-difference-between-restful-apis-and-websockets)

[^35] TanStack Query and WebSockets: Real-time React data fetching - LogRocket
Blog, accessed on August 20, 2025,
[https://blog.logrocket.com/tanstack-query-websockets-real-time-react-data-fetching/](https://blog.logrocket.com/tanstack-query-websockets-real-time-react-data-fetching/)

[^36] Optimistic Updates | TanStack Query React Docs, accessed on
August 20, 2025,
[https://tanstack.com/query/v5/docs/react/guides/optimistic-updates](https://tanstack.com/query/v5/docs/react/guides/optimistic-updates)

[^37] TkDodo's Blog | TanStack Query React Docs, accessed on August 20, 2025,
[https://tanstack.com/query/v4/docs/react/community/tkdodos-blog](https://tanstack.com/query/v4/docs/react/community/tkdodos-blog)

[^38] TkDodo's Blog | TanStack Query React Docs, accessed on August 20, 2025,
[https://tanstack.com/query/latest/docs/react/community/tkdodos-blog](https://tanstack.com/query/latest/docs/react/community/tkdodos-blog)

[^39] Using WebSockets with React Query | TkDodo's blog, accessed on
August 20, 2025,
[https://tkdodo.eu/blog/using-web-sockets-with-react-query](https://tkdodo.eu/blog/using-web-sockets-with-react-query)

[^40] Using Websockets with React Query - Jon Bellah, accessed on
August 20, 2025,
[https://jonbellah.com/articles/websockets-with-react-query](https://jonbellah.com/articles/websockets-with-react-query)

[^41] How do you guys build offline-first apps with React Native? - Reddit,
accessed on August 20, 2025,
[https://www.reddit.com/r/reactnative/comments/1arlfkd/how_do_you_guys_build_offlinefirst_apps_with/](https://www.reddit.com/r/reactnative/comments/1arlfkd/how_do_you_guys_build_offlinefirst_apps_with/)

[^42] TanStack/db: A reactive client store for building super fast apps on sync
GitHub, accessed on August 20, 2025,
[https://github.com/TanStack/db](https://github.com/TanStack/db)

[^43] Local-first sync with TanStack DB and Electric | ElectricSQL, accessed on
August 20, 2025,
[https://electric-sql.com/blog/2025/07/29/local-first-sync-with-tanstack-db](https://electric-sql.com/blog/2025/07/29/local-first-sync-with-tanstack-db)

[^44] XState | Stately, accessed on August 21, 2025,
[https://stately.ai/docs/xstate](https://stately.ai/docs/xstate); also
statelyai/xstate: Actor-based state management & orchestration for complex app
logic. - GitHub, accessed on August 21, 2025,
[https://github.com/statelyai/xstate](https://github.com/statelyai/xstate)

[^46] Do You use XState? Pros and cons? When use it ? : r/reactjs - Reddit,
accessed on August 21, 2025,
[https://www.reddit.com/r/reactjs/comments/16l39r5/do_you_use_xstate_pros_and_cons_when_use_it/](https://www.reddit.com/r/reactjs/comments/16l39r5/do_you_use_xstate_pros_and_cons_when_use_it/)

[^47] XState for React Developers, accessed on August 21, 2025,
[https://www.xstateforreactdevelopers.com/](https://www.xstateforreactdevelopers.com/)

[^48] Mastering State Management with XState React: Best Practices for
Developers - DhiWise, accessed on August 21, 2025,
[https://www.dhiwise.com/post/mastering-state-management-with-xstate-react-best-practices](https://www.dhiwise.com/post/mastering-state-management-with-xstate-react-best-practices)

[^49] This Library Makes State Management So Much Easier - YouTube, accessed on
August 21, 2025,
[https://www.youtube.com/watch?v=s0h34OkEVUE](https://www.youtube.com/watch?v=s0h34OkEVUE)

[^50] How do you actually use xstate? : r/reactjs - Reddit, accessed on
August 21, 2025,
[https://www.reddit.com/r/reactjs/comments/1hggghc/how_do_you_actually_use_xstate/](https://www.reddit.com/r/reactjs/comments/1hggghc/how_do_you_actually_use_xstate/)

[^51] What's the deal with XState? : r/reactjs - Reddit, accessed on
August 21, 2025,
[https://www.reddit.com/r/reactjs/comments/yjaqhi/whats_the_deal_with_xstate/](https://www.reddit.com/r/reactjs/comments/yjaqhi/whats_the_deal_with_xstate/)

[^52] pmndrs/zustand: Bear necessities for state management in React - GitHub,
accessed on August 21, 2025,
[https://github.com/pmndrs/zustand](https://github.com/pmndrs/zustand)

[^53] Effective State Management in React with XState | by Daniel Oberman |
Medium, accessed on August 21, 2025,
[https://medium.com/@danieloberman770/effective-state-management-in-react-with-xstate-775d27ee1445](https://medium.com/@danieloberman770/effective-state-management-in-react-with-xstate-775d27ee1445)

[^54] How do you use XState with React Query (or other data-fetching/caching
libs)? Should they even be used together? : r/reactjs

- Reddit, accessed on August 21, 2025,
[https://www.reddit.com/r/reactjs/comments/1m2g5n9/how_do_you_use_xstate_with_react_query_or_other/](https://www.reddit.com/r/reactjs/comments/1m2g5n9/how_do_you_use_xstate_with_react_query_or_other/)

[^55] biowaffeln/zustand-middleware-xstate - GitHub, accessed on
August 21, 2025,
[https://github.com/biowaffeln/zustand-middleware-xstate](https://github.com/biowaffeln/zustand-middleware-xstate)
