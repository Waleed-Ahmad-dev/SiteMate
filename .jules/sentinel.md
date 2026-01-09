## 2025-02-12 - Odoo ORM Concurrency and Caching
**Vulnerability:** A race condition exists in Odoo's `check_consumption` logic (TOCTOU). When multiple transactions try to consume a budget simultaneously, `SELECT ... FOR UPDATE` locks the database row but does NOT invalidate the Odoo ORM cache. This means the python code continues to use stale data read before the lock was acquired, leading to "double spend" where budget limits can be exceeded.

**Learning:** In Odoo, `SELECT ... FOR UPDATE` via direct SQL (`cr.execute`) is necessary for locking, but it is INSUFFICIENT for data consistency within the same transaction if the record was already accessed (prefetched). You MUST explicitly call `record.invalidate_recordset()` (Odoo 16+) or `record.invalidate_cache()` (older versions) immediately after acquiring the lock to force the ORM to re-read the fresh values from the database.

**Prevention:** Whenever implementing a critical check-then-act sequence in Odoo that relies on database state (like budget limits, inventory availability, or unique sequences), always pair row locking with explicit cache invalidation.

```python
# Acquire Lock
self.env.cr.execute("SELECT id FROM table WHERE id=%s FOR UPDATE", (record.id,))
# Invalidate Cache to see changes from other committed transactions
record.invalidate_recordset()
# Proceed with check
if record.value > limit:
    raise ...
```

## 2025-02-12 - Business Logic Bypass via API
**Vulnerability:** Critical business logic checks (like budget limits) were implemented only in the workflow methods (e.g., `account.move.action_post`) but not in the data model's `create`/`write` methods. This allows users with API access (like `xml-rpc` or `import` capabilities) or other modules to create records directly, bypassing the intended validations.

**Learning:** In Odoo, workflow buttons are merely "happy paths". Security constraints and data integrity rules must be enforced at the lowest level possible (the Model's `create`, `write`, `unlink` methods or SQL constraints) to prevent bypasses.

**Prevention:** Always identify the "invariant" of the model (e.g., "Consumption cannot exceed Budget") and enforce it in `api.constrains` or by overriding `create`/`write`. Workflow methods should handle the process, but the Model must defend its own integrity.
