/**
 * Priority Guardian Widget - Internationalization (EN + DE)
 *
 * Copied from ChatGPT widget. Adapted for MCP Apps:
 * - Locale set via setLocale() from App.tsx after app.connect()
 * - Falls back to 'en' if locale not set
 */

const messages = {
  en: {
    // Loading states
    loading: 'Loading...',
    noData: 'Unable to load dashboard',

    // Empty states
    noPriorities: 'No priorities yet',
    noPrioritiesHint: 'Ask the assistant to help you set up your top priorities.',

    // Deliverables
    e2eDeliverables: 'E2E Deliverables',
    deliverablesDone: 'Deliverables done',
    noDeliverablesHint: 'Without E2E deliverables, you only see hours spent - add them to track real progress.',

    // Goals
    oneMonthGoal: '1-Month Goal',
    oneMonthGoals: '1-Month Goals',
    noGoalsYet: 'No goals yet',
    by: 'by',

    // Flexible card
    trackingInProgress: 'Tracking in progress - your average builds after this week.',
    ofWeeklyTargetOnAvg: 'of weekly target on avg',

    // Time allocation
    timeAllocationHeading: 'Time allocation this week',
    noTrackedHours: 'Time allocation: no tracked hours this week',
    timeAllocationPrefix: 'Time allocation: ',

    // Days interpolated
    dDaysLeft: '{n} days left',
    dueToday: 'Due today',
    dDaysOverdue: '{n} days overdue',
    weekStreak: '{n}w streak',

    // HourRing
    hoursUnit: 'hours',
    hourRingAria: '{hours} of {target} hours this week',

    // Pie chart labels
    otherLabel: 'Other',
    uncategorized: 'Uncategorized',

    // Connection
    googleCalendar: 'Google Calendar',
    calendarConnected: 'Google Calendar connected',
    calendarNotConnected: 'Google Calendar not connected',
  },
  de: {
    // Loading states
    loading: 'Ladt...',
    noData: 'Dashboard konnte nicht geladen werden',

    // Empty states
    noPriorities: 'Noch keine Prioritaten vorhanden',
    noPrioritiesHint: 'Bitte den Assistenten, dir beim Einrichten deiner Prioritaten zu helfen',

    // Deliverables
    e2eDeliverables: 'E2E Lieferergebnisse',
    deliverablesDone: 'Erledigte Lieferergebnisse',
    noDeliverablesHint: 'Ohne E2E Lieferergebnisse siehst du nur investierte Stunden',

    // Goals
    oneMonthGoal: 'Ziel (1 Monat)',
    oneMonthGoals: 'Ziele (1 Monat)',
    noGoalsYet: 'Noch keine Ziele vorhanden',
    by: 'bis',

    // Flexible card
    trackingInProgress: 'Tracking lauft - wird ab nachster Woche berechnet',
    ofWeeklyTargetOnAvg: 'vom Wochenziel im Durchschnitt',

    // Time allocation
    timeAllocationHeading: 'Zeitaufteilung diese Woche',
    noTrackedHours: 'Zeitaufteilung: Keine erfassten Stunden diese Woche',
    timeAllocationPrefix: 'Zeitaufteilung: ',

    // Days interpolated
    dDaysLeft: 'Noch {n} Tage',
    dueToday: 'Heute fallig',
    dDaysOverdue: '{n} Tage uberfallig',
    weekStreak: '{n} Wochen Serie',

    // HourRing
    hoursUnit: 'Stunden',
    hourRingAria: '{hours} von {target} Stunden diese Woche',

    // Pie chart labels
    otherLabel: 'Sonstige',
    uncategorized: 'Nicht kategorisiert',

    // Connection
    googleCalendar: 'Google Calendar',
    calendarConnected: 'Mit Google Calendar verbunden',
    calendarNotConnected: 'Google Calendar nicht verbunden',
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
