Approved and unchanged from what you reviewed — running it:

  Called render (ctrl+o to expand)

⏺ Two rows, and both are private addresses — this changes the recommendation.

  ┌──────────────────┬───────────────────────────┬────────┬─────────────┐
  │   client_addr    │           user            │ state  │ connections │
  ├──────────────────┼───────────────────────────┼────────┼─────────────┤
  │ 10.27.98.68/32   │ priority_guardian_db_user │ idle   │ 3           │
  ├──────────────────┼───────────────────────────┼────────┼─────────────┤
  │ 10.29.145.170/32 │ priority_guardian_db_user │ active │ 1           │
  └──────────────────┴───────────────────────────┴────────┴─────────────┘
  
  Internal connectivity is confirmed working — the 3 idle connections are a service holding a pool (backend or Celery), on
  RFC1918 space. Locking down external access will not sever the app.

  The more useful finding: the Render MCP query tool connects internally too. The reasoning is tight — pg_stat_activity
  includes the querying session, the tool connects over TCP so its client_addr is non-null and can't have been filtered by the
  WHERE, and only two rows exist, both 10.x. So my session is one of them, and it's private. (The one assumption: that the tool
  isn't on a unix socket, which it can't be — it's remote.)

  That removes one of the two reasons we thought external access was needed. The only remaining known external dependency is 
  pg_dump/psql from your own machine, per OPERATIONS_PREDEPLOY.md.

  And your caveat holds in the other direction: this is a snapshot, so absence of external connections right now isn't proof
  nothing ever connects externally.

  So I'd revise the recommendation you gave — toward tighter, not looser. The narrow-allowlist plan assumed the MCP diagnostics
  needed an external hole. They don't. That makes the options:
  
  - (a) Empty external allowlist. Removes the entire internet. Services unaffected (internal). MCP admin queries still work —
  including the ones we've been running. Cost: pg_dump/psql from your laptop stops working until you temporarily re-add an
  entry. Given how rarely you do that versus how permanently 0.0.0.0/0 sits there, this is what I'd recommend now.
  - (b) Your current public IP as a /32. Keeps pg_dump working. But home IPs are typically dynamic, so it will silently break
  in days-to-weeks, and the entry then lingers pointing at whoever inherits that address.
  - (c) Your ISP's prefix. Survives IP rotation, but re-admits thousands of strangers' machines — most of the weakness, little
  of the benefit.

  I don't know your public IP and I'd rather not probe for it without asking; if you want (b), tell me the IP or say go and
  I'll look it up.

  Nothing has been written. When you pick, I'll show you the exact allowlist value before applying, and immediately after the
  change I'll verify the services still connect — the fastest check is re-running the pg_stat_activity query, since a broken
  service shows up as its connections disappearing.
  
  One correction to your sequencing note, in your favour: because the MCP tool is internal, the post-change verification does
  not depend on external access surviving. If I lock it down and something was silently external, I'll still be able to see it.

✻ Baked for 1m 4s

※ recap: Goal: lock down the production database, which is reachable from the whole internet. I confirmed all services connect 
  internally, so tightening won't break them. Waiting on your pick: empty the external allowlist (my recommendation) or allow 
  just your IP.
  
  3 tasks (1 done, 1 in progress, 1 open)
  ◼ Restrict priority-guardian-db ipAllowList (currently 0.0.0.0/0)