# Code Quality and Architecture Rules (rules.md)

This document establishes development rules for the **AI Architecture Code Reviewer** codebase itself, alongside the architectural rules that the system's review engine detects.

---

## 1. Development Rules for this Codebase (Enterprise Standards)

To ensure this codebase is maintainable, scalable, and follows enterprise-grade practices, the following guidelines are mandatory:

### 1.1 Code Organization
- **Separation of Concerns**: Core logic, API routing, database transactions, and service schemas must be decoupled.
- **Pydantic Validation**: All input payloads and API responses must go through Pydantic models. Avoid returning raw dicts.
- **Dependency Injection**: Use FastAPI's `Depends` system for sharing dependencies (e.g., db sessions, auth contexts).

### 1.2 Error Handling & Resiliency
- **Strict Exception Handling**: Never use catch-all empty blocks (`except: pass`). Log specific error messages with log-levels (`logger.exception()`).
- **HTTP Exceptions**: Always raise appropriate HTTP exceptions (`HTTPException`) in routers, and let services raise custom application exceptions that are caught by exception handlers.
- **API Retries**: Any external HTTP request (e.g., calling GitHub API or LLM API) must be wrapped in retry logic with exponential backoff.

### 1.3 Database Best Practices
- **Explicit Transactions**: Use async contexts (`async with Session() as session:`) to manage transaction boundaries.
- **No N+1 Queries**: Eagerly load relationships (`selectinload`, `joinedload`) instead of lazy loading when querying relationships.

---

## 2. Review Engine Architecture Rules (Detected Patterns)

The review engine evaluates incoming Pull Requests against these core architectural rules:

### Rule 2.1: Layered Isolation Violations
- **Definition**: Ensures clean boundaries between UI/API layers, business logic, and database operations.
- **Check logic**: AST parser inspects imports.
  - *Violation Type A*: API routers (`api/routes/`) importing database models (`models/`) directly, bypassing the service layer.
  - *Violation Type B*: Business services (`services/`) importing UI-related elements or frameworks.

### Rule 2.2: Circular Dependencies
- **Definition**: Two or more modules importing each other directly or transitively, creating a tight coupling cycle.
- **Check logic**: NetworkX cycle detection algorithm (`simple_cycles`) over the module import graph.
  - *Violation Type*: Module `auth.py` imports `users.py`, and `users.py` imports `auth.py`.

### Rule 2.3: Database Performance & N+1 Queries
- **Definition**: Executing database queries inside loops (such as `for` loops or map lists), resulting in excessive network roundtrips.
- **Check logic**: AST parser detects database query method calls (`session.execute`, `.all()`, `.filter()`, etc.) nested inside loop contexts (`For`, `While`, List Comprehensions).

### Rule 2.4: Sync Blocking Event Loop
- **Definition**: Performing CPU-bound operations or synchronous network calls in async handlers, blocking FastAPI's single-threaded event loop.
- **Check logic**: Scanner flags `time.sleep()`, synchronous `requests.get()`, or heavy file system calls inside `async def` function blocks.

### Rule 2.5: API Contract Breakage (Schema Drift)
- **Definition**: Making breaking changes to existing public schema fields, breaking backward compatibility for API clients.
- **Check logic**: Schema diff compares modified schema Pydantic classes with their counterparts in the `base` commit.
  - *Violation Type*: Renaming or removing a required attribute in a schema file.

### Rule 2.6: Unindexed Foreign Keys
- **Definition**: Creating database relation columns without corresponding database indexes, leading to full table scans.
- **Check logic**: Parser checks Alembic migrations or SQLAlchemy models for missing `index=True` or `Index(...)` declarations on columns ending with `_id` or defined as Foreign Keys.
