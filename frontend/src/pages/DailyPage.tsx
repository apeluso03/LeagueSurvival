import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type CSSProperties, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState } from '../components/ui'
import { useChampionMap, useGameNumber } from '../hooks/queries'
import { formatDuration, queueName } from '../lib/queues'
import { teamColor } from '../lib/teams'
import type { DailyGuess, DailyHint, DailyQuestion, DailyQuestionId, DailyView, Role } from '../types'

const ROLE_NAME: Record<Role, string> = { TOP: 'Top', JUNGLE: 'Jungle', MIDDLE: 'Mid', BOTTOM: 'Bot', UTILITY: 'Support' }

/**
 * Daily Statline (SPEC 20): one statline a day from the group's run history. Guess the result, who
 * was piloting, the K/D/A and the grade. Same puzzle and guesses as the Discord bot's /daily.
 */
export function DailyPage() {
  const qc = useQueryClient()
  const daily = useQuery({ queryKey: ['daily'], queryFn: api.daily, refetchOnWindowFocus: true })
  const guess = useMutation({
    mutationFn: ({ q, value }: { q: DailyQuestionId; value: string | number | number[] }) => api.dailyGuess(q, value),
    onSuccess: (data) => qc.setQueryData(['daily'], data),
  })

  if (daily.isPending) return <LoadingState />
  if (daily.error) return <ErrorText error={daily.error} />
  const v = daily.data
  if (!v?.available) {
    return (
      <EmptyState title="No Daily Statline yet">
        <p className="max-w-md text-sm text-slate-400">
          Each day's puzzle is a statline from one of your group's finished challenge games with Riot stats. Once you
          have some, a new one shows up here every day at midnight.
        </p>
      </EmptyState>
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="broadcast-tag" style={{ ['--tag' as string]: '#c8aa6e' } as CSSProperties}>
          Daily
        </span>
        <h1 className="text-lg text-white">
          Daily Statline <span className="font-sans font-bold">#{v.number}</span>
        </h1>
        <span className="text-sm text-slate-400">{new Date(`${v.day}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}</span>
        {v.streak > 0 && <span className="ml-auto text-sm text-gold-300">🔥 {v.streak}-day streak</span>}
      </div>

      <Clue v={v} />

      <ol className="flex flex-col gap-3">
        {v.questions.map((q, i) => (
          <QuestionCard key={q.id} n={i + 1} q={q} v={v} active={q.id === v.current} busy={guess.isPending} onGuess={(value) => guess.mutate({ q: q.id, value })} />
        ))}
      </ol>
      <ErrorText error={guess.error} />

      {v.done && <Finished v={v} />}
      <p className="text-center text-xs text-slate-500">
        A new puzzle every day at midnight. Also playable in Discord with <code>/daily</code>.
      </p>
    </div>
  )
}

function Clue({ v }: { v: DailyView }) {
  const champs = useChampionMap()
  const c = v.clue
  const champ = c.champion_id ? champs.get(c.champion_id) : undefined
  return (
    <section className="card flex items-center gap-4 p-4">
      <ChampionPortrait champion={champ} size="lg" eager className="land-glow rounded-sm" />
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-[11px] font-bold tracking-[0.16em] text-slate-500 uppercase">Whose game was this?</span>
        <span className="font-display text-2xl text-white">{champ?.name ?? c.champion_id ?? '?'}</span>
        <span className="flex flex-wrap gap-x-3 text-sm text-slate-300">
          {c.role && <span>{ROLE_NAME[c.role] ?? c.role}</span>}
          {c.duration != null && <span>{formatDuration(c.duration)}</span>}
          {c.queue_id != null && <span>{queueName(c.queue_id)}</span>}
        </span>
      </div>
    </section>
  )
}

const ARROW: Record<Exclude<DailyHint, 'exact'>, string> = { higher: '▲', lower: '▼' }

/** One feedback chip: green when right, amber when close, grey with an arrow when off. */
function Chip({ children, tone, title }: { children: ReactNode; tone: 'right' | 'close' | 'wrong'; title?: string }) {
  const tones = {
    right: 'bg-emerald-500/20 text-emerald-200 ring-emerald-400/50',
    close: 'bg-amber-500/15 text-amber-200 ring-amber-400/50',
    wrong: 'bg-white/[0.04] text-slate-300 ring-white/10',
  }
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-sm tabular-nums ring-1 ring-inset ${tones[tone]}`}>
      {children}
    </span>
  )
}

function hintChip(value: ReactNode, hint: DailyHint, close: boolean, key?: number) {
  if (hint === 'exact') return <Chip key={key} tone="right">{value} ✓</Chip>
  const words = hint === 'higher' ? 'The answer is higher' : 'The answer is lower'
  return (
    <Chip key={key} tone={close ? 'close' : 'wrong'} title={close ? `${words} (close)` : words}>
      {value} {ARROW[hint]}
    </Chip>
  )
}

function GuessRow({ q, g, names }: { q: DailyQuestion; g: DailyGuess; names: Map<number, string> }) {
  if (q.id === 'kda' && g.parts) {
    return <span className="flex gap-1">{g.parts.map((p, i) => hintChip(p.value, p.hint, p.close, i))}</span>
  }
  if (q.id === 'grade') return hintChip(String(g.value), g.hint ?? 'exact', !!g.close)
  const label = q.id === 'pilot' ? (names.get(g.value as number) ?? '?') : String(g.value) === 'win' ? 'Win' : 'Loss'
  return <Chip tone={g.correct ? 'right' : 'wrong'}>{label} {g.correct ? '✓' : '✗'}</Chip>
}

function QuestionCard({
  n,
  q,
  v,
  active,
  busy,
  onGuess,
}: {
  n: number
  q: DailyQuestion
  v: DailyView
  active: boolean
  busy: boolean
  onGuess: (value: string | number | number[]) => void
}) {
  const names = new Map(v.players.map((p) => [p.id, p.name]))
  const locked = !active && !q.finished
  return (
    <li className={`card flex flex-col gap-2.5 p-4 ${locked ? 'opacity-45' : ''} ${active ? 'ring-1 ring-hex-400/50' : ''}`}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-bold text-slate-500">{n}</span>
        <h2 className="text-sm font-semibold text-white">{q.label}</h2>
        <span className="ml-auto text-xs text-slate-400 tabular-nums">
          {q.finished
            ? `${q.points} / ${q.max_points} pts`
            : `worth ${q.worth} ${q.worth === 1 ? 'pt' : 'pts'}${q.tries == null && q.worth > 0 ? ' · -1 per wrong guess' : ''}`}
        </span>
      </div>
      {q.guesses.length > 0 && (
        <div className="flex flex-col items-start gap-1.5">
          {q.guesses.map((g, i) => (
            <GuessRow key={i} q={q} g={g} names={names} />
          ))}
        </div>
      )}
      {active && <GuessInput q={q} v={v} busy={busy} onGuess={onGuess} />}
      {(q.id === 'kda' || q.id === 'grade') && active && (
        <p className="text-[11px] text-slate-500">▲▼ the answer is higher or lower · amber means close (within 2, or one grade)</p>
      )}
    </li>
  )
}

function GuessInput({
  q,
  v,
  busy,
  onGuess,
}: {
  q: DailyQuestion
  v: DailyView
  busy: boolean
  onGuess: (value: string | number | number[]) => void
}) {
  const [kda, setKda] = useState(['', '', ''])
  const guessed = new Set(q.guesses.map((g) => String(g.value)))
  if (q.id === 'result') {
    return (
      <div className="flex gap-2">
        <button className="btn-primary px-6" disabled={busy} onClick={() => onGuess('win')}>
          Win
        </button>
        <button className="btn-danger px-6" disabled={busy} onClick={() => onGuess('loss')}>
          Loss
        </button>
      </div>
    )
  }
  if (q.id === 'pilot') {
    return (
      <div className="flex flex-wrap gap-2">
        {v.players.map((p) => (
          <button
            key={p.id}
            className="team-chip"
            style={{ ['--team' as string]: teamColor(p.id) } as CSSProperties}
            disabled={busy || guessed.has(String(p.id))}
            onClick={() => onGuess(p.id)}
          >
            {p.name}
          </button>
        ))}
      </div>
    )
  }
  if (q.id === 'grade') {
    return (
      <div className="flex flex-wrap gap-1.5">
        {v.grades.map((g) => (
          <button
            key={g}
            className="btn-secondary min-w-11 px-2.5 py-1 text-sm"
            disabled={busy || guessed.has(g)}
            onClick={() => onGuess(g)}
          >
            {g}
          </button>
        ))}
      </div>
    )
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onGuess(kda.map((x) => Number(x)))
    setKda(['', '', ''])
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      {['Kills', 'Deaths', 'Assists'].map((label, i) => (
        <label key={label} className="flex flex-col gap-1 text-[11px] text-slate-400">
          {label}
          <input
            className="input w-20 text-center tabular-nums"
            type="number"
            inputMode="numeric"
            min={0}
            max={99}
            required
            autoFocus={i === 0}
            value={kda[i]}
            onChange={(e) => setKda((k) => k.map((x, j) => (j === i ? e.target.value : x)))}
          />
        </label>
      ))}
      <button type="submit" className="btn-primary" disabled={busy}>
        Guess
      </button>
    </form>
  )
}

function Finished({ v }: { v: DailyView }) {
  const gameNo = useGameNumber()
  const [copied, setCopied] = useState(false)
  const a = v.answer!
  const copy = () => {
    void navigator.clipboard?.writeText(v.share ?? '').then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <section className="card flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-display text-3xl text-white tabular-nums">
          {v.score}/{v.max_score}
        </span>
        <span className="text-sm text-slate-300">
          It was <b style={{ color: teamColor(a.pilot) }}>{a.pilot_name}</b> · {a.result === 'win' ? 'Win' : 'Loss'} ·{' '}
          {a.kda.join('/')}
          {a.grade ? ` · ${a.grade}` : ''}
        </span>
        <Link to="/history" className="ml-auto text-xs text-hex-200 hover:underline">
          Game {gameNo(a.game_id)} in History
        </Link>
      </div>
      {v.share && (
        <div className="flex flex-col gap-2">
          <pre className="rounded-sm bg-black/40 px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap text-slate-200">{v.share}</pre>
          <button className="btn-secondary self-start" onClick={copy}>
            {copied ? 'Copied!' : 'Copy my result'}
          </button>
        </div>
      )}
      {v.leaderboard && v.leaderboard.length > 0 && (
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold text-white">Today</h2>
          <ol className="flex flex-col gap-0.5 text-sm">
            {v.leaderboard.map((e, i) => (
              <li key={e.user_id} className="flex gap-2">
                <span className="w-5 text-slate-500 tabular-nums">{i + 1}</span>
                <span className="flex-1 text-slate-200">{e.name}</span>
                <span className="text-slate-300 tabular-nums">
                  {e.score}/{v.max_score}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}
