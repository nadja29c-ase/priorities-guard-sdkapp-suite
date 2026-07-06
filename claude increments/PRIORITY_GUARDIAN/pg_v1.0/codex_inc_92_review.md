Codex Adversarial Review — inc_98 (ef282f9)                                                                                  
                                                                                                                               
  Findings                                                                                                                     
  #: 1                                                                                                                         
  Severity: Medium                                                                                                             
  Issue: Raw attacker-controlled URI logged at INFO and returned in error meta. URL-encoded PII, tokens, or very long URIs     
  would                                                                                                                        
     leak to production logs.                                                                                                  
  Location: resources.py:134, 177, 180                                                                                         
  ────────────────────────────────────────                                                                                     
  #: 2                                                                                                                         
  Severity: Medium                                                                                                             
  Issue: Tests don't prove log level is INFO. If impl regressed to DEBUG, tests could still pass (just checking substring in   
    stdout).                                                                                                                   
  Location: test_widget_render_observability.py:43, 72                                                                         
  ────────────────────────────────────────                                                                                     
  #: 3                                                                                                                         
  Severity: Low/Medium                                                                                                         
  Issue: Malformed request can fail before any INFO log. Missing params, missing uri, or __str__ raising would exit before     
    resource.read.requested.                                                                                                   
  Location: resources.py:129                                                                                                   
  ────────────────────────────────────────                                                                                     
  #: 4                                                                                                                         
  Severity: Low/Medium                                                                                                         
  Issue: Resource logs lack correlation_id. Tool logs have it, resource logs don't — concurrent sessions hard to diagnose.     
  Location: resources.py:134, 139, 177                                                                                         
  ────────────────────────────────────────                                                                                     
  #: 5                                                                                                                         
  Severity: Low                                                                                                                
  Issue: outputTemplate consistency test is partial. Checks TOOL_REGISTRY[*].widget_uri but not actual list_tools() _meta or   
    runtime structuredContent.                                                                                                 
  Location: test_widget_render_observability.py:123                                                                            
  Audit Notes                                                                                                                  
                                                                                                                               
  - resource.read.unknown_uri naming is unambiguous — won't be confused with a resource named "unknown"                        
  - Fallback HTML has same logging behavior — html_length logged whether real or fallback                                      
  - openai/widgetCSP may be stale legacy correctly framed as speculation — repo notes indicate redirect_domains is still used  
  for openExternal and Google OAuth redirect                                                                                   
                                                                                                                               
  Recommendations                                                                                                              
                                                                                                                               
  1. Sanitize logged URI: Log scheme/host/path only, strip query/fragment, cap max length, add uri_hash for correlation        
  2. Test log level explicitly: Use structlog.testing.capture_logs() or patch and assert level == "info"                       
  3. Defensive URI extraction: Wrap str(req.params.uri) in try/except, log resource.read.invalid_request on failure            
  4. Add correlation_id to resource logs: Extract from ReadResourceRequest.params._meta or middleware context                  
                                                                                                                               
  ---                                                                                                                          
  Action needed? Finding #1 (raw URI in logs) is the most actionable — a malicious client could inject PII into your production
   logs via crafted URIs. Consider sanitizing in a follow-up increment.                                                        
                                                                                                                               
✻ Worked for 8m 18s                                                                                                            
                                                                                                                               
⏺ Background command "Run Codex adversarial review on inc_98" completed (exit code 0)                                          
                                                                                                                               
⏺ I already captured and summarized the Codex output above. The review is complete.                                            
                                                                                                                               
  Summary of actionable items from Codex:                                                                                      
  ┌──────────┬─────────────────────────────────────────────────────────────────┬────────┐                                      
  │ Priority │                               Fix                               │ Effort │                                      
  ├──────────┼─────────────────────────────────────────────────────────────────┼────────┤                                      
  │ High     │ Sanitize logged URIs (strip query/fragment, cap length)         │ Small  │                                      
  ├──────────┼─────────────────────────────────────────────────────────────────┼────────┤                                      
  │ Medium   │ Add correlation_id to resource logs                             │ Small  │                                      
  ├──────────┼─────────────────────────────────────────────────────────────────┼────────┤                                      
  │ Medium   │ Test log level explicitly with structlog.testing.capture_logs() │ Small  │                                      
  ├──────────┼─────────────────────────────────────────────────────────────────┼────────┤                                      
  │ Low      │ Defensive URI extraction with try/except                        │ Small  │                                      
  └──────────┴─────────────────────────────────────────────────────────────────┴────────┘                                      
  Would you like me to address any of these findings now, or defer to a separate hardening increment?