











Privacy Policy
Priority Guard App Suite

Effective Date: March 3, 2026 | Version: 3.0 | Last Updated: March 27, 2026




In short: We do not request or require direct identifiers such as your name or email address. We identify you by a pseudonymous identifier provided by ChatGPT and an internal user ID derived from it. Priority Guardian reads your Google Calendar (read-only) to compute time spent on priorities — we never store your events. MindSort AI stores only the board content you create — clusters, thought items, and priorities. Your stored application data is hosted on EU servers. Some data is transferred to the US when processed by OpenAI during app usage.



This Privacy Policy explains how Priority Guard Suite ("we," "us," "our") collects, uses, and protects your data when you use our ChatGPT applications. Priority Guard is a suite of productivity tools that run inside ChatGPT. This policy covers all apps in the suite.



Currently active apps with thin the Priority Guard Suite: Priority Guardian and MindSort AI.





PART I — GENERAL (ALL APPS)



Controller and Contact



Data Controller: Nadja Carabulea
Email: support@priority-guard.com
Website: https://www.fulfilling-productivity.com/priority-guard

For any privacy-related questions, data access requests, or deletion requests, contact us at the email above. We respond within 30 days per GDPR Art. 12(3).



Shared Infrastructure



User Identifier:

Pseudonymous identifier provided by ChatGPT, plus an internal user ID derived from it (UUID)

Purpose: Identify your account across sessions. We do not receive your real name or email address from ChatGPT.



OAuth Session:

Hashed and encrypted session token

Purpose: Cross-app authentication. No plaintext tokens stored.



Consent Records:

App name, scope, timestamp

Purpose: GDPR compliance audit trail.



Operational Logs:

Transient IP addresses handled by hosting provider (Render)

Purpose: Infrastructure security and abuse prevention. Not stored in our application database.



Note: The data categories above (OAuth Session, Consent Records) also appear in the Priority Guardian data table (Addendum A.1) for completeness, as they form part of the full data inventory for that app.



How We Use Your Data



We use your data solely to provide the functionality you requested. App-specific use descriptions are provided in each app addendum. Across all apps, we do NOT use your data for advertising, analytics, profiling, model training, or any purpose other than the features described in this policy.





Lawful Basis for Processing



We process your data primarily on the basis of your consent (GDPR Art. 6(1)(a)), granted when you authorize the app through ChatGPT's OAuth flow. Certain processing activities — such as security logging, fraud prevention, and inactivity cleanup — may rely on legitimate interests (GDPR Art. 6(1)(f)) where consent is not the appropriate basis. You can withdraw consent at any time by disconnecting the app or contacting us.





Data Sharing and Service Providers



We share your data only with the following service providers, each necessary for the service to function. 

Some providers are only used by specific apps. App-specific usage is explained in the addenda below.





OpenAI (ChatGPT runtime)

Role: Processes app data during app usage via requests and responses exchanged with the ChatGPT runtime.

Legal basis: Acts as data processor on our behalf under a signed Data Processing Addendum (DPA).

EU/EEA processing: OpenAI Ireland Ltd.

International transfers: Covered by Standard Contractual Clauses (SCCs) included in the DPA.

Privacy policy: https://openai.com/policies/privacy-policy

Location / transfer: United States — Signed DPA / SCCs



Render Services, Inc. (hosting)

Role: Hosts backend, PostgreSQL database, and Redis cache.

Location: Frankfurt, Germany (EU)

DPA: https://render.com/dpa

Transfer basis: EU-US Data Privacy Framework



IONOS SE (email forwarding)

Role: Forwards support emails.

Location: Germany (EU)



Google LLC (Google Calendar API — Priority Guardian only)

Role: Provides read-only access to Google Calendar events when you use the Priority Guardian app and choose to connect your calendar via OAuth 2.0.

Scope: MindSort AI does not access Google data.

Privacy policy: https://policies.google.com/privacy

