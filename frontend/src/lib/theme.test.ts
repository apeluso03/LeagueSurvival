import { afterEach, describe, expect, it } from 'vitest'
import { THEMES, getTheme, setTheme } from './theme'

afterEach(() => setTheme('broadcast'))

describe('themes', () => {
  it('sets data-theme on <html>, remembers it, and the default clears it', () => {
    document.head.innerHTML = '<meta name="theme-color" content="#010a13">'
    setTheme('aero')
    expect(document.documentElement.dataset.theme).toBe('aero')
    expect(localStorage.getItem('hd:theme')).toBe('aero')
    expect(getTheme()).toBe('aero')
    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute('content')).toBe('#6cc3f2')
    setTheme('broadcast')
    expect(document.documentElement.dataset.theme).toBeUndefined()
    expect(getTheme()).toBe('broadcast')
  })

  it('has the default, Frutiger Aero and two more', () => {
    expect(THEMES.map((t) => t.id)).toEqual(['broadcast', 'aero', 'spectral', 'synthwave'])
  })

  it('ignores an unknown theme on the page', () => {
    document.documentElement.dataset.theme = 'nope'
    expect(getTheme()).toBe('broadcast')
  })
})
