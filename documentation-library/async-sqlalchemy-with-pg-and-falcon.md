# A Comprehensive Guide to Asynchronous SQLAlchemy 2.0 with PostgreSQL and Falcon

## I. Introduction: Embracing Asynchronicity in Modern Web Services

The evolution of web frameworks and database interaction libraries has
increasingly emphasized asynchronous operations to build high-performance,
scalable applications. SQLAlchemy, a cornerstone of Python's ORM landscape,
introduced robust asynchronous capabilities in version 2.0, aligning with the
Python asyncio paradigm.[^1] This guide provides an expert-level overview of best
practices for leveraging asynchronous SQLAlchemy 2.0 with PostgreSQL,
specifically using the asyncpg driver, within the context of the Falcon web
framework. Falcon, known for its minimalist design and performance focus,
supports ASGI (Asynchronous Server Gateway Interface), making it suitable for
building asynchronous APIs.[^3] When combined with SQLAlchemy's async features,
developers can create highly concurrent services capable of handling numerous
I/O-bound database operations without blocking the main execution thread. This
document will delve into the intricacies of setting up the asynchronous engine
and session management, integrating these components effectively within Falcon
applications, mastering asynchronous ORM operations, managing transactions,
handling errors robustly, tuning performance, and implementing effective
testing strategies. The objective is to equip developers with the knowledge to
build efficient, reliable, and maintainable asynchronous applications using
this powerful technology stack. The transition from synchronous patterns, such
as those offered by encode/databases (which is no longer actively maintained),
to SQLAlchemy's native async support represents a significant step forward.[^6]

## II. Core Asynchronous SQLAlchemy Setup: Engine and Session Factory

The foundation of any SQLAlchemy application, synchronous or asynchronous, lies
in the correct configuration of its engine and session-generating components.
In an asynchronous context, these are create\_async\_engine and
async\_sessionmaker.

### A. The create_async_engine: The Foundation for Asynchronous Database Communication

The create\_async\_engine function is the entry point for establishing
asynchronous communication with the PostgreSQL database.[^7] It requires an
asynchronous database driver; for PostgreSQL, asyncpg is the recommended choice
due to its performance and feature set.[^6] A typical engine setup for PostgreSQL
with asyncpg is as follows:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

DATABASE_URL = "postgresql+asyncpg://user:password@host:port/dbname"

engine = create_async_engine(
    DATABASE_URL,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,  # Recycle connections every hour
    pool_pre_ping=True,  # Check connection liveness
    echo=False,  # Set to True for SQL logging in development
)
```

6 The DATABASE\_URL string uses the postgresql+asyncpg:// scheme to specify the
dialect and driver. Several parameters are crucial for configuring the engine's
behaviour, particularly its connection pool. Logging SQL statements generated
by SQLAlchemy can be enabled by setting echo=True on the engine, which is
invaluable during development and debugging.[^9]

#### Deep Dive: Connection Pooling with AsyncEngine

Connection pooling is paramount for the performance and stability of web
applications, as it mitigates the overhead of establishing new database
connections for each request.[^9] SQLAlchemy's AsyncEngine manages a pool of
database connections that can be reused. The poolclass parameter specifies the
pooling implementation. For asynchronous operations, AsyncAdaptedQueuePool is
the appropriate choice.[^9] It is important to distinguish this from the
synchronous QueuePool. The SQLAlchemy documentation explicitly notes that
QueuePool is not compatible with asyncio.[^10] AsyncAdaptedQueuePool acts as a
wrapper, adapting a queue-based pooling mechanism to function correctly within
an asynchronous environment. This adaptation ensures that operations like
checking out and returning connections do not block the asyncio event loop.
Using an incompatible pool class, such as inadvertently configuring QueuePool
with an AsyncEngine, could introduce subtle bugs or performance degradation.
Thus, the selection of the correct poolclass is fundamental for reliable
asynchronous database interactions. Several key parameters govern the behaviour
of this pool: **Table 1: create\_async\_engine Key Pooling Parameters**

| Parameter       | Description                                                                                         | Typical Value/Range                               | Impact & Best Practice                                                                                                                                               |
| :-------------- | :-------------------------------------------------------------------------------------------------- | :------------------------------------------------ | :------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pool\_size      | The number of connections to keep persistently in the pool.[^9]                                     | 5-20 (application-dependent)                      | Sets the baseline for available connections. Too small can lead to waiting; too large can strain database resources. Tune based on load tests and database capacity. |
| max\_overflow   | The maximum number of additional connections that can be opened beyond pool\_size under load.[^9]   | 10-50 (application-dependent)                     | Allows handling of temporary spikes in demand. Total connections \= pool\_size \+ max\_overflow. Ensure the database can handle this total.                          |
| pool\_recycle   | Time in seconds after which a connection is automatically recycled (closed and replaced).[^9]       | 1800-7200 (30-120 minutes)                        | Prevents issues with stale connections due to network or database timeouts. Should be less than any server-side connection timeout.                                  |
| pool\_pre\_ping | If True, issues a lightweight "ping" (e.g., SELECT 1\) on connection checkout to test liveness.[^9] | True / False                                      | Recommended as True for production to avoid errors from dead connections, especially with long pool\_recycle times. Adds minor overhead but improves reliability.    |
| pool\_timeout   | Number of seconds to wait for a connection from the pool before raising a timeout error.[^10]       | 30 (default)                                      | Prevents indefinite blocking if the pool is exhausted. Adjust based on application tolerance for waiting.                                                            |
| echo\_pool      | If True or a logging level string (e.g., "debug"), logs connection pool activity.[^13]              | False (production), True or "debug" (development) | Useful for debugging pool behaviour, such as checkouts, checkins, and recycling. Can be verbose for production.                                                      |

7 Properly configuring these parameters is essential for balancing performance,
resource utilization, and application resilience.

### B. The async_sessionmaker: Crafting Your Session Factory

Once the AsyncEngine is configured, an async\_sessionmaker is used to create a
factory for AsyncSession instances.[^7] The AsyncSession is the primary interface
for ORM operations in an asynchronous context.

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

# Assuming 'engine' is the create_async_engine instance from above
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
```

9 Several parameters are critical when configuring the async\_sessionmaker:

- bind=engine: This associates the session factory directly with the previously
  configured AsyncEngine.
- class\_=AsyncSession: Explicitly specifies that the factory should produce
  instances of AsyncSession.
- expire\_on\_commit=False: This is a **critical best practice** for
  asynchronous applications.[^9] Setting it to False prevents SQLAlchemy from
  expiring the attributes of ORM-mapped instances after a transaction commits.
  In an asynchronous environment, if attributes are expired, subsequent access
  might trigger implicit I/O operations (lazy loading). If this I/O is not
  properly awaited (which it typically cannot be if the access is not within an
  async function or not using awaitable\_attrs), it can lead to runtime errors
  such as MissingGreenlet or, if the underlying I/O were synchronous, block the
  event loop. SQLAlchemy's asyncio extension is designed to prevent such
  implicit I/O by requiring explicit await for operations that load data.[^7]
  Thus, expire\_on\_commit=False ensures that already loaded data remains
  accessible without triggering unexpected, unawaited I/O.
- autoflush=False: This is generally recommended for asynchronous operations.[^9]
  Autoflush can trigger database I/O at potentially unexpected moments during a
  session's lifecycle. In an async context, it is preferable to have explicit
  control over when data is flushed to the database using await
  session.flush(). This ensures that all I/O operations are consciously awaited
  and managed within the asynchronous flow of the application.

**Table 2: async\_sessionmaker Configuration Options**

| Parameter          | Description                                          | Recommended Setting (Async) | Rationale for Async                                                                                                                                                                         |
| :----------------- | :--------------------------------------------------- | :-------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| bind               | The AsyncEngine to which new sessions will be bound. | engine instance             | Essential for connecting sessions to the database.                                                                                                                                          |
| class\_            | The class of session to be generated.                | AsyncSession                | Ensures that sessions are compatible with asynchronous operations.                                                                                                                          |
| expire\_on\_commit | If True, all instances are expired after commit().   | False                       | Prevents attributes from being expired post-commit, avoiding potential unawaited lazy-loading I/O that can cause errors or block the event loop in an async context.[^7]                    |
| autoflush          | If True, pending changes are flushed before queries. | False                       | Provides more explicit control over when database I/O occurs via await session.flush(), preventing unexpected blocking or unawaited operations that could arise from automatic flushes.[^9] |

