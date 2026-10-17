import { Link } from 'react-router-dom'

/** The project's name as it appears in Riot's required notice. */
export const APP_NAME = 'Hardcore Draft'

/**
 * The notice Riot's "Legal Jibber Jabber" policy asks fan projects to show conspicuously
 * (section 6). It goes in the footer of every page.
 */
export function LegalNotice({ className = '' }: { className?: string }) {
  return (
    <p className={`text-center text-[11px] leading-relaxed text-slate-500 ${className}`}>
      {APP_NAME} was created under Riot Games' "Legal Jibber Jabber" policy using assets owned by Riot Games. Riot
      Games does not endorse or sponsor this project.{' '}
      <Link to="/legal" className="whitespace-nowrap underline hover:text-slate-300">
        Privacy &amp; terms
      </Link>
    </p>
  )
}
