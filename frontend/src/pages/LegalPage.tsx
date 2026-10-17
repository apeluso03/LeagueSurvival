import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { LogoMark } from '../components/icons'
import { APP_NAME, LegalNotice } from '../components/LegalNotice'
import { usePageTitle } from '../hooks/usePageTitle'

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-gold-100">{title}</h2>
      <div className="flex flex-col gap-3 text-sm leading-relaxed text-slate-300">{children}</div>
    </section>
  )
}

/** Privacy policy and terms of use. Public: no sign-in needed. */
export function LegalPage() {
  usePageTitle('Privacy & terms')
  return (
    <div className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-8 px-4 py-10">
      <Link to="/" className="flex items-center gap-2 self-start">
        <LogoMark className="h-8 w-8" />
        <span className="font-display text-sm tracking-[0.15em] text-white uppercase">{APP_NAME}</span>
      </Link>
      <h1 className="text-3xl font-bold text-white">Privacy &amp; terms</h1>
      <p className="text-xs text-slate-500">Last updated October 17, 2026</p>

      <Section id="privacy" title="Privacy">
        <p>
          {APP_NAME} is a free fan project for running a hardcore champion challenge in League of Legends with friends:
          spin for your champions, and the ones you lose with are gone for good. It keeps as little about people as it
          can.
        </p>
        <p className="font-semibold text-slate-100">What we store about you, if you have an account</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Your username and a scrambled (hashed) version of your password. We can't see your password.</li>
          <li>One sign-in cookie, used only to keep you signed in. No ads, no tracking, no analytics cookies.</li>
          <li>Your challenge records: spins, results, gold, items, titles and your team colour.</li>
        </ul>
        <p className="font-semibold text-slate-100">Riot data about players in a group</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            If the group owner adds your Riot ID, we look up your Riot account ID (PUUID) and save your stats from your
            recent matches (champion, KDA, CS, damage, vision and so on) to show stats and award gold.
          </li>
          <li>While a challenge game is live, we show both teams' champions, items, levels and scores.</li>
        </ul>
        <p className="font-semibold text-slate-100">Other League players</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            Matches include other players. We remove their names and account IDs before saving a match, and keep only
            game numbers (for team averages and grades). Live games label opponents by champion, never by name.
          </li>
          <li>
            For build and ban suggestions we read public high-elo ranked games and keep only totals per champion (games
            and wins by role, runes, items, summoner spells and matchups), never who played them. The list of
            high-elo account IDs to read is temporary and replaced every 12 hours.
          </li>
        </ul>
        <p className="font-semibold text-slate-100">Deleting your data</p>
        <p>
          Ask your group's owner, who can remove your account and your Riot data from Settings. Your challenge history
          (which champions you played, wins and losses) stays with the group, but your Riot match stats and account ID
          are deleted. We also act on deletion requests Riot Games passes on to developers.
        </p>
        <p>
          We don't sell or share your data. Riot data comes from the Riot Games API and is used only to show it in this
          app.
        </p>
      </Section>

      <Section id="terms" title="Terms of use">
        <ul className="list-disc space-y-1 pl-5">
          <li>
            {APP_NAME} is free and not for profit. There's nothing to buy: shop "gold" is a game inside the app and has
            no real-world value.
          </li>
          <li>
            Don't run contests, sweepstakes or anything with real prizes, entry fees or money through the app. Riot's
            API terms don't allow it.
          </li>
          <li>
            Don't use the app to harass anyone. The Hall of Shame is for friendly teasing inside your own group only.
          </li>
          <li>
            The app never changes or interferes with the game, and doesn't track summoner spell or ultimate cooldowns.
            Don't use it in a way that would break Riot's rules.
          </li>
          <li>The app is provided as is. It may change or shut down, and data may be lost.</li>
        </ul>
      </Section>

      <footer className="mt-auto border-t border-white/10 pt-6">
        <LegalNotice />
        <p className="mt-2 text-center text-[11px] text-slate-500">
          League of Legends and Riot Games are trademarks or registered trademarks of Riot Games, Inc.
        </p>
      </footer>
    </div>
  )
}
