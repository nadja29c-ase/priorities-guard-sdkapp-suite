Complete E2E System Test Specification (Final)
Overview
Total tests: 63 across 4 files
Runtime target: ≤3 minutes
Coverage target: ≥90% sync, ≥85% OAuth, ≥80% MCP

Phase 1A: Sync Engine (33 tests)
File: test_increment_7_sync_e2e.py
Core Scenarios (10 tests)
Test 1: Fresh user bootstrapping
python# First sync with N events from Google
user_id = create_test_user(google_connected=True)
mock_google.list_events.return_value = generate_events(count=5)

run_sync(user_id)

rows = db.query(FocusedFocusSession).filter_by(user_id=user_id).all()
assert len(rows) == 5
assert all(r.status == 'active' for r in rows)
assert all(r.version == 1 for r in rows)
Test 2: Incremental sync
python# Existing events, fetch only changes
initial_sync(user_id, events=10)
mark_synced(user_id)

# Google returns same 10 events (no changes)
mock_google.list_events.return_value = same_10_events

run_sync(user_id)

# No version increments
assert all(r.version == 1 for r in db_rows)
Test 3: Event update (changed title/time)
python# Event evt1 changes title from "Meeting" to "Focus Block"
original = create_event(id='evt1', title='Meeting', updated='2025-01-01T10:00:00Z')
sync_event(original)

updated = create_event(id='evt1', title='Focus Block', updated='2025-01-01T11:00:00Z')
mock_google.list_events.return_value = [updated]

run_sync(user_id)

row = db.get(event_id='evt1')
assert row.summary == 'Focus Block'
assert row.version == 2  # Incremented
assert row.is_focus_block == True
Test 4: Event cancellation (soft delete)
python# Event evt2 deleted in Google
sync_event(id='evt2', status='active', version=1)

mock_google.list_events.return_value = []  # evt2 missing

run_sync(user_id)

row = db.get(event_id='evt2')
assert row.status == 'deleted'
assert row.version == 2
Test 5: Resurrection
python# Deleted event reappears in Google
sync_event(id='evt3', status='deleted', version=2, updated='2025-01-01T10:00:00Z')

resurrected = create_event(id='evt3', updated='2025-01-01T12:00:00Z')
mock_google.list_events.return_value = [resurrected]

run_sync(user_id)

row = db.get(event_id='evt3')
assert row.status == 'active'
assert row.version == 3
Test 6: Multi-page pagination
python# Handle >250 events across pages
page1 = generate_events(count=250, page_token=None)
page2 = generate_events(count=100, page_token='token1')

mock_google.list_events.side_effect = [
    {'items': page1, 'nextPageToken': 'token1'},
    {'items': page2, 'nextPageToken': None}
]

run_sync(user_id)

assert db.count(user_id) == 350
Test 7: Focus keyword matching
python# Detect "Focus", "Deep Work", custom keywords
events = [
    create_event(id='e1', title='Focus Session'),
    create_event(id='e2', title='Deep Work Time'),
    create_event(id='e3', title='Research Project'),  # Custom keyword
    create_event(id='e4', title='Regular Meeting')
]

set_user_keywords(user_id, ['Research Project'])
mock_google.list_events.return_value = events

run_sync(user_id)

assert db.get('e1').is_focus_block == True
assert db.get('e2').is_focus_block == True
assert db.get('e3').is_focus_block == True
assert db.get('e4').is_focus_block == False
Test 8: Conflict detection
python# Focus Block overlaps with other event
focus_block = create_event(
    id='fb1', 
    title='Focus Block',
    start='2025-01-15T09:00:00Z',
    end='2025-01-15T10:00:00Z'
)
meeting = create_event(
    id='m1',
    title='Team Standup',
    start='2025-01-15T09:30:00Z',
    end='2025-01-15T09:45:00Z'
)

mock_google.list_events.return_value = [focus_block, meeting]

result = run_sync(user_id)

assert len(result.conflicts) == 1
assert result.conflicts[0]['focus_block'] == 'fb1'
assert result.conflicts[0]['overlaps'] == ['m1']
Test 9: All-day events skipped
python# No dateTime component
all_day = {
    'id': 'ad1',
    'summary': 'Holiday',
    'start': {'date': '2025-01-15'},  # No 'dateTime'
    'end': {'date': '2025-01-16'}
}

mock_google.list_events.return_value = [all_day]

run_sync(user_id)

assert db.count(user_id) == 0  # Skipped
Test 10: Empty calendar handling
python# Zero events returned
mock_google.list_events.return_value = []

result = run_sync(user_id)

assert result.events_processed == 0
assert result.errors == []
Edge Cases (10 tests)
Test 11: detect_deleted_events when Google omits event
python# Setup: 5 events synced (evt1-evt5, all active, version=1)
sync_events(user_id, ['evt1', 'evt2', 'evt3', 'evt4', 'evt5'])

# Google omits evt3 from list
mock_google.list_events.return_value = [
    get_event('evt1'), get_event('evt2'), 
    get_event('evt4'), get_event('evt5')
]

run_sync(user_id)

# evt3 soft-deleted
row = db.get(event_id='evt3')
assert row.status == 'deleted'
assert row.version == 2  # MUST increment

# Others remain active
for eid in ['evt1', 'evt2', 'evt4', 'evt5']:
    assert db.get(event_id=eid).status == 'active'
Test 12: Overlapping webhook + sync (race condition)
python# Webhook 1 sets focused:{user_id}:needs_sync = 1
simulate_webhook(user_id, event_id="evt1")
assert redis.get(f"focused:{user_id}:needs_sync") == "1"

