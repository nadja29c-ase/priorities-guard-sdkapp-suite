Claude Code Briefing: Fix Landing Page Structure
Problem

unpack.fulfilling-productivity.com shows the suite landing page (should show Unpack-specific page)
fulfilling-productivity.com should show the suite landing page

Required Changes
1. Create new file: assets/unpack-landing.html
Single-app landing page for Unpack (like the Clarity page in screenshot 2):

Large Unpack icon at top
"Unpack" title
Description: "Flip your brainstorming on its head. Generate better questions before jumping to solutions, and see them clustered by theme."
Feature list:

Generate questions before jumping to solutions
See questions clustered by theme
Export your summary


"Available as a ChatGPT app" label
"Open ChatGPT" button
Footer: Privacy Policy | Terms of Service links
Contact email

2. Update routes
Domain/RouteFilePurposefulfilling-productivity.com/assets/index.htmlSuite landing (current)unpack.fulfilling-productivity.com/assets/unpack-landing.htmlUnpack app page (NEW)*/privacy-policyassets/privacy-policy.htmlPrivacy policy*/termsassets/terms.htmlTerms of service
3. Route logic
Check request host:

If host starts with unpack. → serve unpack-landing.html for /
Otherwise → serve index.html for /

Design Reference
Follow the Clarity page design (screenshot 2):

White card, centered
Icon at top (use Unpack diamond+bolt icon)
Title below icon
Description paragraph
Feature list with icons
CTA section at bottom
Dark background

Files to Modify

mcp_server/unpack/server.py — Update route logic
Create mcp_server/unpack/assets/unpack-landing.html