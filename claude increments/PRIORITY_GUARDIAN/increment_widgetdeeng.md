Claude Code Briefing — Widget i18n (EN + DE)
Context
Priority Guardian is distributed in English-speaking markets and DACH. Widget UI strings are hardcoded in English. ChatGPT localizes conversation text automatically, but widget chrome does not — it must be localized explicitly.
window.openai.locale is already typed in src/types.ts (locale?: string). Date formatting using window.openai.locale already exists in DeadlineCard.tsx, TimeAllocationBar.tsx, and GoalSection.tsx — those are correct and must not be changed.
Backend strings (priority names, deliverable text, goal text, assistant_guidance) are user-generated or model-generated — no backend changes needed.

What to build
1. Create src/i18n.ts
Single source of truth. No external libraries.
tsconst messages = {
  en: { ... },
  de: { ... },
} as const

type Locale = keyof typeof messages
type TranslationKey = keyof typeof messages.en

export function getLocale(): Locale {
  if (typeof window === 'undefined') return 'en'
  const raw = window.openai?.locale ?? 'en'
  return raw.toLowerCase().startsWith('de') ? 'de' : 'en'
}

export function t(key: TranslationKey): string {
  const locale = getLocale()
  return messages[locale][key] ?? messages['en'][key]
}
getLocale() requirements:

Guard typeof window === 'undefined' first — required for tests (Node), SSR, CI
Must handle: undefined, "de-DE", "de-AT", "de-CH", "de", "DE-DE" (uppercase) — all normalize to "de". Everything else → "en"
Must be called inside functions, never at module import time

t() requirements:

Runtime fallback to messages['en'][key] — prevents crash if a key is missing in a locale
TypeScript TranslationKey type ensures invalid keys are caught at compile time

messages must stay as const — required for TypeScript key safety.

2. Translation map
All keys must exist in both locales. Use exactly these strings:
KeyENDEloadingLoading…Lädt…noDataUnable to load dashboardDashboard konnte nicht geladen werdennoPrioritiesNo priorities yetNoch keine Prioritäten vorhandennoPrioritiesHintAsk the assistant to help you set up your top priorities.Bitte ChatGPT, dir beim Einrichten deiner Prioritäten zu helfenaddNewPriorityAdd a new priorityNeue Priorität hinzufügenaddPriorityTitleAdd PriorityPriorität anlegenwhatToTrackWhat do you want to track?Was möchtest du tracken?namePlaceholdere.g., Ship v1.0, Client outreachz. B. v1.0 launchen, KundenakquisewhatKindOfPriorityWhat kind of priority?Welche Art von Priorität?deadlineTypeDeadlineDeadlinedeadlineTypeHintHas a hard end dateHat ein festes EnddatumflexibleTypeFlexibleFlexibelflexibleTypeHintOngoing weekly commitmentWöchentliches EngagementdeadlinePriorityDeadline PriorityPriorität mit FälligkeitsdatumflexiblePriorityFlexible PriorityFlexible PrioritätdeadlineLabelDeadlineDeadlineweeklyHourTargetWeekly Hour TargetWochenziel (Stunden)checkpointDateCheckpoint DateCheckpoint-DatuminitialGoalInitial GoalErstes ZielinitialGoalPlaceholderWhat do you want to achieve in ~1 month?Was möchtest du in ~1 Monat erreichen?nextNextWeitercancelCancelAbbrechencreatePriorityCreate PriorityPriorität anlegencreatingCreating…Wird erstellt…saveSaveSpeicherndoneDoneFertigdeleteDeleteLöschendeletingDeleting…Wird gelöscht…disconnectDisconnectVerbindung trennendisconnectConfirmDisconnect?Verbindung trennen?disconnectYesYesJadisconnectNoNoNeinconnectConnectVerbindenconnectingConnecting…Wird verbunden…checkStatusCheck statusStatus prüfencheckingChecking…Wird geprüft…googleCalendarGoogle CalendarGoogle CalendarcalendarConnectedGoogle Calendar connectedMit Google Calendar verbundencalendarInstructionSuffixto your calendar event titles to track time toward each priority.in den Titel deiner Kalendertermine einawaitingOAuthComplete the authorization in the opened window, then click "Check status".Autorisierung im geöffneten Fenster abschließen, dann „Status prüfen" klickenfailedToConnectFailed to start connection. Please try again.Verbindung konnte nicht hergestellt werdenfailedToDisconnectFailed to disconnect. Please try again.Verbindung konnte nicht hergestellt werdenconnectionNotAvailableConnection not availableVerbindung nicht verfügbarnameRequiredName is requiredName ist erforderlichdeadlineRequiredDeadline is requiredDeadline ist erforderlichweeklyHoursRequiredWeekly hour target is requiredWochenziel ist erforderlichweeklyHoursPositiveWeekly hour target must be greater than 0Wochenziel muss größer als 0 seincheckpointRequiredCheckpoint date is requiredCheckpoint-Datum ist erforderlichinitialGoalRequiredInitial goal is requiredErstes Ziel ist erforderlichcouldntSaveCouldn't save. Try again.Speichern fehlgeschlagenfailedToCreateFailed to create priorityPriorität konnte nicht angelegt werdenaddDeliverableAdd deliverableLieferergebnis hinzufügendeliverableNamePlaceholderDeliverable nameName des LieferergebnissesdeliverableNameRequiredName is requiredName ist erforderlichaddingAdding…Wird hinzugefügt…addAddHinzufügene2eDeliverablesE2E DeliverablesE2E LieferergebnissedeliverablesDoneDeliverables doneErledigte LieferergebnissenoDeliverablesHintWithout E2E deliverables, you only see hours spent — add them to track real progress.Ohne E2E Lieferergebnisse siehst du nur investierte StundenchangesAutoSaveChanges save automaticallyÄnderungen werden automatisch gespeichertoneMonthGoal1-Month GoalZiel (1 Monat)oneMonthGoals1-Month GoalsZiele (1 Monat)noGoalsYetNo goals yetNoch keine Ziele vorhandenaddGoalAdd goalZiel hinzufügengoalPlaceholderEnter goal…Ziel eingeben…bybybistrackingInProgressTracking in progress — your average builds after this week.Tracking läuft — wird ab nächster Woche berechnetofWeeklyTargetOnAvgof weekly target on avgvom Wochenziel im DurchschnitttimeAllocationHeadingTime allocation this weekZeitaufteilung diese WochenoTrackedHoursTime allocation: no tracked hours this weekZeitaufteilung: Keine erfassten Stunden diese WocherefreshCalendarRefresh calendar dataKalenderdaten neu ladenopenFullDashboardOpen full dashboardDashboard öffnenmyPrioritiesMy prioritiesMeine PrioritätenminimizeMinimizeMinimierengoBackGo backZurückdDaysLeft{n}d leftNoch {n} TagedueTodayDue todayHeute fälligdDaysOverdue{n}d overdue{n} Tage überfälligweekStreak{n}w streak{n} Wochen Serie
Interpolated strings (dDaysLeft, dDaysOverdue, weekStreak): t() returns the raw string with {n} literal. Callers replace inline: t('dDaysLeft').replace('{n}', String(days)). No templating helper needed. All interpolated keys must contain {n} and nothing else — no JSX, no HTML inside any translation string.
calendarInstructionSuffix: The calendar instruction in ConnectionStatus.tsx is already multi-part JSX — <strong>P1</strong>, <strong>P2</strong>, <strong>P3</strong> are separate elements with {' '} spacers. Replace only the trailing text node with t('calendarInstructionSuffix'). Do not alter the <strong> structure. The rendered output must remain identical to the current JSX.

