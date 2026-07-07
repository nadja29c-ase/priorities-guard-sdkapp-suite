 Codex Adversarial Review — inc_99 (85519b8)                                                                                  
                                                                                                                               
  Findings                                                                                                                     
  #: 1                                                                                                                         
  Severity: High                                                                                                               
  Issue: Sanitizer leaks data for non-netloc URIs. data:, ?token=, /path?token= bypass sanitization because parsed.netloc is   
    empty → returns original URI                                                                                               
  Location: resources.py:47                                                                                                    
  ────────────────────────────────────────                                                                                     
  #: 2                                                                                                                         
  Severity: High                                                                                                               
  Issue: Userinfo preserved in logs. ui://user:pass@host/path logs user:pass@host because parsed.netloc includes userinfo      
  Location: resources.py:47                                                                                                    
  ────────────────────────────────────────                                                                                     
  #: 3                                                                                                                         
  Severity: Medium                                                                                                             
  Issue: Non-dict _meta crashes handler. If _meta is a string/list, meta.get(...) raises AttributeError before any log         
  Location: resources.py:171, mcp_auth.py:464                                                                                  
  ────────────────────────────────────────                                                                                     
  #: 4                                                                                                                         
  Severity: Medium                                                                                                             
  Issue: _meta vs meta precedence inconsistent. Uses or which depends on truthiness, not source authority                      
  Location: resources.py:171                                                                                                   
  ────────────────────────────────────────                                                                                     
  #: 5                                                                                                                         
  Severity: Low/Medium                                                                                                         
  Issue: Sanitized URI can mislead diagnostics. Request for widget.html?x=1 rejected but log shows widget.html — unclear why it
                                                                                                                               
    failed                                                                                                                     
  Location: resources.py:226                                                                                                   
  Test Coverage Gaps                                                                                                           
                                                                                                                               
  Missing test cases:                                                                                                          
  - data:text/html,...?token=x (opaque URI scheme)                                                                             
  - ui://user:pass@widget/path (userinfo)                                                                                      
  - ?token=secret (no path)                                                                                                    
  - /path?token=secret#frag (no scheme)                                                                                        
  - Exact 512 chars / 513 chars (boundary)                                                                                     
  - Empty string URI                                                                                                           
  - _meta as string/list (non-dict)                                                                                            
  - Both _meta and meta present with conflicting IDs                                                                           
                                                                                                                               
  Audit Notes                                                                                                                  
                                                                                                                               
  - Log level test is adequate for unit testing (handler calls logger.info), but doesn't prove production structlog config     
  emits INFO                                                                                                                   
  - No import cycle, but importing resources.py now pulls in mcp_auth.py which constructs global JWKS cache — unnecessary      
  coupling                                                                                                                     
                                                                                                                               
  ---                                                                                                                          
  Action needed? Findings #1 and #2 are the real issues — the sanitizer fails for non-standard URIs and leaks userinfo. #3 is a
   crash waiting to happen with malformed requests. Worth a quick fix before deploy.                                           
                                                                                     