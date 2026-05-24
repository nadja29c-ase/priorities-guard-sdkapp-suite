Claude Code Briefing: Update OAuth Consent UI for Clarity

Context:
Clarity is a brain dump organization tool that helps users cluster their thoughts into visual groups. The OAuth consent page needs to reflect this - currently it has Focused/Priority Guardian copy that doesn't apply.
Files to update:

backend/templates/oauth_consent_en.html
backend/templates/oauth_consent_de.html
backend/core/oauth_provider/authorize.py (scope descriptions)


Template Changes (both EN and DE):

Remove "Priority Guardian" subtitle entirely - just show the app name
Update purpose sentence:

EN: "This app helps you organize your thoughts by clustering them into visual groups you can save and revisit."
DE: "Diese App hilft dir, deine Gedanken zu ordnen, indem sie sie in visuelle Gruppen clustert, die du speichern und später wieder ansehen kannst."


Keep everything else - the permission list, privacy notice, buttons, styling all work fine


Scope Description Changes (authorize.py):
Update SCOPE_DESCRIPTIONS_EN and SCOPE_DESCRIPTIONS_DE to use human-friendly language:
English:

clarity.read: "View your saved thought boards"
clarity.write: "Save and organize your thought boards"

German:

clarity.read: "Deine gespeicherten Gedanken-Boards ansehen"
clarity.write: "Deine Gedanken-Boards speichern und organisieren"


Do NOT change:

Form action URLs (/oauth/pg/consent)
Button labels (Allow/Deny)
Privacy policy link structure
CSS styling
Accessibility features (ARIA labels, contrast, etc.)


Acceptance criteria:

Consent page shows "Clarity" as app name (dynamic from client_name)
No mention of "Priority Guardian", "Focused", "calendar", or "Focus Mode"
Permission descriptions are plain language a non-technical user understands
Both EN and DE templates updated consistently