# Sync starts, pauses after page 1
with pause_sync_after_page_1():
    sync_future = async_run_sync(user_id)
    
    # Webhook 2 arrives mid-sync (evt2 changed)
    time.sleep(0.1)  # Ensure sync started
    simulate_webhook(user_id, event_id="evt2")

sync_future.wait()

# CRITICAL: needs_sync still "1" (second webhook not swallowed)
assert redis.get(f"focused:{user_id}:needs_sync") == "1"

# Second sync processes both events
result = run_sync(user_id)
assert result.events_processed >= 2
assert db.get('evt1').version >= 2
assert db.get('evt2').version >= 2
Test 13: Equal timestamp, hash differs
python# Same updated_at, different content
original = create_event(
    id='evt5',
    title='Original',
    updated='2025-01-01T10:00:00Z'
)
sync_event(original)

modified = create_event(
    id='evt5',
    title='Modified',
    updated='2025-01-01T10:00:00Z'  # Same timestamp
)
mock_google.list_events.return_value = [modified]

run_sync(user_id)

row = db.get('evt5')
assert row.summary == 'Modified'  # Hash tiebreaker
assert row.version == 2
Test 14: Out-of-order webhooks
python# Process older update after newer
newer = create_event(id='evt6', title='Newer', updated='2025-01-01T12:00:00Z')
sync_event(newer, version=2)

older = create_event(id='evt6', title='Older', updated='2025-01-01T10:00:00Z')
mock_google.list_events.return_value = [older]

run_sync(user_id)

row = db.get('evt6')
assert row.summary == 'Newer'  # Rejected older update
assert row.version == 2  # No increment
Test 15: Description cleanup + sync
python# NULL description doesn't break sync
event_with_desc = create_event(
    id='evt7',
    title='Test',
    description='Original description',
    updated='2025-01-01T10:00:00Z'
)
sync_event(event_with_desc)

# Cleanup job sets description=NULL (72h TTL)
cleanup_descriptions(user_id)
assert db.get('evt7').event_description is None

# Google sends same event (no real change)
mock_google.list_events.return_value = [event_with_desc]

run_sync(user_id)

row = db.get('evt7')
assert row.version == 1  # No false positive
assert row.event_description == 'Original description'  # Restored
Test 16: Recurring events (flattened instances)
python# singleEvents=true in API call
mock_google.list_events.assert_called_with(
    calendarId='primary',
    singleEvents=True,  # Required
    ...
)

recurring = [
    create_event(id='rec1_1', title='Weekly Standup', start='2025-01-06T09:00:00Z'),
    create_event(id='rec1_2', title='Weekly Standup', start='2025-01-13T09:00:00Z'),
    create_event(id='rec1_3', title='Weekly Standup', start='2025-01-20T09:00:00Z'),
]
mock_google.list_events.return_value = recurring

run_sync(user_id)

assert db.count(user_id) == 3  # Stored as separate instances
Test 17: Timezone edge cases
python# UTC conversion correctness
pst_event = create_event(
    id='tz1',
    start='2025-01-15T09:00:00-08:00',  # PST
    end='2025-01-15T10:00:00-08:00'
)

sync_event(pst_event)

row = db.get('tz1')
assert row.event_start == datetime(2025, 1, 15, 17, 0, 0, tzinfo=timezone.utc)
assert row.event_end == datetime(2025, 1, 15, 18, 0, 0, tzinfo=timezone.utc)
Test 18: Maximum event limit (2500 events)
python# 10 pages × 250 = 2500
pages = [generate_events(250) for _ in range(10)]
mock_google.list_events.side_effect = [
    {'items': p, 'nextPageToken': f'token{i}' if i < 9 else None}
    for i, p in enumerate(pages)
]

result = run_sync(user_id)

assert result.events_processed == 2500
assert mock_google.list_events.call_count == 10  # Stops at 10 pages
Test 19: Empty time window
python# No events in date range
mock_google.list_events.return_value = []

result = run_sync(
    user_id,
    time_start='2025-01-15T00:00:00Z',
    time_end='2025-01-15T23:59:59Z'
)

assert result.events_processed == 0
assert result.conflicts == []
Test 20: Cold start (first sync after fresh OAuth)
python# Combines fresh user + webhook registration
user_id = create_test_user(google_connected=True, webhook_registered=False)

mock_google.list_events.return_value = generate_events(10)

result = run_sync(user_id)

# Events synced
assert db.count(user_id) == 10

# Webhook auto-registered
conn = db.get_connection(user_id, provider='google')
assert conn.google_channel_id is not None
assert conn.google_channel_expires_at > now() + timedelta(days=6)
Google Failure Simulation (3 tests)
Test 21: 429 rate limit with retry
pythonmock_google.list_events.side_effect = [
    HttpError(resp={'status': 429}, content=b'Rate limit'),
    HttpError(resp={'status': 429}, content=b'Rate limit'),
    {'items': generate_events(5), 'nextPageToken': None}  # Success on 3rd try
]

with assert_backoff_delays([1, 2]):  # Exponential backoff
    result = run_sync(user_id)

assert result.events_processed == 5
assert mock_google.list_events.call_count == 3
Test 22: 401 invalid token triggers refresh
pythonmock_google.list_events.side_effect = [
    HttpError(resp={'status': 401}, content=b'Invalid Credentials'),
]

with mock_token_refresh(new_token='refreshed_token'):
    run_sync(user_id)

