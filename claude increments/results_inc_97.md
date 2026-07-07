ROOT CAUSE CONFIRMED.                                                                                                        
                                                                                                                               
  Per OpenAI Apps SDK Reference:                                                                                               
  "_meta fields belong at the TOP LEVEL of the tool result, not nested inside structuredContent."                              
  "_meta object is strictly for component hydration and must sit at the top level of the response."                            
                                                                                                                               
  ---                                                                                                                          
  DIAGNOSTIC REPORT — inc_pg_render_diff                                                                                       
                                                                                                                               
  Summary                                                                                                                      
                                                                                                                               
  Root cause identified: PG's get_priorities places the widget binding inside structuredContent._meta, while MindSort places it
   at top-level CallToolResult._meta. ChatGPT only reads top-level _meta for widget hydration; nested _meta is invisible to the
   host.                                                                                                                       
                                                                                                                               
  Field-by-Field Comparison                                                                                                    
  Element: File                                                                                                                
  MindSort (commit a25811ae, Jul 1 deployed): mcp_server/clarity/tools/organize_thoughts.py:380-390                            
  PG (current HEAD): mcp_server/priority_guardian/tools/get_priorities.py:285-312                                              
  ────────────────────────────────────────                                                                                     
  Element: Top-level _meta                                                                                                     
  MindSort (commit a25811ae, Jul 1 deployed): ✅ Present                                                                       
  PG (current HEAD): ❌ Missing                                                                                                
  ────────────────────────────────────────                                                                                     
  Element: _meta.ui.resourceUri                                                                                                
  MindSort (commit a25811ae, Jul 1 deployed): ✅ WIDGET_URI                                                                    
  PG (current HEAD): ❌ Absent                                                                                                 
  ────────────────────────────────────────                                                                                     
  Element: _meta["openai/outputTemplate"]                                                                                      
  MindSort (commit a25811ae, Jul 1 deployed): ✅ WIDGET_URI                                                                    
  PG (current HEAD): ❌ Only in structuredContent._meta                                                                        
  ────────────────────────────────────────                                                                                     
  Element: structuredContent._meta                                                                                             
  MindSort (commit a25811ae, Jul 1 deployed): Not used                                                                         
  PG (current HEAD): ✅ Contains openai/outputTemplate (but host ignores it)                                                   
  Code Evidence                                                                                                                
                                                                                                                               
  MindSort (working) — organize_thoughts.py:380-390:                                                                           
  meta = {                                                                                                                     
      "ui": {"resourceUri": WIDGET_URI},                                                                                       
      "openai/outputTemplate": WIDGET_URI,                                                                                     
      ...                                                                                                                      
  }                                                                                                                            
  return mcp_types.CallToolResult(                                                                                             
      content=[],                                                                                                              
      structuredContent=result["structuredContent"],                                                                           
      _meta=meta,  # TOP-LEVEL ✅                                                                                              
  )                                                                                                                            
                                                                                                                               
  PG (not working) — get_priorities.py:285-312:                                                                                
  structured_content = {                                                                                                       
      "success": True,                                                                                                         
      "data": {...},                                                                                                           
      "_meta": {"openai/outputTemplate": WIDGET_URI},  # NESTED ❌                                                             
      ...                                                                                                                      
  }                                                                                                                            
  return mcp_types.CallToolResult(                                                                                             
      content=[...],                                                                                                           
      structuredContent=structured_content,                                                                                    
      # NO top-level _meta ❌                                                                                                  
  )                                                                                                                            
                                                                                                                               
  Canon Source                                                                                                                 
                                                                                                                               
  OpenAI Apps SDK Reference (https://developers.openai.com/apps-sdk/reference):                                                
  - "_meta fields belong at the TOP LEVEL of the tool result"                                                                  
  - "structuredContent appears in transcripts; _meta does not"                                                                 
  - Widget hydration requires top-level _meta.ui.resourceUri                                                                   
                                                                                                                               
  Verdict                                                                                                                      
                                                                                                                               
  Confirmed structural divergence: PG's nesting of _meta inside structuredContent is invisible to ChatGPT's widget hydration   
  logic. This explains why resources/read fires for MindSort (top-level binding) but never for PG (nested binding).            
                                                                                                                               
  What I Did NOT Verify                                                                                                        
                                                                                                                               
  1. Openai_uiux.md — Not reachable in codebase; used official OpenAI reference instead (flagged)                              
  2. Other PG widget-producing tools — Only verified get_priorities; other tools may have same issue                           
                                                                                                                               
  Recommendation                                                                                                               
                                                                                                                               
  A fix increment should move PG's widget binding from structuredContent._meta to top-level CallToolResult._meta, mirroring    
  MindSort's pattern. This is a same-codebase fix under your control, not a host-side issue requiring OpenAI escalation.       
                                                                                                                               
✻ Cogitated for 2m 42s                                                                                                         
                                                                                                                               
❯ can you check which date was this announcement made? ⏺ ROOT CAUSE CONFIRMED.                                                 
                                                                                                                               
                                                                                                                               
                                                                                                                               
  Per OpenAI Apps SDK Reference:                                                                                               
                                                                                                                               
  "_meta fields belong at the TOP LEVEL of the tool result, not nested inside structuredContent."                              
                                                                                                                               
  "_meta object is strictly for component hydration and must sit at the top level of the response."       