


Privacy Policy

Effective Date: March 3, 2026

Version: 2.0

Last Updated: March 3, 2026



In short: We do not collect direct identifiers such as your name or email address. We identify you only by a pseudonymous ID assigned by ChatGPT. We read your Google Calendar to compute how you spend time on your priorities — we never modify your calendar, and we never store your calendar events. Everything runs on EU servers.

This Privacy Policy explains how Priority Guard ("we," "us," "our") collects, uses, and protects your data when you use our ChatGPT applications. Priority Guard is a suite of productivity tools that run inside ChatGPT. This policy covers all apps in the suite.

Currently active apps: Priority Guardian.

Priority Guardian connects to your Google Calendar (read-only) to track how much time you spend on your declared priorities each week. It never writes to your calendar.

1. Controller and Contact

Data Controller: Nadja Carabulea

Email: support@priority-guard.com

Website: priority-guard.com

For any privacy-related questions, data access requests, or deletion requests, contact us at the email above. We respond within 30 days per GDPR Art. 12(3).

2. Data We Collect

Below is the complete list of data we store. If it is not listed here, we do not collect it.

2.1 Priority Guardian

Data Category — What We Store — Purpose

User Identifier — Pseudonymous ChatGPT user ID (UUID) — Identify your account across sessions. We never know your real name or email.

Priority Configuration — Priority name (max 100 characters), type (deadline or flexible), assigned calendar keyword (P1, P2, or P3), deadline date, weekly hour target, checkpoint date, status (active or retired) — Store your declared priorities so the app can track time against them.

Goals — Goal text (max 200 characters per goal, up to 3 per flexible priority), achieved status — Track concrete outcomes you set for each priority.

Deliverables — Deliverable name (max 200 characters), completion status — Track deliverables for deadline priorities.

Weekly Snapshots — Per-priority aggregated hours per week, target hours, streak count, calendar keyword at time of snapshot — Enable week-over-week comparison and trend reporting. Contains only computed numbers, never raw calendar data.

Running Aggregates — Streak count, average target achievement, total hours invested — Computed from weekly snapshots. Updated weekly. Frozen when you retire a priority.

Google OAuth Tokens — Encrypted access and refresh tokens for Google Calendar — Authenticate with Google to read your calendar. Encrypted with AES-256 at rest.

Consent Records — App name, scope, timestamp — GDPR compliance audit trail.

OAuth Session — Hashed and encrypted session token — Cross-app authentication. No plaintext tokens stored.

2.2 What Priority Guardian Reads from Your Calendar (But Does NOT Store)

Priority Guardian reads your Google Calendar events to compute how many hours you spent on each priority during a given week. Here is exactly what is read, why, and what happens to it:

Event title (summary) — Used to match your priority keywords (P1, P2, P3). Only the computed hours are stored, never the title itself.

Event description — Used for semantic grouping of non-priority time in the current week's report. Passed to ChatGPT's language model so it can propose categories like "Client calls ~3h, Admin ~2h." Never stored by our backend.

Event start and end time — Used to compute duration in hours. Only the computed total is stored per priority per week.

Event status — Used to filter out cancelled events. Not stored.

Attendee response status — Only your own acceptance status (accepted, declined, tentative) is read to filter out events you declined. No attendee names, emails, or identifiers are ever received from Google. Our API request explicitly restricts the response to only your own status.

Event ID — Used for in-memory deduplication within a single computation. Never stored.

After processing, all calendar event data is discarded. The only thing that persists is aggregated hours per priority per week.

For the current week, event titles, descriptions, and times are included in the report sent to ChatGPT so the language model can propose semantic groupings of your non-priority time. For past weeks, no event-level data is transferred — only stored aggregates are used.

2.3 We Only Ask Google for What We Need

When we request your calendar events from Google, we explicitly tell Google to send us only the fields listed above — nothing more. Google never sends us your event locations, organizer emails, attendee emails, attachments, video call links, or reminders. We don't just ignore extra data; we prevent it from being sent to us in the first place.

2.4 Data We Do NOT Collect

Your name, email address, or real identity.