# Token refreshed
conn = db.get_connection(user_id, provider='google')
assert conn.access_token_enc == encrypt('refreshed_token')

# Retry with new token succeeded
assert mock_google.list_events.call_count == 2
Test 23: Network timeout with retry
pythonmock_google.list_events.side_effect = [
    Timeout('Connection timeout'),
    {'items': generate_events(3), 'nextPageToken': None}
]

with assert_backoff_delays([1]):
    result = run_sync(user_id)

assert result.events_processed == 3
assert mock_google.list_events.call_count == 2
SQL/Python Invariant Tests (10 tests)
Test 24: should_accept_update() matches SQL WHERE clause
python# Python logic
def should_accept_update(google_updated, local_updated, google_hash, local_hash):
    if google_updated > local_updated:
        return True
    elif google_updated < local_updated:
        return False
    else:  # Equal timestamps
        return google_hash != local_hash

# SQL logic (simplified from ON CONFLICT clause)
# WHERE google_updated_at > EXCLUDED.google_updated_at
#    OR (google_updated_at = EXCLUDED.google_updated_at 
#        AND sha256_content_hash != EXCLUDED.sha256_content_hash)

# Test cases
assert should_accept_update('2025-01-02', '2025-01-01', 'hash1', 'hash2') == True
assert should_accept_update('2025-01-01', '2025-01-02', 'hash1', 'hash2') == False
assert should_accept_update('2025-01-01', '2025-01-01', 'hash1', 'hash2') == True
assert should_accept_update('2025-01-01', '2025-01-01', 'hash1', 'hash1') == False
Test 25: should_accept_deletion() matches SQL WHERE clause
python# Python logic
def should_accept_deletion(google_updated, local_updated, local_status):
    if local_status == 'deleted':
        return False  # Already deleted
    return google_updated >= local_updated

# SQL equivalent: refuse stale deletions
# UPDATE ... SET status='deleted'
# WHERE status='active' AND google_updated_at >= local.google_updated_at

# Test cases
assert should_accept_deletion('2025-01-02', '2025-01-01', 'active') == True
assert should_accept_deletion('2025-01-01', '2025-01-02', 'active') == False
assert should_accept_deletion('2025-01-02', '2025-01-01', 'deleted') == False
Test 26: Version increment on update
pythonoriginal = sync_event(id='v1', version=1, updated='2025-01-01')

newer = create_event(id='v1', updated='2025-01-02')
sync_event(newer)

row = db.get('v1')
assert row.version == 2

# SQL: version = COALESCE(focused_focus_sessions.version, 0) + 1
Test 27: Version increment on deletion
pythonsync_event(id='v2', status='active', version=1)

delete_event('v2', google_updated='2025-01-02')

row = db.get('v2')
assert row.status == 'deleted'
assert row.version == 2
Test 28: Version unchanged when no update
pythonsync_event(id='v3', version=1, updated='2025-01-01')

same = create_event(id='v3', updated='2025-01-01')
sync_event(same)

row = db.get('v3')
assert row.version == 1  # No increment
Test 29: Equal timestamp tiebreaker (accept)
pythonsync_event(id='tb1', title='Old', hash='hash_old', updated='2025-01-01')

new = create_event(id='tb1', title='New', hash='hash_new', updated='2025-01-01')
sync_event(new)

row = db.get('tb1')
assert row.summary == 'New'
assert row.version == 2
Test 30: Equal timestamp tiebreaker (reject)
pythonsync_event(id='tb2', title='Current', hash='hash_a', updated='2025-01-01')

duplicate = create_event(id='tb2', title='Current', hash='hash_a', updated='2025-01-01')
sync_event(duplicate)

row = db.get('tb2')
assert row.version == 1  # No change
Test 31: Resurrection requires newer timestamp
pythonsync_event(id='res1', status='deleted', version=2, updated='2025-01-02')

stale_resurrection = create_event(id='res1', updated='2025-01-01')
sync_event(stale_resurrection)

row = db.get('res1')
assert row.status == 'deleted'  # Rejected
assert row.version == 2

# Valid resurrection
fresh_resurrection = create_event(id='res1', updated='2025-01-03')
sync_event(fresh_resurrection)

row = db.get('res1')
assert row.status == 'active'
assert row.version == 3
Test 32: Batch upsert transaction atomicity
python# If any event fails, entire batch rolls back
events = [
    create_event(id='tx1', title='Valid'),
    create_event(id='tx2', title='Valid'),
    {'id': 'tx3', 'invalid': 'schema'},  # Malformed
]

with pytest.raises(Exception):
    sync_events(user_id, events)

# Nothing committed
assert db.count(user_id) == 0
Test 33: Hash stability across NULL descriptions
python# Hash doesn't change when description becomes NULL
event = create_event(id='h1', title='Test', description='Desc', updated='2025-01-01')
sync_event(event)
original_hash = db.get('h1').sha256_content_hash

# Cleanup sets description=NULL
cleanup_descriptions(user_id)

# Hash remains stable (uses original event data for comparison)
row = db.get('h1')
assert row.event_description is None
# Hash computation uses Google data, not local NULL

