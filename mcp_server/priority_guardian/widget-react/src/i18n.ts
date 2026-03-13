/**
 * Priority Guardian Widget — Internationalization (EN + DE)
 *
 * Single source of truth for all UI strings. No external libraries.
 * Backend strings (priority names, deliverables, goals) are user/model-generated.
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
    openFullDashboard: 'Open full dashboard',
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
    breakdownCta: 'Ask ChatGPT to break down any category to see where the time went.',
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
  },
  de: {
    // Loading states
    loading: 'Lädt…',
    noData: 'Dashboard konnte nicht geladen werden',

    // Empty states
    noPriorities: 'Noch keine Prioritäten vorhanden',
    noPrioritiesHint: 'Bitte ChatGPT, dir beim Einrichten deiner Prioritäten zu helfen',

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
    openFullDashboard: 'Dashboard öffnen',
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
    breakdownCta: 'Bitte ChatGPT, eine Kategorie aufzuschlüsseln, um zu sehen, wie die Zeit genutzt wurde.',
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
    keywordChangeTitle: 'Badge ändern?',
    keywordChangeBody: 'Bereits mit {oldKeyword} getaggte Termine dieser Woche werden der Priorität zugeordnet, die jetzt {oldKeyword} trägt — das aktuelle Tracking stimmt dann nicht mehr.',
    keywordChangeBestTime: 'Bester Zeitpunkt: Montag früh, bevor du Termine für die Woche erstellst.',
    keywordChangeHowTo: 'Tagge Kalendertermine mit {keyword}, um Zeit für diese Priorität zu erfassen.',
    keywordChangeConfirm: 'Ändern',
    keywordChangeCancel: 'Abbrechen',
  },
} as const

type Locale = keyof typeof messages
type TranslationKey = keyof typeof messages['en']

/**
 * Get the current locale from window.openai.locale.
 * Returns 'de' for any German variant, 'en' for everything else.
 * Must be called inside functions, not at module import time.
 *
 * Note: iOS may return underscored locales (e.g., "en_DE"). We normalize
 * to BCP 47 (hyphens) for consistency, though this function only checks
 * the language prefix so underscores don't affect it directly.
 */
export function getLocale(): Locale {
  if (typeof window === 'undefined') return 'en'
  // Normalize underscores to hyphens (iOS sends en_DE, BCP 47 uses en-DE)
  const raw = (window.openai?.locale ?? 'en').replace(/_/g, '-')
  return raw.toLowerCase().startsWith('de') ? 'de' : 'en'
}

/**
 * Get a translated string by key.
 * Falls back to English if key is missing in current locale.
 */
export function t(key: TranslationKey): string {
  const locale = getLocale()
  return messages[locale][key] ?? messages['en'][key]
}

export type { TranslationKey }
