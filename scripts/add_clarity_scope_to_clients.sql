-- ============================================================================
-- Add clarity.write scope to existing OAuth clients
--
-- This script adds the 'clarity.write' scope to existing OAuth provider clients
-- so they can request Clarity MCP access during authorization.
--
-- Safe to run multiple times (idempotent).
--
-- Usage:
--   psql -h <host> -U <user> -d <database> -f scripts/add_clarity_scope_to_clients.sql
--
-- Or via Render console:
--   Copy-paste this script into the Render PostgreSQL console
-- ============================================================================

-- First, show current state (for verification)
SELECT
    id,
    client_id,
    scopes,
    created_at
FROM core_connections
WHERE connection_type = 'oauth_provider';

-- Update all OAuth provider clients to include 'clarity.write' scope
-- Only adds if not already present (idempotent)
UPDATE core_connections
SET scopes = array_append(scopes, 'clarity.write')
WHERE connection_type = 'oauth_provider'
  AND NOT ('clarity.write' = ANY(scopes));

-- Show updated state
SELECT
    id,
    client_id,
    scopes,
    created_at
FROM core_connections
WHERE connection_type = 'oauth_provider';

-- Count of updated clients
SELECT
    COUNT(*) as total_oauth_clients,
    COUNT(*) FILTER (WHERE 'clarity.write' = ANY(scopes)) as clients_with_clarity_scope
FROM core_connections
WHERE connection_type = 'oauth_provider';