Policy: Google API Services User Data Policy applies.

Location / transfer: Subject to Google's Privacy Policy and applicable transfer mechanisms.



We do not sell your data. We do not share your data with advertisers.



Data We Do Request or Store by Default



Across all apps, we do not intentionally request or require:

Your name, email address, or real identity.

Payment information, health data, or government identifiers.

Location data or device information.

Full chat history or conversation logs with ChatGPT.

Behavioral tracking or profiling data.

Any data from Google services other than Calendar (no Drive, Contacts, Gmail, etc.) — Priority Guardian only.

Calendar event locations, organizer details, or attendee identities — Priority Guardian only.

IP addresses are not stored in our application database; they may appear transiently in infrastructure access logs handled by our hosting provider (Render) for security and operational purposes.

Note on free-text fields: Our apps include free-text input fields where you may voluntarily enter any content, including personal information. Please do not enter sensitive personal data (such as health information, financial data, or government identifiers) into these fields. We process whatever you enter solely to provide the requested functionality, and we do not use it for any other purpose.



International Data Transfer



Your stored application data (database, cache, backups) is hosted in the EU (Frankfurt, Germany). Data is transferred to the US when OpenAI processes app requests and responses during your use of the app. App-specific details of what gets transferred are described in each app addendum below.

This EU-to-US transfer is covered by Standard Contractual Clauses (SCCs) included in our signed DPA with OpenAI. EU/EEA data is processed by OpenAI Ireland Ltd. under that DPA. When you connect Google Calendar (Priority Guardian only), Google may also process your data in the US as an independent data controller, subject to Google's own Privacy Policy and Google's participation in the EU-US Data Privacy Framework.



Data Retention - Shared Data



OAuth access tokens (ChatGPT) - Retention period: 1 hour (auto-expire)

OAuth refresh tokens (ChatGPT) - Retention period: 30 days (encrypted, rotated on use)

Browser session - Retention period: 30 days sliding window (extended on each use; deleted after 30 days of inactivity)

Consent records - Retention period: Persistent until you revoke consent (required for compliance)

Audit logs - Retention period: 90 days (rolling delete)

Database backups - Retention period: 7 days (encrypted, then permanently deleted by hosting provider)

Automatic Inactivity Cleanup: After 6 months with no active connections or consents, your account is permanently deleted. This cleanup process runs monthly.



Your Rights (GDPR Art. 12–22)



You have the following rights regarding your personal data:

Access (Art. 15) — View your app data directly within each app. For a full data export, contact us by email.

Rectification (Art. 16) — Update your data directly within each app where editing is supported.

Erasure (Art. 17) — Delete your app data directly within each app. For full account deletion, contact us by email.

Restriction (Art. 18) — Where supported, you can archive or freeze app-specific data within the app.

Portability (Art. 20) — Request a JSON export of your data by email.

Objection (Art. 21) — Delete or modify your data at any time. We perform no automated profiling.

Complaint (Art. 77) — You have the right to lodge a complaint with a data protection supervisory authority.

To exercise any of these rights, contact support@priority-guard.com. We respond within 30 days. App-specific examples of how to exercise these rights are provided in each app addendum.



 How to Delete Your Entire Account



Contact support@priority-guard.com to request full account deletion. We delete your user record, which cascade-deletes all associated app data, connections, and consents stored in our database. We respond within 30 days.

Please note: deletion audit log entries (created when you use the in-app deletion tools) are retained separately for up to 90 days as required for compliance purposes, after which they are permanently deleted. Encrypted database backups are retained by our hosting provider for 7 days after deletion, then permanently destroyed. After that, no recovery is possible.



11. Cookies



We use a single cookie (pg_session) that is strictly necessary for the app to work. It keeps you logged in during the authorization process — that's all it does. It cannot be read by other websites or by JavaScript, and it only works over secure connections (technical details: HttpOnly, Secure, SameSite=Lax, scoped to /oauth paths). It expires after 30 days of inactivity.