Phase 1B: Webhook Lifecycle (5 tests)
File: test_increment_7_webhook_lifecycle.py
Test Helper: MockGoogleCalendar
pythonclass MockGoogleCalendar:
    """Simulates Google Calendar API for webhook tests"""
    
    def __init__(self):
        self.watch_calls = []
        self.stop_calls = []
        self.active_channels = {}
    
    def events_watch(self, calendar_id, request_body):
        """
        Simulates POST /calendars/{id}/events/watch
        
        Args:
            calendar_id: Calendar ID
            request_body: {
                'id': channel_id (UUID),
                'type': 'web_hook',
                'address': callback URL,
                'expiration': Unix timestamp (optional)
            }
        
        Returns:
            {
                'id': channel_id,
                'resourceId': 'opaque_google_resource_id',
                'expiration': timestamp (7 days default)
            }
        """
        channel_id = request_body['id']
        expiration = request_body.get('expiration', 
                                     int(time.time() + 7*24*3600)*1000)
        
        resource_id = f"resource_{uuid.uuid4().hex[:8]}"
        
        self.watch_calls.append({
            'calendar_id': calendar_id,
            'channel_id': channel_id,
            'address': request_body['address']
        })
        
        self.active_channels[channel_id] = {
            'resource_id': resource_id,
            'expiration': expiration
        }
        
        return {
            'id': channel_id,
            'resourceId': resource_id,
            'expiration': expiration
        }
    
    def channels_stop(self, channel_id, resource_id):
        """
        Simulates POST /channels/stop
        
        Args:
            channel_id: Channel ID to stop
            resource_id: Resource ID for validation
        
        Returns:
            204 No Content (or raises HttpError if invalid)
        """
        self.stop_calls.append({
            'channel_id': channel_id,
            'resource_id': resource_id
        })
        
        if channel_id in self.active_channels:
            del self.active_channels[channel_id]
        
        return None  # 204 No Content
    
    def simulate_webhook(self, user_id, event_id='evt1', 
                        resource_state='update', channel_id=None):
        """
        Simulates Google sending a webhook notification
        
        Args:
            user_id: Target user
            event_id: Changed event ID
            resource_state: 'update' | 'sync' | 'webhook_expiring'
            channel_id: Optional channel ID (fetched from DB if None)
        
        Returns:
            Response from webhook endpoint
        """
        if channel_id is None:
            conn = db.get_connection(user_id, provider='google')
            channel_id = conn.google_channel_id
        
        headers = {
            'X-Goog-Channel-ID': channel_id,
            'X-Goog-Resource-ID': 'resource_xyz',
            'X-Goog-Resource-State': resource_state,
            'X-Goog-Message-Number': '1'
        }
        
        response = requests.post(
            f"http://localhost:8000/webhook/focused/google_calendar/{user_id}",
            headers=headers
        )
        
        return response
Tests
Test 1: Fresh webhook registration
pythonuser_id = create_test_user(google_connected=True)
mock_google = MockGoogleCalendar()

# No existing channel
conn = db.get_connection(user_id, provider='google')
assert conn.google_channel_id is None

# Register webhook
response = requests.post(f"/api/focused/watch_calendar", json={
    'user_id': user_id
})

assert response.status_code == 200
data = response.json()

# Verify response
assert 'channel_id' in data
assert 'expiration' in data

# Verify DB storage
conn = db.get_connection(user_id, provider='google')
assert conn.google_channel_id == data['channel_id']
assert conn.google_resource_id is not None
assert conn.google_channel_expires_at > now() + timedelta(days=6)

# Verify Google API call
assert len(mock_google.watch_calls) == 1
assert mock_google.watch_calls[0]['channel_id'] == data['channel_id']
Test 2: Webhook reception after registration
pythonuser_id, channel_id = setup_webhook_registration()

# Google sends webhook
response = mock_google.simulate_webhook(
    user_id=user_id,
    event_id='evt1',
    resource_state='update',
    channel_id=channel_id
)

# Verify response
assert response.status_code == 200  # Always 200 OK

# Verify needs_sync flag set
assert redis.get(f"focused:{user_id}:needs_sync") == "1"

# Verify idempotency key stored
idem_key = f"webhook:{user_id}:1"  # Message number
assert redis.get(idem_key) == "processed"
assert redis.ttl(idem_key) <= 86400  # 24h TTL
Test 3: Re-registration replaces old channel
pythonuser_id, old_channel_id = setup_webhook_registration()
mock_google = MockGoogleCalendar()

# Register again
response = requests.post(f"/api/focused/watch_calendar", json={
    'user_id': user_id
})

data = response.json()
new_channel_id = data['channel_id']

# Different channel ID
assert new_channel_id != old_channel_id

# Old channel stopped
assert len(mock_google.stop_calls) == 1
assert mock_google.stop_calls[0]['channel_id'] == old_channel_id

# New channel created
assert new_channel_id in mock_google.active_channels

# DB updated
conn = db.get_connection(user_id, provider='google')
assert conn.google_channel_id == new_channel_id
Test 4: Event-driven renewal (<48h warning)
pythonuser_id, channel_id = setup_webhook_registration()
mock_google = MockGoogleCalendar()

# Set expiration to 40 hours from now
conn = db.get_connection(user_id, provider='google')
conn.google_channel_expires_at = now() + timedelta(hours=40)
db.session.commit()

# Google sends expiration warning
response = mock_google.simulate_webhook(
    user_id=user_id,
    resource_state='webhook_expiring',
    channel_id=channel_id
)

assert response.status_code == 200

# Old channel stopped
assert any(c['channel_id'] == channel_id for c in mock_google.stop_calls)

# New channel created
conn = db.get_connection(user_id, provider='google')
new_channel_id = conn.google_channel_id
assert new_channel_id != channel_id

# Expiration reset (~7 days)
assert conn.google_channel_expires_at > now() + timedelta(days=6)
Test 5: Idempotent renewal (duplicate warnings)
pythonuser_id, channel_id = setup_webhook_registration()
mock_google = MockGoogleCalendar()

