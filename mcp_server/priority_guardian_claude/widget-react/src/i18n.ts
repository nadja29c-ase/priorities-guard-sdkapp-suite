/**
 * Priority Guardian Widget — Internationalization (EN + DE)
 *
 * Copied from ChatGPT widget. Adapted for MCP Apps:
 * - Locale set via setLocale() from App.tsx after app.connect()
 * - Falls back to 'en' if locale not set
 */

const messages = {
  en: {
    // Loading states
    loading: 'Loading…',
    noData: 'Unable to load dashboard',

    // Empty states
    noPriorities: 'No priorities yet',
    noPrioritiesHint: 'Ask the assistant to help you set up your top priorities.',

    // Add priority flow
    addNewPriority: 'Add a new priority',
    addPriorityTitle: 'Add Priority',
    whatToTrack: 'What do you want to track?',
    namePlaceholder: 'e.g., Ship v1.0, Client outreach',
    whatKindOfPriority: 'What kind of priority?',
    deadlineType: 'Deadline',
    deadlineTypeHint: 'Has a hard end date',
    flexibleType: 'Flexible',
    flexibleTypeHint: 'Ongoing weekly commitment',
    deadlinePriority: 'Deadline Priority',
    flexiblePriority: 'Flexible Priority',
    deadlineLabel: 'Deadline',
    weeklyHourTarget: 'Weekly Hour Target',
    checkpointDate: 'Checkpoint Date',
    initialGoal: 'Initial Goal',
    initialGoalPlaceholder: 'What do you want to achieve in ~1 month?',
    next: 'Next',
    cancel: 'Cancel',
    createPriority: 'Create Priority',
    creating: 'Creating…',

    // Common actions
    save: 'Save',
    done: 'Done',
    delete: 'Delete',
    deleting: 'Deleting…',
    clickToEdit: 'click to edit',
    edit: 'Edit',
    editPriority: 'Edit priority: {name}',
    hourTargetPlaceholder: 'e.g., 10',

    // Connection status
    disconnect: 'Disconnect',
    disconnectConfirm: 'Disconnect?',
    disconnectYes: 'Yes',
    disconnectNo: 'No',
    connect: 'Connect',
    connecting: 'Connecting…',
    checkStatus: 'Check status',
    checking: 'Checking…',
    googleCalendar: 'Google Calendar',
    calendarConnected: 'Google Calendar connected',
    calendarInstructionPrefix: 'Add',
    calendarInstructionOr: 'or',
    calendarInstructionSuffix: 'to your calendar event titles to track time toward each priority.',
    awaitingOAuth: 'Complete the authorization in the opened window, then click "Check status".',
    failedToConnect: 'Failed to start connection. Please try again.',
    failedToDisconnect: 'Failed to disconnect. Please try again.',
    connectionNotAvailable: 'Connection not available',
    sessionExpiredRetry: 'Session expired. Open a fresh Priority Guardian conversation to reconnect.',
    widgetSessionExpired: 'This dashboard is from a previous session.',
    widgetSessionExpiredHint: 'Start a new conversation with Priority Guardian to interact with your dashboard.',
    // Distinct from the two above: a reported connection failure, not an aged widget.
    widgetConnectionFailed: 'Could not connect to Priority Guardian.',
    widgetConnectionFailedHint: 'Check your connection and reload, or start a new conversation.',
    // NOTE: the generic "payload empty or unusable" case (§5.4) deliberately reuses the
    // existing `noData` key rather than adding a synonym. A second key for one meaning
    // drifts across two locales.
    failedToRefresh: 'Failed to refresh. Please try again.',
    // Button label, not a message. Checked first: couldntSave and failedToRefresh are
    // sentences, refreshCalendar is calendar-specific — none works as a generic control.
    retry: 'Try again',

    // Validation errors
    nameRequired: 'Name is required',
    deadlineRequired: 'Deadline is required',
    weeklyHoursRequired: 'Weekly hour target is required',
    weeklyHoursPositive: 'Weekly hour target must be greater than 0',
    checkpointRequired: 'Checkpoint date is required',
    initialGoalRequired: 'Initial goal is required',
    couldntSave: "Couldn't save. Try again.",
    failedToCreate: 'Failed to create priority',

    // Deliverables
    addDeliverable: 'Add deliverable',
    deliverableNamePlaceholder: 'Deliverable name',
    deliverableNameRequired: 'Name is required',
    adding: 'Adding…',
    add: 'Add',
    e2eDeliverables: 'E2E Deliverables',
    deliverablesDone: 'Deliverables done',
    noDeliverablesHint: 'Without E2E deliverables, you only see hours spent — add them to track real progress.',
    changesAutoSave: 'Changes save automatically',

    // Goals
    oneMonthGoal: '1-Month Goal',
    oneMonthGoals: '1-Month Goals',
    noGoalsYet: 'No goals yet',
    addGoal: 'Add goal',
    goalPlaceholder: 'Enter goal…',
    by: 'by',
    failedToAddGoal: 'Failed to add goal',

    // Flexible card
    trackingInProgress: 'Tracking in progress — your average builds after this week.',
    ofWeeklyTargetOnAvg: 'of weekly target on avg',

    // Time allocation
    timeAllocationHeading: 'Time allocation this week',
    noTrackedHours: 'Time allocation: no tracked hours this week',
    timeAllocationPrefix: 'Time allocation: ',
    refreshCalendar: 'Refresh calendar data',

    // Navigation
    openDashboardToEdit: 'Open full dashboard to edit',
    openFullDashboard: 'Open full dashboard',
    expandDashboard: 'Expand dashboard',
    fullscreenUnavailable: 'Fullscreen mode is unavailable',
    dashboardTitle: 'My Priorities',
    myPriorities: 'My priorities',
    minimize: 'Minimize',
    minimizeToInline: 'Minimize to inline card',
    minimizeDashboard: 'Minimize dashboard',
    goBack: 'Go back',

    // Delete confirmation
    deleteWithKeyword: 'Delete {keyword}: {name}?',
    deleteItem: 'Delete {name}?',
    deleteSubtitlePriority: 'This will also delete all deliverables. This cannot be undone.',
    deleteSubtitleDeliverable: 'This cannot be undone.',
    confirmDeleteType: 'Confirm delete {type}',

    // Inline delete/remove
    removeItem: 'Remove "{name}"?',
    yes: 'Yes',
    no: 'No',
    confirmRemove: 'Confirm remove',
    cancelRemove: 'Cancel remove',

    // DeliverableItem accessibility
    markAsDone: 'Mark "{name}" as done',
    markAsNotDone: 'Mark "{name}" as not done',
    doubleClickToEdit: 'Double-click to edit',
    editItem: 'Edit "{name}"',
    deleteItemAction: 'Delete "{name}"',

    // GoalItem accessibility
    markAsAchieved: 'Mark "{name}" as achieved',
    markAsNotAchieved: 'Mark "{name}" as not achieved',
    editGoalText: 'Edit goal text',

    // GoalSection accessibility
    goalsList: 'Goals list',
    newGoalText: 'New goal text',

    // FlexibleCard accessibility
    priorityNameLabel: 'Priority name',

    // Interpolated (caller replaces {n})
    dDaysLeft: '{n} days left',
    dueToday: 'Due today',
    dDaysOverdue: '{n} days overdue',
    weekStreak: '{n}w streak',

    // Pie chart, HourRing, KeywordPicker
    noTimeData: 'No time data to display',
    timeAllocationTitle: 'Time Allocation',
    breakdown: 'Breakdown: ',
    totalHours: 'total',
    hoursUnit: 'hours',
    pieChartAria: 'Pie chart showing {hours} total hours across {n} categories',
    breakdownCta: 'Ask the assistant to break down any category to see where the time went.',
    hourRingAria: '{hours} of {target} hours this week',
    badgeLabel: 'Badge:',
    swapWith: 'Swap with {name}',
    currentKeyword: 'Current keyword',
    switchTo: 'Switch to',
    willSwapWith: 'will swap with {name}',

    // PieChart sentinel labels (from backend data)
    otherLabel: 'Other',
    uncategorized: 'Uncategorized',
    unnamed: 'Unnamed',

    // Keyword change confirmation
    keywordChangeTitle: 'Change badge?',
    keywordChangeBody: 'Hours already tagged {oldKeyword} this week will shift to whichever priority now holds {oldKeyword} — current week tracking will be off.',
    keywordChangeBestTime: 'Best time to change: Monday morning, before tagging any events.',
    keywordChangeHowTo: 'Tag calendar events with {keyword} to track time toward this priority.',
    keywordChangeConfirm: 'Change',
    keywordChangeCancel: 'Cancel',
    keywordChangeInline: 'Change from {oldKeyword} to {newKeyword}?',
  },
  de: {
    // Loading states
    loading: 'Lädt…',
    noData: 'Dashboard konnte nicht geladen werden',

    // Empty states
    noPriorities: 'Noch keine Prioritäten vorhanden',
    noPrioritiesHint: 'Bitte den Assistenten, dir beim Einrichten deiner Prioritäten zu helfen',

    // Add priority flow
    addNewPriority: 'Neue Priorität hinzufügen',
    addPriorityTitle: 'Priorität anlegen',
    whatToTrack: 'Was möchtest du tracken?',
    namePlaceholder: 'z. B. v1.0 launchen, Kundenakquise',
    whatKindOfPriority: 'Welche Art von Priorität?',
    deadlineType: 'Deadline',
    deadlineTypeHint: 'Hat ein festes Enddatum',
    flexibleType: 'Flexibel',
    flexibleTypeHint: 'Wöchentliches Engagement',
    deadlinePriority: 'Priorität mit Fälligkeitsdatum',
    flexiblePriority: 'Flexible Priorität',
    deadlineLabel: 'Fällig am:',
    weeklyHourTarget: 'Wochenziel (Stunden)',
    checkpointDate: 'Checkpoint-Datum',
    initialGoal: 'Erstes Ziel',
    initialGoalPlaceholder: 'Was möchtest du in ~1 Monat erreichen?',
    next: 'Weiter',
    cancel: 'Abbrechen',
    createPriority: 'Priorität anlegen',
    creating: 'Wird erstellt…',

    // Common actions
    save: 'Speichern',
    done: 'Fertig',
    delete: 'Löschen',
    deleting: 'Wird gelöscht…',
    clickToEdit: 'zum Bearbeiten klicken',
    edit: 'Bearbeiten',
    editPriority: 'Priorität bearbeiten: {name}',
    hourTargetPlaceholder: 'z. B. 10',

    // Connection status
    disconnect: 'Verbindung trennen',
    disconnectConfirm: 'Verbindung trennen?',
    disconnectYes: 'Ja',
    disconnectNo: 'Nein',
    connect: 'Verbinden',
    connecting: 'Wird verbunden…',
    checkStatus: 'Status prüfen',
    checking: 'Wird geprüft…',
    googleCalendar: 'Google Calendar',
    calendarConnected: 'Mit Google Calendar verbunden',
    calendarInstructionPrefix: 'Füge',
    calendarInstructionOr: 'oder',
    calendarInstructionSuffix: 'in den Titel deiner Kalendertermine ein',
    awaitingOAuth: 'Autorisierung im geöffneten Fenster abschließen, dann „Status prüfen" klicken',
    failedToConnect: 'Verbindung konnte nicht hergestellt werden',
    failedToDisconnect: 'Verbindung konnte nicht getrennt werden',
    connectionNotAvailable: 'Verbindung nicht verfügbar',
    sessionExpiredRetry: 'Sitzung abgelaufen. Starte ein neues Priority Guardian Gespräch, um dich erneut zu verbinden.',
    widgetSessionExpired: 'Dieses Dashboard stammt aus einer früheren Sitzung.',
    widgetSessionExpiredHint: 'Starte ein neues Gespräch mit Priority Guardian, um mit deinem Dashboard zu interagieren.',
    widgetConnectionFailed: 'Verbindung zu Priority Guardian fehlgeschlagen.',
    widgetConnectionFailedHint: 'Prüfe deine Verbindung und lade neu, oder starte ein neues Gespräch.',
    failedToRefresh: 'Aktualisierung fehlgeschlagen. Bitte versuche es erneut.',
    retry: 'Erneut versuchen',

    // Validation errors
    nameRequired: 'Name ist erforderlich',
    deadlineRequired: 'Deadline ist erforderlich',
    weeklyHoursRequired: 'Wochenziel ist erforderlich',
    weeklyHoursPositive: 'Wochenziel muss größer als 0 sein',
    checkpointRequired: 'Checkpoint-Datum ist erforderlich',
    initialGoalRequired: 'Erstes Ziel ist erforderlich',
    couldntSave: 'Speichern fehlgeschlagen',
    failedToCreate: 'Priorität konnte nicht angelegt werden',

    // Deliverables
    addDeliverable: 'Lieferergebnis hinzufügen',
    deliverableNamePlaceholder: 'Name des Lieferergebnisses',
    deliverableNameRequired: 'Name ist erforderlich',
    adding: 'Wird hinzugefügt…',
    add: 'Hinzufügen',
    e2eDeliverables: 'E2E Lieferergebnisse',
    deliverablesDone: 'Erledigte Lieferergebnisse',
    noDeliverablesHint: 'Ohne E2E Lieferergebnisse siehst du nur investierte Stunden',
    changesAutoSave: 'Änderungen werden automatisch gespeichert',

    // Goals
    oneMonthGoal: 'Ziel (1 Monat)',
    oneMonthGoals: 'Ziele (1 Monat)',
    noGoalsYet: 'Noch keine Ziele vorhanden',
    addGoal: 'Ziel hinzufügen',
    goalPlaceholder: 'Ziel eingeben…',
    by: 'bis',
    failedToAddGoal: 'Ziel konnte nicht hinzugefügt werden',

    // Flexible card
    trackingInProgress: 'Tracking läuft — wird ab nächster Woche berechnet',
    ofWeeklyTargetOnAvg: 'vom Wochenziel im Durchschnitt',

    // Time allocation
    timeAllocationHeading: 'Zeitaufteilung diese Woche',
    noTrackedHours: 'Zeitaufteilung: Keine erfassten Stunden diese Woche',
    timeAllocationPrefix: 'Zeitaufteilung: ',
    refreshCalendar: 'Kalenderdaten neu laden',

    // Navigation
    openDashboardToEdit: 'Vollständiges Dashboard öffnen zum Bearbeiten',
    openFullDashboard: 'Dashboard öffnen',
    expandDashboard: 'Dashboard erweitern',
    fullscreenUnavailable: 'Vollbildmodus nicht verfügbar',
    dashboardTitle: 'Meine Prioritäten',
    myPriorities: 'Meine Prioritäten',
    minimize: 'Minimieren',
    minimizeToInline: 'Zu Inline-Ansicht minimieren',
    minimizeDashboard: 'Dashboard minimieren',
    goBack: 'Zurück',

    // Delete confirmation
    deleteWithKeyword: '{keyword}: {name} löschen?',
    deleteItem: '{name} löschen?',
    deleteSubtitlePriority: 'Alle Lieferergebnisse werden ebenfalls gelöscht. Dies kann nicht rückgängig gemacht werden.',
    deleteSubtitleDeliverable: 'Dies kann nicht rückgängig gemacht werden.',
    confirmDeleteType: '{type} löschen bestätigen',

    // Inline delete/remove
    removeItem: '„{name}" entfernen?',
    yes: 'Ja',
    no: 'Nein',
    confirmRemove: 'Entfernen bestätigen',
    cancelRemove: 'Entfernen abbrechen',

    // DeliverableItem accessibility
    markAsDone: '„{name}" als erledigt markieren',
    markAsNotDone: '„{name}" als nicht erledigt markieren',
    doubleClickToEdit: 'Doppelklick zum Bearbeiten',
    editItem: '„{name}" bearbeiten',
    deleteItemAction: '„{name}" löschen',

    // GoalItem accessibility
    markAsAchieved: '„{name}" als erreicht markieren',
    markAsNotAchieved: '„{name}" als nicht erreicht markieren',
    editGoalText: 'Zieltext bearbeiten',

    // GoalSection accessibility
    goalsList: 'Zielliste',
    newGoalText: 'Neues Ziel',

    // FlexibleCard accessibility
    priorityNameLabel: 'Name der Priorität',

    // Interpolated (caller replaces {n})
    dDaysLeft: 'Noch {n} Tage',
    dueToday: 'Heute fällig',
    dDaysOverdue: '{n} Tage überfällig',
    weekStreak: '{n} Wochen Serie',

    // Pie chart, HourRing, KeywordPicker
    noTimeData: 'Keine Zeitdaten vorhanden',
    timeAllocationTitle: 'Zeitaufteilung',
    breakdown: 'Aufschlüsselung: ',
    totalHours: 'gesamt',
    hoursUnit: 'Stunden',
    pieChartAria: 'Kreisdiagramm mit {hours} Gesamtstunden in {n} Kategorien',
    breakdownCta: 'Bitte den Assistenten, eine Kategorie aufzuschlüsseln, um zu sehen, wie die Zeit genutzt wurde.',
    hourRingAria: '{hours} von {target} Stunden diese Woche',
    badgeLabel: 'Schlagwort:',
    swapWith: 'Tauschen mit {name}',
    currentKeyword: 'Aktuelles Schlagwort',
    switchTo: 'Wechseln zu',
    willSwapWith: 'tauscht mit {name}',

    // PieChart sentinel labels (from backend data)
    otherLabel: 'Sonstige',
    uncategorized: 'Nicht kategorisiert',
    unnamed: 'Unbenannt',

    // Keyword change confirmation
    keywordChangeTitle: 'Schlagwort ändern?',
    keywordChangeBody: 'Kalendertermine mit {oldKeyword} aus dieser Woche bleiben der Priorität zugeordnet, die {oldKeyword} danach trägt — dein Tracking für diese Woche stimmt dann nicht mehr.',
    keywordChangeBestTime: 'Am besten montags morgens wechseln, bevor du neue Termine anlegst.',
    keywordChangeHowTo: 'Füge {keyword} in deine Kalendertitel ein, um Zeit für diese Priorität zu tracken.',
    keywordChangeConfirm: 'Ändern',
    keywordChangeCancel: 'Abbrechen',
    keywordChangeInline: 'Von {oldKeyword} zu {newKeyword} wechseln?',
  },
} as const