Payment information, health data, or government identifiers.

Location data or device information.

IP addresses are not stored in our application database; they may appear transiently in infrastructure access logs handled by our hosting provider (Render) for security and operational purposes.

Full chat history or conversation logs with ChatGPT.

Behavioral tracking or profiling data.

Calendar event locations, organizer details, or attendee identities.

Any data from Google services other than Calendar (no Drive, Contacts, Gmail, etc.).

2.5 Shared Infrastructure

All Priority Guard apps share a common backend for authentication and user management. This shared layer stores only: a pseudonymous user ID (we never know who you are), encrypted login tokens, consent records showing which apps you authorized, and operational logs that may transiently include IP addresses for security and abuse prevention purposes, handled by our hosting provider (Render).

3. How We Use Your Data

We use your data solely to provide the functionality you requested:

Computing how many hours per week you spend on each declared priority.

Generating weekly progress reports with status indicators (on track, ahead, behind).

Detecting patterns in your time allocation over multiple weeks.

Enabling ChatGPT to propose semantic groupings of your non-priority calendar time.

We do NOT use your data for advertising, analytics, profiling, model training, or any purpose other than the features described above.

4. Lawful Basis for Processing

We process your data based on your consent (GDPR Art. 6(1)(a)), granted when you authorize the app through ChatGPT's OAuth flow and connect your Google Calendar. You can withdraw consent at any time by disconnecting your Google Calendar within the app or by contacting us.

5. Data Retention

Data Type — Retention Period

Priority configuration, goals, deliverables — Until you delete them, retire the priority, or request full account deletion.

Weekly snapshots — Lifetime of the parent priority (deleted when priority is deleted).

Running aggregates — Same as priority record (frozen on retirement, deleted with priority).

Google OAuth tokens — Until you disconnect, or 6 months of inactivity.

OAuth access tokens (ChatGPT) — 1 hour (auto-expire).

OAuth refresh tokens (ChatGPT) — 30 days (encrypted, rotated on use).

Browser session — 2 years sliding window (extended on each use; deleted after 2 years of inactivity).

Consent records — Persistent until you revoke consent (required for compliance).

Audit logs — 90 days (rolling delete).

Database backups — 7 days (encrypted, then permanently deleted by hosting provider).

Automatic Inactivity Cleanup: After 6 months with no active connections or consents, your account is  permanently deleted. This process runs monthly.

6. Data Sharing and Processors

We share your data only with the following processors, each necessary for the service to function:

OpenAI (ChatGPT runtime) — Processes your priority data and calendar summaries during conversations. OpenAI acts as processor under their Data Processing Terms, which include Standard Contractual Clauses (SCCs) for EU-to-US transfers. OpenAI's privacy policy: openai.com/policies/privacy-policy

Render Services, Inc. (hosting) — Hosts our backend, PostgreSQL database, and Redis cache in Frankfurt, Germany (EU). Render's DPA: render.com/dpa. Certified under EU-US Data Privacy Framework.

IONOS SE (email forwarding) — Forwards support emails. Located in Germany (EU).

We do not sell your data. We do not share your data with advertisers. We do not use your data for model training.

7. International Data Transfers

All storage (database, cache, backups) is in the EU (Frankfurt, Germany).

Data is transferred to the US only when ChatGPT processes your requests. This happens during normal app usage when the language model receives your priority data and current-week calendar summaries via tool responses. This transfer includes only pseudonymous data (priority names, goal text, deliverable names, aggregated hours, event titles and descriptions for the current week). No direct identifiers (names, emails, IP addresses) are included.

This EU-to-US transfer is governed by OpenAI's Standard Contractual Clauses (SCCs) included in their Data Processing Terms.

8. Your Rights (GDPR Art. 12–22)

You have the following rights regarding your personal data:

Access (Art. 15) — View your priorities, goals, and weekly reports directly within the app. For a full data export, contact us by email.

Rectification (Art. 16) — Update your priority names, keywords, deadlines, targets, goals, and deliverables directly within the app.