We do not use tracking cookies, analytics cookies, or advertising cookies. Because this cookie is strictly necessary for authentication and is not used for analytics or advertising, we do not display a cookie consent banner.



12. Security



Your calendar login credentials are encrypted before they are stored and can only be decrypted by our system (AES-256 encryption at rest). All data sent between your browser, our servers, and Google is encrypted in transit (TLS 1.3). Session tokens are never stored in readable form — only as cryptographic hashes.

All our servers and databases run in the EU, in Frankfurt, Germany. Backups are encrypted automatically. Temporary data expires and is deleted on a schedule.

Access to production systems is restricted to the minimum necessary for operating and maintaining the service, with multi-factor authentication enabled. All secrets are stored in an encrypted vault.

When we request your calendar data from Google, we ask for the minimum fields necessary — nothing extra.



13. AI-Generated Content (General)



All Priority Guard apps use ChatGPT's language model to generate responses, analyses, and structured output. Across all apps:

AI-generated outputs are non-deterministic — the same input may produce different results at different times.

All outputs are informational suggestions, not professional, financial, legal, medical, or career advice.

You are solely responsible for reviewing, interpreting, and acting on AI-generated content.

OpenAI processes your data according to their own privacy policy.

App-specific details about what data is sent to OpenAI and how AI is used are described in each app addendum.



14. Children



Our services are not intended for children under 13 years of age, consistent with ChatGPT's age requirements. We do not knowingly collect personal data from children. If you believe a child has provided us with personal data, contact us immediately.



15. Changes to This Policy



We may update this Privacy Policy to reflect changes in our practices or legal requirements. Material changes will be communicated via an updated effective date at the top of this document. We encourage you to review this policy periodically.



16. Contact



Email: support@priority-guard.com

Website: https://www.fulfilling-productivity.com/priority-guard



APP-SPECIFIC ADDENDA


Addendum A: Priority Guardian

A.1 Data We Collect and Store

Below is the complete list of data we store for Priority Guardian. If it is not listed here, we do not collect it.



User Identifier

What we store: Pseudonymous identifier provided by ChatGPT, plus an internal user ID derived from it (UUID)

Purpose: Identify your account across sessions. We do not receive your real name or email address from ChatGPT.


Priority Configuration

What we store: Priority name (max 100 characters), type (deadline or flexible), assigned calendar keyword (P1, P2, or P3), deadline date, weekly hour target, checkpoint date, status (active or retired)

Purpose: Store your declared priorities so the app can track time against them.


Goals

What we store: Goal text (max 200 characters per goal, up to 3 per flexible priority), achieved status

Purpose: Track concrete outcomes you set for each priority.


Deliverables

What we store: Deliverable name (max 200 characters), completion status

Purpose: Track deliverables for deadline priorities.


Weekly Snapshots

What we store: Per-priority aggregated hours per week, target hours, streak count at time of snapshot, calendar keyword at time of snapshot, untagged calendar hours for the week (other_hours), total tracked calendar hours for the week (total_tracked_hours)

Purpose: Enable week-over-week comparison, trend reporting, and historical pie chart accuracy. Contains only computed numbers, never raw calendar data.


Running Aggregates

What we store: Streak count, average target achievement percentage, total hours invested — stored directly on the priority record and updated on each snapshot cycle

Purpose: Enable instant display of lifetime progress without recomputing from snapshots. Frozen when you retire a priority.


Google OAuth Tokens

What we store: Encrypted access and refresh tokens for Google Calendar

Purpose: Authenticate with Google to read your calendar. Encrypted with AES-256 at rest.


Consent Records

What we store: App name, scope, timestamp

Purpose: GDPR compliance audit trail. Also part of shared infrastructure (Part I, Section 2).


OAuth Session

What we store: Hashed and encrypted session token

Purpose: Cross-app authentication. No plaintext tokens stored. Also part of shared infrastructure (Part I, Section 2).