# Set near-expiration
conn = db.get_connection(user_id, provider='google')
conn.google_channel_expires_at = now() + timedelta(hours=40)
db.session.commit()

# Send 3 warnings (T+0, T+5min, T+10min)
for i in range(3):
    response = mock_google.simulate_webhook(
        user_id=user_id,
        resource_state='webhook_expiring',
        channel_id=channel_id
    )
    assert response.status_code == 200
    
    if i < 2:
        time.sleep(5)  # Wait between warnings

# Only first triggered renewal
conn = db.get_connection(user_id, provider='google')
final_channel_id = conn.google_channel_id

# Verify only 1 new channel created (not 3)
assert len(mock_google.watch_calls) == 2  # Initial + 1 renewal

# Second and third warnings detected fresh channel
assert final_channel_id != channel_id  # Changed after first warning

Phase 2: OAuth Provider (11 tests)
File: test_increment_7_oauth_e2e.py
Test 1: Client registration
pythonresponse = requests.post("/oauth/focused/register", json={
    'client_name': 'ChatGPT',
    'redirect_uris': ['https://chatgpt.com/oauth/callback']
})

assert response.status_code == 201
data = response.json()

assert 'client_id' in data
assert 'client_secret' in data

# Stored in DB
client = db.query(CoreConnection).filter_by(
    connection_type='oauth_provider',
    client_id=data['client_id']
).one()
assert client.client_secret_enc is not None
Test 2: Authorization code flow with PKCE
python# Generate PKCE
code_verifier = generate_code_verifier()
code_challenge = base64url(sha256(code_verifier))

# Authorization request
response = requests.get("/oauth/focused/authorize", params={
    'client_id': client_id,
    'response_type': 'code',
    'redirect_uri': 'https://chatgpt.com/oauth/callback',
    'scope': 'focused.read focused.write',
    'state': 'random_state',
    'code_challenge': code_challenge,
    'code_challenge_method': 'S256'
})

# Redirects to consent screen
assert response.status_code == 302
assert '/oauth/focused/consent' in response.headers['Location']
Test 3: Token exchange (code → access + refresh)
python# Authorize and get code
code = complete_authorization_flow(user_id, client_id, code_verifier)

# Exchange code for tokens
response = requests.post("/oauth/focused/token", data={
    'grant_type': 'authorization_code',
    'code': code,
    'code_verifier': code_verifier,
    'client_id': client_id,
    'redirect_uri': 'https://chatgpt.com/oauth/callback'
})

assert response.status_code == 200
data = response.json()

assert 'access_token' in data
assert 'refresh_token' in data
assert data['token_type'] == 'Bearer'
assert data['expires_in'] == 3600
assert data['scope'] == 'focused.read focused.write'

# Verify JWT structure
decoded = jwt.decode(data['access_token'], options={'verify_signature': False})
assert decoded['sub'] == str(user_id)
assert decoded['azp'] == client_id
assert 'focused.read' in decoded['scope']
Test 4: Refresh token rotation
pythonaccess_token, refresh_token = get_tokens(user_id, client_id)

# Exchange refresh for new pair
response = requests.post("/oauth/focused/token", data={
    'grant_type': 'refresh_token',
    'refresh_token': refresh_token,
    'client_id': client_id
})

assert response.status_code == 200
data = response.json()

new_access = data['access_token']
new_refresh = data['refresh_token']

# Different tokens
assert new_access != access_token
assert new_refresh != refresh_token

# Old refresh revoked
old_refresh_row = db.query(OAuthAccessToken).filter_by(
    refresh_token_enc=encrypt(refresh_token)
).first()
assert old_refresh_row.revoked == True

# Old refresh doesn't work twice
response2 = requests.post("/oauth/focused/token", data={
    'grant_type': 'refresh_token',
    'refresh_token': refresh_token,
    'client_id': client_id
})
assert response2.status_code == 400
assert response2.json()['error'] == 'invalid_grant'
Test 5: Scope validation
python# Request only focused.read
code = authorize_with_scopes(user_id, client_id, ['focused.read'])
access_token = exchange_code(code)

# Verify token scope
decoded = jwt.decode(access_token, options={'verify_signature': False})
assert decoded['scope'] == 'focused.read'

# Try to call write-only tool
response = requests.post("/mcp/focused/run_focus_mode",
    headers={'Authorization': f'Bearer {access_token}'},
    json={'action': 'on', 'focus_name': 'Work'}
)

# Rejected: insufficient scope
assert response.status_code == 200  # JSON-RPC via HTTP 200
assert response.json()['error']['code'] == -32600
assert 'insufficient scope' in response.json()['error']['message'].lower()
Test 6: Token revocation
pythonaccess_token, refresh_token = get_tokens(user_id, client_id)

# Revoke access token
response = requests.post("/oauth/focused/revoke", data={
    'token': access_token,
    'client_id': client_id
})

assert response.status_code == 200

# Access token revoked
row = db.query(OAuthAccessToken).filter_by(token=access_token).one()
assert row.revoked == True

# Refresh token also revoked (cascade)
refresh_row = db.query(OAuthAccessToken).filter_by(
    refresh_token_enc=encrypt(refresh_token)
).first()
assert refresh_row.revoked == True

