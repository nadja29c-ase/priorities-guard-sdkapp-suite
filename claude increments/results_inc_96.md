---                                                                                                                          
  inc_96 AUDIT REPORT                                                                                                          
                                                                                                                               
  Commit hash audited: 81eb507ffba2df11950bcdf2c626fd3000941641                                                                
                                                                                                                               
  ---                                                                                                                          
  CRITICAL FINDING: Unpack v2.0 Cannot Be Audited                                                                              
                                                                                                                               
  Unpack is in a DIFFERENT repository (fulfilling-productivity repo at apps/unpack/server.py). It is NOT in the                
  priority-guardian repo.                                                                                                      
                                                                                                                               
  Per claude increments/SHARED ARCHITECTURE/health_endpoints.md:14:                                                            
  "Unpack — apps/unpack/server.py (fulfilling-productivity repo)"                                                              
                                                                                                                               
  Per claude increments/SHARED ARCHITECTURE/remove_azp.md:32:                                                                  
  "Unpack shipped without it. Unpack has no auth at all and was approved."                                                     
                                                                                                                               
  Implication: Unpack reportedly has no OAuth authentication, so the OAuth/JWKS guard concerns may not apply. However, I cannot
   verify this without access to the fulfilling-productivity repo. Flagging as incomplete per MOST-CRITICAL rule.              
                                                                                                                               
  ---                                                                                                                          
  Priority Guardian V1.0 Audit                                                                                                 
                                                                                                                               
  Location: mcp_server/priority_guardian/                                                                                      
  ADR_005 Shape: #1 (mixed-origin)                                                                                             
  Files read: config.py (279 lines), mcp_auth.py (first 100 lines)                                                             
                                                                                                                               
  Coverage Table                                                                                                               
  #: 1                                                                                                                         
  Guard: OAuth issuer URL exact-match                                                                                          
  Status: ABSENT                                                                                                               
  File:Line: —                                                                                                                 
  Evidence: No exact-match guard. Has origin-matching check (config.py:192-197) and localhost rejection (config.py:200-204),   
  but                                                                                                                          
     not assert-known-good.                                                                                                    
  ────────────────────────────────────────                                                                                     
  #: 2                                                                                                                         
  Guard: JWKS URL exact-match                                                                                                  
  Status: ABSENT                                                                                                               
  File:Line: —                                                                                                                 
  Evidence: Blocklist-style guard at config.py:211-230 rejects localhost/http://, but does NOT assert specific expected value. 
  ────────────────────────────────────────                                                                                     
  #: 3                                                                                                                         
  Guard: Backend URL localhost rejection                                                                                       
  Status: PRESENT                                                                                                              
  File:Line: config.py:217,224                                                                                                 
  Evidence: BACKEND_URL included in production URL invariants check; rejects localhost and http://.                            
  ────────────────────────────────────────                                                                                     
  #: 4                                                                                                                         
  Guard: CORS_ALLOWED_ORIGINS required                                                                                         
  Status: PRESENT                                                                                                              
  File:Line: config.py:245-249                                                                                                 
  Evidence: Raises RuntimeError if not set in production/staging.                                                              
  ────────────────────────────────────────                                                                                     
  #: 5                                                                                                                         
  Guard: Unknown-ENV fail-fast                                                                                                 
  Status: ABSENT                                                                                                               
  File:Line: config.py:17                                                                                                      
  Evidence: ENV = os.getenv("ENV", "dev") — no validation. Typo ENV=produciton silently treated as dev.                        
  ────────────────────────────────────────                                                                                     
  #: 6                                                                                                                         
  Guard: Production predicate aliases                                                                                          
  Status: PARTIAL                                                                                                              
  File:Line: config.py:43,138,200,211,245                                                                                      
  Evidence: Uses ENV in ("production", "prod", "staging") — covers 3 aliases. BUT IS_DEV at line 258 only checks == "dev", not 
    development/local/test/ci.                                                                                                 
  ────────────────────────────────────────                                                                                     
  #: 7                                                                                                                         
  Guard: Startup logging of resolved config                                                                                    
  Status: ABSENT                                                                                                               
  File:Line: —                                                                                                                 
  Evidence: No startup logging of resolved OAuth/infra URLs like Clarity has.                                                  
  Gap Set (PG V1.0)                                                                                                            
                                                                                                                               
  1. No exact-match guards for OAuth/JWKS URLs — uses blocklist (localhost/http rejection) instead of assert-known-good. A     
  wrong-but-valid HTTPS URL (e.g., https://wrong-domain.com/oauth/jwks) would pass.                                            
  2. No unknown-ENV fail-fast — typos like ENV=produciton silently disable all production guards.                              
  3. No startup logging — dashboard-vs-runtime ambiguity for OAuth URLs; diagnosis relies on inference rather than captured    
  runtime values.                                                                                                              
  4. IS_DEV flag incomplete — only checks ENV == "dev", not other dev-like values (development, local, test, ci).              
                                                                                                                               
  Structural Differences from Clarity                                                                                          
  ┌──────────────────────────┬──────────────────────────────────┬──────────────────────────────────────┐                       
  │          Aspect          │             Clarity              │               PG V1.0                │                       
  ├──────────────────────────┼──────────────────────────────────┼──────────────────────────────────────┤                       
  │ Guard style              │ Exact-match assert-known-good    │ Blocklist (localhost/http rejection) │                       
  ├──────────────────────────┼──────────────────────────────────┼──────────────────────────────────────┤                       
  │ Expected value constants │ _CLARITY_EXPECTED_JWKS_URL, etc. │ None                                 │                       
  ├──────────────────────────┼──────────────────────────────────┼──────────────────────────────────────┤                       
  │ Production predicate     │ _is_production_env() function    │ Inline ENV in (...) tuples           │                       
  ├──────────────────────────┼──────────────────────────────────┼──────────────────────────────────────┤                       
  │ Known ENV validation     │ Fail-fast on unknown ENV         │ None                                 │                       
  ├──────────────────────────┼──────────────────────────────────┼──────────────────────────────────────┤                       
  │ Env var prefix           │ CLARITY_*                        │ PG_*                                 │                       
  ├──────────────────────────┼──────────────────────────────────┼──────────────────────────────────────┤                       
  │ Backend URL env var      │ CLARITY_BACKEND_URL              │ PG_BACKEND_URL                       │                       
  ├──────────────────────────┼──────────────────────────────────┼──────────────────────────────────────┤                       
  │ .strip() normalization   │ Yes (inc_95)                     │ No                                   │                       
  └──────────────────────────┴──────────────────────────────────┴──────────────────────────────────────┘                       
  ADR_005 Shape #1 Expected Values (PG-OpenAI)                                                                                 
                                                                                                                               
  Per ADR_005, PG-OpenAI uses mixed-origin shape:                                                                              
  - authorization_servers = RS origin (https://pg.priority-guard.com)                                                          
  - jwks_uri = https://pg.priority-guard.com/oauth/jwks (same-origin proxy)                                                    
  - issuer = https://www.priority-guard.com (JWT iss claim)                                                                    
                                                                                                                               
  Note: PG's expected JWKS URL (pg.priority-guard.com) differs from MindSort's (www.priority-guard.com/oauth/mindsort/jwks). A 
  future fix increment must use PG-specific expected values, NOT copy MindSort's.                                              
                                                                                                                               
  ---                                                                                                                          
  Summary                                                                                                                      
  App: Priority Guardian V1.0                                                                                                  
  Auditable?: ✅ Yes                                                                                                           
  Gaps Found: 4 gaps (no exact-match, no unknown-ENV, no startup logging, incomplete IS_DEV)                                   
  ────────────────────────────────────────                                                                                     
  App: Unpack v2.0                                                                                                             
  Auditable?: ❌ No (different repo)                                                                                           
  Gaps Found: Cannot determine — reportedly has no auth                                                                        
  Recommendation: If PG V1.0 gaps are to be fixed, scope a separate increment with PG-specific expected values per ADR_005     
  Shape #1. Do NOT copy Clarity's guards verbatim — the expected values differ.                                                
                                                                                                                               
                         