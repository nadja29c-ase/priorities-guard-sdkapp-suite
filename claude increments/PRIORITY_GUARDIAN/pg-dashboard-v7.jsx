import { useState } from "react";

// ═══════════════════════════════════════════════════════════
// Priority Guardian Dashboard — V7 + Tweaks + Display Modes
// ═══════════════════════════════════════════════════════════
// Tweak 1: Colored left border on cards
// Tweak 2: Collapsible deliverables + collapsible 1-Month Goal (only when 2-3 goals)
// Tweak 3: Inline vs Fullscreen display modes
//   - Inline: same cards, deliverables collapsed, minimal calendar
//   - Fullscreen: everything expanded, full calendar connection
// ═══════════════════════════════════════════════════════════

const MOCK_DATA = {
  timeAllocation: {
    weekStart: "2026-02-09",
    weekEnd: "2026-02-16",
    totalTrackedHours: 28.5,
    keywords: {
      P1: { hours: 12.0, eventCount: 8 },
      P2: { hours: 6.5, eventCount: 5 },
      P3: { hours: 3.0, eventCount: 3 },
    },
    otherHours: 7.0,
    barSegments: { P1: 12.0, P2: 6.5, P3: 3.0, other: 7.0 },
  },
  priorities: [
    {
      id: "1",
      name: "Launch Marketing Site",
      type: "deadline",
      calendarKeyword: "P1",
      deadline: "2026-03-15",
      deliverables: [
        { id: "d1", name: "Sales page copy", done: true },
        { id: "d2", name: "Design mockups", done: true },
        { id: "d3", name: "Domain + hosting setup", done: true },
        { id: "d4", name: "Development", done: false },
        { id: "d5", name: "SEO optimization", done: false },
        { id: "d6", name: "Testing", done: false },
        { id: "d7", name: "Go-live", done: false },
      ],
    },
    {
      id: "2",
      name: "Build LinkedIn Presence",
      type: "flexible",
      calendarKeyword: "P2",
      weeklyHourTarget: 5,
      weeklyHourActual: 3.5,
      checkpointDate: "2026-03-09",
      // Multiple goals (2) → collapsible
      desiredResults: [
        { id: "g1", text: "Posting on LinkedIn twice a week consistently", achieved: false },
        { id: "g2", text: "Grow connections to 500+", achieved: true },
      ],
      streakCount: 6,
      avgTargetAchievement: 84,
    },
    {
      id: "3",
      name: "Complete AI Certification",
      type: "flexible",
      calendarKeyword: "P3",
      weeklyHourTarget: 3,
      weeklyHourActual: 1.0,
      checkpointDate: "2026-03-23",
      // Single goal → always expanded, no chevron
      desiredResults: [
        { id: "g1", text: "First 3 modules of certification program completed", achieved: false },
      ],
      streakCount: 2,
      avgTargetAchievement: null,
    },
  ],
};

const KEYWORD_STYLES = {
  P1: {
    badge: "bg-blue-50 text-blue-600 border border-blue-200",
    dot: "bg-blue-500",
    bar: "bg-blue-500",
    ring: "#0285ff",
    accent: "var(--blue-400, #0285ff)",
    accentSoft: "var(--blue-50, #eff6ff)",
    borderColor: "#0285ff",
  },
  P2: {
    badge: "bg-purple-50 text-purple-600 border border-purple-200",
    dot: "bg-purple-500",
    bar: "bg-purple-500",
    ring: "#924ff7",
    accent: "var(--purple-400, #924ff7)",
    accentSoft: "var(--purple-50, #faf5ff)",
    borderColor: "#924ff7",
  },
  P3: {
    badge: "bg-yellow-50 text-yellow-700 border border-yellow-300",
    dot: "bg-yellow-500",
    bar: "bg-yellow-400",
    ring: "#ffc300",
    accent: "var(--yellow-500, #e0ac00)",
    accentSoft: "var(--yellow-50, #fefce8)",
    borderColor: "#ffc300",
  },
};