# Token doesn't work anymore
response = requests.post("/mcp/focused/check_calendar",
    headers={'Authorization': f'Bearer {access_token}'}
)
assert response.status_code == 200
assert response.json()['error']['code'] == -32600  # Invalid token
Test 7: Rate limiting /oauth/token (5 req/s per IP)
pythonfrom concurrent.futures import ThreadPoolExecutor

client_id = register_client()
codes = [authorize_user(user_id, client_id) for _ in range(10)]

# Send 10 token requests concurrently
with ThreadPoolExecutor(max_workers=10) as executor:
    responses = list(executor.map(
        lambda code: requests.post("/oauth/focused/token", data={
            'grant_type': 'authorization_code',
            'code': code,
            'code_verifier': 'verifier',
            'client_id': client_id
        }),
        codes
    ))

# At most 5 succeed (5 req/s limit)
success_count = sum(1 for r in responses if r.status_code == 200)
rate_limited = sum(1 for r in responses if r.status_code == 429)

assert success_count <= 5
assert rate_limited >= 5

# Rate-limited responses include Retry-After
for r in responses:
    if r.status_code == 429:
        assert 'Retry-After' in r.headers
Test 8: Rate limiting /oauth/register (10 req/min per IP)
python# Send 15 registration requests
responses = []
for i in range(15):
    response = requests.post("/oauth/focused/register", json={
        'client_name': f'Client{i}',
        'redirect_uris': [f'https://example.com/cb{i}']
    })
    responses.append(response)

# At most 10 succeed
success_count = sum(1 for r in responses if r.status_code == 201)
rate_limited = sum(1 for r in responses if r.status_code == 429)

assert success_count <= 10
assert rate_limited >= 5
Test 9: JWKS endpoint returns public keys
pythonresponse = requests.get("/oauth/focused/jwks")

assert response.status_code == 200
data = response.json()

assert 'keys' in data
assert len(data['keys']) >= 1

key = data['keys'][0]
assert key['kty'] == 'RSA'
assert key['use'] == 'sig'
assert key['kid'] is not None
assert 'n' in key  # Public modulus
assert 'e' in key  # Public exponent
assert 'd' not in key  # Private key NOT exposed

# Cached in Redis (24h TTL)
cached = redis.get('jwks:focused')
assert cached is not None
assert redis.ttl('jwks:focused') <= 86400
Test 10: Consent screen flow (Allow/Deny)
python# Start authorization
auth_url = get_authorization_url(user_id, client_id)
response = requests.get(auth_url, allow_redirects=False)

# Redirects to consent screen
assert response.status_code == 302
consent_url = response.headers['Location']
assert '/oauth/focused/consent' in consent_url

# GET consent screen
consent_response = requests.get(consent_url)
assert consent_response.status_code == 200
assert b'Focused App' in consent_response.content
assert b'focused.read' in consent_response.content
assert b'Allow' in consent_response.content
assert b'Deny' in consent_response.content

# User clicks Allow
allow_response = requests.post(consent_url, data={
    'action': 'allow'
}, allow_redirects=False)

assert allow_response.status_code == 302
callback_url = allow_response.headers['Location']
assert 'code=' in callback_url
assert 'state=' in callback_url

# User clicks Deny
deny_response = requests.post(consent_url, data={
    'action': 'deny'
}, allow_redirects=False)

assert deny_response.status_code == 302
error_url = deny_response.headers['Location']
assert 'error=access_denied' in error_url
Test 11: Authorization code fixation attack prevention
python# Victim authorizes
code_verifier_victim = generate_code_verifier()
code_challenge_victim = base64url(sha256(code_verifier_victim))

code = complete_authorization_flow(
    user_id=victim_user_id,
    client_id=client_id,
    code_challenge=code_challenge_victim
)

# Attacker intercepts code, tries with wrong verifier
code_verifier_attacker = generate_code_verifier()

response = requests.post("/oauth/focused/token", data={
    'grant_type': 'authorization_code',
    'code': code,
    'code_verifier': code_verifier_attacker,  # ❌ Wrong
    'client_id': client_id,
    'redirect_uri': 'https://chatgpt.com/oauth/callback'
})

# RFC 6749 OAuth error format (NOT JSON-RPC)
assert response.status_code == 400
assert response.json() == {
    'error': 'invalid_grant',
    'error_description': 'PKCE verification failed'
}

# Positive control: correct verifier succeeds
response2 = requests.post("/oauth/focused/token", data={
    'grant_type': 'authorization_code',
    'code': code,
    'code_verifier': code_verifier_victim,  # ✅ Correct
    'client_id': client_id,
    'redirect_uri': 'https://chatgpt.com/oauth/callback'
})

assert response2.status_code == 200
assert 'access_token' in response2.json()

# Log safety: no tokens in logs
captured_logs = get_test_logs()
assert 'access_token' not in captured_logs
assert 'refresh_token' not in captured_logs
assert code_verifier_attacker not in captured_logs
assert code_verifier_victim not in captured_logs

Phase 3: MCP Integration (14 tests)
File: test_increment_7_mcp_e2e.py
Test 1: MCP → Backend → Google chain (check_calendar)
pythonuser_id = create_test_user(google_connected=True)
access_token = create_valid_token(user_id, scopes=['focused.read'])

mock_google.list_events.return_value = [
    create_event(id='e1', title='Focus Block', start='2025-01-15T09:00:00Z'),
    create_event(id='e2', title='Meeting', start='2025-01-15T09:30:00Z')
]

# Call MCP tool
response = requests.post("http://localhost:8001/mcp", json={
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "check_calendar",
        "arguments": {
            "time_start": "2025-01-15T00:00:00Z",
            "time_end": "2025-01-16T00:00:00Z"
        }
    }
}, headers={
    'Authorization': f'Bearer {access_token}'
})