9 Finally, during application shutdown, it is crucial to dispose of the engine
using await engine.dispose(). This call gracefully closes all underlying
database connections in the pool.[^7]

## III. Integrating AsyncSession with Falcon: Best Practices

Integrating asynchronous SQLAlchemy sessions into a Falcon application requires
careful consideration of Falcon's ASGI nature and the need for request-scoped
session management.

### A. Falcon's ASGI Nature: falcon.asgi.App and Async Responders

Falcon supports asynchronous operations through its falcon.asgi.App class.[^3]
When using this class, all components involved in request processing, including
resource responders (e.g., on\_get, on\_post), middleware methods, hooks, and
error handlers, **must** be defined as async def coroutine functions.[^16]
Falcon's ASGI implementation does not perform implicit wrapping or scheduling
of synchronous functions in an executor; developers are responsible for
ensuring all parts of the request-response cycle are awaitable if they involve
asynchronous operations.

### B. Core Best Practice: Request-Scoped Session Management via Custom Async Middleware

A fundamental principle when working with AsyncSession is that instances are
not safe for concurrent use across different asyncio tasks.[^17] Since each
incoming web request might be handled by a distinct asyncio task, each request
must have its own isolated AsyncSession instance. This prevents race conditions
and ensures data integrity. While the falcon-sqla package provides middleware
for SQLAlchemy session management in synchronous Falcon applications 18, it
does not appear to support AsyncEngine or AsyncSession based on available
information.[^18] Consequently, a custom asynchronous middleware solution is
necessary for managing AsyncSession lifecycle in a Falcon ASGI application.
Middleware is Falcon's standard mechanism for intercepting and processing
requests and responses 3, making it the ideal place to manage the creation,
provision, and cleanup of per-request database sessions. This approach mirrors
the "dependency injection" pattern seen in other frameworks, where resources
are made available to request handlers. In Falcon, middleware can attach the
session to the req.context object, allowing responders and other middleware
components to access it throughout the request's duration. This pattern offers
a clean and decoupled method for resource management, consistent with Falcon's
minimalist philosophy.

#### Step-by-Step: Building an Asynchronous Falcon Middleware for AsyncSession

Constructing a custom middleware involves defining a class with async def
process\_request and async def process\_response methods. 1\. Middleware Class
Definition: The middleware class will take the async\_session\_factory (created
in the previous section) as an argument during initialization.

```python
import falcon
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError  # For broader SQLAlchemy error catching


class SQLAlchemySessionManager:
    def __init__(self, async_session_factory):
        self.async_session_factory = async_session_factory

    async def process_request(self, req, resp):
        # Create a new session for each request and attach it to req.context
        req.context.session = self.async_session_factory()
        # Optionally, begin a transaction immediately.
        # Alternatively, responders can manage their own transactions if more granularity is needed.
        # await req.context.session.begin()

    async def process_response(self, req, resp, resource, req_succeeded):
        if hasattr(req.context, "session") and req.context.session:
            session: AsyncSession = req.context.session
            try:
                # If a transaction was started in process_request or by the responder,
                # and is still open, decide whether to commit or rollback.
                if session.in_transaction():  # Check if a transaction is still open
                    if req_succeeded and not resp.status.startswith(("4", "5")):
                        # Commit on success
                        await session.commit()
                    else:  # Rollback on client/server error or if req_succeeded is False
                        await session.rollback()
            except SQLAlchemyError:  # Catch SQLAlchemy specific errors during commit/rollback
                await session.rollback()
                # Potentially log the error
                raise  # Re-raise to allow Falcon's error handling to take over
            except Exception:
                if session.in_transaction():  # Rollback if a transaction is still open, e.g. after a failed flush
                    await session.rollback()
                # Potentially log the error
                raise  # Re-raise
            finally:
                await session.close()  # Always close the session to return connection to pool
```

9 The transaction handling within process\_response is crucial. The example
above attempts to commit if the request was successful (indicated by
req\_succeeded and a non-error HTTP status) and the session's transaction is
still active. An active transaction implies that the responder did not
explicitly commit or roll back. If an error occurred or the request was not
successful, it attempts a rollback. Robust error handling ensures a rollback
occurs if exceptions arise during the commit or close operations. The
session.is\_active check is important to avoid attempting to commit or roll
back an already concluded transaction. 2\. Initializing and Registering the
Middleware: The middleware instance is passed to the falcon.asgi.App during its
instantiation.

```python
# In the application setup file (e.g., app.py or main.py)
# 'async_session_factory' is the async_sessionmaker() instance configured earlier.
session_middleware = SQLAlchemySessionManager(async_session_factory)
app = falcon.asgi.App(middleware=[session_middleware])

# Define ORM models (e.g., in models.py)
# from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
# class Base(DeclarativeBase):
#     pass
# class User(Base):
#     __tablename__ = "users"
#     id: Mapped[int] = mapped_column(primary_key=True, index=True)
#     name: Mapped[str]
#     email: Mapped[str] = mapped_column(unique=True)
```

18 3\. Using the Session in Falcon Responders: Responders can access the
session via req.context.session.

```python
from sqlalchemy import select

# Assuming User model is defined as above and session is provided by middleware
# from .models import User  # Your ORM model


class UserResource:
    async def on_get(self, req: falcon.Request, resp: falcon.Response, user_id: int):
        session: AsyncSession = req.context.session
        try:
            # Example: Begin a transaction if not handled by middleware's process_request
            # async with session.begin():
            #     result = await session.execute(select(User).where(User.id == user_id))
            #     user = result.scalar_one_or_none()

            # Simpler approach if middleware handles top-level transaction:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user:
                resp.media = {"id": user.id, "name": user.name, "email": user.email}
                resp.status = falcon.HTTP_200
            else:
                raise falcon.HTTPNotFound(
                    title="User not found",
                    description=f"User with ID {user_id} not found.",
                )
        except SQLAlchemyError:
            # Log the database error
            # Consider rolling back if the middleware doesn't guarantee it on error
            # if session.is_active:
            #     await session.rollback()
            raise falcon.HTTPInternalServerError(
                title="Database error", description="A database error occurred."
            )


# Add route to the Falcon app
# app.add_route('/users/{user_id:int}', UserResource())
```

16 A key design decision is whether the middleware should automatically manage
the main transaction (begin on request, commit/rollback on response) or if
responders should explicitly manage their transactions. If the middleware
handles the top-level transaction, responders can perform operations directly.
For more complex scenarios requiring finer control, responders can use await
session.begin\_nested() to create savepoints within the middleware-managed
transaction. The example middleware leans towards managing the top-level
transaction, committing on success if the responder hasn't already, and rolling
back on failure. This simplifies responder logic for common cases but requires
careful consideration of the interaction between middleware and responder
transaction management.

## IV. Mastering Asynchronous ORM Operations

With the AsyncSession available, performing database operations involves using
SQLAlchemy's 2.0-style ORM constructs with await.

### A. Executing SELECT Queries Asynchronously

All query types are executed using await session.execute(statement).[^9] The
Result object returned by execute provides various methods for fetching data:

- result.scalars(): Yields scalar values from the first column of each row,
  typically used for retrieving lists of ORM objects when the statement selects
  entity instances.[^20]
- result.scalar\_one\_or\_none(): Returns a single scalar value from the first
  column of the first row, or None if no rows are found. Raises an error if
  multiple rows are returned.
- result.scalar(): Returns the first scalar value of the first row, or None
  when no row exists. Use scalar\_one() when the absence of a row must raise
  an error, and scalar\_one\_or\_none() when absence is a valid outcome.
- result.all(): Returns a list of all Row objects (which behave like tuples).  
- result.first(): Returns the first Row object or None.  
- result.one(): Returns exactly one Row, raising an error if the result set
  does not contain exactly one row.
