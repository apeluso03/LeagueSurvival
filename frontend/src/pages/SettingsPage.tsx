import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { api } from '../api/client'
import { ChampionPortrait, ErrorText, Modal } from '../components/ui'
import { useAction, useChampions, usePlayers, useRiotStatus, useRuns, useSettings } from '../hooks/queries'
import { allTags, filterChampions } from '../lib/champions'
import { QUEUES } from '../lib/queues'
import type { AppSettings, Player } from '../types'

export function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PlayersSection />
      <RunsSection />
      <ChallengeSection />
      <ChampionsSection />
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card flex flex-col gap-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  )
}

// --- players -----------------------------------------------------------------

function splitRiotId(value: string): { riot_game_name: string | null; riot_tag_line: string | null } {
  const [name, tag] = value.split('#').map((s) => s.trim())
  return { riot_game_name: name || null, riot_tag_line: tag || null }
}

const REGIONS = [
  { id: 'americas', label: 'Americas (NA, BR, LAN, LAS)' },
  { id: 'europe', label: 'Europe (EUW, EUNE, TR, ME)' },
  { id: 'asia', label: 'Asia (KR, JP)' },
  { id: 'sea', label: 'SEA (OCE, SG, TW, VN)' },
]

function RegionSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Region">
      {REGIONS.map((r) => (
        <option key={r.id} value={r.id}>
          {r.label}
        </option>
      ))}
    </select>
  )
}

function PlayersSection() {
  const players = usePlayers()
  const [name, setName] = useState('')
  const [riotId, setRiotId] = useState('')
  const [region, setRegion] = useState('americas')
  const [warning, setWarning] = useState<string | null>(null)
  const create = useAction(api.createPlayer)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate(
      { display_name: name.trim(), region, ...splitRiotId(riotId) },
      {
        onSuccess: (p) => {
          setName('')
          setRiotId('')
          setWarning(p.link_error ? `${p.display_name} was added but not linked: ${p.link_error}` : null)
        },
      },
    )
  }

  return (
    <Section title="Players">
      <ul className="flex flex-col divide-y divide-slate-800">
        {players.data?.map((p) => <PlayerRow key={p.id} player={p} />)}
        {players.data?.length === 0 && <li className="py-2 text-sm text-slate-400">No players yet.</li>}
      </ul>
      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <input className="input" placeholder="Display name" value={name} onChange={(e) => setName(e.target.value)} />
        <input
          className="input"
          placeholder="Riot ID (Name#TAG), optional"
          value={riotId}
          onChange={(e) => setRiotId(e.target.value)}
        />
        <RegionSelect value={region} onChange={setRegion} />
        <button className="btn-primary" disabled={!name.trim() || create.isPending}>
          Add player
        </button>
      </form>
      <ErrorText error={create.error} />
      {warning && <p className="text-sm text-amber-300">{warning}</p>}
    </Section>
  )
}

function LinkBadge({ player }: { player: Player }) {
  const link = useAction(() => api.linkPlayer(player.id))
  if (!player.riot_game_name) return null
  if (player.puuid) {
    return (
      <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300" title="Matches can be imported">
        Linked
      </span>
    )
  }
  return (
    <span className="flex flex-wrap items-center gap-2">
      <span className="rounded bg-slate-700/60 px-2 py-0.5 text-xs text-slate-300">Not linked</span>
      <button className="text-xs underline" disabled={link.isPending} onClick={() => link.mutate(undefined)}>
        {link.isPending ? 'Linking...' : 'Link now'}
      </button>
      {link.error && <span className="text-xs text-red-300">{link.error.message}</span>}
    </span>
  )
}

function PlayerRow({ player }: { player: Player }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(player.display_name)
  const [riotId, setRiotId] = useState(
    player.riot_game_name ? `${player.riot_game_name}#${player.riot_tag_line ?? ''}` : '',
  )
  const [region, setRegion] = useState(player.region)
  const update = useAction((body: Partial<Player>) => api.updatePlayer(player.id, body))
  const remove = useAction(() => api.deletePlayer(player.id))

  if (editing) {
    return (
      <li className="flex flex-wrap items-center gap-2 py-2">
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="input" placeholder="Name#TAG" value={riotId} onChange={(e) => setRiotId(e.target.value)} />
        <RegionSelect value={region} onChange={setRegion} />
        <button
          className="btn-primary"
          disabled={update.isPending}
          onClick={() =>
            update.mutate(
              { display_name: name.trim(), region, ...splitRiotId(riotId) },
              { onSuccess: () => setEditing(false) },
            )
          }
        >
          Save
        </button>
        <button className="btn-secondary" onClick={() => setEditing(false)}>
          Cancel
        </button>
        <ErrorText error={update.error} />
      </li>
    )
  }
  return (
    <li className="flex flex-wrap items-center gap-3 py-2">
      <span className="font-medium">{player.display_name}</span>
      <span className="text-sm text-slate-400">
        {player.riot_game_name ? `${player.riot_game_name}#${player.riot_tag_line}` : 'No Riot ID'}
      </span>
      <LinkBadge player={player} />
      <div className="ml-auto flex gap-2">
        <button className="btn-secondary" onClick={() => setEditing(true)}>
          Edit
        </button>
        <button
          className="btn-secondary"
          onClick={() => confirm(`Remove ${player.display_name}?`) && remove.mutate(undefined)}
        >
          Remove
        </button>
      </div>
      <ErrorText error={remove.error} />
    </li>
  )
}

