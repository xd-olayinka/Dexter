// Mock data for the Phase-0 shell (PRD §9 · Milestone 0).
// Ported from the v4 prototype; replaced by live services in Phase 1.

export type Mode = 'orch' | 'shadow'

export const TABS: Record<Mode, [id: string, glyph: string, label: string][]> = {
  orch: [
    ['home', '◉', 'Home'],
    ['projects', '▦', 'Projects'],
    ['tasks', '☑', 'Tasks'],
    ['team', '◈', 'Team'],
    ['chat', '✦', 'Chat'],
  ],
  shadow: [
    ['ops', '⬢', 'Ops'],
    ['swarm', '⬡', 'Swarm'],
    ['selector', '◬', 'Selector'],
    ['credits', '▤', 'Burn'],
    ['chat', '✦', 'Chat'],
  ],
}

export const PROJECTS = [
  {
    mark: 'M', name: 'Meridian Deal', cat: 'Revenue · Ledger&Co', badge: ['red', 'High'],
    dark: true, due: 'Fri, Jul 12', status: 'Closing', statusCls: 'hot', tasks: '6 / 8',
    people: ['MB', 'LN', 'AK'], plus: true, agents: '2 agents', agentsNote: 'Outreach + QA',
  },
  {
    mark: 'W', name: 'Website Rebuild', cat: 'Product · Northwind Studio', badge: ['ylw', 'Medium'],
    dark: false, due: 'Aug 6', status: 'Ongoing', statusCls: '', tasks: '9 / 21',
    people: ['RS', 'TO', 'DP'], plus: false, agents: '1 agent', agentsNote: 'Content',
  },
  {
    mark: 'Q', name: 'Q3 Pipeline Audit', cat: 'Finance · Ledger&Co', badge: ['grn', 'On Track'],
    dark: false, due: 'Jul 20', status: '62%', statusCls: 'warn', tasks: '5 / 8',
    people: ['LN', 'AK'], plus: false, agents: '3 agents', agentsNote: 'via Shadow',
  },
  {
    mark: 'B', name: 'Brand Refresh', cat: 'Design · Northwind Studio', badge: ['', 'Low'],
    dark: false, due: 'Sep 2', status: 'Kickoff', statusCls: '', tasks: '1 / 14',
    people: ['RS', 'DP'], plus: false, agents: '0 agents', agentsNote: 'assign?',
  },
]

export const TASKS_TODAY = [
  { nm: 'Review Meridian terms draft', meta: 'Meridian Deal · You · 09:00', tag: ['badge red', 'High'] },
  { nm: 'Approve 4 investor follow-ups', meta: 'Meridian Deal · staged by Dexter', tag: ['sent', '⬢ Shadow'] },
  { nm: 'Send brand assets to copy team', meta: 'Website Rebuild · Rina S.', tag: ['badge ylw', 'Blocked'] },
  { nm: 'Normalize Q3 expense records', meta: 'Pipeline Audit · running overnight', tag: ['sent', '⬢ Shadow'] },
  { nm: 'Book supplier call', meta: 'Ops · unassigned', tag: ['del', 'Delegate'] },
]

export const TASKS_UPCOMING = [
  { nm: 'Draft August content calendar', meta: 'Brand Refresh · Dev P. · Mon', tag: ['del', 'Delegate'] },
  { nm: 'Payroll pre-check', meta: 'Finance · Lena N. · Jul 14', tag: null },
  { nm: 'Prototype checkout flow', meta: 'Website Rebuild · Tomas O. · Jul 15', tag: null },
]

export const TEAM = [
  ['AK', 'Aisha K.', 'COO', 'Meridian + Audit · load 74%', 'In', 'grn'],
  ['MB', 'Marcus B.', 'Head of Sales', 'Meridian lead · 3 tasks today', 'In', 'grn'],
  ['RS', 'Rina S.', 'Design Lead', 'Website + Brand · 1 blocker owned', 'In', 'grn'],
  ['TO', 'Tomas O.', 'Engineer', 'Website Rebuild · deep focus', 'Focus', ''],
  ['LN', 'Lena N.', 'Finance', 'Audit reviewer · payroll Jul 14', 'In', 'grn'],
  ['DP', 'Dev P.', 'Analyst', 'Brand research · back Monday', 'Away', 'red'],
] as const

export const LOAD = [
  ['Aisha K.', 74, false],
  ['Marcus B.', 88, true],
  ['Rina S.', 61, false],
  ['Tomas O.', 52, false],
] as const