- result.one\_or\_none(): Returns one Row or None if no rows; raises an error
  if multiple rows.

For handling potentially large result sets without loading everything into
memory at once, SQLAlchemy provides streaming capabilities:

- await session.stream(statement): Returns an AsyncResult object that supports
  asynchronous iteration.
- async for obj in (await session.stream(stmt)).scalars(): Iterates over
  scalar results (e.g., ORM objects) in a streaming fashion.[^7]

```python
from sqlalchemy import select

# Assuming User is an ORM model and session is an active AsyncSession
# from .models import User


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()  # Returns a single User object or None


async def get_all_users_list(session: AsyncSession) -> list[User]:
    stmt = select(User).order_by(User.name)
    result = await session.execute(stmt)
    return result.scalars().all()  # Returns a list of User objects


async def stream_all_user_names(session: AsyncSession):
    stmt = select(User.name).order_by(User.name)
    async_result = await session.stream(stmt)
    async for name in async_result.scalars():
        # Process each name as it streams in
        print(name)
```

20

### B. Data Modification: add(), add_all(), delete()

Modifying data involves staging changes within the AsyncSession and then
committing them.

- session.add(instance) and session.add\_all(\[instance1, instance2,…\]) are
  used to add new or modified ORM instances to the session, staging them for an
  INSERT or UPDATE operation.[^17]
- session.delete(instance) stages an ORM instance for a DELETE operation.[^21]

These changes are typically written to the database when await session.commit()
is called. The await session.flush() method can be used to send pending changes
to the database and update instance states (e.g., with auto-generated primary
keys or server defaults) *without* ending the current transaction. This is
particularly relevant in asynchronous contexts if these updated states are
needed before the transaction fully commits, ensuring that no other concurrent
task interacts with stale data. Explicitly awaiting flush() provides control
over when these intermediate state updates occur.

```python
# from .models import User  # Assuming User model


async def create_new_user(session: AsyncSession, name: str, email: str) -> User:
    new_user = User(name=name, email=email)
    session.add(new_user)
    await session.flush()  # Send INSERT to DB, get auto-generated ID, server defaults
    # The new_user object now has its ID and any server-set defaults populated.
    # await session.refresh(new_user)  # May be needed if there are other server-side triggers not covered by flush
    return new_user

async def update_user_email(
    session: AsyncSession, user_id: int, new_email: str
) -> User | None:
    user_to_update = await session.get(User, user_id)  # Efficiently get by Primary Key
    if user_to_update:
        user_to_update.email = new_email
        session.add(user_to_update)  # Stage the update
        await session.flush()  # Send UPDATE to DB
        return user_to_update
    return None


async def remove_user(session: AsyncSession, user_id: int) -> bool:
    user_to_delete = await session.get(User, user_id)
    if user_to_delete:
        await session.delete(user_to_delete)  # Stage the delete
        # The actual DELETE SQL will be issued on the next flush/commit.
        # Commit is typically handled by middleware or at the end of request logic.
        return True
    return False

```

20

### C. Efficient Relationship Loading: selectinload, joinedload in an Async Context

Lazy loading, the default behaviour for relationships, can lead to the "N+1
query problem," where accessing a relationship on N parent objects results in N
additional database queries. This is highly inefficient. Eager loading
strategies are essential to mitigate this.[^23]

- selectinload(Model.relationship\_attr): This strategy is generally preferred
  for loading one-to-many or many-to-many collections. It issues a second
  SELECT statement that fetches all related objects for the parent objects
  retrieved in the initial query, typically using an IN clause with the parent
  primary keys.[^20]
- joinedload(Model.relationship\_attr): This strategy uses a JOIN (usually a
  LEFT OUTER JOIN) in the primary SELECT statement to fetch related objects
  simultaneously. It is often suitable for many-to-one or one-to-one
  relationships.[^24]

```python
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

# from .models import User, Address  # Assuming User and Address models with a relationship

# Example: Get users and eagerly load their addresses (one-to-many)
stmt_users_with_addresses = select(User).options(selectinload(User.addresses))

# Example: Get an address and eagerly load its associated user (many-to-one)
stmt_address_with_user = select(Address).options(joinedload(Address.user))
```

20 In an asynchronous context, minimizing the number of await points (database
round-trips) might seem like a primary goal, which could favour joinedload (one
query) over selectinload (two queries). However, the choice is more nuanced.
joinedload can lead to Cartesian products if joining across collections,
potentially increasing data transfer and processing time. selectinload, while
involving a second query, often results in simpler individual queries and can
be more efficient for collections, especially since the awaits are
non-blocking, allowing the event loop to perform other work. The general
guidance often remains: selectinload for collections and joinedload for scalar
references (many-to-one, one-to-one) is a good starting point, but performance
should be verified through benchmarking for specific use cases.[^23] Fewer awaits
do not inherently guarantee better performance; the overall query complexity
and data volume are critical factors. Another useful strategy is lazy='raise'
or the raiseload() option, which can be used to prevent accidental lazy loads
by raising an exception if an unloaded attribute is accessed.[^24] This is
particularly helpful in async code to ensure all data access is explicit and
awaited. **Table 3: Async Relationship Loading Strategies: A Quick Comparison**

| Strategy                    | Async Mechanism                                            | No. of DB Round Trips (await points) | Typical Use Case                            | Async Considerations                                                                                                               |
| :-------------------------- | :--------------------------------------------------------- | :----------------------------------- | :------------------------------------------ | :--------------------------------------------------------------------------------------------------------------------------------- |
| selectinload                | Issues a second SELECT… WHERE id IN (…)                    | 2 (or more for nested)               | Collections (one-to-many, many-to-many)     | Generally efficient for collections. Avoids Cartesian products. The two awaits are non-blocking.                                   |
| joinedload                  | Uses JOIN in the primary SELECT                            | 1                                    | Scalar references (many-to-one, one-to-one) | Single await. Can create Cartesian products with collections, potentially increasing data transfer. Best for to-one relationships. |
| lazy='raise' or raiseload() | Raises InvalidRequestError on access of unloaded attribute | 0 (until access attempt)             | Preventing accidental lazy loads            | Crucial in async to ensure all I/O is explicit and awaited. Helps identify missing eager loads during development.                 |

20

## V. Asynchronous Transaction Control

Proper transaction management is vital for data consistency. SQLAlchemy's
AsyncSession provides robust mechanisms for handling transactions
asynchronously.

### A. Atomic Operations with async with session.begin()

The async with session.begin(): context manager is the primary and recommended
way to manage transactions.[^8] It ensures that the block of operations is treated
atomically:

- Upon entering the block, a new transaction is started (or a savepoint, if
  already within a transaction managed by begin\_nested).
- If the block completes without any exceptions, the transaction is
  automatically committed (await session.commit() is implicitly called).
- If an exception occurs within the block, the transaction is automatically
  rolled back (await session.rollback() is implicitly called), and the
  exception is re-raised.

```python
# Assuming session is an active AsyncSession and User is an ORM model
# from .models import User


async def update_user_name_atomically(
    session: AsyncSession, user_id: int, new_name: str
):
    async with session.begin():  # Starts a new transaction
        user = await session.get(User, user_id)
        if user:
            user.name = new_name
            session.add(user)  # Stage the change
        else:
            raise ValueError(f"User with ID {user_id} not found.")
    # Transaction is committed here if no exceptions were raised.
    # If ValueError or any other exception occurred, transaction is rolled back.
```

20 It's important to distinguish async with session.begin(): from async with
async\_session\_factory.begin() as session:. The latter,
async\_sessionmaker.begin(), is a convenience method that both creates a new
AsyncSession from the factory *and* starts a transaction within that new
session, managing the lifecycle of both.[^7] In the context of the Falcon
middleware pattern where a session is already created and provided per request
(e.g., req.context.session), one would typically use async with
req.context.session.begin(): within a responder if that responder needs to
manage its own transactional block. If the middleware itself initiates a
transaction (as shown in the SQLAlchemySessionManager example), responders
might operate within that existing transaction or use begin\_nested() for
savepoints.