A.2 What Priority Guardian Reads from Your Calendar (But Does NOT Store)

Priority Guardian reads your Google Calendar events to compute how many hours you spent on each priority during a given week. Here is exactly what is read, why, and what happens to it:


Data read via calendar.events.readonly:

Event title (summary) — Used to match your priority keywords (P1, P2, P3). Only the computed hours are stored, never the title itself.

Event description — Used for semantic grouping of non-priority time in the current week's report. Passed to the ChatGPT runtime so it can propose categories like "Client calls ~3h, Admin ~2h." Never stored by our backend.

Event start and end time — Used to compute duration in hours. Only the computed total is stored per priority per week.

Event status — Used to filter out cancelled events. Not stored.

Attendee response status — Only your own acceptance status (accepted, declined, tentative) is read to filter out events you declined. No attendee names, emails, or identifiers are ever received from Google. Our API request explicitly restricts the response to only your own status.

Event ID — Used for in-memory deduplication within a single computation. Never stored.

Calendar ID — Used to identify which calendar an event belongs to during priority matching. Never stored.


Data read via calendar.settings.readonly:

Timezone — We read your Google Calendar timezone setting to determine the boundaries of your local week (Monday 00:00 to Sunday 23:59 in your timezone). This ensures weekly reports reflect your actual work week, not UTC. We do not store this value — it is read at report generation time and discarded immediately after use.


After processing, all calendar event data is discarded. The only thing that persists is aggregated hours per priority per week.


For the current week, event titles, descriptions, and times may be included in app requests and responses exchanged with the ChatGPT runtime in two scenarios: (1) to propose semantic groupings of your non-priority time, and (2) when you request a breakdown of time within a specific priority (P1, P2, or P3), that priority's event titles and descriptions are sent to generate subcategory groupings. For past weeks, no event-level data is transferred — only stored aggregates are used.


A.3 We Only Ask Google for What We Need



When we request your calendar events from Google, we explicitly tell Google to send us only the fields listed above — nothing more. Google never sends us your event locations, organizer emails, attendee emails, attachments, video call links, or reminders. We don't just ignore extra data; we prevent it from being sent to us in the first place.



A.4 What is Stored vs. Computed

Stored: Priority names, types, keywords, deadlines, targets, checkpoint dates, goals, deliverables, weekly aggregated hours, streak counts, and running averages. All user-authored text. Google OAuth tokens (AES-256 encrypted).


Computed and discarded: Event titles and descriptions are processed in real-time to compute hours and semantic groupings, then discarded. Only the aggregated numbers persist. For the current week's report, event titles and descriptions are included in app requests and responses exchanged with the ChatGPT runtime so it can propose categories — this data is not stored by our backend.


A.5 How We Use Your Data 

We use your Priority Guardian data solely to provide the following functionality:

Computing how many hours per week you spend on each declared priority.

Generating weekly progress reports with status indicators (on track, ahead, behind).

Detecting patterns in your time allocation over multiple weeks.

Enabling the ChatGPT runtime to propose semantic groupings of your calendar time — including non-priority time and, on request, time within individual priorities.      




A.6 What Gets Sent to OpenAI


During app usage, the following Priority Guardian data is included in requests and responses exchanged with the ChatGPT runtime:

Priority names, types, keywords, statuses, and weekly hour targets — always included so the model can display and discuss your current priorities.

Goal text and deliverable names — included when relevant to the current conversation.

Aggregated hours per priority — weekly totals and running aggregates, used to generate reports and trend analysis.

Current week: event titles and descriptions — included in two scenarios: (1) to propose semantic groupings of your non-priority time, and (2) when you request a breakdown of time within a specific priority (P1, P2, or P3), that priority's event titles and descriptions are sent to generate subcategory groupings.

Past weeks: no event-level data is transferred — only stored aggregates are used.

