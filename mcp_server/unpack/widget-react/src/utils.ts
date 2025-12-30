import type { UnpackData, QuestionCluster } from './types'

/**
 * Get unpack data from window.openai.toolOutput
 * Includes defensive mapping for theme/label compatibility
 */
export function getToolOutput(): UnpackData | null {
  const t = window.openai?.toolOutput
  if (!t) return null

  // Try multiple paths (ChatGPT puts data in different places)
  const data: any =
    t.result?.structuredContent ??
    t.structuredContent ??
    t  // Sometimes the data IS toolOutput directly

  if (!data || !data.clusters) return null

  // Defensive mapping: handle both "theme" and "label" field names
  const clusters: QuestionCluster[] = (data.clusters ?? []).map((c: any) => ({
    id: c.id ?? '',
    theme: c.theme ?? c.label ?? 'Untitled',  // Fallback to label if theme missing
    questions: c.questions ?? [],
    insight: c.insight ?? '',
  }))

  return {
    problem_statement: data.problem_statement ?? '',
    clusters,
    unclustered: data.unclustered ?? [],
    summary_markdown: data.summary_markdown ?? '',
  }
}

/**
 * Truncate text with ellipsis
 */
export function truncateText(text: string | undefined, maxLength = 80): string {
  if (!text || text.length <= maxLength) return text ?? ''
  return text.substring(0, maxLength).trim() + '...'
}

/**
 * Copy text to clipboard
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