### B. Managing await session.commit() and await session.rollback() Explicitly

While async with session.begin(): is preferred for its explicitness and safety,
there might be scenarios requiring more granular control over when commit() or
rollback() are called. In such cases, these methods can be invoked directly,
ensuring they are awaited.[^8] The custom Falcon middleware detailed in Section
III.B is an example where explicit commit/rollback logic is implemented in the
process\_response method.

```python
# Caution: Manual transaction management requires careful error handling.
# from .models import User
try:
    # user = User(name="Example", email="<example@example.com>")
    # session.add(user)
    # … other operations…
    await session.commit()  # Explicit commit
except Exception:
    await session.rollback()  # Explicit rollback on error
    raise
```

### C. Handling Nested Transactions (Savepoints) with session.begin_nested()

SQLAlchemy supports nested transactions through savepoints. The
session.begin\_nested() method initiates a new savepoint within the current
transaction.[^17] This is useful for operations that should be partially committed
or rolled back without affecting the entire outer transaction. begin\_nested()
returns a transaction object that may be awaited directly or used as an
asynchronous context manager.

```python
# from .models import AuditLog, User


async def process_user_with_audit(session: AsyncSession, user_data: dict):
    async with session.begin():  # Outer transaction
        # Main operation: create or update user
        user = await session.get(User, user_data.get("id"))
        if not user:
            user = User(name=user_data["name"], email=user_data["email"])
            session.add(user)
        else:
            user.name = user_data["name"]

        await session.flush()  # Ensure user ID is available for audit log

        try:
            async with session.begin_nested():  # Inner block (SAVEPOINT for audit log)
                audit_entry = AuditLog(user_id=user.id, action="USER_PROCESSED")
                session.add(audit_entry)
                await session.flush()
            # If successful, audit_entry is committed to the outer transaction (RELEASE SAVEPOINT)
        except Exception as e:
            # Log the audit failure, but the main user operation might still proceed
            print(f"Failed to write audit log: {e}")
            # The savepoint for the audit log is implicitly rolled back due to the exception
            # The outer transaction (user operation) is still active.
            # If this was await session.rollback(), it would rollback the savepoint.
            # The context manager handles this rollback automatically on exception.

    # Outer transaction commits (user and potentially audit log if successful) or
    # rolls back if an error occurred in the outer block.
```

30 When using nested transactions (savepoints) in an asynchronous environment,
meticulous error handling around the begin\_nested block is paramount. An
unhandled exception within this nested block must be caught to allow the outer
transaction to either proceed or be explicitly rolled back. The await
session.rollback() rolls back the outermost transaction, not just the
savepoint, so calling it directly within an except block that catches an
error from a begin\_nested operation would discard the whole transaction. Only
the transaction object returned by begin\_nested(), or the async with
session.begin\_nested(): context manager, rolls back just the savepoint when
an exception leaves its block, leaving the outer transaction intact and
active. The overall
transaction managed by the outer session.begin() will then be subject to its
own commit or rollback logic based on whether it completes successfully or
encounters an error.

## VI. Robust Error Handling in Async Applications

Effective error handling is crucial for building resilient asynchronous
services. This involves catching specific SQLAlchemy and database driver
exceptions and translating them into meaningful responses or actions.

### A. Common SQLAlchemy Exceptions

SQLAlchemy raises a variety of exceptions to signal different error conditions.
Key exceptions to handle include 31:

- sqlalchemy.exc.IntegrityError: Typically raised for violations of database
  integrity constraints (e.g., unique key, foreign key). asyncpg might raise
  its own asyncpg.exceptions.IntegrityConstraintViolationError, which
  IntegrityError often wraps.
- sqlalchemy.exc.NoResultFound: Raised when Result.one() or ScalarResult.one()
  expect a single row but find none.
- sqlalchemy.exc.MultipleResultsFound: Raised when Result.one() or
  ScalarResult.one() expect a single row but find multiple.
- sqlalchemy.exc.DBAPIError: A base class for exceptions raised by the
  underlying DBAPI driver (like asyncpg).
- sqlalchemy.exc.OperationalError: A subclass of DBAPIError, often indicating
  issues like connection problems, database unavailability, or other
  operational issues. asyncpg might raise specific connection errors like
  asyncpg.exceptions.ConnectionDoesNotExistError.[^33]

It's also beneficial to be aware of asyncpg-specific exceptions (e.g., from
asyncpg.exceptions) if more granular error handling related to the driver is
needed.[^11]

```python
import asyncpg  # For asyncpg specific exceptions
import falcon
from sqlalchemy.exc import IntegrityError, NoResultFound, OperationalError

# Example within a Falcon responder's method
# async def on_post(self, req, resp):
#     session: AsyncSession = req.context.session
#     try:
#         # … ORM operations leading to a potential commit…
#         # new_item = Item(**await req.get_media())
#         # session.add(new_item)
#         # await session.commit()  # Assuming commit is handled here or by middleware
#         resp.media = {"message": "Item created"}
#         resp.status = falcon.HTTP_201
#     except IntegrityError:  # Handles unique constraint violations, etc.
#         await session.rollback()  # Ensure transaction is rolled back
#         raise falcon.HTTPConflict(
#             title="Data integrity issue",
#             description="The resource could not be created due to a data conflict (e.g., already exists).",
#         )
#     except NoResultFound:  # If an operation expected a result (e.g., updating a specific item)
#         await session.rollback()
#         raise falcon.HTTPNotFound(
#             title="Resource not found",
#             description="A required related resource was not found.",
#         )
#     except asyncpg.PostgresConnectionError as e:  # More specific asyncpg connection error
#         # Log detailed error: e
#         if session.is_active:
#             await session.rollback()
#         raise falcon.HTTPServiceUnavailable(title="Database connection error")
#     except OperationalError as e:  # Broader SQLAlchemy operational errors
#         # Log detailed error: e
#         if session.is_active:
#             await session.rollback()
#         raise falcon.HTTPServiceUnavailable(title="Database operation failed")
#     except Exception as e:  # Catch-all for other unexpected errors
#         # Log detailed error: e
#         if hasattr(req.context, "session") and req.context.session.is_active:
#             await req.context.session.rollback()
#         # Re-raise to be handled by Falcon's global error handlers or for further logging
#         raise falcon.HTTPInternalServerError(title="An unexpected error occurred.")
```

31

### B. The DetachedInstanceError Pitfall: Causes and Async Solutions

A common pitfall in ORM usage is the DetachedInstanceError. This error occurs
when an application attempts to access an attribute that requires a database
load (lazy loading) on an ORM object that is no longer associated with an
active session; the object is in a "detached" state.[^35] This can happen if an
object is fetched, the session used to fetch it is closed, and then an attempt
is made to access a related collection or a deferred attribute. In an
asynchronous context, even with expire\_on\_commit=False (which keeps
attributes loaded after a commit), DetachedInstanceError can still arise if the
session is closed or the object is explicitly expunged (e.g., via
session.expunge(instance)), and a subsequent operation tries to trigger a lazy
load. The nature of asyncio, where tasks can yield and resume, can sometimes
make it less obvious when an object's originating session is no longer the
"active" session in the current execution context, especially if objects are
passed between tasks or coroutines without careful session management. This
underscores the importance of strict per-request session scoping, as advocated
by the middleware pattern. **Solutions to prevent or handle
DetachedInstanceError:**

1. **Maintain Session Association:** Ensure that an ORM object is associated
   with an active AsyncSession whenever attributes that might trigger lazy
   loading are accessed. The per-request session provided by middleware helps
   here.
2. **Eager Loading:** Proactively load all necessary related data when the
   object is initially queried using strategies like selectinload or
   joinedload.[^20] This avoids the need for later lazy loading.
3. **await session.refresh(instance):** If an object is detached or its data
   might be stale, and it's re-associated with an active session, await
   session.refresh(instance) can be used to reload its attributes from the
   database.[^35]