Erasure (Art. 17) — Delete individual priorities (which cascade-deletes all associated goals, deliverables, and snapshots) directly within the app. For full account deletion, contact us by email.

Restriction (Art. 18) — Retire a priority to freeze it. Retired priorities are read-only and no longer updated.

Portability (Art. 20) — Request a JSON export of your data by email.

Objection (Art. 21) — Retire or delete any priority at any time. We perform no automated profiling.

Complaint (Art. 77) — You have the right to lodge a complaint with a data protection supervisory authority.

To exercise any of these rights, contact support@priority-guard.com. We respond within 30 days.

9. How to Delete Your Data

9.1 Delete a Priority (In-App)

Ask ChatGPT to delete a specific priority, or use the Priority Guardian dashboard. This permanently deletes the priority and all associated goals, deliverables, and weekly snapshots. This action cannot be undone.

9.2 Disconnect Google Calendar (In-App)

Ask ChatGPT to disconnect your Google Calendar, or use the dashboard. This revokes our access to your calendar. Your priority data is preserved (disconnect does not mean deletion).

9.3 Delete Your Entire Account (By Email)

Contact support@priority-guard.com to request full account deletion. We delete your user record, which cascade-deletes all priority data, snapshots, goals, deliverables, connections, and consents. We respond within 30 days.

9.4 What Happens When You Delete

All associated data is permanently removed from our database. When you delete a priority, everything connected to it (goals, deliverables, weekly snapshots) is automatically deleted too. Encrypted database backups kept by our hosting provider are retained for 7 days, then permanently deleted. After that, no recovery is possible.

10. Cookies

We use a single cookie (pg_session) that is strictly necessary for the app to work. It keeps you logged in during the authorization process — that's all it does. It cannot be read by other websites or by JavaScript, and it only works over secure connections (technical details: HttpOnly, Secure, SameSite=Lax, scoped to /oauth paths). It expires after 2 years of inactivity.

We do not use tracking cookies, analytics cookies, or advertising cookies. No cookie consent banner is required because this cookie is strictly necessary for functionality per GDPR Art. 5(3) of the ePrivacy Directive.

11. Security

We take the following measures to protect your data:

Your calendar login credentials are encrypted before they are stored and can only be decrypted by our system (AES-256 encryption at rest). All data sent between your browser, our servers, and Google is encrypted in transit (TLS 1.3). Session tokens are never stored in readable form — only as cryptographic hashes.

All our servers and databases run in the EU, in Frankfurt, Germany. Backups are encrypted automatically. Temporary data expires and is deleted on a schedule.

Only one person (the developer and data controller) has access to production systems, with multi-factor authentication enabled on all accounts. No credentials are shared with anyone. All secrets are stored in an encrypted vault. When we request your calendar data from Google, we ask for the minimum fields necessary — nothing extra.

12. Google Limited-Use Compliance

Priority Guardian accesses Google Calendar data solely for its declared purpose: computing per-priority time allocation and enabling conversational semantic grouping of non-priority time. No calendar data is used for advertising, analytics, profiling, or model training. We comply with Google's Limited Use Requirements.

13. Children

Our services are not intended for children under 13 years of age, consistent with ChatGPT's age requirements. We do not knowingly collect personal data from children. If you believe a child has provided us with personal data, contact us immediately.

14. AI-Generated Content

Priority Guardian uses ChatGPT to generate weekly reports, pattern analysis, and semantic groupings of your calendar time. Important notes:

Reports are generated from your priority data and calendar time computations.

Semantic groupings of non-priority time are proposed by the language model based on event titles and descriptions — these are non-deterministic and may vary between sessions.

AI-generated analysis should be reviewed and interpreted by you. It is not financial, medical, or professional advice.

OpenAI processes your data according to their own privacy policy.

15. Changes to This Policy

We may update this Privacy Policy to reflect changes in our practices or legal requirements. Material changes will be communicated via an updated effective date at the top of this page. We encourage you to review this policy periodically.

16. Contact

For questions, concerns, or to exercise your rights:

Email: support@priority-guard.com

Website: https://www.fulfilling-productivity.com/priority-guard