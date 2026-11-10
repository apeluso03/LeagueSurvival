import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorText } from '../components/ui'
import { useAction } from '../hooks/queries'
import { useAccess } from '../hooks/useAuth'
import type { DiscordKind, DiscordStatus } from '../types'

const ERRORS: Record<string, string> = {
  expired: 'That Discord link expired or was opened in another browser. Try again.',
  cancelled: 'Discord was cancelled.',
  discord: "Discord didn't answer. Try again in a moment.",
  taken: 'That Discord account is already linked to another Hardcore Draft account.',
  'not-owner': "Only the group's owner can add the bot.",
  'no-server': 'Pick a server on the Discord page.',
  'server-taken': 'That Discord server is already linked to another group.',
}

const DONE: Record<string, string> = {
  linked: 'Your Discord account is linked.',
  server: 'The bot is in your server. Pick the channel for announcements below.',
}

/**
 * The Discord bot (SPEC 19): everyone links their own Discord account (so the bot knows who's
 * who); the group owner adds the bot to the group's server, picks the channel and what gets posted.
 */
export function DiscordSection() {
  const { isOwner } = useAccess()
  const status = useQuery({ queryKey: ['discord'], queryFn: api.discord })
  const [params] = useSearchParams()
  const unlink = useAction(api.unlinkDiscord)
  const s = status.data
  if (!s?.enabled) return null
  const done = params.get('discord')
  const error = params.get('discord_error')

  return (
    <section id="discord" className="card flex scroll-mt-32 flex-col gap-4">
      <h2 className="text-lg font-semibold">Discord</h2>
      {done && DONE[done] && <p className="text-sm text-emerald-300">{DONE[done]}</p>}
      {error && <p className="text-sm text-red-300">{ERRORS[error] ?? 'Something went wrong with Discord.'}</p>}

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-slate-400">Your Discord</span>
        {s.linked ? (
          <>
            <span className="text-emerald-300">Linked</span>
            <button className="btn-secondary px-3 py-1 text-xs" disabled={unlink.isPending} onClick={() => unlink.mutate()}>
              Unlink
            </button>
          </>
        ) : (
          <a className="btn-secondary px-3 py-1 text-xs" href="/api/discord/connect">
            Link Discord
          </a>
        )}
        <span className="text-xs text-slate-500">
          Lets the bot know which player you are, and lets you sign in with Discord.
        </span>
      </div>
      <ErrorText error={unlink.error} />

      {isOwner && <ServerSettings status={s} />}
    </section>
  )
}

function ServerSettings({ status }: { status: DiscordStatus }) {
  const server = status.server
  const channels = useQuery({ queryKey: ['discord', 'channels'], queryFn: api.discordChannels, enabled: !!server })
  const update = useAction(api.updateDiscordServer)
  const test = useAction(api.discordTest)
  const remove = useAction(api.removeDiscordServer)

  if (!server) {
    return (
      <div className="flex flex-col gap-2 border-t border-white/[0.07] pt-4">
        <p className="text-sm text-slate-300">
          Add the bot to your group's Discord server. It posts spins, the live game, results, trophies and recaps, and
          everyone can use slash commands like <code>/run</code>, <code>/build</code> and <code>/role</code>.
        </p>
        <a className="btn-primary self-start" href="/api/discord/install">
          Add the bot to Discord
        </a>
      </div>
    )
  }

  const muted = new Set(server.muted)
  const toggle = (kind: DiscordKind) => {
    const next = new Set(muted)
    if (next.has(kind)) next.delete(kind)
    else next.add(kind)
    update.mutate({ muted: [...next] })
  }

  return (
    <div className="flex flex-col gap-4 border-t border-white/[0.07] pt-4">
      <p className="text-sm">
        <span className="text-slate-400">Server </span>
        <b>{server.guild_name || 'Your server'}</b>
      </p>
      {server.last_error && (
        <p className="rounded-sm bg-red-950/50 px-3 py-2 text-sm text-red-200 ring-1 ring-red-800/60 ring-inset">
          Discord refused the last post ({server.last_error}). Check the bot is still in the server and may post in the
          channel.
        </p>
      )}
      <label className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-400">Announcements go to</span>
        <select
          className="input w-auto"
          value={server.channel_id ?? ''}
          disabled={channels.isLoading || update.isPending}
          onChange={(e) => e.target.value && update.mutate({ channel_id: e.target.value })}
        >
          {!server.channel_id && <option value="">Pick a channel</option>}
          {(channels.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              #{c.name}
            </option>
          ))}
          {server.channel_id && !channels.data?.some((c) => c.id === server.channel_id) && (
            <option value={server.channel_id}>{channels.isLoading ? 'Loading...' : 'A channel the bot can no longer see'}</option>
          )}
        </select>
        <button
          className="btn-secondary px-3 py-1 text-xs"
          disabled={!server.channel_id || test.isPending}
          onClick={() => test.mutate()}
        >
          {test.isSuccess ? 'Sent' : 'Send a test message'}
        </button>
      </label>
      <ErrorText error={channels.error ?? update.error ?? test.error} />

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm text-slate-400">What the bot posts</legend>
        {(Object.entries(status.kinds) as [DiscordKind, string][]).map(([kind, label]) => (
          <label key={kind} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!muted.has(kind)} disabled={update.isPending} onChange={() => toggle(kind)} />
            {label}
          </label>
        ))}
      </fieldset>

      <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.07] pt-3">
        <button
          className="btn-danger px-3 py-1 text-xs"
          disabled={remove.isPending}
          onClick={() => window.confirm('Remove the bot from this server?') && remove.mutate()}
        >
          Remove the bot
        </button>
        <span className="text-xs text-slate-500">
          To move to another server, remove it here, then add it again.
        </span>
      </div>
      <ErrorText error={remove.error} />
    </div>
  )
}