4. **instance.awaitable\_attrs:** SQLAlchemy's AsyncAttrs extension provides
   the awaitable\_attrs namespace on ORM objects. Accessing relationships
   through this mechanism (e.g., related\_items \= await
   my\_object.awaitable\_attrs.children) allows lazy loading to occur correctly
   and be awaited in an asynchronous context, provided the object is still
   bound to an active session.[^7] A potential issue arises if an object itself
   was lazy-loaded via awaitable\_attrs, and then one attempts to access *its*
   relationships. These nested relationships might still attempt a lazy load
   that could fail if not handled correctly. One documented solution involves
   explicitly refreshing these child objects within the current session before
   accessing their relationships (e.g., children \= await
   parent.awaitable\_attrs.children; \[await db\_session.refresh(c) for c in
   children\]).[^35]

The DetachedInstanceError often signals an issue with how sessions are scoped
or how object lifecycles are managed relative to session lifecycles in an
asynchronous application.

### C. Mapping Database Errors to Falcon HTTP Responses

Falcon allows for clean error handling by enabling responders to raise specific
falcon.HTTPStatus exceptions (e.g., falcon.HTTPNotFound, falcon.HTTPConflict,
falcon.HTTPBadRequest).[^3] Custom error handlers can also be registered globally
using app.add\_error\_handler(SomeException, custom\_handler\_func).[^3] It is a
best practice to use try…except blocks within service layers or Falcon
responders to catch specific SQLAlchemy or asyncpg exceptions and translate
them into appropriate Falcon HTTP error responses, providing meaningful
feedback to the client while abstracting database-specific error details. The
session should generally be rolled back when a database-related exception is
caught before raising an HTTP error.

## VII. Performance Tuning for Async SQLAlchemy

Optimizing the performance of an asynchronous database layer involves tuning
connection pool settings, writing efficient queries, strategically loading
related data, and identifying and eliminating bottlenecks.

### A. Optimizing Connection Pool Settings

Revisiting Table 1, the connection pool parameters (pool\_size, max\_overflow,
pool\_recycle, pool\_pre\_ping, pool\_timeout) should be fine-tuned based on
the application's expected concurrent load, the database server's capacity, and
network characteristics. Setting pool\_pre\_ping=True is generally advisable
for production environments as it helps avoid errors due to stale or dead
connections, albeit with a minor performance overhead for each connection
checkout.[^9]

### B. Strategic Query Construction and Relationship Loading

The choice of relationship loading strategy (Table 3\) significantly impacts
performance. As a general rule, selectinload is often better for collections
(one-to-many, many-to-many), while joinedload can be more efficient for scalar
(to-one) relationships.[^20] However, these are guidelines; actual performance can
vary. Avoid fetching unnecessary data by selecting only required columns or
using load\_only and defer options for specific attributes. The asyncpg driver,
when used with PostgreSQL, offers performance benefits through its support for
the binary protocol and prepared statements, which SQLAlchemy's async layer can
leverage.[^12] Furthermore, standard database optimization techniques, such as
ensuring appropriate indexes are in place for frequently queried columns and
join conditions, remain crucial.[^12]

### C. Identifying Bottlenecks: SQL Logging and Profiling

To identify performance bottlenecks:

1. **SQLAlchemy SQL Logging:** Enable echo=True on the AsyncEngine or
   echo\_pool=True for pool-specific logging during development.[^9] This allows
   inspection of the exact SQL queries being generated, helping to spot N+1
   problems, inefficient joins, or unexpectedly frequent queries.
2. **Python Profiling:** Use tools like cProfile (built-in) or asyncprofiler
   (for asyncio-specific insights) to identify sections of Python code that are
   consuming excessive time.
3. **Database Profiling:** Utilize database-specific tools (e.g., the
   `EXPLAIN ANALYZE` query in PostgreSQL) to understand the database's
   execution plan for slow queries and identify missing indexes or other
   database-level inefficiencies.

### D. Avoiding Blocking Calls in Async Code

A core tenet of asynchronous programming is to avoid blocking the event loop.

- Ensure all database operations that involve I/O are properly awaited. This
  includes session.execute(), session.commit(), session.rollback(),
  session.flush(), and relationship loading via awaitable\_attrs.
- SQLAlchemy 2.0's async mode is designed to make I/O explicit. Synchronous
  SQLAlchemy functions or attributes that might implicitly trigger I/O in older
  versions are generally not awaitable or are designed to raise errors if
  misused in an async context without proper handling.[^7]

SQLAlchemy's asynchronous support internally uses greenlets to bridge its
predominantly synchronous core logic with the asynchronous event loop provided
by asyncio.[^8] While this architecture is powerful, allowing much of the familiar
SQLAlchemy API to be used asynchronously via await, it implies that any
operation within a greenlet-spawned function that is truly blocking and not
correctly managed by the async driver (asyncpg) could still impede the thread
associated with that greenlet. If not carefully managed, this could indirectly
affect event loop responsiveness. Therefore, it's crucial to rely on asyncpg
and SQLAlchemy's async layer to handle I/O correctly. For situations where
synchronous SQLAlchemy code (e.g., complex event listeners or custom type
compilers that perform I/O) must be run within an async session context,
SQLAlchemy provides await session.run\_sync(). This method runs the
synchronous callable inline, via a greenlet, on the same thread and event
loop as the calling coroutine; it does not offload the work to a separate
thread.[^7] It is intended for synchronous SQLAlchemy code that does not perform
genuinely blocking I/O. For synchronous code that does perform blocking I/O,
use await asyncio.to\_thread(...) instead, which actually runs the callable
in a separate thread and keeps the event loop responsive.

## VIII. Testing Your Asynchronous Falcon & SQLAlchemy Code

Testing asynchronous applications that interact with a database requires
specific setups to ensure test isolation and reliability.

### A. Test Setup with pytest and pytest-asyncio

pytest is a widely adopted Python testing framework. For testing asyncio code,
the pytest-asyncio plugin is indispensable.[^44] It allows pytest to discover and
run async def test functions as coroutines. It's common to configure
pytest-asyncio mode, for example, by setting asyncio\_mode \= auto in the
pytest.ini file, which simplifies the execution of async tests and fixtures.[^45]

### B. Best Practice: Transactional Tests with Per-Test Rollbacks

A critical best practice for database testing is to ensure that each test runs
in an isolated transaction, which is rolled back at the test's conclusion. This
guarantees a clean database state for every test, irrespective of the
operations performed within the test, including calls to await
session.commit().[^46] This is achieved by managing transactions at the connection
level for the test session, while individual tests operate within savepoints. A
common fixture setup in conftest.py might include:

1. **event\_loop fixture (session-scoped):** Provides the asyncio event loop
   for the test session. pytest-async-sqlalchemy requires this to be
   session-scoped if sharing connections.[^49]
2. **AsyncEngine fixture (session-scoped):** Creates a single AsyncEngine for
   the entire test session.
3. **Database Schema Setup/Teardown fixture (session-scoped):** Manages the
   creation of database tables before the test session starts and their
   deletion after it ends.
4. **Test Connection fixture (db\_connection, session-scoped or
   function-scoped):** This fixture establishes a single AsyncConnection for a
   block of tests or the entire session. It begins a "real" database
   transaction on this connection. After all tests using this connection are
   done (or after each test if function-scoped and managing its own
   transaction), it rolls back this main transaction.
5. **AsyncSession fixture (db\_session, function-scoped):** This is the session
   provided to each individual test function.
   - It is bound to the test connection established by the db\_connection
     fixture.  
   - Crucially, it is configured with
     join\_transaction\_mode="create\_savepoint".[^46] When await session.commit()
     is called within a test using this session, SQLAlchemy doesn't commit the
     main database transaction on the connection. Instead, it operates on a
     SAVEPOINT within that main transaction.  
   - The fixture responsible for the db\_connection then ensures that the main
     transaction (and thus all savepoints) is rolled back after the test (or
     group of tests) completes.

This join\_transaction\_mode="create\_savepoint" mechanism is vital. It allows
test code to call await session.commit() as it would in production logic, but
the test framework ensures these commits are only to savepoints, maintaining
overall test isolation via the rollback of the encompassing connection-level
transaction. A conceptual conftest.py for such a setup:

