/**
 * i18n Unit Tests
 * Tests locale detection, translation lookup, and fallback behavior.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { getLocale, t } from '../i18n'

describe('i18n', () => {
  // Store original window.openai
  let originalOpenai: typeof window.openai

  beforeEach(() => {
    // Save original value
    originalOpenai = window.openai
  })

  afterEach(() => {
    // Restore original value
    window.openai = originalOpenai
  })

  describe('getLocale', () => {
    it('returns "en" when window is undefined (SSR)', () => {
      const originalWindow = globalThis.window
      delete (globalThis as Record<string, unknown>).window
      try {
        expect(getLocale()).toBe('en')
      } finally {
        (globalThis as Record<string, unknown>).window = originalWindow
      }
    })

    it('returns "en" when window.openai is undefined', () => {
      window.openai = undefined as unknown as typeof window.openai
      expect(getLocale()).toBe('en')
    })

    it('returns "en" when window.openai.locale is undefined', () => {
      window.openai = {} as typeof window.openai
      expect(getLocale()).toBe('en')
    })

    it('returns "en" for English locale', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(getLocale()).toBe('en')
    })

    it('returns "de" for German locale (de-DE)', () => {
      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(getLocale()).toBe('de')
    })

    it('returns "de" for German locale (de-AT)', () => {
      window.openai = { locale: 'de-AT' } as typeof window.openai
      expect(getLocale()).toBe('de')
    })

    it('returns "de" for German locale (de-CH)', () => {
      window.openai = { locale: 'de-CH' } as typeof window.openai
      expect(getLocale()).toBe('de')
    })

    it('returns "de" for simple "de" locale', () => {
      window.openai = { locale: 'de' } as typeof window.openai
      expect(getLocale()).toBe('de')
    })

    it('returns "en" for French locale (not supported)', () => {
      window.openai = { locale: 'fr-FR' } as typeof window.openai
      expect(getLocale()).toBe('en')
    })

    it('handles case-insensitive locale detection', () => {
      window.openai = { locale: 'DE-DE' } as typeof window.openai
      expect(getLocale()).toBe('de')
    })
  })

  describe('t (translation function)', () => {
    it('returns English string for English locale', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(t('loading')).toBe('Loading…')
    })

    it('returns German string for German locale', () => {
      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(t('loading')).toBe('Lädt…')
    })

    it('returns English fallback when locale is undefined', () => {
      window.openai = {} as typeof window.openai
      expect(t('cancel')).toBe('Cancel')
    })

    it('returns interpolation-ready strings', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(t('dDaysLeft')).toBe('{n} days left')
      expect(t('dDaysLeft').replace('{n}', '5')).toBe('5 days left')
    })

    it('returns German interpolation-ready strings', () => {
      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(t('dDaysLeft')).toBe('Noch {n} Tage')
      expect(t('dDaysLeft').replace('{n}', '5')).toBe('Noch 5 Tage')
    })

    it('handles all common keys', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai

      // Test a sampling of keys to ensure they exist
      const keys = [
        'noPriorities',
        'addNewPriority',
        'cancel',
        'done',
        'googleCalendar',
        'nameRequired',
        'deliverablesDone',
        'oneMonthGoal',
        'trackingInProgress',
        'timeAllocationHeading',
        'openFullDashboard',
        'deleteItem',
        'removeItem',
        'yes',
        'no',
      ] as const

      for (const key of keys) {
        const value = t(key)
        expect(typeof value).toBe('string')
        expect(value.length).toBeGreaterThan(0)
      }
    })

    it('handles German translations for all common keys', () => {
      window.openai = { locale: 'de-DE' } as typeof window.openai

      // Test German versions exist and are different from English where expected
      expect(t('noPriorities')).toBe('Noch keine Prioritäten vorhanden')
      expect(t('cancel')).toBe('Abbrechen')
      expect(t('done')).toBe('Fertig')
      expect(t('yes')).toBe('Ja')
      expect(t('no')).toBe('Nein')
    })

    // PieChart, HourRing, KeywordPicker i18n keys
    it('returns noTimeData in both locales', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(t('noTimeData')).toBe('No time data to display')

      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(t('noTimeData')).toBe('Keine Zeitdaten vorhanden')
    })

    it('returns timeAllocationTitle in both locales', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(t('timeAllocationTitle')).toBe('Time Allocation')

      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(t('timeAllocationTitle')).toBe('Zeitaufteilung')
    })

    it('returns totalHours in both locales', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(t('totalHours')).toBe('total')

      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(t('totalHours')).toBe('gesamt')
    })

    it('returns pieChartAria with interpolation in both locales', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(t('pieChartAria').replace('{hours}', '12.5').replace('{n}', '3'))
        .toBe('Pie chart showing 12.5 total hours across 3 categories')

      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(t('pieChartAria').replace('{hours}', '12.5').replace('{n}', '3'))
        .toBe('Kreisdiagramm mit 12.5 Gesamtstunden in 3 Kategorien')
    })

    it('returns hourRingAria with interpolation in both locales', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(t('hourRingAria').replace('{hours}', '4h').replace('{target}', '10h'))
        .toBe('4h of 10h hours this week')

      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(t('hourRingAria').replace('{hours}', '4h').replace('{target}', '10h'))
        .toBe('4h von 10h Stunden diese Woche')
    })

    it('returns swapWith with interpolation in both locales', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(t('swapWith').replace('{name}', 'Ship v1.0'))
        .toBe('Swap with Ship v1.0')

      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(t('swapWith').replace('{name}', 'Ship v1.0'))
        .toBe('Tauschen mit Ship v1.0')
    })

    it('returns breakdownCta as non-empty string in both locales', () => {
      window.openai = { locale: 'en-US' } as typeof window.openai
      expect(t('breakdownCta').length).toBeGreaterThan(0)

      window.openai = { locale: 'de-DE' } as typeof window.openai
      expect(t('breakdownCta').length).toBeGreaterThan(0)
    })
  })
})
