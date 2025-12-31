import { Badge } from '@openai/apps-sdk-ui/components/Badge'
import type { QuestionCluster } from '../types'

interface ClusterCardProps {
  cluster: QuestionCluster
}

export function ClusterCard({ cluster }: ClusterCardProps) {
  return (
    <article
      tabIndex={0}
      className="rounded-2xl border border-default bg-surface-secondary p-5 flex flex-col min-h-[120px] shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)]"
      aria-label={`Cluster: ${cluster.theme}, ${cluster.questions.length} questions`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <h3 className="text-sm font-semibold text-default m-0">
          {cluster.theme}
        </h3>
        <Badge color="secondary" variant="outline" size="sm">
          {cluster.questions.length}
        </Badge>
      </div>

      {/* Questions */}
      <ul role="list" className="space-y-2 flex-1 list-none m-0 p-0">
        {cluster.questions.map((q, i) => (
          <li
            key={i}
            tabIndex={0}
            aria-label={q}
            className="text-sm text-default pl-3 border-l-2 border-default focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-ring)]"
          >
            {q}
          </li>
        ))}
      </ul>

    </article>
  )
}