```python
# conftest.py
import asyncio
import sys  # For platform check

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

# from my_app.models import Base  # Assuming your declarative base

TEST_DATABASE_URL = (
    "postgresql+asyncpg://test_user:test_password@localhost/test_db"  # Replace with your test DB URL
)


@pytest.fixture(scope="session")
def event_loop():
    if sys.platform.startswith("win") and sys.version_info[:2] >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    async_engine = create_async_engine(TEST_DATABASE_URL)
    # Optional: Create tables for the test session
    # async with async_engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    yield async_engine
    # Optional: Drop tables after the test session
    # async with async_engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)
    await async_engine.dispose()


@pytest.fixture
async def db_connection(engine: AsyncEngine) -> AsyncConnection:
    connection = await engine.connect()
    await connection.begin()  # Start a real transaction
    # Optionally begin a nested transaction (savepoint) immediately for the session to use
    # await connection.begin_nested()
    yield connection
    await connection.rollback()  # Rollback the real transaction
    await connection.close()


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncSession:
    # Session operates within the connection's transaction, using savepoints for its commits
    async_session_factory = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",  # Key for transactional tests
    )
    async_sess = async_session_factory()

    # This event listener ensures that after a test "commits" (releases a savepoint),
    # a new savepoint is started if the session is used further within the same test.
    # This is important because session.commit() in "create_savepoint" mode
    # actually DEACTIVATES the savepoint. The next operation would then be on the main transaction
    # unless a new savepoint is begun.
    @event.listens_for(async_sess.sync_session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:  # Check if it was a top-level savepoint for this session
            # Ensure the connection is still valid and in a transaction
            if db_connection.is_active and not db_connection.in_transaction():
                # This state should ideally not be reached if connection fixture manages transaction properly
                pass
            elif db_connection.is_active and db_connection.in_transaction():
                # Begin a new savepoint for subsequent operations in the same test if any
                db_connection.begin_nested()

    # Start the initial savepoint for the session to operate on
    await db_connection.begin_nested()
    yield async_sess
    await async_sess.close()
    # The db_connection fixture handles the final rollback of the main transaction.
```

(This fixture setup is a more detailed interpretation based on SQLAlchemy
testing patterns and snippets.[^46] The pytest-async-sqlalchemy library 49 offers
pre-built fixtures that implement similar logic, but understanding the manual
setup is valuable for customization and deeper comprehension.)

### C. Testing Falcon Endpoints with an Injected Test Session

To test Falcon endpoints that rely on the SQLAlchemy session middleware, you'll
use Falcon's testing utilities, such as falcon.testing.TestClient.[^48] For more
fine-grained control over the ASGI lifecycle, especially for streaming
responses or WebSockets, falcon.testing.ASGIConductor can be used.[^48] The
primary challenge is to ensure that your Falcon application, when run under
test, uses the transactional db\_session fixture instead of its production
database session factory. Falcon does not have a direct equivalent to FastAPI's
app.dependency\_overrides. Common strategies include:

1. **Application Factory Pattern:** Design your Falcon application with a
   factory function (e.g., create\_app()) that can accept configuration for
   testing, such as a custom session middleware or session factory.
2. **Middleware Replacement/Mocking:** In your test setup, create a
   test-specific Falcon App instance and provide it with a version of your
   session middleware that is hardcoded or configured to use the db\_session
   fixture.
3. **Patching:** Less ideal for middleware, but you could potentially patch the
   async\_session\_factory attribute of your production middleware instance if
   it's globally accessible, though this can be brittle.

A robust approach involves creating a test-specific application instance that
uses a test middleware:

```python
# conftest.py (extending previous example)
# from my_app.main import create_app_with_routes  # Assuming you have a function that adds routes

import falcon
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def client(db_session: AsyncSession):  # Uses the transactional db_session from above
    # Test middleware that injects the transactional db_session
    class TestSessionMiddleware:
        async def process_request(self, req, resp):
            req.context.session = db_session
            # The db_session fixture already handles the transaction/savepoint start

        async def process_response(self, req, resp, resource, req_succeeded):
            # The db_session fixture and its underlying connection fixture handle rollback
            pass

    # Create a Falcon ASGI app instance specifically for testing
    # and inject the test middleware.
    test_app = falcon.asgi.App(middleware=[TestSessionMiddleware()])

    # Add your application routes to this test_app
    # e.g., from my_app.routes import configure_routes
    # configure_routes(test_app)

    return falcon.testing.TestClient(test_app)


# In your test file (e.g., test_user_endpoints.py)
# async def test_get_specific_user(client, db_session: AsyncSession):
#     # Setup: Create a user directly using the test session
#     # from my_app.models import User
#     # test_user = User(name="Test User", email="<test@example.com>")
#     # db_session.add(test_user)
#     # await db_session.commit()  # This commits to the savepoint
#
#     response = await client.simulate_get(f"/users/{test_user.id}")
#     assert response.status == falcon.HTTP_200
#     assert response.json["name"] == "Test User"
# The db_session fixture ensures this test_user is rolled back.
```

46 It is also beneficial to test the session middleware itself in isolation to
verify its session creation, provision, and cleanup logic, separate from
testing the business logic within the resource responders. This layered testing
strategy improves the maintainability and diagnostic capability of your test
suite.

## IX. Conclusion: Building Scalable and Reliable Async Services

Successfully leveraging asynchronous SQLAlchemy 2.0 with PostgreSQL and Falcon
hinges on a clear understanding of asynchronous programming paradigms and
careful application of best practices. The transition to SQLAlchemy's native
async capabilities, particularly with the asyncpg driver, offers significant
performance potential for I/O-bound applications. **Key best practices
identified include:**

- **Core Setup:** Correctly configuring create\_async\_engine with
  AsyncAdaptedQueuePool and appropriate pooling parameters. Configuring
  async\_sessionmaker with expire\_on\_commit=False and autoflush=False is
  paramount for stable asynchronous behaviour.
- **Falcon Integration:** Implementing custom asynchronous middleware in Falcon
  to manage a request-scoped AsyncSession, making it available via req.context.
  This middleware should also handle top-level transaction demarcation (begin,
  commit/rollback) and ensure sessions are closed.
- **ORM Operations:** Explicitly awaiting all I/O-bound ORM operations,
  including query execution, data modification, and relationship loading.
  Strategic use of eager loading techniques like selectinload and joinedload is
  crucial to prevent N+1 query problems.
- **Transaction Management:** Utilizing async with session.begin(): for atomic
  operations and understanding how to use session.begin\_nested() for
  savepoints.
- **Error Handling:** Robustly catching SQLAlchemy and asyncpg exceptions,
  translating them into appropriate Falcon HTTP responses, and carefully
  managing DetachedInstanceError through proper session scoping and eager
  loading.
- **Performance:** Continuously tuning connection pool settings, optimizing
  queries, and using logging/profiling to identify and address bottlenecks.
  Avoiding any unintended blocking calls within the async workflow is
  essential, using session.run\_sync() for necessary synchronous code execution.
- **Testing:** Employing pytest with pytest-asyncio and implementing
  transactional tests where each test runs in an isolated, rolled-back
  transaction using join\_transaction\_mode="create\_savepoint" for the test
  sessions.

By adhering to these guidelines, developers can build Falcon applications that
interact with PostgreSQL asynchronously in a manner that is performant,
reliable, and maintainable. The combination of Falcon's minimalism and
SQLAlchemy's powerful async ORM capabilities provides a potent stack for modern
Python web services. **Pointers for Further Learning:**

- The official SQLAlchemy documentation, particularly the sections on
  Asynchronous I/O and ORM usage.[^7]
- The official Falcon framework documentation for ASGI applications and
  middleware.[^3]
- The asyncpg driver documentation for advanced features and
  PostgreSQL-specific interactions.[^53]
- Deeper exploration of asyncio patterns and best practices for concurrent
  programming in Python.[^1]

### Works cited

