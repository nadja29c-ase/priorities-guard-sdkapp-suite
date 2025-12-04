PRIORITY GUARDIAN OAUTH PROVIDER
BACKEND AUTO TEST SUITE (IMPLEMENTATION SPEC)
TEST SUITE STRUCTURE

Test framework: pytest
Client: httpx.AsyncClient
Database: test DB with migrations applied
Redis: ephemeral test instance
Time control: monkeypatch datetime.utcnow() where needed

1. AUTHORIZATION CODE TESTS
1.1. Generate authorization code (Happy Path)

Given: valid GET /oauth/focused/authorize?client_id=x&redirect_uri=y&code_challenge=z&scope=abc
Expect:

Response = HTML/JSON with "authorization_code"

Code row stored in oauth_authorization_codes

code_challenge stored

expires_at ≈ now()+10min

1.2. Authorization Code – single use

Steps:

Exchange code once → expect 200

Exchange same code second time → expect 400 invalid_grant

DB: used = TRUE

1.3. Authorization Code – expired

Set expires_at = now() - 1s

Exchange → expect 400 invalid_grant + error "code_expired"

1.4. Authorization Code – PKCE mismatch

Send wrong code_verifier

Expect: 400 invalid_grant + pkce_mismatch

1.5. Authorization Code – redirect_uri mismatch

Create auth code with redirect_uri=A

Exchange with redirect_uri=B

Expect: 400 invalid_grant + redirect_uri_mismatch

2. TOKEN ENDPOINT TESTS
2.1. Authorization Code → Token (Happy Path)

POST /oauth/focused/token

Expect:

access_token is returned (JWT, RS256 signed)

refresh_token returned (opaque random)

DB: row in oauth_access_tokens stored

Claims: sub=user_id, scope, exp=1h

2.2. Refresh Token → New Access Token (Happy Path)

Inputs:

valid refresh_token for user

Expect:

New access token

New refresh token

Old refresh token marked revoked

New row appended in DB (rotation)

2.3. Refresh Token – expired

Set refresh_token_expires_at = now() - 1s

Expect:

400 invalid_grant + reason "refresh_token_expired"

2.4. Refresh Token – replay use

Steps:

Exchange refresh_token → works

Exchange same token again → expect 400 invalid_grant + reason "refresh_token_used"

2.5. Refresh Token – wrong client_id

Submit refresh_token with wrong client_id

Expect 401 invalid_client

3. TOKEN VALIDATION TESTS (JWT)
3.1. Valid access token → backend accepts

Call any protected endpoint using Authorization: Bearer <token>
Expect:

200

backend extracts user_id from sub

3.2. Expired access token

Set exp to past

Call protected endpoint
Expect:

401 Unauthorized

JSON includes WWW-Authenticate: Bearer error="invalid_token"

3.3. Tampered token signature

Change payload

Expect:

401 Unauthorized

error invalid_signature

3.4. Wrong kid (key rotation scenario)

Generate token signed with old key that is not in JWKS

Expect 401 unknown_kid

4. SCOPE ENFORCEMENT TESTS
4.1. check_calendar() requires focused.read

Token without focused.read → 403 Forbidden

Token with focused.read → 200

4.2. run_focus_mode() requires focused.write

Token with only focused.read → 403

Token with focused.write → 200

4.3. notify_user() requires focused.notify

Missing scope → 403

Correct scope → 200

5. REVOCATION TESTS
5.1. /oauth/focused/revoke revokes access + refresh tokens

Steps:

Have active access + refresh tokens

POST /oauth/focused/revoke
Expect:

DB: all revoked = TRUE for this user and client

access token no longer valid

refresh token no longer valid

5.2. Revoked access token → protected endpoint fails

Expect 401 invalid_token

5.3. Revoked refresh token → cannot refresh

Expect 400 invalid_grant

6. RATE LIMITING TESTS
6.1. /oauth/token – 5 requests / second

Make 6 quick requests

Expect 429 Too Many Requests for the 6th

6.2. /oauth/register – 10 requests / minute

Fire 11 requests

Expect 429 on 11th

6.3. /oauth/authorize – 20/min per user_id

Simulate 21 calls from same user

Expect temporary lock (your spec says 5 min)

Response = 429

7. SECURITY & ERROR PATH TESTS
7.1. Missing Authorization header

Call protected endpoint → expect:

401

WWW-Authenticate: Bearer realm="oauth"

7.2. Invalid Bearer prefix

Authorization: Token x instead of Bearer x
Expect:

401 invalid_request

7.3. Unknown client_id in /token

Expect:

401 invalid_client

7.4. Unknown client_id in /authorize

Expect:

400 invalid_client

7.5. Token exchange with missing fields

E.g.:

missing code_verifier

missing redirect_uri

missing grant_type

Expect:

400 invalid_request

8. JWKS ENDPOINT TESTS
8.1. GET /oauth/focused/jwks → returns valid JWKS

Expect:

JSON with keys: [...]

Each key contains: kty, kid, n, e, alg: RS256, use: sig

8.2. JWKS caching behavior

First call fetches JWKS

Second call uses cache (no network request)
(This is MCP-level, optional for backend.)

9. DATABASE STATE TESTS
9.1. Authorization code inserts correct row

Check:

user_id

client_id

scope

expires_at

redirect_uri

code_challenge

used = FALSE

9.2. Access token inserts correct row

Check:

encrypted refresh token stored

expires_at = now()+1h

jti unique

9.3. Revocation flips all rows for user+client

After /revoke:

oauth_access_tokens.revoked = TRUE

oauth_authorization_codes used or expired

core_connections.status = "revoked"

10. MISC SECURITY TESTS
10.1. Token issued for one client cannot be used for another

Simulate:

Register client A

Register client B

Token issued for A

Use token on B → expect 403

10.2. Non-HTTPS redirect rejected

Any redirect starting with “http://” → expect:

400 invalid_redirect_uri

OUTPUT FORMAT (Claude Implementation Instructions)

Claude should generate:

tests/oauth/test_authorization.py

tests/oauth/test_token.py

tests/oauth/test_refresh.py

tests/oauth/test_revocation.py

tests/oauth/test_scopes.py

tests/oauth/test_jwks.py

tests/oauth/test_ratelimits.py

tests/oauth/test_security.py

tests/oauth/test_db_state.py

Each test MUST:

use async httpx.AsyncClient against a test instance of the FastAPI app

use factory functions to create user, client, tokens

clean DB + Redis between tests