// --- runs --------------------------------------------------------------------

function RunsSection() {
  const runs = useRuns()
  const settings = useSettings()
  const setActive = useAction((id: number) => api.updateSettings({ active_run_id: id }))
  const end = useAction((id: number) => api.endRun(id))
  const [creating, setCreating] = useState(false)

  return (
    <Section title="Runs">
      <ul className="flex flex-col divide-y divide-slate-800">
        {runs.data?.map((r) => {
          const active = settings.data?.active_run_id === r.id
          return (
            <li key={r.id} className="flex flex-wrap items-center gap-3 py-2">
              <span className="font-medium">{r.name}</span>
              {active && <span className="rounded bg-gold-500/20 px-2 py-0.5 text-xs text-gold-300">selected</span>}
              <span className="text-sm text-slate-400">
                {r.status === 'ended' ? 'Ended' : 'Active'} · {r.win_count} wins · best streak {r.best_streak} ·{' '}
                {r.alive_count}/{r.total_count} alive · {r.options_per_player} options
              </span>
              <div className="ml-auto flex gap-2">
                {!active && (
                  <button className="btn-secondary" onClick={() => setActive.mutate(r.id)}>
                    Select
                  </button>
                )}
                {r.status === 'active' && (
                  <button
                    className="btn-danger"
                    onClick={() => confirm(`End "${r.name}" with ${r.win_count} wins?`) && end.mutate(r.id)}
                  >
                    End run
                  </button>
                )}
              </div>
            </li>
          )
        })}
        {runs.data?.length === 0 && <li className="py-2 text-sm text-slate-400">No runs yet.</li>}
      </ul>
      <ErrorText error={setActive.error ?? end.error} />
      <div>
        <button className="btn-primary" onClick={() => setCreating(true)}>
          Start a new run
        </button>
      </div>
      {creating && <NewRunModal onClose={() => setCreating(false)} />}
    </Section>
  )
}

