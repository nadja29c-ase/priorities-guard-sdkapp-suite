-- §11 gating query: which live grants would break if the audience env vars were
-- tightened from issuer to resource URL?
--
-- READ-ONLY. Aggregate only. No user content, no user identifiers.
--
-- resource IS NULL  == token minted with aud = OAUTH_ISSUER (Rule 5 fallback).
--                      These are the grants that would stop validating.
-- live_grants       == unrevoked rows whose REFRESH token is still valid. This is the
--                      number that decides it: access tokens die in an hour, but a live
--                      grant keeps minting issuer-aud tokens indefinitely.
-- refreshable_but_no_expiry == diagnostic. If non-zero, live_grants undercounts and
--                      "0" is NOT a safe signal.
--
-- READ resource_value, NOT the shape label. "Safe" means THIS APP'S OWN resource URL,
-- not merely non-NULL: a row carrying the OTHER app's resource would also break.

SELECT
    CASE
        WHEN 'clarity.write' = ANY(t.scope) THEN 'MindSort'
        WHEN 'pg.access'     = ANY(t.scope) THEN 'PriorityGuardian'
        ELSE 'other'
    END                                              AS app,
    CASE WHEN t.resource IS NULL
         THEN 'issuer-shaped  << WOULD BREAK'
         ELSE 'non-null (CHECK resource_value)' END  AS aud_shape,
    t.resource                                       AS resource_value,
    count(*)                                         AS total_rows,
    count(*) FILTER (
        WHERE NOT t.revoked
          AND t.refresh_token_expires_at > now()
    )                                                AS live_grants,
    count(*) FILTER (
        WHERE NOT t.revoked
          AND t.refresh_token_hash IS NOT NULL
          AND t.refresh_token_expires_at IS NULL
    )                                                AS refreshable_but_no_expiry,
    max(t.created_at)                                AS newest
FROM oauth_access_tokens t
GROUP BY 1, 2, 3
ORDER BY 1, 5 DESC;
