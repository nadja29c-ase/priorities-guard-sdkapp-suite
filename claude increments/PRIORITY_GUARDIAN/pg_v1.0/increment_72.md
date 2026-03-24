Increment 72 — Edit/Add a11y, i18n, keyboard cleanup
Files: i18n.ts, DeadlineCard.tsx, FlexibleCard.tsx, AddPriorityForm.tsx, __tests__/CardCompliance.test.tsx, __tests__/i18n.test.ts, __tests__/AddPriorityForm.test.tsx (new)

i18n.ts — add three keys to both en and de objects. Do not remove or rename any existing keys. Do not modify the t() helper — it does not support interpolation natively.
Place under // Common actions:
edit: 'Edit'                              →  'Bearbeiten'
editPriority: 'Edit priority: {name}'    →  'Priorität bearbeiten: {name}'
hourTargetPlaceholder: 'e.g., 10'        →  'z. B. 10'

DeadlineCard.tsx — three changes. t is already imported, do not change the import.

Pencil button aria-label: `Edit priority: ${priority.name}` → t('editPriority').replace('{name}', priority.name)
Pencil button title: "Edit" → {t('edit')}
h3 title: "Click to edit" → {t('clickToEdit')}

FlexibleCard.tsx — identical three changes.

AddPriorityForm.tsx — three changes:

Hours input placeholder: "e.g., 10" → {t('hourTargetPlaceholder')}
Name input (step 1) — add onKeyDown:

tsxonKeyDown={(e) => {
  if (e.key === 'Enter' && name.trim()) {
    e.preventDefault()
    handleNameNext()
  }
}}

<input id="priority-deadline"> and <input id="priority-hours"> only — add onKeyDown. Do NOT add to <input id="priority-checkpoint"> or the textarea:

tsxonKeyDown={(e) => {
  if (e.key === 'Enter') {
    e.preventDefault()
    handleSubmit()
  }
}}
Do not add new validation logic. handleSubmit() already validates.

__tests__/CardCompliance.test.tsx — add to existing describe blocks
Use setMockLocale from '../test/setup' for locale-dependent tests. Do not reassign window.openai directly in this file. After each locale test, the existing afterEach in setup.ts restores state automatically.
Use the existing deadlinePriority and flexiblePriority fixtures already defined in the file. Assert against their actual .name values, not hardcoded strings.
Add to DeadlineCard Keyboard Accessibility:
tsit('edit pencil button aria-label contains priority name in English', () => {
  render(<DeadlineCard priority={deadlinePriority} priorities={[deadlinePriority]} isEditing={false} {...mockHandlers} />)
  const editBtn = screen.getByRole('button', { name: new RegExp(`Edit priority: ${deadlinePriority.name}`, 'i') })
  expect(editBtn).toBeInTheDocument()
})

it('edit pencil button aria-label renders in German', () => {
  setMockLocale('de-DE')
  render(<DeadlineCard priority={deadlinePriority} priorities={[deadlinePriority]} isEditing={false} {...mockHandlers} />)
  const editBtn = screen.getByRole('button', { name: new RegExp(`Priorität bearbeiten: ${deadlinePriority.name}`, 'i') })
  expect(editBtn).toBeInTheDocument()
})
Add identical two tests to FlexibleCard Keyboard Accessibility using flexiblePriority.

__tests__/i18n.test.ts — add three tests to the existing t (translation function) describe block
Follow the existing pattern in this file — direct window.openai reassignment is the established pattern here:
tsit('returns edit in both locales', () => {
  window.openai = { locale: 'en-US' } as typeof window.openai
  expect(t('edit')).toBe('Edit')
  window.openai = { locale: 'de-DE' } as typeof window.openai
  expect(t('edit')).toBe('Bearbeiten')
})

it('returns editPriority with interpolation in both locales', () => {
  window.openai = { locale: 'en-US' } as typeof window.openai
  expect(t('editPriority').replace('{name}', 'Ship v1.0')).toBe('Edit priority: Ship v1.0')
  window.openai = { locale: 'de-DE' } as typeof window.openai
  expect(t('editPriority').replace('{name}', 'Ship v1.0')).toBe('Priorität bearbeiten: Ship v1.0')
})

it('returns hourTargetPlaceholder in both locales', () => {
  window.openai = { locale: 'en-US' } as typeof window.openai
  expect(t('hourTargetPlaceholder')).toBe('e.g., 10')
  window.openai = { locale: 'de-DE' } as typeof window.openai
  expect(t('hourTargetPlaceholder')).toBe('z. B. 10')
})

__tests__/AddPriorityForm.test.tsx (new file)
Use vi.fn(), render, screen, fireEvent, waitFor from the standard imports already used across the test suite. Use userEvent for typing. onAdd should be vi.fn().mockResolvedValue(undefined). Use availableKeywords={['P1']} for all renders. Do not model this after DeleteConfirmation.test.tsx — it is a modal, not a form. Use standard RTL patterns.
Four tests:
1. Enter on name input advances to type step
Render form → type name in #priority-name → press Enter → assert type selection heading appears.
2. Enter on deadline input submits
Type name → Enter → click Deadline type button → fill #priority-deadline → press Enter on deadline input → assert onAdd called with { name, type: 'deadline', deadline }.
3. Enter on hours input submits (flexible)
Type name → Enter → click Flexible type button → fill #priority-hours, #priority-checkpoint, #priority-goal (all required fields) → then focus #priority-hours and press Enter → assert onAdd called with correct data. Fill all fields before triggering Enter — the form validates on submit.
4. Enter on textarea does NOT submit
Navigate to step 3 flexible → fill all required fields → press Enter while focused on #priority-goal textarea → assert onAdd not called.

Read OPERATIONS_PREDEPLOY.md before committing. Build with npm run build inside widget-react/. Run full test suite — all existing tests must still pass.