function NewRunModal({ onClose }: { onClose: () => void }) {
  const champions = useChampions()
  const [name, setName] = useState(`Run ${new Date().toLocaleDateString()}`)
  const [options, setOptions] = useState<3 | 4>(3)
  const [custom, setCustom] = useState(false)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [tag, setTag] = useState<string | null>(null)
  const create = useAction(api.createRun)

  const all = champions.data ?? []
  const tags = useMemo(() => allTags(all), [all])
  const shown = filterChampions(all, search, tag)

  const toggle = (id: string) =>
    setPicked((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const setMany = (ids: string[], on: boolean) =>
    setPicked((s) => {
      const next = new Set(s)
      ids.forEach((id) => (on ? next.add(id) : next.delete(id)))
      return next
    })

  const submit = () =>
    create.mutate(
      { name: name.trim(), options_per_player: options, champion_ids: custom ? [...picked] : null },
      { onSuccess: onClose },
    )

  return (
    <Modal title="Start a new run" onClose={onClose}>
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          Name
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          Options per player
          <div className="flex gap-2">
            {([3, 4] as const).map((n) => (
              <button
                key={n}
                className={options === n ? 'btn-primary' : 'btn-secondary'}
                onClick={() => setOptions(n)}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2 text-sm">
          Champion pool
          <div className="flex gap-2">
            <button className={!custom ? 'btn-primary' : 'btn-secondary'} onClick={() => setCustom(false)}>
              All {all.length} champions
            </button>
            <button className={custom ? 'btn-primary' : 'btn-secondary'} onClick={() => setCustom(true)}>
              Custom subset
            </button>
          </div>
        </div>

        {custom && (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <input className="input flex-1" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} />
              <select className="input" value={tag ?? ''} onChange={(e) => setTag(e.target.value || null)}>
                <option value="">All classes</option>
                {tags.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-400">{picked.size} selected</span>
              <button className="underline" onClick={() => setMany(shown.map((c) => c.id), true)}>
                Select shown
              </button>
              <button className="underline" onClick={() => setMany(shown.map((c) => c.id), false)}>
                Clear shown
              </button>
            </div>
            <div className="grid max-h-72 grid-cols-5 gap-1.5 overflow-y-auto sm:grid-cols-7">
              {shown.map((c) => (
                <button
                  key={c.id}
                  onClick={() => toggle(c.id)}
                  title={c.name}
                  className={`rounded-md p-0.5 ${picked.has(c.id) ? 'ring-2 ring-gold-400' : 'opacity-60 hover:opacity-100'}`}
                >
                  <ChampionPortrait champion={c} size="md" className="w-full" />
                </button>
              ))}
            </div>
          </div>
        )}

        <ErrorText error={create.error} />
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-primary"
            disabled={!name.trim() || create.isPending || (custom && picked.size === 0)}
            onClick={submit}
          >
            Start run
          </button>
        </div>
      </div>
    </Modal>
  )
}

// --- challenge settings ---------------------------------------------------------


function ChallengeSection() {
  const { data: s } = useSettings()
  const update = useAction((body: Partial<AppSettings>) => api.updateSettings(body))
  if (!s) return null

  const toggleQueue = (id: number) =>
    update.mutate({
      allowed_queue_ids: s.allowed_queue_ids.includes(id)
        ? s.allowed_queue_ids.filter((q) => q !== id)
        : [...s.allowed_queue_ids, id],
    })

  return (
    <Section title="Riot API">
      <RiotStatusPanel />
      <div className="flex flex-col gap-1 text-sm">
        <span>Queues that count for the challenge (used by auto results)</span>
        <div className="flex flex-wrap gap-3">
          {QUEUES.map((q) => (
            <label key={q.id} className="flex items-center gap-1.5">
              <input type="checkbox" checked={s.allowed_queue_ids.includes(q.id)} onChange={() => toggleQueue(q.id)} />
              {q.label}
            </label>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-4 text-sm">
        <NumberSetting
          label="Poll interval (seconds)"
          value={s.poll_interval_seconds}
          min={30}
          onSave={(v) => update.mutate({ poll_interval_seconds: v })}
        />
        <NumberSetting
          label="Remake threshold (seconds)"
          value={s.remake_threshold_seconds}
          min={0}
          onSave={(v) => update.mutate({ remake_threshold_seconds: v })}
        />
      </div>
      <ErrorText error={update.error} />
    </Section>
  )
}

function RiotStatusPanel() {
  const [checked, setChecked] = useState(false)
  const status = useRiotStatus(checked)
  const sync = useAction(api.sync)
  const st = status.data
  if (!st) return null

  let keyLabel = <span className="text-slate-300">set</span>
  if (!st.key_set) keyLabel = <span className="text-red-300">not set</span>
  else if (st.key_valid === true) keyLabel = <span className="text-emerald-300">working</span>
  else if (st.key_valid === false) keyLabel = <span className="text-red-300">not working</span>

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span>API key:</span>
        {keyLabel}
        {st.key_set && (
          <button
            className="text-xs underline"
            disabled={status.isFetching}
            onClick={() => (checked ? status.refetch() : setChecked(true))}
          >
            {status.isFetching ? 'Testing...' : 'Test key'}
          </button>
        )}
      </div>
      {st.key_set && st.message && <p className="text-red-300">{st.message}</p>}
      {!st.key_set && (
        <p className="text-slate-400">
          Get a personal key at developer.riotgames.com, put <code>RIOT_API_KEY=your-key</code> in a <code>.env</code>{' '}
          file in the project folder, then restart the backend. Everything else works without it.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn-secondary" disabled={!st.key_set || sync.isPending} onClick={() => sync.mutate(undefined)}>
          {sync.isPending ? 'Syncing...' : 'Sync matches now'}
        </button>
        <span className="text-slate-400">
          Last sync: {st.last_sync_at ? new Date(st.last_sync_at).toLocaleString() : 'never'}
        </span>
      </div>
      {sync.data && (
        <p className="text-slate-300">
          Synced {sync.data.players_synced} player(s), {sync.data.new_matches} new match(es).
        </p>
      )}
      {st.last_sync_error && <p className="text-red-300">Last sync problem: {st.last_sync_error}</p>}
      <ErrorText error={sync.error} />
    </div>
  )
}

function NumberSetting({ label, value, min, onSave }: { label: string; value: number; min: number; onSave: (v: number) => void }) {
  const [draft, setDraft] = useState(String(value))
  const commit = () => {
    const n = Number(draft)
    if (Number.isInteger(n) && n >= min && n !== value) onSave(n)
    else setDraft(String(value))
  }
  return (
    <label className="flex flex-col gap-1">
      {label}
      <input
        className="input w-32"
        type="number"
        min={min}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === 'Enter' && commit()}
      />
    </label>
  )
}

// --- champions ---------------------------------------------------------------

function ChampionsSection() {
  const champions = useChampions()
  const qc = useQueryClient()
  const refresh = useMutation({
    mutationFn: api.refreshChampions,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['champions'] }),
  })
  const version = champions.data?.[0]?.ddragon_version
  return (
    <Section title="Champions">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span>
          {champions.data?.length ?? 0} champions cached{version && <> from patch {version}</>}.
        </span>
        <button className="btn-secondary" disabled={refresh.isPending} onClick={() => refresh.mutate(undefined)}>
          {refresh.isPending ? 'Refreshing...' : 'Refresh from Data Dragon'}
        </button>
      </div>
      <ErrorText error={refresh.error} />
    </Section>
  )
}