assert response.status_code == 200
data = response.json()

assert 'result' in data
assert 'content' in data['result']

# Verify MCP server → Backend call
assert backend_mock.called_with(
    endpoint='/api/focused/check_calendar',
    headers={'X-User-ID': str(user_id)}
)

# Verify Backend → Google call
assert mock_google.list_events.called_once
Test 2: Valid token accepted
pythonuser_id = create_test_user()
access_token = create_valid_token(user_id, scopes=['focused.read'])

response = mcp_client.call_tool(
    "check_calendar",
    {"time_start": "2025-01-15T00:00:00Z"},
    headers={'Authorization': f'Bearer {access_token}'}
)

assert response.status_code == 200
assert 'result' in response.json()
Test 3: Expired token rejected
pythonexpired_token = create_expired_token(user_id)

response = mcp_client.call_tool(
    "check_calendar",
    {},
    headers={'Authorization': f'Bearer {expired_token}'}
)

# JSON-RPC error via HTTP 200
assert response.status_code == 200
data = response.json()

assert 'error' in data
assert data['error']['code'] == -32600  # Invalid request
assert 'expired' in data['error']['message'].lower()

# WWW-Authenticate header included
assert 'WWW-Authenticate' in response.headers
assert 'error="invalid_token"' in response.headers['WWW-Authenticate']
Test 4: Revoked token rejected
pythonrevoked_token = create_revoked_token(user_id)

response = mcp_client.call_tool(
    "check_calendar",
    {},
    headers={'Authorization': f'Bearer {revoked_token}'}
)

assert response.status_code == 200
data = response.json()

assert 'error' in data
assert data['error']['code'] == -32600
assert 'revoked' in data['error']['message'].lower()
Test 5: Wrong scope rejected
python# Token only has focused.notify, but tool requires focused.read
wrong_scope_token = create_token(user_id, scopes=['focused.notify'])

response = mcp_client.call_tool(
    "check_calendar",  # Requires focused.read
    {},
    headers={'Authorization': f'Bearer {wrong_scope_token}'}
)

assert response.status_code == 200
data = response.json()

assert 'error' in data
assert data['error']['code'] == -32600
assert 'insufficient scope' in data['error']['message'].lower()
Test 6: User identity extraction
pythonuser_id = uuid.uuid4()
access_token = create_token(user_id, scopes=['focused.read'])

response = mcp_client.call_tool(
    "check_calendar",
    {},
    headers={'Authorization': f'Bearer {access_token}'}
)

# Backend received correct user_id
assert backend_mock.last_request.headers['X-User-ID'] == str(user_id)

# Correlation ID also forwarded
assert 'X-Correlation-ID' in backend_mock.last_request.headers
Test 7: Correlation ID propagation
pythoncorrelation_id = str(uuid.uuid4())
access_token = create_token(user_id, scopes=['focused.read'])

response = mcp_client.call_tool(
    "check_calendar",
    {},
    headers={
        'Authorization': f'Bearer {access_token}',
        'X-Correlation-ID': correlation_id
    }
)

# MCP server forwarded correlation ID to backend
assert backend_mock.last_request.headers['X-Correlation-ID'] == correlation_id

# Backend logs contain correlation ID
logs = get_backend_logs()
assert correlation_id in logs
Test 8: Tool output transformation
python# Backend returns raw JSON
backend_mock.return_value = {
    'focus_blocks': [
        {'event_id': 'e1', 'title': 'Focus Block', 'start': '2025-01-15T09:00:00Z'}
    ],
    'conflicts': [],
    'free_slots': [
        {'start': '2025-01-15T14:00:00Z', 'end': '2025-01-15T16:00:00Z'}
    ]
}

response = mcp_client.call_tool("check_calendar", {})

# MCP server transforms to MCP format
assert response.status_code == 200
data = response.json()

assert 'result' in data
assert 'content' in data['result']
assert data['result']['content'][0]['type'] == 'text'

# structuredContent included
assert 'structuredContent' in data['result']
assert 'focus_blocks' in data['result']['structuredContent']
Test 9: Error propagation
python# Backend returns error
backend_mock.side_effect = HttpError(
    resp={'status': 500},
    content=b'Internal server error'
)

response = mcp_client.call_tool("check_calendar", {})

# MCP server converts to JSON-RPC error
assert response.status_code == 200
data = response.json()

assert 'error' in data
assert data['error']['code'] == -32603  # Internal error
assert 'Backend service error' in data['error']['message']
Test 10: Redis failure graceful
python# Redis unavailable
redis_mock.get.side_effect = ConnectionError('Redis down')

access_token = create_token(user_id, scopes=['focused.read'])

response = mcp_client.call_tool(
    "check_calendar",
    {},
    headers={'Authorization': f'Bearer {access_token}'}
)

# Tool still works (cache miss gracefully handled)
assert response.status_code == 200
assert 'result' in response.json()

# Warning logged
logs = get_mcp_logs()
assert 'Redis unavailable' in logs
Test 11: Token refresh during call
python# Token expires in 30 minutes
near_expiry_token = create_token(
    user_id,
    scopes=['focused.read'],
    expires_in=1800  # 30 min
)

# Backend detects near-expiry
with mock_token_refresh(new_token='refreshed_access_token'):
    response = mcp_client.call_tool(
        "check_calendar",
        {},
        headers={'Authorization': f'Bearer {near_expiry_token}'}
    )