function daysUntil(dateStr) {
  const target = new Date(dateStr + "T00:00:00");
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.ceil((target - now) / (1000 * 60 * 60 * 24));
}

function formatHours(h) {
  if (h === 0) return "0h";
  if (h % 1 === 0) return `${h}h`;
  return `${h.toFixed(1)}h`;
}

function EditIcon({ color = "var(--gray-350, #9f9f9f)" }) {
  return (
    <svg className="w-3.5 h-3.5" style={{ color }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M11.5 2.5l2 2M2 14l.5-2 9-9 2 2-9 9-2.5.5z" />
    </svg>
  );
}

function TrashIcon({ color = "var(--gray-350, #9f9f9f)" }) {
  return (
    <svg className="w-3.5 h-3.5" style={{ color }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 4h12M5.5 4V2.5a1 1 0 011-1h3a1 1 0 011 1V4" />
      <path d="M12.5 4v9a1.5 1.5 0 01-1.5 1.5H5a1.5 1.5 0 01-1.5-1.5V4" />
      <path d="M6.5 7v5M9.5 7v5" />
    </svg>
  );
}

function RefreshIcon({ color = "var(--gray-400, #8f8f8f)" }) {
  return (
    <svg className="w-3 h-3" style={{ color }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2.5 8a5.5 5.5 0 019.3-3.9M13.5 8a5.5 5.5 0 01-9.3 3.9" />
      <path d="M12 1v3.5h-3.5M4 15v-3.5h3.5" />
    </svg>
  );
}

function CalendarIcon({ color }) {
  return (
    <svg className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="1.5">
      <rect x="2" y="3" width="12" height="11" rx="1.5" />
      <path d="M5 1.5v3M11 1.5v3M2 7h12" />
    </svg>
  );
}

function ChevronIcon({ expanded }) {
  return (
    <svg
      className="w-3.5 h-3.5"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      style={{
        color: "var(--gray-400, #8f8f8f)",
        transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
        transition: "transform 150ms ease-out",
      }}
    >
      <path d="M4 6l4 4 4-4" />
    </svg>
  );
}

// ═══════════════════════════════════════════════════
// TIME ALLOCATION BAR (V7 exact)
// ═══════════════════════════════════════════════════
function TimeAllocationBar({ data, activeKeywords, onRefresh, isRefreshing }) {
  if (!data) return null;
  const { totalTrackedHours, barSegments, otherHours, keywords } = data;

  const segments = [];
  for (const kw of activeKeywords) {
    const hours = barSegments[kw];
    if (hours > 0) {
      segments.push({
        key: kw,
        width: Math.max((hours / totalTrackedHours) * 100, 2),
        color: KEYWORD_STYLES[kw].bar,
      });
    }
  }
  if (otherHours > 0) {
    segments.push({
      key: "other",
      width: Math.max((otherHours / totalTrackedHours) * 100, 2),
      color: "bg-gray-300",
    });
  }
  const total = segments.reduce((s, x) => s + x.width, 0);
  if (total > 100) segments.forEach((s) => (s.width *= 100 / total));

  return (
    <section className="mb-5">
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-xs font-medium tracking-wide uppercase" style={{ color: "var(--gray-500, #5d5d5d)" }}>
          This week
        </span>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold tabular-nums" style={{ color: "var(--gray-900, #181818)" }}>
            {formatHours(totalTrackedHours)}
          </span>
          <button
            onClick={onRefresh}
            className="p-1 rounded-full hover:bg-gray-100 transition-colors"
            title="Refresh calendar data"
            style={{ opacity: isRefreshing ? 0.4 : 1 }}
          >
            <RefreshIcon />
          </button>
        </div>
      </div>
      <p className="text-xs mb-2.5" style={{ color: "var(--gray-450, #767676)" }}>
        Feb 9 – Feb 15
      </p>
      <div className="h-2 rounded-full overflow-hidden flex gap-px" style={{ background: "var(--gray-100, #ededed)" }}>
        {totalTrackedHours === 0 ? (
          <div className="w-full h-full" />
        ) : (
          segments.map((seg) => (
            <div
              key={seg.key}
              className={`h-full first:rounded-l-full last:rounded-r-full ${seg.color}`}
              style={{ width: `${seg.width}%` }}
            />
          ))
        )}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2.5">
        {activeKeywords.map((kw) => (
          <div key={kw} className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${KEYWORD_STYLES[kw].dot}`} />
            <span className="text-xs tabular-nums" style={{ color: "var(--gray-500, #5d5d5d)" }}>
              {kw} {formatHours(keywords[kw].hours)}
            </span>
          </div>
        ))}
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-gray-300" />
          <span className="text-xs italic tabular-nums" style={{ color: "var(--gray-400, #8f8f8f)" }}>
            other {formatHours(otherHours)}
          </span>
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════════════════════════════
// HOUR RING (V7 exact)
// ═══════════════════════════════════════════════════
function HourRing({ actual, target, keyword, size = 56 }) {
  const center = size / 2;
  const radius = size / 2 - 4;
  const circumference = 2 * Math.PI * radius;
  const percentage = Math.min((actual / target) * 100, 100);
  const dashoffset = circumference - (circumference * percentage) / 100;
  const stroke = KEYWORD_STYLES[keyword]?.ring || "#5d5d5d";

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-full">
        <circle cx={center} cy={center} r={radius} fill="none" stroke="var(--gray-100, #ededed)" strokeWidth={3.5} />
        {percentage > 0 && (
          <circle
            cx={center} cy={center} r={radius} fill="none"
            stroke={stroke} strokeWidth={3.5} strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={dashoffset}
            style={{ transform: "rotate(-90deg)", transformOrigin: "center" }}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-semibold text-xs tabular-nums leading-none" style={{ color: "var(--gray-900, #181818)" }}>
          {formatHours(actual)}
        </span>
        <span className="leading-none mt-0.5" style={{ color: "var(--gray-400, #8f8f8f)", fontSize: "0.6rem" }}>
          /{formatHours(target)}
        </span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════
// GOAL ITEM — single goal row with toggle
// ═══════════════════════════════════════════════════
function GoalItem({ goal, onToggle }) {
  return (
    <div className="flex items-start gap-2.5">
      <button
        onClick={() => onToggle(goal.id)}
        className="mt-0.5 flex-shrink-0 transition-all"
        title={goal.achieved ? "Mark as not yet achieved" : "Mark as achieved"}
      >
        <span
          className="rounded-full flex items-center justify-center"
          style={{
            width: "18px",
            height: "18px",
            border: goal.achieved ? "none" : "1.5px solid var(--gray-300, #afafaf)",
            background: goal.achieved ? "var(--green-500, #00a240)" : "transparent",
            transition: "all 150ms ease-out",
          }}
        >
          {goal.achieved && (
            <svg className="w-2.5 h-2.5" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2">
              <path d="M2 6l3 3 5-5" />
            </svg>
          )}
        </span>
      </button>
      <p
        className={`text-sm flex-1 ${goal.achieved ? "line-through" : ""}`}
        style={{
          color: goal.achieved ? "var(--gray-350, #9f9f9f)" : "var(--gray-700, #303030)",
          transition: "color 150ms ease-out",
        }}
      >
        {goal.text}
      </p>
    </div>
  );
}

// ═══════════════════════════════════════════════════
// GOAL SECTION
// 1 goal → always expanded, no chevron (V7 behavior)
// 2-3 goals → collapsible with chevron
// ═══════════════════════════════════════════════════
function GoalSection({ priority, onToggleGoal, defaultExpanded = true }) {
  const goals = priority.desiredResults || [];
  const isCollapsible = goals.length > 1;
  const [expanded, setExpanded] = useState(defaultExpanded);

  const checkpointDate = new Date(priority.checkpointDate).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  const checkpointDays = daysUntil(priority.checkpointDate);
  const checkpointLabel =
    checkpointDays > 0
      ? `${checkpointDays}d to check-in`
      : checkpointDays === 0
      ? "Check-in today"
      : "Check-in overdue";

  const achievedCount = goals.filter((g) => g.achieved).length;

  return (
    <div className="pt-3" style={{ borderTop: "1px solid var(--gray-75, #f3f3f3)" }}>
      {/* Header — clickable only when collapsible */}
      {isCollapsible ? (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 w-full mb-0 hover:opacity-80 transition-opacity"
          style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
        >
          <h4 className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--gray-400, #8f8f8f)" }}>
            1-Month Goals
          </h4>
          <span className="text-xs tabular-nums" style={{ color: "var(--gray-350, #9f9f9f)" }}>
            ({achievedCount}/{goals.length})
          </span>
          <span className="text-xs tracking-normal font-normal normal-case" style={{ color: "var(--gray-350, #9f9f9f)" }}>
            · by {checkpointDate} · {checkpointLabel}
          </span>
          <span className="ml-auto">
            <ChevronIcon expanded={expanded} />
          </span>
        </button>
      ) : (
        <div className="flex items-baseline justify-between mb-2">
          <h4 className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--gray-400, #8f8f8f)" }}>
            1-Month Goal
            <span className="normal-case tracking-normal font-normal ml-2" style={{ color: "var(--gray-350, #9f9f9f)" }}>
              by {checkpointDate} · {checkpointLabel}
            </span>
          </h4>
        </div>
      )}

      {/* Goal items — always shown for single, toggle for multi */}
      {(isCollapsible ? expanded : true) && (
        <div className={`space-y-2 ${isCollapsible ? "mt-2" : ""}`}>
          {goals.map((goal) => (
            <GoalItem key={goal.id} goal={goal} onToggle={onToggleGoal} />
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════
// DEADLINE CARD
// ═══════════════════════════════════════════════════
function DeadlineCard({ priority, defaultDeliverablesExpanded = true }) {
  const days = daysUntil(priority.deadline);
  const done = priority.deliverables.filter((d) => d.done).length;
  const total = priority.deliverables.length;
  const kw = priority.calendarKeyword;
  const style = KEYWORD_STYLES[kw];

  const [deliverablesExpanded, setDeliverablesExpanded] = useState(defaultDeliverablesExpanded);

  const deadlineDate = new Date(priority.deadline).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <article
      className="rounded-xl overflow-hidden"
      style={{
        background: "var(--gray-0, #ffffff)",
        border: "1px solid var(--gray-100, #ededed)",
        borderLeft: `4px solid ${style.borderColor}`,
      }}
    >
      <div className="px-5 py-2.5 flex items-center justify-between" style={{ background: style.accentSoft }}>
        <div className="flex items-center gap-2">
          <CalendarIcon color={style.accent} />
          <span className="text-xs font-semibold" style={{ color: style.accent }}>
            {deadlineDate}
          </span>
        </div>
        <span className="text-xs font-bold tabular-nums" style={{ color: style.accent }}>
          {days > 0 ? `${days}d left` : days === 0 ? "Due today" : `${Math.abs(days)}d overdue`}
        </span>
      </div>

      <div className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <span
            className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0 ${style.badge}`}
            style={{ fontSize: "0.65rem" }}
          >
            {kw}
          </span>
          <h3 className="text-sm font-semibold flex-1 truncate" style={{ color: "var(--gray-900, #181818)" }}>
            {priority.name}
          </h3>
          <button className="p-1 rounded hover:bg-gray-100 transition-colors" title="Edit">
            <EditIcon />
          </button>
          <button className="p-1 rounded hover:bg-red-50 transition-colors" title="Delete priority">
            <TrashIcon />
          </button>
        </div>

        <div className="mb-4">
          <span className="text-2xl font-bold tabular-nums leading-none" style={{ color: "var(--gray-900, #181818)" }}>
            {done}
            <span className="text-lg font-normal" style={{ color: "var(--gray-350, #9f9f9f)" }}>
              /{total}
            </span>
          </span>
          <p className="text-xs mt-0.5" style={{ color: "var(--gray-450, #767676)" }}>
            deliverables done
          </p>
        </div>

        {/* Collapsible deliverables */}
        <div className="pt-3" style={{ borderTop: "1px solid var(--gray-75, #f3f3f3)" }}>
          <button
            onClick={() => setDeliverablesExpanded(!deliverablesExpanded)}
            className="flex items-center gap-1.5 w-full mb-2 hover:opacity-80 transition-opacity"
            style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
          >
            <h4 className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--gray-400, #8f8f8f)" }}>
              E2E Deliverables
            </h4>
            <span className="text-xs tabular-nums" style={{ color: "var(--gray-350, #9f9f9f)" }}>
              ({done}/{total})
            </span>
            <span className="ml-auto">
              <ChevronIcon expanded={deliverablesExpanded} />
            </span>
          </button>

          {deliverablesExpanded && (
            <>
              <ul className="space-y-1.5">
                {priority.deliverables.map((d) => (
                  <li key={d.id} className="flex items-center gap-2">
                    <span
                      className="w-4 h-4 rounded flex items-center justify-center flex-shrink-0"
                      style={{
                        border: d.done ? "none" : "1.5px solid var(--gray-250, #b9b9b9)",
                        background: d.done ? "var(--gray-200, #cdcdcd)" : "transparent",
                      }}
                    >
                      {d.done && (
                        <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M2 6l3 3 5-5" />
                        </svg>
                      )}
                    </span>
                    <span
                      className={`text-sm ${d.done ? "line-through" : ""}`}
                      style={{ color: d.done ? "var(--gray-350, #9f9f9f)" : "var(--gray-700, #303030)" }}
                    >
                      {d.name}
                    </span>
                  </li>
                ))}
              </ul>
              <button className="mt-2 text-xs flex items-center gap-1 py-1" style={{ color: "var(--gray-400, #8f8f8f)" }}>
                <span className="text-base leading-none">+</span> Add deliverable
              </button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}

// ═══════════════════════════════════════════════════
// FLEXIBLE CARD
// ═══════════════════════════════════════════════════
function FlexibleCard({ priority, onToggleGoal, defaultGoalExpanded = true }) {
  const kw = priority.calendarKeyword;
  const style = KEYWORD_STYLES[kw];
  const hasAvg = priority.avgTargetAchievement != null;

  return (
    <article
      className="rounded-xl p-5"
      style={{
        background: "var(--gray-0, #ffffff)",
        border: "1px solid var(--gray-100, #ededed)",
        borderLeft: `4px solid ${style.borderColor}`,
      }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span
          className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0 ${style.badge}`}
          style={{ fontSize: "0.65rem" }}
        >
          {kw}
        </span>
        <h3 className="text-sm font-semibold flex-1 truncate" style={{ color: "var(--gray-900, #181818)" }}>
          {priority.name}
        </h3>
        {priority.streakCount > 0 && (
          <span
            className="text-xs tabular-nums px-1.5 py-0.5 rounded-full font-medium"
            style={{
              color: "var(--gray-600, #414141)",
              background: "var(--gray-75, #f3f3f3)",
              fontSize: "0.7rem",
            }}
          >
            {priority.streakCount}w streak
          </span>
        )}
        <button className="p-1 rounded hover:bg-gray-100 transition-colors" title="Edit">
          <EditIcon />
        </button>
        <button className="p-1 rounded hover:bg-red-50 transition-colors" title="Delete priority">
          <TrashIcon />
        </button>
      </div>

      <div className="flex items-start gap-4 mb-4">
        <HourRing
          actual={priority.weeklyHourActual}
          target={priority.weeklyHourTarget}
          keyword={kw}
          size={64}
        />
        <div className="flex-1 pt-1">
          {hasAvg ? (
            <div className="mb-1.5">
              <span className="text-2xl font-bold tabular-nums leading-none" style={{ color: "var(--gray-900, #181818)" }}>
                ~{Math.round(priority.avgTargetAchievement)}%
              </span>
              <p className="text-xs mt-0.5" style={{ color: "var(--gray-450, #767676)" }}>
                of weekly target on avg
              </p>
            </div>
          ) : (
            <div className="mb-1.5">
              <span className="text-sm" style={{ color: "var(--gray-350, #9f9f9f)" }}>
                Building your average…
              </span>
            </div>
          )}
        </div>
      </div>

      <GoalSection
        priority={priority}
        onToggleGoal={onToggleGoal}
        defaultExpanded={defaultGoalExpanded}
      />
    </article>
  );
}

// ═══════════════════════════════════════════════════
// CALENDAR CONNECTION — full (V7 exact)
// ═══════════════════════════════════════════════════
function CalendarConnection({ connected }) {
  const [isConnected, setIsConnected] = useState(connected);

  return (
    <section
      className="mt-4 rounded-xl p-4"
      style={{
        background: "var(--gray-0, #ffffff)",
        border: "1px solid var(--gray-100, #ededed)",
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: isConnected ? "var(--green-500, #00a240)" : "var(--gray-300, #afafaf)" }}
          />
          <span className="text-sm font-medium" style={{ color: "var(--gray-700, #303030)" }}>
            Google Calendar
          </span>
        </div>
        <button
          onClick={() => setIsConnected(!isConnected)}
          className="text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
          style={{
            color: isConnected ? "var(--red-500, #e02e2a)" : "var(--blue-500, #0169cc)",
            background: isConnected ? "var(--red-50, #fef2f2)" : "var(--blue-50, #eff6ff)",
          }}
        >
          {isConnected ? "Disconnect" : "Connect"}
        </button>
      </div>

      {isConnected && (
        <div
          className="rounded-lg px-3 py-2.5 mt-2"
          style={{ background: "var(--gray-50, #f9f9f9)" }}
        >
          <p className="text-xs leading-relaxed" style={{ color: "var(--gray-450, #767676)" }}>
            Add <strong style={{ color: "var(--gray-700, #303030)" }}>P1</strong>,{" "}
            <strong style={{ color: "var(--gray-700, #303030)" }}>P2</strong>, or{" "}
            <strong style={{ color: "var(--gray-700, #303030)" }}>P3</strong>{" "}
            to your calendar event titles to track time toward each priority.
          </p>
        </div>
      )}
    </section>
  );
}

// ═══════════════════════════════════════════════════
// CALENDAR CONNECTION — minimal hint (inline mode)
// ═══════════════════════════════════════════════════
function CalendarConnectionMinimal() {
  return (
    <div className="mt-4 flex items-center gap-2 px-1">
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ background: "var(--green-500, #00a240)" }}
      />
      <span className="text-xs" style={{ color: "var(--gray-400, #8f8f8f)" }}>
        Google Calendar connected
      </span>
    </div>
  );
}

// ═══════════════════════════════════════════════════
// FULLSCREEN HEADER
// ═══════════════════════════════════════════════════
function FullscreenHeader({ onMinimize }) {
  return (
    <div
      className="flex items-center justify-between px-4 py-2.5 mb-1"
      style={{
        background: "var(--gray-0, #ffffff)",
        borderBottom: "1px solid var(--gray-75, #f3f3f3)",
      }}
    >
      <span className="text-sm font-semibold" style={{ color: "var(--gray-900, #181818)" }}>
        My Priorities
      </span>
      <button
        onClick={onMinimize}
        className="text-xs px-2.5 py-1 rounded-lg transition-colors hover:bg-gray-100"
        style={{
          color: "var(--gray-500, #5d5d5d)",
          background: "none",
          border: "none",
          cursor: "pointer",
        }}
        title="Minimize to inline card"
      >
        Minimize
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════
// EXPAND BUTTON (inline → fullscreen)
// ═══════════════════════════════════════════════════
function ExpandButton({ onExpand }) {
  return (
    <button
      onClick={onExpand}
      className="mt-4 w-full py-2.5 rounded-xl text-xs font-medium flex items-center justify-center gap-1.5 transition-colors hover:opacity-80"
      style={{
        color: "var(--blue-500, #0169cc)",
        background: "var(--blue-50, #eff6ff)",
        border: "none",
        cursor: "pointer",
      }}
    >
      Open full dashboard
      <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M6 4l4 4-4 4" />
      </svg>
    </button>
  );
}

// ═══════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════
export default function PGDashboardV7Tweaked() {
  const [data, setData] = useState(MOCK_DATA);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [displayMode, setDisplayMode] = useState("inline");
  const activeKeywords = ["P1", "P2", "P3"];

  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 1000);
  };

  const handleToggleGoal = (priorityId, goalId) => {
    setData((prev) => ({
      ...prev,
      priorities: prev.priorities.map((p) =>
        p.id === priorityId
          ? {
              ...p,
              desiredResults: p.desiredResults.map((g) =>
                g.id === goalId ? { ...g, achieved: !g.achieved } : g
              ),
            }
          : p
      ),
    }));
  };

  const isInline = displayMode === "inline";

  return (
    <div
      style={{
        background: "var(--gray-50, #f9f9f9)",
        fontFamily: 'ui-sans-serif, -apple-system, system-ui, "Segoe UI", "Noto Sans", "Helvetica", "Arial", sans-serif',
        minHeight: isInline ? "auto" : "100vh",
      }}
    >
      {/* Mode label (mockup only) */}
      <div className="px-4 pt-2 pb-0 flex items-center gap-2">
        <span
          className="text-xs px-2 py-0.5 rounded-full font-medium"
          style={{
            background: isInline ? "var(--blue-50, #eff6ff)" : "var(--purple-50, #faf5ff)",
            color: isInline ? "var(--blue-500, #0169cc)" : "var(--purple-500, #8046d9)",
          }}
        >
          {isInline ? "inline mode" : "fullscreen mode"}
        </span>
        <span className="text-xs" style={{ color: "var(--gray-400, #8f8f8f)" }}>
          {isInline
            ? "Deliverables collapsed · Multi-goals collapsed · Minimal calendar"
            : "Everything expanded · Full calendar connection"}
        </span>
      </div>

      {/* Fullscreen header */}
      {!isInline && <FullscreenHeader onMinimize={() => setDisplayMode("inline")} />}

      <div className="p-4 max-w-md mx-auto">
        <TimeAllocationBar
          data={data.timeAllocation}
          activeKeywords={activeKeywords}
          onRefresh={handleRefresh}
          isRefreshing={isRefreshing}
        />

        <div className="flex flex-col gap-3">
          <DeadlineCard
            key={`deadline-${displayMode}`}
            priority={data.priorities[0]}
            defaultDeliverablesExpanded={!isInline}
          />
          <FlexibleCard
            key={`flex1-${displayMode}`}
            priority={data.priorities[1]}
            onToggleGoal={(goalId) => handleToggleGoal("2", goalId)}
            defaultGoalExpanded={!isInline}
          />
          <FlexibleCard
            key={`flex2-${displayMode}`}
            priority={data.priorities[2]}
            onToggleGoal={(goalId) => handleToggleGoal("3", goalId)}
            defaultGoalExpanded={!isInline}
          />
        </div>

        {isInline ? (
          <CalendarConnectionMinimal />
        ) : (
          <CalendarConnection connected={true} />
        )}

        {isInline && <ExpandButton onExpand={() => setDisplayMode("fullscreen")} />}
      </div>
    </div>
  );
}