We do not intentionally include direct account identifiers such as your name or email address in these transfers. The transfer is covered by our signed DPA with OpenAI, which includes Standard Contractual Clauses (SCCs) for EU-to-US data transfers.


A.7 Data Retention 


Priority configuration, goals, deliverables

Retention period: Until you delete them, retire the priority, or request full account deletion.

Weekly snapshots

Retention period: Lifetime of the parent priority (deleted when priority is deleted).

Running aggregates

Retention period: Same as priority record (frozen on retirement, deleted with priority).

Google OAuth tokens

Retention period: Until you disconnect, or 6 months of inactivity.

For shared retention periods (OAuth tokens, browser session, consent records, audit logs, database backups), see Part I, Section 8.



A.8 How to Delete Your Priority Guardian Data



Delete a Priority (In-App):

Ask ChatGPT to delete a specific priority, or use the Priority Guardian dashboard. This permanently deletes the priority and all associated goals, deliverables, and weekly snapshots. When you delete a priority, everything connected to it (goals, deliverables, weekly snapshots) is automatically deleted too. This action cannot be undone.

Disconnect Google Calendar (In-App):

Ask ChatGPT to disconnect your Google Calendar, or use the dashboard. This revokes our access to your calendar. Your priority data is preserved (disconnect does not mean deletion).

Delete Your Entire Account:

Contact support@priority-guard.com. See Part I, Section 10 for details.

What Happens When You Delete:

All associated data is permanently removed from our database. When you delete a priority, everything connected to it (goals, deliverables, weekly snapshots) is automatically deleted too. Encrypted database backups kept by our hosting provider are retained for 7 days, then permanently deleted. After that, no recovery is possible.



A.9 Google Limited-Use Compliance

Priority Guardian accesses Google Calendar data solely for its declared purpose: computing per-priority time allocation and enabling conversational semantic grouping of non-priority time. No calendar data is used for advertising, analytics, profiling, or model training. We do not sell or transfer Google user data to data brokers or surveillance entities. We do not use Google user data for credit, lending, or insurance decisions. Access to Google user data is restricted to the minimum necessary to operate the service, subject to confidentiality obligations. Human access to Google user data is limited to debugging, security review, and user-requested support. We comply with Google's Limited Use Requirements.


A.10 AI-Generated Content

Priority Guardian uses the ChatGPT runtime to generate weekly reports, pattern analysis, and semantic groupings of your calendar time. Important notes:

Reports are generated from your priority data and calendar time computations.

Semantic groupings of non-priority time are proposed by the language model based on event titles and descriptions — these are non-deterministic and may vary between sessions.

AI-generated analysis should be reviewed and interpreted by you. It is not financial, medical, or professional advice.

OpenAI processes your data according to their own privacy policy.





A.11 Data Accuracy Disclaimer

Time computations depend on keyword matching against your calendar event titles. Events without the correct keyword are not counted. Events with incorrect keywords are counted toward the wrong priority. Time zones, DST transitions, recurring event exceptions, and cancelled events may affect accuracy. We make reasonable efforts to handle these edge cases but do not guarantee perfect accuracy.


Addendum B: MindSort AI


B.1 Data We Collect and Store

Below is the complete list of data we store for MindSort AI. If it is not listed here, we do not collect it.



User Identifier

What we store: Pseudonymous identifier provided by ChatGPT, plus an internal user ID derived from it (UUID)

Purpose: Identify your board across sessions. We do not receive your real name or email address from ChatGPT.


Board Content

What we store: Cluster names, subcluster names, thought items (user-authored text, max 500 characters per item), behavioral tags (decide, research, test, delegate, automate, learn, align), priority assignments (up to 3, with rank P1/P2/P3 and optional reason: "blocker" or "goal-aligned")

Purpose: Store your organized board so it persists across conversations.


Content Hash

What we store: SHA256 hash of board content

Purpose: Detect whether the board has changed since last load. Not used for identification.


Board Snapshot Timestamp