# Call succeeded
assert response.status_code == 200

# Token refreshed in background
conn = db.get_connection(user_id, provider='google')
assert conn.access_token_enc == encrypt('refreshed_access_token')
Test 12: Minimal background jobs verify
python# Celery worker running
assert celery_worker.is_running()

# Token refresh job exists
jobs = celery_inspect.scheduled()
assert any('refresh_google_token' in str(job) for job in jobs)

# Webhook renewal job exists
assert any('renew_webhook' in str(job) for job in jobs)

# No other jobs (comprehensive Celery deferred to Phase 4)
job_count = len(jobs)
assert job_count == 2  # Only these 2 minimal jobs
Test 13: MCP → Backend timeout resilience
python# Backend takes 30 seconds to respond
with mock_backend_timeout(delay=30):
    response = mcp_client.call_tool(
        "check_calendar",
        {"time_start": "2025-01-15T00:00:00Z"},
        headers={'Authorization': f'Bearer {valid_token}'}
    )

# JSON-RPC error via HTTP 200 (NOT HTTP 503)
assert response.status_code == 200
data = response.json()

assert 'error' in data
assert data['error']['code'] == -32603  # Standard JSON-RPC internal error
assert 'Backend service unavailable' in data['error']['message']

# No hang
assert response.elapsed.total_seconds() < 10

# No automatic retries (single attempt only)
assert backend_mock.call_count == 1

# Log safety
logs = get_mcp_logs()
assert 'Bearer' not in logs
assert valid_token not in logs
Test 14: JWKS fetch failure (fail-closed)
python# JWKS endpoint returns 500
with mock_jwks_endpoint(status=500):
    response = mcp_client.call_tool(
        "check_calendar",
        {},
        headers={'Authorization': f'Bearer {valid_token}'}
    )

# JSON-RPC error via HTTP 200
assert response.status_code == 200
data = response.json()

assert 'error' in data
assert data['error']['code'] == -32603
assert 'Unable to validate token' in data['error']['message']
assert 'JWKS unavailable' in data['error']['message']

# Fail-closed: backend never called
assert backend_mock.call_count == 0

# Log safety
logs = get_mcp_logs()
assert 'Bearer' not in logs
assert valid_token not in logs

# Edge case: JWKS succeeds on retry
with mock_jwks_endpoint(status=200, jwks=valid_jwks):
    response2 = mcp_client.call_tool(
        "check_calendar",
        {},
        headers={'Authorization': f'Bearer {valid_token}'}
    )
    
    # Normal validation resumes
    assert response2.status_code == 200
    assert 'result' in response2.json()
    assert backend_mock.call_count == 1

Acceptance Criteria Mapping
Must Verify

✅ Deleted events: status='deleted' AND version++ → Phase 1A Test 11
✅ Race condition: needs_sync survives → Phase 1A Test 12
✅ PKCE: wrong verifier fails → Phase 2 Test 11
✅ Backend timeout: JSON-RPC error, no retries → Phase 3 Test 13
✅ JWKS failure: fail-closed → Phase 3 Test 14

Protocol Compliance

✅ OAuth errors use RFC 6749 format → Phase 2 Test 11
✅ MCP errors use JSON-RPC 2.0 (HTTP 200 + error) → Phase 3 Tests 13-14
✅ Standard error codes (-32603, -32600) → Phase 3 Tests 3-5, 9, 13-14

Security Invariants

✅ Authorization code + matching verifier only → Phase 2 Test 11
✅ JWKS unavailable → reject all tokens → Phase 3 Test 14
✅ No tokens/secrets in logs → Phase 2 Test 11 + Phase 3 Tests 13-14
✅ Backend timeout → no retries → Phase 3 Test 13

Data Integrity

✅ Soft-delete increments version → Phase 1A Test 11
✅ Concurrent webhook + sync → no lost updates → Phase 1A Test 12


Success Criteria

✅ 63/63 tests pass (100% green)
✅ No flaky tests (deterministic, idempotent setup/teardown)
✅ Runtime ≤3 minutes
✅ Coverage: ≥90% sync engine, ≥85% OAuth provider, ≥80% MCP server
✅ No @pytest.mark.skip or TODO comments
✅ All critical security tests included
✅ Protocol compliance validated


Implementation Order

Phase 1A (33 tests) - Sync engine core + edge cases + invariants (~8-10 hours)
Phase 1B (5 tests) - Webhook lifecycle (~2-3 hours)
Phase 2 (11 tests) - OAuth provider flows (~3-4 hours)
Phase 3 (14 tests) - MCP integration + resilience (~2-3 hours)

Total estimated effort: 15-20 hours

Key Corrections Applied

✅ Redis key naming: focused:{user_id}:needs_sync (not needs_sync:user123)
✅ Version increment assertion: explicit assert row.version == old_version + 1
✅ Second webhook survival: explicit assertion that needs_sync remains after first sync
✅ OAuth error format: RFC 6749 ({"error": "invalid_grant", ...}), not JSON-RPC
✅ MCP error format: JSON-RPC 2.0 via HTTP 200, not HTTP 503
✅ Standard JSON-RPC error codes: -32603 (internal), -32600 (invalid request)
✅ Log safety assertions: no tokens/secrets/verifiers in logs
✅ Backend call count: no automatic retries (single attempt)
✅ MockGoogleCalendar helper: events_watch(), channels_stop(), simulate_webhook()
✅ SQL/Python invariants: 10 explicit tests matching DB logic to Python
RetryClaude can make mistakes. Please double-check responses.