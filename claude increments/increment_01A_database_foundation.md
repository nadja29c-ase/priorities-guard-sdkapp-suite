# Goal:
Set up the database layer for OAuth token storage.
No OAuth logic. No endpoints. No tools.

# Deliverable:
- DB engine + async session
- core_connections table
- Alembic migration
- AES-256 encryption
- Manual test script verifying encryption + DB insert/retrieve

# 1. Only create or modify the following files:
- backend/core/database.py
- backend/core/models.py
- backend/core/encryption.py
- alembic/env.py
- alembic/versions/001_create_core_connections.py
- backend/test_db.py

Do NOT modify any other files in the project.
Do NOT create OAuth code.
Do NOT modify routers or main.py.
Do NOT add new endpoints.

# 2. Required Dependencies
Add to pyproject.toml:

sqlalchemy = "^2.0.0"
alembic = "^1.13.0"
psycopg2-binary = "^2.9.9"
cryptography = "^43.0.0"

No other packages added in this increment.

# 3. Environment Variables (.env)
DATABASE_URL=postgresql://localhost/focused_dev
ENCRYPTION_KEY=<generated-from-fernet>

Generate ENCRYPTION_KEY:

from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())

# 4. Encryption Module (backend/core/encryption.py)
**Requirements**:
- Use cryptography.fernet.Fernet
- Load key from env

**Provide**:
def encrypt_token(token: str) -> str:
def decrypt_token(token: str) -> str:

Raise clear exceptions on invalid keys
Never print/log tokens.

# 5. Database Module (backend/core/database.py)
**Requirements**:
- Async SQLAlchemy engine (create_async_engine)
- Use DATABASE_URL from env

**Pool settings**:
pool_size=10
max_overflow=20

**Session factory**:
- AsyncSessionLocal = sessionmaker(...)
- Provide async def get_db(): generator for FastAPI future use
- Test connection on startup (simple engine.connect())

# 6. SQLAlchemy Model (backend/core/models.py)
**Model**: core_connections

**Columns**:

id → UUID primary key
server_default=text("gen_random_uuid()")

user_id → VARCHAR(255), NOT NULL

provider → VARCHAR(50), NOT NULL, CHECK in ('google','apple')

encrypted_access_token → TEXT NOT NULL

encrypted_refresh_token → TEXT (nullable)

token_expires_at → TIMESTAMPTZ NOT NULL

scopes → ARRAY(TEXT) NOT NULL

created_at → TIMESTAMPTZ, default NOW()

updated_at → TIMESTAMPTZ, default NOW()

**Constraints**:

UNIQUE (user_id, provider)

Index: (user_id, provider)

Index: token_expires_at

Use declarative base:

Base = declarative_base()

# 7. Alembic Setup
Step 1: Initialize
alembic init alembic

Step 2: Edit alembic/env.py
Import Base from backend.core.models
Set target_metadata = Base.metadata
Use asyncio migration setup per Alembic docs
Use DATABASE_URL from env

Step 3: Create migration
alembic revision --autogenerate -m "create core_connections"

Step 4: Apply
alembic upgrade head

Step 5: Verify
psql focused_dev -c "\d core_connections"

# 8. Manual Test Script (backend/test_db.py)
Write a small async script:
Test flow:
- Import AsyncSessionLocal, core_connections, encrypt_token, decrypt_token
- Create session
- Encrypt a test token
- Insert row
- Query row back
- Decrypt
- Assert decrypted == original
- Delete row
- Print only success message (no token values)

Run:
python -m backend.test_db

# 9. Technical Constraints
- All DB operations async
- No print() of tokens
- No logging of tokens
- Structured logging only
- Models and DB engine async-compatible
- Migrations must autogenerate correctly
- ENCRYPTION_KEY validated early

# 10. Success Criteria (Must All Pass)

✔ Database exists
✔ Alembic migration runs
✔ core_connections table present
✔ All constraints + indexes created
✔ encrypt_token / decrypt_token round-trip works
✔ You can insert encrypted token into DB
✔ You can read + decrypt it
✔ Manual test script completes successfully

# 11. Coding Style

Keep each file concise, minimal, and production-ready.

No placeholder functions.
No pseudo-code.
No TODOs.
No comments like "example".
All code must be fully runnable.

**Critical to remember when coding**: All database code must use SQLAlchemy async engine and AsyncSession.
Never use sync engine or synchronous session.
Use create_async_engine().