3. Files to modify
FileWhat changessrc/App.tsxLoading..., No Priorities Yet, assistant hint textsrc/components/AddDeliverableInput.tsxButton text, placeholder, error messagesrc/components/AddPriorityForm.tsxAll labels, placeholders, button text, type card text, error messagessrc/components/CalendarConnectionMinimal.tsxConnected labelsrc/components/ConnectionStatus.tsxAll button states, confirmation text, instruction suffix, error messages, OAuth awaiting textsrc/components/DeadlineCard.tsxE2E Deliverables, Deliverables done, no-deliverables hint, Changes save automatically, Done, days-left display, Deadline field labelsrc/components/DeleteConfirmation.tsxCancel, Delete, Deleting…, subtitle — title is dynamic (Delete ${calendarKeyword}: ${itemName}?), translate static parts only, keep dynamic values as-issrc/components/DeliverableItem.tsxError messagessrc/components/ExpandButton.tsxButton labelsrc/components/FlexibleCard.tsxField labels, Changes save automatically, Done, Tracking in progress…, of weekly target on avgsrc/components/FullscreenHeader.tsxMy priorities, Minimizesrc/components/GoalSection.tsxSection heading, by, No goals yet, Add goal, input placeholdersrc/components/GoalItem.tsxError messagessrc/components/TimeAllocationBar.tsxSection heading, aria-label for no tracked hours, refresh button aria-label
Do NOT change:

P1, P2, P3 — functional, language-agnostic
Date formatting — already uses window.openai.locale with Intl correctly
User-entered content (priority names, deliverable names, goal text)
window.openai.locale type declaration in types.ts


Pre-deployment
Read OPERATIONS_PREDEPLOYMENT.md before committing. Widget-only — no backend changes, no migrations. Build step required: npm run build inside widget-react/ before deploy.

Tests
Unit — src/__tests__/i18n.test.ts (new file)
Window mock required. In Node, window does not exist. Every test that calls getLocale() or t() must mock global.window in beforeEach:
tsbeforeEach(() => {
  // @ts-ignore
  global.window = { openai: { locale: 'en-US' } }
})

afterEach(() => {
  // @ts-ignore
  delete global.window
})
TestSetupExpectedtypeof window === 'undefined'Delete global.window entirelyReturns 'en'window.openai undefinedglobal.window = {}Returns 'en'"en-US"locale: 'en-US'EN strings"fr-FR"locale: 'fr-FR'EN strings (fallback)"de-DE"locale: 'de-DE'DE strings"de-AT"locale: 'de-AT'DE strings"de-CH"locale: 'de-CH'DE strings"de" (bare)locale: 'de'DE strings"DE-DE" (uppercase)locale: 'DE-DE'DE stringsAll keys present in both locales—No missing keys between en and deTypeScript: invalid key—Compile error
Integration — existing test files
Add locale assertions to App.test.tsx: verify "Lädt…" renders when locale is "de-DE", "Loading…" for "en-US". Apply the same global.window mock pattern. Keep additions minimal — do not rewrite existing tests. Sonnet 4.6Claude is AI and can make mistakes. Please double-check responses.