type Locale = keyof typeof messages
type TranslationKey = keyof typeof messages['en']

// Module-level locale state (set by App.tsx after MCP App connects)
let currentLocale: Locale = 'en'

/**
 * Set the locale from MCP Apps host context.
 * Called by App.tsx after app.connect().
 */
export function setLocale(locale: string): void {
  // Normalize underscores to hyphens (iOS sends en_DE, BCP 47 uses en-DE)
  const normalized = locale.replace(/_/g, '-')
  currentLocale = normalized.toLowerCase().startsWith('de') ? 'de' : 'en'
}

/**
 * Get the current locale.
 */
export function getLocale(): Locale {
  return currentLocale
}

/**
 * Get raw locale string for Intl formatting.
 */
export function getRawLocale(): string {
  return currentLocale === 'de' ? 'de-DE' : 'en-US'
}

/**
 * Get a translated string by key.
 * Falls back to English if key is missing in current locale.
 * Supports interpolation: t('dDaysLeft', { n: 5 }) -> "5 days left"
 */
export function t(key: TranslationKey, vars?: Record<string, string | number>): string {
  let str: string = messages[currentLocale][key] ?? messages['en'][key]
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      str = str.replaceAll(`{${k}}`, String(v))
    }
  }
  return str
}

export type { TranslationKey }

// Dev-mode parity check: warn if DE is missing any EN keys
if (import.meta.env.DEV) {
  const enKeys = Object.keys(messages.en) as TranslationKey[]
  const deKeys = new Set(Object.keys(messages.de))
  for (const k of enKeys) {
    if (!deKeys.has(k)) {
      console.warn(`[i18n] Missing DE key: "${k}"`)
    }
  }
}