[^1]: asyncio — Asynchronous I/O — Python 3.13.3 documentation, accessed on June
    1, 2025,
    [https://docs.python.org/3/library/asyncio.html](https://docs.python.org/3/library/asyncio.html)

[^3]: Introduction to Python Falcon \- Tutorialspoint, accessed on June 1, 2025,
    [https://www.tutorialspoint.com/python\_falcon/python\_falcon\_introduction.htm](https://www.tutorialspoint.com/python_falcon/python_falcon_introduction.htm)

[^6]: seapagan/fastapi\_async\_sqlalchemy2\_example: A Simple example how to use
    FastAPI with Async SQLAlchemy 2.0 \- GitHub, accessed on June 1, 2025,
    [https://github.com/seapagan/fastapi\_async\_sqlalchemy2\_example](https://github.com/seapagan/fastapi_async_sqlalchemy2_example)

[^7]: Asynchronous I/O (asyncio) — SQLAlchemy 2.0 Documentation, accessed on
    June 1, 2025,
    [http://docs.sqlalchemy.org/en/latest/orm/extensions/asyncio.html](http://docs.sqlalchemy.org/en/latest/orm/extensions/asyncio.html)

[^8]: SQLAlchemy 2.0 \- GINO 1.1.0b2 documentation, accessed on June 1, 2025,
    [https://python-gino.org/docs/en/1.1b2/explanation/sa20.html](https://python-gino.org/docs/en/1.1b2/explanation/sa20.html)

[^9]: Asynchronous Database Sessions in FastAPI with SQLAlchemy \- DEV
    Community, accessed on June 1, 2025,
    [https://dev.to/akarshan/asynchronous-database-sessions-in-fastapi-with-sqlalchemy-1o7e](https://dev.to/akarshan/asynchronous-database-sessions-in-fastapi-with-sqlalchemy-1o7e)

[^10]: Asynchronous SQLAlchemy in FastAPI \- lricardo.space, accessed on June 1,
    2025,
    [https://lricardo.space/posts/asynchronous-sqlalchemy/](https://lricardo.space/posts/asynchronous-sqlalchemy/)

[^11]: Building an Async Product Management API with FastAPI, Pydantic, and
    PostgreSQL \- Neon, accessed on June 1, 2025,
    [https://neon.tech/guides/fastapi-async](https://neon.tech/guides/fastapi-async)

[^12]: Boost Your Application Performance With Asyncpg and PostgreSQL \-
    Timescale, accessed on June 1, 2025,
    [https://www.timescale.com/blog/how-to-build-applications-with-asyncpg-and-postgresql](https://www.timescale.com/blog/how-to-build-applications-with-asyncpg-and-postgresql)

[^13]: Connection Pooling — SQLAlchemy 2.0 Documentation, accessed on June 1,
    2025,
    [http://docs.sqlalchemy.org/en/latest/core/pooling.html](http://docs.sqlalchemy.org/en/latest/core/pooling.html)

[^16]: How to use async await in python falcon? \- Stack Overflow, accessed on
    June 1, 2025,
    [https://stackoverflow.com/questions/40791420/how-to-use-async-await-in-python-falcon](https://stackoverflow.com/questions/40791420/how-to-use-async-await-in-python-falcon)

[^17]: Session Basics — SQLAlchemy 2.0 Documentation, accessed on June 1, 2025,
    [http://docs.sqlalchemy.org/en/latest/orm/session\_basics.html](http://docs.sqlalchemy.org/en/latest/orm/session_basics.html)

[^18]: vytas7/falcon-sqla: SQLAlchemy session management middleware for Falcon
    applications., accessed on June 1, 2025,
    [https://github.com/vytas7/falcon-sqla](https://github.com/vytas7/falcon-sqla)

[^20]: examples.asyncio.async\_orm — SQLAlchemy 2.0 Documentation, accessed on
    June 1, 2025,
    [http://docs.sqlalchemy.org/en/latest/\_modules/examples/asyncio/async\_orm.html](http://docs.sqlalchemy.org/en/latest/_modules/examples/asyncio/async_orm.html)

[^21]: Using SQLAlchemy Asynchronously With AsyncIO (SQLAlchemy 2.0) \- YouTube,
    accessed on June 1, 2025,
    [https://www.youtube.com/watch?v=hkvngd\_BUrY](https://www.youtube.com/watch?v=hkvngd_BUrY)

[^23]: Understanding Lazy Loading in SQLAlchemy \- Optimize Your Performance
    Effectively, accessed on June 1, 2025,
    [https://moldstud.com/articles/p-understanding-lazy-loading-in-sqlalchemy-optimize-your-performance-effectively](https://moldstud.com/articles/p-understanding-lazy-loading-in-sqlalchemy-optimize-your-performance-effectively)

[^24]: Relationship Loading Techniques — SQLAlchemy 2.0 Documentation, accessed
    on June 1, 2025,
    [http://docs.sqlalchemy.org/en/latest/orm/queryguide/relationships.html](http://docs.sqlalchemy.org/en/latest/orm/queryguide/relationships.html)

[^33]: I keep getting asyncpg.exceptions.ConnectionDoesNotExistError: connection
    was closed in the middle of operation in my Sqlalchemy application \- DBA
    Stack Exchange, accessed on June 1, 2025,
    [https://dba.stackexchange.com/questions/345227/i-keep-getting-asyncpg-exceptions-connectiondoesnotexisterror-connection-was-cl](https://dba.stackexchange.com/questions/345227/i-keep-getting-asyncpg-exceptions-connectiondoesnotexisterror-connection-was-cl)

[^35]: python \- Accessing Eager-Loaded Relationships When Lazy …, accessed on
    June 1, 2025,
    [https://stackoverflow.com/questions/77812185/accessing-eager-loaded-relationships-when-lazy-loading-in-async-sqlalchemy](https://stackoverflow.com/questions/77812185/accessing-eager-loaded-relationships-when-lazy-loading-in-async-sqlalchemy)

[^44]: Essential pytest asyncio Tips for Modern Async Testing \- Continuously
    Merging, accessed on June 1, 2025,
    [https://blog.mergify.com/pytest-asyncio-2/](https://blog.mergify.com/pytest-asyncio-2/)

[^45]: Trouble getting testing working with async FastAPI \+ SQLAlchemy \-
    Reddit, accessed on June 1, 2025,
    [https://www.reddit.com/r/FastAPI/comments/1jcw7l7/trouble\_getting\_testing\_working\_with\_async/](https://www.reddit.com/r/FastAPI/comments/1jcw7l7/trouble_getting_testing_working_with_async/)

[^46]: Pytest \+ FastAPI \+ Async SQLAlchemy · GitHub, accessed on June 1, 2025,
    [https://gist.github.com/e-kondr01/969ae24f2e2f31bd52a81fa5a1fe0f96](https://gist.github.com/e-kondr01/969ae24f2e2f31bd52a81fa5a1fe0f96)

[^48]: Testing Helpers — Falcon 3.1.3 documentation, accessed on June 1, 2025,
    [https://falcon.readthedocs.io/en/3.1.3/api/testing.html](https://falcon.readthedocs.io/en/3.1.3/api/testing.html)

[^49]: pytest-async-sqlalchemy · PyPI, accessed on June 1, 2025,
    [https://pypi.org/project/pytest-async-sqlalchemy/](https://pypi.org/project/pytest-async-sqlalchemy/)

[^53]: asyncpg Usage, accessed on June 1, 2025,
    [https://magicstack.github.io/asyncpg/current/usage.html](https://magicstack.github.io/asyncpg/current/usage.html)

### Further reading

Sources consulted while preparing this guide that are not cited
inline above.

- 2.0 Changelog — SQLAlchemy 2.0 Documentation, accessed on June 1, 2025,
  [https://www.sqlalchemy.org/changelog/CHANGES\_2\_0\_40](https://www.sqlalchemy.org/changelog/CHANGES_2_0_40)
- Python Falcon Quick Guide \- Tutorialspoint, accessed on June 1, 2025,
  [https://www.tutorialspoint.com/python\_falcon/python\_falcon\_quick\_guide.htm](https://www.tutorialspoint.com/python_falcon/python_falcon_quick_guide.htm)
- Python Falcon ASGI \- Tutorialspoint, accessed on June 1, 2025,
  [https://www.tutorialspoint.com/python\_falcon/python\_falcon\_asgi.htm](https://www.tutorialspoint.com/python_falcon/python_falcon_asgi.htm)
- SQLAlchemy \- FastAPI Users, accessed on June 1, 2025,
  [https://fastapi-users.github.io/fastapi-users/latest/configuration/databases/sqlalchemy/](https://fastapi-users.github.io/fastapi-users/latest/configuration/databases/sqlalchemy/)
- From Zero to Production: Setting Up a SQL Database with Async Engine in
  FastAPI, accessed on June 1, 2025,
  [https://timothy.hashnode.dev/from-zero-to-production-setting-up-a-sql-database-with-async-engine-in-fastapi](https://timothy.hashnode.dev/from-zero-to-production-setting-up-a-sql-database-with-async-engine-in-fastapi)
- Build APIs with Falcon in Python | GeeksforGeeks, accessed on June 1, 2025,
  [https://www.geeksforgeeks.org/build-apis-with-falcon-in-python/](https://www.geeksforgeeks.org/build-apis-with-falcon-in-python/)
- Cascades — SQLAlchemy 2.0 Documentation, accessed on June 1, 2025,
  [http://docs.sqlalchemy.org/en/latest/orm/cascades.html](http://docs.sqlalchemy.org/en/latest/orm/cascades.html)
- Patterns and Practices for using SQLAlchemy 2.0 with FastAPI \- The Chaotic
  Engineer, accessed on June 1, 2025,
  [https://chaoticengineer.hashnode.dev/fastapi-sqlalchemy](https://chaoticengineer.hashnode.dev/fastapi-sqlalchemy)
- awesome-cursor-rules-mdc/rules-mdc/sqlalchemy.mdc at main \- GitHub, accessed
  on June 1, 2025,
  [https://github.com/sanjeed5/awesome-cursor-rules-mdc/blob/main/rules-mdc/sqlalchemy.mdc](https://github.com/sanjeed5/awesome-cursor-rules-mdc/blob/main/rules-mdc/sqlalchemy.mdc)
- Why joinedload() is the better choice than selectinload() in many to one
  relationship in SQLAlchemy \- Stack Overflow, accessed on June 1, 2025,
  [https://stackoverflow.com/questions/77368813/why-joinedload-is-the-better-choice-than-selectinload-in-many-to-one-relatio](https://stackoverflow.com/questions/77368813/why-joinedload-is-the-better-choice-than-selectinload-in-many-to-one-relatio)
- Performance — SQLAlchemy 2.0 Documentation, accessed on June 1, 2025,
  [http://docs.sqlalchemy.org/en/latest/faq/performance.html](http://docs.sqlalchemy.org/en/latest/faq/performance.html)
- Connect to PostgreSQL with SQLAlchemy and asyncio \- Makimo, accessed on June
  1, 2025,
  [https://makimo.com/blog/connect-to-postgresql-with-sqlalchemy-and-asyncio/](https://makimo.com/blog/connect-to-postgresql-with-sqlalchemy-and-asyncio/)
- Transactions and Connection Management — SQLAlchemy 2.0 …, accessed on June 1,
  2025,
  [http://docs.sqlalchemy.org/en/latest/orm/session\_transaction.html](http://docs.sqlalchemy.org/en/latest/orm/session_transaction.html)
- Core Exceptions — SQLAlchemy 2.0 Documentation, accessed on June 1, 2025,
  [http://docs.sqlalchemy.org/en/latest/core/exceptions.html](http://docs.sqlalchemy.org/en/latest/core/exceptions.html)
- How to check and handle errors in SQLAlchemy \- Stack Overflow, accessed on
  June 1, 2025,
  [https://stackoverflow.com/questions/2136739/how-to-check-and-handle-errors-in-sqlalchemy](https://stackoverflow.com/questions/2136739/how-to-check-and-handle-errors-in-sqlalchemy)
- How to catch SQL errors with AsyncPG? \- python \- Stack Overflow, accessed on
  June 1, 2025,
  [https://stackoverflow.com/questions/68008508/how-to-catch-sql-errors-with-asyncpg](https://stackoverflow.com/questions/68008508/how-to-catch-sql-errors-with-asyncpg)
- State Management — SQLAlchemy 2.0 Documentation, accessed on June 1, 2025,
  [http://docs.sqlalchemy.org/en/latest/orm/session\_state\_management.html](http://docs.sqlalchemy.org/en/latest/orm/session_state_management.html)
- Exception related to async Sqlalchemy \- python \- Stack Overflow, accessed on
  June 1, 2025,
  [https://stackoverflow.com/questions/71807902/exception-related-to-async-sqlalchemy](https://stackoverflow.com/questions/71807902/exception-related-to-async-sqlalchemy)
- Using the Session — SQLAlchemy 2.0 Documentation, accessed on June 1, 2025,
  [http://docs.sqlalchemy.org/en/latest/orm/session.html](http://docs.sqlalchemy.org/en/latest/orm/session.html)
- Python Falcon Error Handling \- Tutorialspoint, accessed on June 1, 2025,
  [https://www.tutorialspoint.com/python\_falcon/python\_falcon\_error\_handling.htm](https://www.tutorialspoint.com/python_falcon/python_falcon_error_handling.htm)
- Request-scoped transactions with async SQLAlchemy · Issue \#4224 \- GitHub,
  accessed on June 1, 2025,
  [https://github.com/fastapi/fastapi/issues/4224](https://github.com/fastapi/fastapi/issues/4224)
- Can SQLAlchemy be configured to be non-blocking? \- Stack Overflow, accessed
  on June 1, 2025,
  [https://stackoverflow.com/questions/10214042/can-sqlalchemy-be-configured-to-be-non-blocking](https://stackoverflow.com/questions/10214042/can-sqlalchemy-be-configured-to-be-non-blocking)
- ORM Examples — SQLAlchemy 2.0 Documentation, accessed on June 1, 2025,
  [http://docs.sqlalchemy.org/en/latest/orm/examples.html](http://docs.sqlalchemy.org/en/latest/orm/examples.html)
- How to Use SQLAlchemy to Make Database Requests Asynchronously, accessed on
  June 1, 2025,
  [https://towardsdatascience.com/how-to-use-sqlalchemy-to-make-database-requests-asynchronously-e90a4c8c11b1/](https://towardsdatascience.com/how-to-use-sqlalchemy-to-make-database-requests-asynchronously-e90a4c8c11b1/)
- External transaction with asyncio · sqlalchemy sqlalchemy · Discussion \#10857
  \- GitHub, accessed on June 1, 2025,
  [https://github.com/sqlalchemy/sqlalchemy/discussions/10857](https://github.com/sqlalchemy/sqlalchemy/discussions/10857)
- Python Falcon – Testing | GeeksforGeeks, accessed on June 1, 2025,
  [https://www.geeksforgeeks.org/python-falcon-testing/](https://www.geeksforgeeks.org/python-falcon-testing/)
- Testing Helpers — Falcon 4.0.2 documentation, accessed on June 1, 2025,
  [https://falcon.readthedocs.io/en/stable/api/testing.html](https://falcon.readthedocs.io/en/stable/api/testing.html)
- SQLAlchemy Documentation — SQLAlchemy 2.0 Documentation, accessed on June 1,
  2025, [https://docs.sqlalchemy.org/](https://docs.sqlalchemy.org/)
- Technical question on async SqlAlchemy session and … \- Reddit, accessed on
  June 1, 2025,
  [https://www.reddit.com/r/FastAPI/comments/1fhkekz/technical\_question\_on\_async\_sqlalchemy\_session/](https://www.reddit.com/r/FastAPI/comments/1fhkekz/technical_question_on_async_sqlalchemy_session/)
- Using dependency injection to get SQLAlchemy session can lead to …, accessed
  on June 1, 2025,
  [https://github.com/tiangolo/fastapi/discussions/6628](https://github.com/tiangolo/fastapi/discussions/6628)
