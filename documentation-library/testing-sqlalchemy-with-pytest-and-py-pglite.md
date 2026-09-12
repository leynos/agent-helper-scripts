# Testing SQLAlchemy 2.x with Postgres: PyTest and **py-pglite** Guide

## Why Use **py-pglite** for SQLAlchemy Tests

Testing a PostgreSQL-backed application can be slow or complex when real
databases or containers must be started. **py-pglite** offers an embeddable
Postgres for Python tests – essentially a **real PostgreSQL database running
in-memory** – with **zero config**. Tests can run **just like using SQLite**
while still exercising Postgres features (JSONB, array types, extensions, etc.)
in tests([1](https://github.com/wey-gu/py-pglite)). With **py-pglite**, each
test can have a **fresh, isolated database** that is created and destroyed
automatically, ensuring no state leaks between
tests([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)). In
short, it provides:

- **Real Postgres in tests:** Tests run against a true Postgres engine (not an
  SQLite or mock), so Postgres-specific features are available and issues are
  early([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)).

- **Ephemeral & isolated:** By default, each test gets its own clean database,
  preventing flaky runs caused by leftover
  data([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)).

- **Fast startup:** No Docker or external service needed – py-pglite
  initializes in a couple of seconds vs. tens of seconds for a
  container([1](https://github.com/wey-gu/py-pglite)).

- **Minimal boilerplate:** PyTest fixtures are provided to set up and tear down
  the DB automatically, removing manual setup/cleanup
  scripts([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)).

**py-pglite** achieves this by running a WebAssembly-based Postgres engine
under the hood (PGlite) inside a Node.js
runtime([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)).
(Node.js 18+ must be installed; the first run fetches the PGlite WASM
package.) Once installed with `pip install py-pglite[sqlalchemy]`, it
integrates with PyTest to make database testing almost seamless.

## Setting Up **py-pglite** Fixtures in PyTest

After installing, **py-pglite** provides out-of-the-box PyTest fixtures for
SQLAlchemy. The most important are:

- **`pglite_engine`** – a SQLAlchemy Engine connected to a temporary Postgres
  instance (typically one per test).

- **`pglite_session`** – a SQLAlchemy ORM Session bound to the above engine.

These fixtures can be requested in tests. **No database URL or manual server
startup is required** – simply including the fixture triggers py-pglite to
launch an in-memory Postgres and yield a connection. For example, a basic test
might look like:

```python
# models.py – define an example model
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]
```

```python
# test_models.py
from sqlalchemy import select


def test_user_creation(pglite_session):
    # Ensure the test database has the schema (e.g., run migrations or create tables)
    Base.metadata.create_all(pglite_session.bind)  # Using Base from the project models

    # Use the session fixture just like a normal Session
    new_user = User(name="Alice", email="[email protected]")
    pglite_session.add(new_user)
    pglite_session.commit()

    # Query back the data to verify
    result = pglite_session.execute(select(User).where(User.name == "Alice"))
    user = result.scalar_one()

    assert user.email == "[email protected]"
    assert user.id is not None
```

When this test runs, `pglite_session` provides a **fully configured Session**
connected to a temporary Postgres. **The database instance is started just for
this test and torn down after**, so the next test starts with a clean
slate([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)).
`pglite_session` can be used exactly like a normal SQLAlchemy session to
add/query objects. In this example, `Base.metadata.create_all(...)` creates the
tables for the model in the ephemeral database. In a real project, Alembic
migrations would typically set up the schema (more on this below), but using
`create_all` is fine for simple cases.

**Note:** The first py-pglite test may take a moment to download the WASM
Postgres bundle via Node.js. Once installed, database startup is very fast (a
couple of seconds or less) for each test.

## Writing Asynchronous Tests with SQLAlchemy 2.x and **pytest-asyncio**

SQLAlchemy 2.x supports an async ORM API, and async database logic can be
tested with py-pglite as well. Py-pglite does not yet provide a ready-made
`AsyncSession` fixture, but it can be integrated with a small amount of setup.
The key steps are:

- **Enable async driver:** Install py-pglite with the async extra
  (`pip install py-pglite[asyncpg]`) so that the asyncpg driver is available.
  Py-pglite’s default engine uses the Psycopg driver via a Unix socket, which
  doesn’t directly work with SQLAlchemy’s `AsyncEngine`. Instead, run the
  Postgres in TCP mode and use `asyncpg`.

- **Get connection info:** Use a PGlite manager to obtain the host, port, and
  database name of the running instance. Requesting the `pglite_manager`
  fixture (which yields a `PGliteManager`) provides an engine or DSN.

- **Create an AsyncEngine:** Build a SQLAlchemy AsyncEngine using
  `create_async_engine()` with the `asyncpg` driver pointing to the PGlite
  host/port. For example:
  `create_async_engine(f"postgresql+asyncpg://{host}:{port}/{database}")`
  ([1](https://github.com/wey-gu/py-pglite)).

- **Use `pytest-asyncio`** to write async test functions that await database
  operations.

Below is an illustrative async test setup:

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.mark.asyncio
async def test_async_insert_and_query():
    # Start a PGlite instance manually and get connection details
    from py_pglite import PGliteConfig, PGliteManager

    import os

    # Derive a unique port per pytest-xdist worker to avoid collisions.
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    tcp_port = 54321 + int(worker_id.replace("gw", "") or 0)
    config = PGliteConfig(tcp_port=tcp_port, tcp_host="127.0.0.1")  # use TCP mode
    with PGliteManager(config) as pg_manager:  # start the Postgres WASM instance
        # Build an AsyncEngine using asyncpg driver
        pg_url = f"postgresql+asyncpg://postgres:postgres@{config.tcp_host}:{config.tcp_port}/postgres"
        async_engine = create_async_engine(
            pg_url,
            future=True,
            connect_args={"server_settings": {}, "ssl": False},
        )
        async with async_engine.begin() as conn:
            # (Optionally, run Alembic migrations here or create tables)
            await conn.run_sync(Base.metadata.create_all)
        # Use an AsyncSession to interact with the DB
        async with AsyncSession(async_engine) as session:
            new_item = User(name="Bob", email="[email protected]")
            session.add(new_item)
            await session.commit()
            # Query using SQLAlchemy's async API
            result = await session.execute(select(User).where(User.name == "Bob"))
            bob = result.scalar_one()
            assert bob.email == "[email protected]"
        # Dispose engine (closing all connections)
        await async_engine.dispose()
```

In this example, the PGlite lifecycle is managed manually with `PGliteManager`
(usable as an async context manager). The manager is configured to listen on a
TCP port, then an AsyncEngine is created to connect via `asyncpg`. The test runs
`Base.metadata.create_all` inside an `engine.begin()` block to create tables
(in production, migrations would typically be invoked instead). The test then
performs async session operations (`await session.commit()`,
`await session.execute(...)`) and assertions.

**Key points for async usage:**

- Ensure the **driver and connection string** are correct. The DSN must use
  `postgresql+asyncpg://` (or an async psycopg DSN if using psycopg3’s async
  support). Py-pglite’s built-in connection string is hard-coded for
  psycopg+Unix socket by
  default([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)), so
  switching to TCP as shown above is the easiest path for async.

- **Use `pytest.mark.asyncio`** (from `pytest-asyncio`) on async test functions
  so PyTest handles the event loop.

- The rest of the async test workflow naturally allows mixing `asyncio` awaits
  with database calls as shown.

## Resetting the Database Between Tests (Function vs. Session Scope)

One of the advantages of py-pglite is test **isolation** – each test starts
with a blank database. By default, the provided `pglite_session` fixture has
**function scope**, meaning **each test function gets its own fresh
database**([1](https://github.com/wey-gu/py-pglite)). This is the safest
approach to avoid cross-test interference. However, database scope and reset
behaviour can be adjusted:

- **Per test (function-scope)** – **Default**. Every test uses a new ephemeral
  Postgres instance. Migrations or table creation can run at the start of each
  test. This guarantees isolation but has the overhead of repeated startup and
  schema setup. Use this when tests need complete independence or if the
  database setup is lightweight.

- **Per test module or session (module/session-scope)** – A single database
  instance is shared by multiple tests, typically created at the beginning of
  the test run. Migrations typically run **once per session** (not for each
  test) for
  speed([3](https://hoop.dev/blog/the-simplest-way-to-make-postgresql-pytest-work-like-it-should/)).
  This can significantly speed up a large test suite by avoiding redundant DB
  initialization. **However**, isolation *within* that shared database still
  needs to be enforced. Common strategies include:

- **Truncate or clean tables between tests:** After each test, delete the data
  that was added. Py-pglite provides a utility
  `utils.clean_database_data(engine)` to wipe all tables (with an option to
  exclude certain tables).[^py-pglite-guide] Call this in a function-scoped
  fixture that runs after each test when using a shared engine. Likewise,
  `utils.reset_sequences(engine)` will reset serial primary key counters so IDs
  start from 1 again – useful for consistency in tests. These utilities help
  keep a session-scoped database *logically* fresh between tests.

- **Use savepoint rollbacks or transactions:** Another approach is to run each
  test inside a transaction and roll it back at the end, so no changes persist.
  For example, open a transaction in a setup fixture, yield the session to the
  test, and roll back in teardown. This works best when the code under test
  does not manage transactions. (Note: When using SQLAlchemy’s Session,
  expiring the session after rollback prevents stale state.)

- **Use separate schemas per test:** Py-pglite’s utilities can create/drop
  schemas when isolating data by schema.[^py-pglite-guide] For instance, each
  test could operate in a schema named after the test function, and the schema
  is dropped afterwards. This avoids altering the entire DB and is useful in
  multi-tenant style testing.

Choosing the scope often involves a **trade-off between performance and
isolation**. When test suites are small or deterministic isolation is
prioritized, function-scoped (fresh DB each test) is simplest. For large suites
where DB setup is a bottleneck, consider a session-scoped database with careful
cleaning. As a rule of thumb: **apply schema migrations once per test session
and reuse the database for speed, but ensure each test starts from a known empty
state**([3](https://hoop.dev/blog/the-simplest-way-to-make-postgresql-pytest-work-like-it-should/)).

When a shared py-pglite instance is also shared across `pytest-xdist` workers,
guard schema resets with an inter-process file lock acquired around the whole
drop-and-recreate sequence, or give each worker a separate database or
schema. A module-level `asyncio.Lock` does not help here: `pytest-xdist`
workers are separate OS processes, each with its own Python interpreter and
event loop, so an `asyncio.Lock` in one process is invisible to the others.
Without process-level coordination, one worker can drop the schema while
another is mid-migration, producing intermittent, hard-to-reproduce failures.

## Applying Alembic Migrations in Tests

When using SQLAlchemy with Alembic for migrations, apply those migrations to
the test database so that the test schema matches the production schema.
**Never assume ORM models alone define the database structure** – migrations
may include critical DDL like constraints or indexes. Integrate Alembic into
the test setup as follows:

- **Run migrations at setup:** Use a PyTest fixture (often session-scoped) to
  run `alembic upgrade head` against the test database. For example, load the
  Alembic `Config` and call `alembic.command.upgrade(config, "head")` once the
  py-pglite engine is up. If the `pglite_engine` fixture is available, create
  another fixture that depends on it:

```python
from alembic import command
from alembic.config import Config


@pytest.fixture(scope="session")
def migrated_engine(pglite_engine):
    # Point Alembic to the test DB URL
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", str(pglite_engine.url))
    command.upgrade(alembic_cfg, "head")
    yield pglite_engine
    # (Optionally, downgrade or clean after tests)
```

Then use `migrated_engine` in tests instead of `pglite_engine` to ensure schema
is ready. This runs migrations once for the session. For strict per-test
isolation, migrations could run in a function fixture, but that approach is
slower and usually unnecessary once the schema is in
place([3](https://hoop.dev/blog/the-simplest-way-to-make-postgresql-pytest-work-like-it-should/)).)

- **Use `pytest-alembic` (optional):** The community has a plugin
  **pytest-alembic** that can automate applying migrations in tests and even
  has built-in tests for migration consistency. When installed, it can be
  configured to run migrations in a fixture and validate that migrations
  produce the intended schema. This can be overkill for basic needs, but it is
  useful when the migrations themselves need direct coverage.

- **Teardown (if needed):** For a session-scoped DB, drop the database or roll
  back migrations after the tests if desired. With py-pglite, the in-memory
  database vanishes once the process ends, so explicit teardown of the schema
  is usually not required – simply let py-pglite shut down. Clean any
  persistent artefacts (like files on disk via `work_dir` config) if they were
  created.

Using Alembic in tests ensures ORM code is exercised against the **actual
database structure** as defined by migrations. This catches issues like missing
migrations or mismatches between models and DB (a common source of bugs) early
in development. Migrations that add seed data or required setup then benefit
the tests automatically.

**Checking for migration drift:** As a separate, complementary check (often
its own script or CI step rather than a pytest fixture), start a fresh
py-pglite instance, apply the full Alembic migration set to it, and compare
the resulting schema against the ORM's `Base.metadata`. Any mismatch signals
that a model change was made without a corresponding migration, or vice versa.
This check is independent of the main fixture stack and can run outside pytest
entirely.

## Injecting Test Database into Your Application (Dependency Injection)

In many applications, especially web frameworks like **FastAPI** or **Flask**,
database access is provided via some form of *dependency injection* or global
session. For example, FastAPI often exposes a `get_db()` dependency that yields
a session, or a module-level `SessionLocal()` may be defined for the app.
During testing, those dependencies should be **overridden to use the py-pglite
test database** instead of the production database. Approaches include:

- **FastAPI dependency override:** Override the `get_db` dependency in tests.
  Suppose a FastAPI app uses `Depends(get_db)` to obtain a Session. In a test,
  request the `pglite_engine` fixture and override `get_db` to yield a Session
  from that engine. For example:

```python
import pytest
from fastapi.testclient import TestClient
from myapp.main import app, get_db  # the FastAPI app and the original dependency
from sqlalchemy.orm import Session


@pytest.fixture
def client(pglite_engine):
    # Override get_db to use pglite_engine
    def override_get_db():
        with Session(pglite_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_create_user_api(client):
    resp = client.post("/users/", json={"name": "Bob", "email": "[email protected]"})
    assert resp.status_code == 200
    # ... further assertions ...
```

In this snippet, a new Session bound to the `pglite_engine` is injected for each
request.[^py-pglite-guide] The test client calls the override, using the
in-memory Postgres. The API is therefore exercised against the ephemeral DB and
**no data goes to the real database**. After the test, remove the override if
needed. `app.dependency_overrides` is a plain dict attached to the application
object, so it persists across tests unless removed explicitly.

- **Flask or others:** If an application uses a global SQLAlchemy `db` object
  or sessionmaker, configure it for tests. For instance, create a PyTest
  fixture that **re-binds the session/engine** to the pglite engine. In
  Flask-SQLAlchemy, configure
  `app.config["SQLALCHEMY_DATABASE_URI"] = pglite_engine.url` before
  initializing the app context for testing.

- **Manual injection:** For pure Python code, design functions to accept a
  session or engine as a parameter. In tests, pass in `pglite_session` or
  `pglite_engine`. This form of dependency injection keeps the code testable.
  For example, if a repository function
  `def get_user_by_email(email: str, session: Session) -> User:` is defined,
  call `get_user_by_email("alice@example.com", pglite_session)` with the
  fixture.

Using dependency injection techniques ensures the **application code under test
uses the same test database**. In both direct function calls and endpoint
invocations, everything operates on the py-pglite Postgres. The result is
end-to-end tests that are isolated yet use realistic database interactions.

## Generating Test Data with Factory Boy and Faker

Manually crafting test data can be tedious and can lead to repetitive tests.
**Factory Boy** is a popular library that helps create ORM model instances with
fake data easily, and **Faker** is used under the hood (or directly) to
generate realistic data (names, emails, etc.). When testing a SQLAlchemy
application, factories and fake data can make tests more concise and robust:

- **Define factories for the models:** A factory is a class that knows how to
  create a model object. For SQLAlchemy ORM, Factory Boy offers
  `SQLAlchemyModelFactory`, which can handle session persistence. For example,
  with the `User` model above, define a factory:

```python
import factory
from factory.alchemy import SQLAlchemyModelFactory
from faker import Faker

fake = Faker()


class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session = None  # to be set later by a fixture
        sqlalchemy_session_persistence = False

    name = factory.LazyAttribute(lambda _: fake.name())
    email = factory.LazyAttribute(lambda _: fake.safe_email())
```

This factory generates a `name` and `email` using Faker whenever a UserFactory
is built. `sqlalchemy_session` is left as None for now – the actual session is
injected at test time.

- **Use a fixture to attach the session:** In tests,
  `UserFactory.create()` should automatically add the user to the
  `pglite_session`. Assign the PyTest session to the factory before using it.
  One approach is an autouse fixture that runs for each test and sets
  `UserFactory._meta.sqlalchemy_session = pglite_session`. Factory Boy’s docs
  suggest this
  approach([5](https://medium.com/@aasispaudelthp2/factoryboy-tutorial-with-sqlalchemy-and-pytest-1cda908d783a)).
  For example:

```python
@pytest.fixture(autouse=True)
def _set_factory_session(pglite_session):
    UserFactory._meta.sqlalchemy_session = pglite_session
```

Calls to `UserFactory()` use the provided session to insert the User into the
database. For instance, `alice = UserFactory(name="Alice")` creates a new User
with name "Alice" (and a fake email) and adds it to `pglite_session`. Commit
the session if needed (or set `sqlalchemy_session_persistence=True` to have
Factory Boy commit automatically after creation).

- **Quick data generation:** Factories can generate multiple records in one go.
  For example, Factory Boy allows creating batches:
  `UserFactory.create_batch(5)` will make five User records at
  once([5](https://medium.com/@aasispaudelthp2/factoryboy-tutorial-with-sqlalchemy-and-pytest-1cda908d783a)).
  Each will have unique fake data for the fields. This is extremely handy for
  populating a test database with sample data. Override specific fields per
  call (e.g., `UserFactory(name="Specific Name")`) to test particular
  scenarios([5](https://medium.com/@aasispaudelthp2/factoryboy-tutorial-with-sqlalchemy-and-pytest-1cda908d783a)).

- **Faker for direct use:** Even outside of Factory Boy, **Faker** can generate
  data for ad hoc inserts or assertions. For example, `fake.email()` returns a
  random email address, ensuring a test covers varied inputs. Faker can
  generate consistent data if seeded (e.g., `Faker.seed(1234)`) for
  reproducibility.

Using Factory Boy and Faker makes tests more **expressive** – the required data
is declared without manual value selection. This can uncover edge cases (e.g.
names with non-ASCII characters, very long text, etc. from Faker) and keeps
tests maintainable. It is especially powerful in integration with py-pglite: it
is possible to **create a complex object graph with one factory call** (thanks
to Factory Boy’s support for SubFactory
relations([5](https://medium.com/@aasispaudelthp2/factoryboy-tutorial-with-sqlalchemy-and-pytest-1cda908d783a))),
and have that data immediately persisted to the in-memory Postgres for the
test to use.

## Final Tips and Best Practices

Combining **SQLAlchemy**, **PyTest**, and **py-pglite** gives a potent testing
setup that is fast, isolated, and faithful to the production environment. Here
are some parting best-practice tips for this setup:

- **Keep tests deterministic:** Because each test starts with a known empty
  database (or resets it), tests are less likely to flicker due to state
  bleed-over. When a shared DB is used for speed, be rigorous in cleaning up
  data between tests. Tools like `verify_database_empty(engine)` from py-pglite
  can assert that no data remains.[^py-pglite-guide]

- **Always commit or flush when needed:** SQLAlchemy’s Session will not persist
  changes to the database until a commit (or autoflush) occurs. Tests often
  fail when a query returns no data because a commit was forgotten. Commit in
  tests or use `session.flush()` before selecting, to be safe.[^py-pglite-guide]

- **Parallel testing:** When running tests in parallel (e.g., with
  `pytest-xdist`), ensure each process has an isolated database. Py-pglite’s
  default of one DB per test should handle this, but if a session-scoped DB is
  shared, it *cannot* be reused across processes. Configure separate ports for
  each worker or simply stick to function-scoped isolation for parallel runs.

- **Node.js dependency:** As noted, py-pglite currently relies on Node to run
  the WASM
  Postgres([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)). In
  a CI environment, make sure Node is installed. Once set up, the tests behave
  the same locally and in CI. The maintainers are exploring more direct WASM
  integration to drop the Node requirement in the
  future([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)). Node
  startup can occasionally stall on shared or loaded hosts; a session-scoped
  fixture that retries startup a small, bounded number of times with a fresh
  work directory absorbs this without masking genuine failures.

- **Set a generous but bounded test timeout:** py-pglite startup plus Alembic
  migrations can take longer than a typical unit test on a busy CI host. Give
  database-backed tests enough headroom to complete reliably, but treat tests
  that repeatedly run close to the timeout as a fixture or migration
  performance problem to investigate, not a reason to keep raising the limit.

- **Use real Postgres features confidently:** Since py-pglite *is* Postgres,
  JSON fields, text search, `pg_trgm`, or other extensions belong in both the
  application and the tests. Extensions like `pgvector` can be enabled in
  py-pglite for testing advanced
  features([1](https://github.com/wey-gu/py-pglite)). Tests can then validate
  functionality that would be impossible to cover with SQLite or mocks.

Following this guide sets up a robust testing environment for SQLAlchemy 2.x
applications. The result is the **best of both worlds** – quick, ephemeral
databases as convenient as SQLite, and the full power and accuracy of
PostgreSQL. This enables thorough tests (unit tests, integration tests, even
testing API endpoints with the DB in play) with minimal friction. In practice,
teams find that such a setup **“shaves minutes from every build, and hours from
every week” by ensuring every test run starts from a known good state with no
manual DB management
overhead([3](https://hoop.dev/blog/the-simplest-way-to-make-postgresql-pytest-work-like-it-should/))
**. Happy testing!

**Sources:**

- Arun Babu Neelicattu, *"Python, PostgreSQL and Wasm walk into a pytest bar"*
  – Overview of py-pglite for in-process Postgres
  testing([2](https://void.abn.is/a-python-project-postgresql-and-wasm/)).

- wey-gu (GitHub) – **py-pglite** README and examples (SQLAlchemy usage, async
  tips, extension support)([1](https://github.com/wey-gu/py-pglite)).

- High Efficiency Coder Blog –
  *"秒建PostgreSQL内存数据库：Python测试效率翻倍秘籍"* (Chinese) – In-depth
  guide on py-pglite usage and utilities.[^py-pglite-guide]

- hoop.dev blog – *"PostgreSQL PyTest work like it should"* – Best practices
  for database test isolation and
  performance([3](https://hoop.dev/blog/the-simplest-way-to-make-postgresql-pytest-work-like-it-should/)).

- Aashish Paudel, *Factory Boy tutorial with SQLAlchemy and Pytest* – Usage of
  Factory Boy with SQLAlchemy (session fixture, `SQLAlchemyModelFactory`)
  ([5](https://medium.com/@aasispaudelthp2/factoryboy-tutorial-with-sqlalchemy-and-pytest-1cda908d783a)).

[^py-pglite-guide]:
  <https://www.xugj520.cn/archives/py-pglite-postgresql-testing-guide.html>