export const RUN_LOG = [
  ['✓', '04:12 Spawned Executor-01', 'Selector picked Haiku-class for scrape, cost floor', 'Done', 'grn'],
  ['✓', '04:40 Batch parse complete', '860 records normalized, 0 errors', 'Done', 'grn'],
  ['▸', '05:58 Voice executor killed', 'Budget guard tripped at 88%, auto-terminated', 'Guard', 'red'],
  ['▸', '06:10 Mailer gated', '4 sends held for Commander approval', 'Held', 'ylw'],
  ['✓', '06:31 Patch pushed', 'Invoice fix on branch dexter/fix-2204', 'Done', 'grn'],
] as const

export const GATES = [
  { ic: '✉', nm: 'Release 4 follow-up emails', meta: 'Executor-03 Mailer · est. cost $0.40', badge: ['grn', 'Approve'] },
  { ic: '⬢', nm: 'Respawn voice executor', meta: 'Needs cap raise from $50 to $80/mo', badge: ['red', 'Decide'] },
]

export const SWARM = [
  ['EX-01', 'Scraper', 'live', 0.94, '1.2K pages', '$2.10'],
  ['EX-02', 'Parser', 'live', 0.91, '860 records', '$1.44'],
  ['EX-03', 'Mailer', 'q', 0.88, '4 queued', '$0.00'],
  ['EX-04', 'Coder', 'live', 0.86, '3 commits', '$6.80'],
  ['EX-05', 'Voice', 'dead', 0.41, 'killed 05:58', '$3.90'],
  ['EX-06', 'Researcher', 'live', 0.79, '2 briefs', '$0.96'],
] as const

export const MODEL_POOL = [
  ['◆', 'Claude Opus', 'Heavy', 'Complex plans, legal, strategy', '$$$', 'slow ok'],
  ['◇', 'Claude Fable', 'Route', 'Conductor, tool use, delegation', '$$', 'balanced'],
  ['○', 'GPT 5.5', 'Cross', 'Second opinion, parallel drafts', '$$', 'balanced'],
  ['·', 'Haiku-class', 'Default', 'Scrape, parse, classify, bulk work', '$', 'fast'],
] as const

export const PICKS = [
  ['Scrape 1.2K pages → Haiku', 'Capability floor met at 1/9th the cost of Fable'],
  ['Invoice patch → Fable', 'Needed tool use + repo context, Haiku failed dry run'],
  ['Deal terms review → Opus', 'High stakes flag set by Orchestrator, cost override'],
] as const

export const BURN = [
  ['Anthropic API', '$812 · 42%', 42, false],
  ['OpenAI API', '$507 · 26%', 26, false],
  ['Search / Scrape', '$281 · 15%', 15, false],
  ['Voice + Media', '$196 · 88% of cap', 88, true],
  ['Infra / Vector DB', '$132 · 7%', 7, false],
] as const

export const GUARDS = [
  { ic: '△', nm: 'Voice cap tripped, executor killed', meta: 'Respawn requires Commander approval', badge: ['red', 'Active'] },
  { ic: '✓', nm: 'Off-peak batch routing saved $114', meta: 'Opus batch discount applied this cycle', badge: ['grn', 'Saved'] },
  { ic: '◍', nm: 'Per-executor ceiling: $10/day', meta: 'Configurable per template', badge: ['', 'Rule'] },
]

export const CHAT_SEED: Record<Mode, { voice: string; m1: string; me: string; m2: string; pills: string[] }> = {
  orch: {
    voice: 'Orchestrator',
    m1: "Morning, Commander. Meridian terms are drafted, the audit hit 62% overnight, and Rina's blocker is the only thing threatening this week. Want me to nudge the asset handoff?",
    me: 'Nudge it, and show me the terms at 9.',
    m2: 'Done. Reminder set, nudge sent softly through Slack. Terms will be on your screen at 09:00 sharp.',
    pills: ['✓ Approve all', 'View terms', 'Delegate to Shadow', 'Hold'],
  },
  shadow: {
    voice: 'Shadow',
    m1: 'Overnight run complete. 1,284 tasks terminated, one voice executor killed on budget guard. Two gates await your word.',
    me: 'Approve the mailer, deny the respawn.',
    m2: 'Executed. 4 follow-ups releasing now at $0.40 est. Voice respawn denied, cap holds at $50. Log updated.',
    pills: ['✓ Approve gate', 'Kill executor', 'Force spawn', 'Raise cap'],
  },
}
