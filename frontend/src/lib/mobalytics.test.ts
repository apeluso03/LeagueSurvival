import { describe, expect, it } from 'vitest'
import { mobaBuildUrl, mobaRole, mobaSlug, widgetPage } from './mobalytics'

describe('mobalytics', () => {
  it('uses the Data Dragon id as the slug', () => {
    expect(mobaSlug('MonkeyKing')).toBe('monkeyking')
    expect(mobaSlug('Nunu')).toBe('nunu')
    expect(mobaBuildUrl('KSante')).toBe('https://mobalytics.gg/lol/champions/ksante/build')
  })

  it('maps roles to theirs', () => {
    expect(mobaRole('BOTTOM')).toBe('ADC')
    expect(mobaRole('UTILITY')).toBe('SUPPORT')
    expect(mobaRole('MIDDLE')).toBe('MID')
    expect(mobaRole(null)).toBeUndefined()
  })

  it('builds the frame page with only safe characters', () => {
    const page = widgetPage({ championId: 'Ahri"><script>x</script>', role: 'MID', compact: true, frameId: 'f1' })
    expect(page).toContain('data-moba-widget="lol-champion-build-compact"')
    expect(page).toContain('data-moba-champion="ahriscriptxscript"')
    expect(page).toContain('data-moba-champion-role="MID"')
    expect(page).not.toContain('<script>x')
    // their image server rejects any Referer but its own, so the frame must not send one
    expect(page).toContain('<meta name="referrer" content="no-referrer">')
  })
})