What we store: Timestamp of the last board save (reset on each save — not a creation date)

Purpose: Record when the board was last saved. Operational metadata only — not linked to your identity.




B.2 What Gets Sent to OpenAI


During app usage, the following board data is included in requests and responses exchanged with the ChatGPT runtime:


Your full board content (cluster names, subcluster names, thought items, tags, and priority assignments including rank and reason) is included in app requests and responses so the language model can display, organize, and update your board conversationally.

When you use the board-organizing and prioritization features, the text you provide to confirm you are done adding thoughts, state your prioritization criterion, or name your priorities may be included in app requests needed to run those features.



We do not intentionally include direct account identifiers such as your name or email address in these transfers. The transfer is covered by our signed DPA with OpenAI, which includes Standard Contractual Clauses (SCCs) for EU-to-US data transfers.


B.3 Data Model

MindSort AI stores one board per user. Every time you organize your thoughts using MindSort AI, your board is automatically saved to the database and overwrites the previous version. There is no version history and no undo. The board is the complete current state of your saved clusters, thought items, tags, and priorities.



B.4 No External Connections

MindSort AI does not connect to Google Calendar or any external data source. It does not require Google Calendar or any OAuth connection beyond the standard ChatGPT authentication. It processes only the text you provide during the conversation.



B.5 How We Use Your Data

We use your MindSort AI data solely to provide the following functionality:

Persisting your organized board across conversations so you can return to it at any time.

Enabling the ChatGPT runtime to display, update, and reorganize your board based on your instructions.

Facilitating the prioritization flow by fetching your current board to apply priority assignments.





B.6 Data Retention

Board content (clusters, thought items, tags, priorities)

Retention period: Until you delete it in-app, or until full account deletion.

Content hash

Retention period: Same as board content.

Board snapshot timestamp

Retention period: Same as board content.



For shared retention periods (OAuth tokens, browser session, consent records, audit logs, database backups) see Part I, Section 8.





B.7 How to Delete Your MindSort AI Board Data

Delete Your Board (In-App)

Ask ChatGPT to delete your MindSort AI Board data. The app will confirm exactly what will be deleted before proceeding: your saved board with all its clusters, thought items, tags, and priorities. Once confirmed, all board data is permanently deleted. This action cannot be undone.

Delete Your Entire Account

Contact support@priority-guard.com. See Part I, Section 10 for details.

What Happens When You Delete

All board data is permanently removed from our database. Encrypted database backups kept by our hosting provider are retained for 7 days, then permanently deleted. After that, no recovery is possible.





B.8 AI-Generated Content

MindSort AI uses the ChatGPT runtime to cluster and organize your thoughts, suggest tags, and facilitate prioritization. Important notes:

The clustering, subclustering, and tagging of your thoughts is performed by the language model. Results are non-deterministic and may vary between sessions.

Clusters are organizational suggestions — not assessments, diagnoses, or recommendations. You decide what to do with the structured output.

AI-generated structures should be reviewed by you and adjusted as needed. They are not professional, medical, or psychological advice.

OpenAI processes your data according to their own privacy policy.





B.9 AI Clustering Disclaimer

The organization of your thoughts into clusters and subclusters is proposed by the language model based on the content you provide. Within our service, only the data explicitly stored in our database persists across sessions — see B.1 for the complete list. For information about how OpenAI handles data processed through their runtime, refer to OpenAI's privacy policy. The same thoughts may be organized differently in different sessions — this is expected behavior, not an error.


Addendum C: Future Apps


When new apps are added to the Priority Guard suite, a corresponding addendum will be appended to this Privacy Policy. Until a specific addendum is published for a new app, Part I (General) of this policy applies in full. We will update the version number and effective date of this document when new addenda are added.


Priority Guard  ·  support@priority-guard.com  ·  https://www.fulfilling-productivity.com/priority-guard

© 2026 Nadja Carabulea. All rights reserved.

