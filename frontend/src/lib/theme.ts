/**
 * Site themes (SPEC 22). The look is a set of CSS variables (index.css); a theme swaps them through
 * `data-theme` on <html> (themes.css). The choice is per browser (localStorage), and index.html
 * applies it before the page draws, so there's no flash of the default theme.
 */
import { useSyncExternalStore } from 'react'

export type ThemeId = 'broadcast' | 'aero' | 'spectral' | 'synthwave'

export interface ThemeInfo {
  id: ThemeId
  name: string
  blurb: string
  swatch: string[] // colours for the picker's preview chip
  browserColor: string // <meta name="theme-color">: the phone's address bar
}

export const THEMES: ThemeInfo[] = [
  {
    id: 'broadcast',
    name: 'Broadcast',
    blurb: 'The default: an esports stage in electric blue and gold',
    swatch: ['#05070b', '#2e9bff', '#e8c97a'],
    browserColor: '#010a13',
  },
  {
    id: 'aero',
    name: 'Frutiger Aero',
    blurb: 'Glossy glass, blue skies, bubbles and fresh green',
    swatch: ['#bfe8ff', '#18a4e8', '#7cd35b'],
    browserColor: '#6cc3f2',
  },
  {
    id: 'spectral',
    name: 'Spectral',
    blurb: 'Ghost-light teal drifting through midnight mist',
    swatch: ['#030807', '#33e6b8', '#d4f27a'],
    browserColor: '#030807',
  },
  {
    id: 'synthwave',
    name: 'Neon Sunset',
    blurb: 'Synthwave: hot pink, a striped sun and a neon grid',
    swatch: ['#0b0418', '#ff3fb4', '#ffc247'],
    browserColor: '#12052a',
  },
]

const KEY = 'hd:theme'
const listeners = new Set<() => void>()

function isTheme(v: string | null): v is ThemeId {
  return THEMES.some((t) => t.id === v)
}

export function getTheme(): ThemeId {
  const v = typeof document === 'undefined' ? null : document.documentElement.dataset.theme ?? null
  return isTheme(v) ? v : 'broadcast'
}

export function setTheme(id: ThemeId) {
  const root = document.documentElement
  if (id === 'broadcast') delete root.dataset.theme
  else root.dataset.theme = id
  const meta = document.querySelector('meta[name="theme-color"]')
  meta?.setAttribute('content', THEMES.find((t) => t.id === id)!.browserColor)
  try {
    localStorage.setItem(KEY, id)
  } catch {
    /* a private window: the theme just won't be remembered */
  }
  listeners.forEach((fn) => fn())
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export const useTheme = () => useSyncExternalStore(subscribe, getTheme, () => 'broadcast' as ThemeId)
