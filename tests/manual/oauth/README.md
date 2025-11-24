# OAuth 2.1 Manual Test Scripts

Manual testing scripts for increment 7B OAuth provider flow.

## Prerequisites

1. **Start Redis:**
   ```bash
   redis-server
   ```

2. **Start FastAPI server:**
   ```bash
   cd "/Users/nadja/Desktop/Priority Guard Suite/priority-guardian"
   uvicorn backend.main:app --reload --port 8000
   ```

## Test Flow

### Step 1: Register OAuth Client

```bash
bash tests/manual/oauth/01_register_client.sh
```

**Expected Output:**
```json
{
  "client_id": "focused-client-XXXXXXXX",
  "client_secret": "YYYYYYYY",
  "redirect_uris": ["https://chatgpt.com/aip/callback"],
  "scope": "focused.read focused.write focused.notify"
}
```

Save the `client_id` for subsequent steps.

---

### Step 2: Generate PKCE Codes

```bash
bash tests/manual/oauth/02_generate_pkce.sh
```

**Expected Output:**
```
Verifier: XXXXXXXX
Challenge: YYYYYYYY
```

Save both values for the next steps.

---

### Step 3: Visit Authorization URL

**Manually construct the URL:**
```
http://localhost:8000/oauth/focused/authorize?response_type=code&client_id=<CLIENT_ID>&redirect_uri=https://chatgpt.com/aip/callback&code_challenge=<CODE_CHALLENGE>&code_challenge_method=S256&scope=focused.read%20focused.write&state=test123&user_id=00000000-0000-0000-0000-000000000001
```

1. Open URL in browser
2. Click "Allow" on consent screen
3. Copy the `code` parameter from redirect URL

---

### Step 4: Exchange Code for Tokens

**Update the script** with your authorization code and code_verifier, then run:

```bash
bash tests/manual/oauth/03_exchange_token.sh
```

**Expected Output:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "XXX...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": ["focused.read", "focused.write"]
}
```

Save the `access_token` and `refresh_token`.

**Verify JWT at jwt.io:**
- Paste access_token
- Check claims: sub, aud, iss, exp, iat, jti, scope, client_id

---

### Step 5: Refresh Token (Optional)

**Update the script** with your refresh_token, then run:

```bash
bash tests/manual/oauth/04_refresh_token.sh
```

**Expected Output:**
New access_token and refresh_token with updated expiration.

---

### Step 6: Revoke Token (Optional)

**Update the script** with your access_token, then run:

```bash
bash tests/manual/oauth/05_revoke_token.sh
```

**Expected Output:**
```json
{"success": true}
```

---

## Notes

- Authorization codes expire after **10 minutes**
- Access tokens expire after **1 hour**
- Refresh tokens expire after **30 days**
- All codes/tokens are **single-use** (except refresh tokens)

## Test User

Default test user ID: `00000000-0000-0000-0000-000000000001`

If this user doesn't exist in your database:
```sql
INSERT INTO core_users (id) VALUES ('00000000-0000-0000-0000-000000000001'::uuid);
```
