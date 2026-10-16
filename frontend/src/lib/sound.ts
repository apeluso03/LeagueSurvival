/**
 * Spin sound effects, synthesized with the Web Audio API (no audio files). SPEC 17.3.
 * Browsers only allow audio after a user gesture; the Spin click counts, so `unlock()` is called then.
 */
import { useSyncExternalStore } from 'react'

const STORAGE_KEY = 'lol-survival:muted'
let ctx: AudioContext | null = null
let master: GainNode | null = null // everything plays through this, so muting is instant
let muted = readMuted()
const listeners = new Set<() => void>()

function readMuted(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function setMuted(value: boolean) {
  muted = value
  if (master && ctx) master.gain.setTargetAtTime(value ? 0 : 1, ctx.currentTime, 0.01)
  try {
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0')
  } catch {
    /* storage unavailable: keep it for this session only */
  }
  listeners.forEach((l) => l())
}

export function useMuted(): boolean {
  return useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    () => muted,
  )
}

function audio(): AudioContext | null {
  if (muted || typeof window === 'undefined') return null
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return null
  if (!ctx) {
    ctx = new Ctor()
    master = ctx.createGain()
    master.connect(ctx.destination)
  }
  if (ctx.state === 'suspended') void ctx.resume()
  return ctx
}

const out = () => master ?? ctx!.destination

/** Call from a click handler so later sounds are allowed to play. */
export function unlock() {
  audio()
}

function blip(freq: number, duration: number, volume: number, type: OscillatorType = 'triangle', at = 0) {
  const ac = audio()
  if (!ac) return null
  const t = ac.currentTime + at
  const osc = ac.createOscillator()
  const gain = ac.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, t)
  gain.gain.setValueAtTime(0.0001, t)
  gain.gain.exponentialRampToValueAtTime(volume, t + 0.004)
  gain.gain.exponentialRampToValueAtTime(0.0001, t + duration)
  osc.connect(gain).connect(out())
  osc.start(t)
  osc.stop(t + duration + 0.02)
  return osc
}

const MIN_TICK_GAP_MS = 45 // early in a spin cards pass ~25x a second; more ticks than this is just noise

/**
 * Schedule a whole spin's ticks on the audio clock in one go (no JavaScript runs during the spin).
 * `ticks` are [ms after startAt, progress 0..1]; `startAt` is a performance.now() timestamp.
 * Returns a function that silences any ticks that haven't played yet (e.g. on Skip).
 */
export function scheduleTicks(ticks: [number, number][], startAt: number): () => void {
  const ac = audio()
  if (!ac) return () => {}
  const lead = (startAt - performance.now()) / 1000
  const nodes: OscillatorNode[] = []
  let last = -Infinity
  for (const [ms, progress] of ticks) {
    if (ms - last < MIN_TICK_GAP_MS) continue
    last = ms
    const at = Math.max(0, lead + ms / 1000)
    for (const n of [blip(1900 - progress * 500, 0.03, 0.08, 'square', at), blip(950 - progress * 250, 0.04, 0.05, 'triangle', at)])
      if (n) nodes.push(n)
  }
  return () => {
    const now = ac.currentTime
    for (const n of nodes) {
      try {
        n.stop(now)
      } catch {
        /* already finished */
      }
    }
  }
}

/** Reels start: a short rising whoosh. */
export function playStart() {
  const ac = audio()
  if (!ac) return
  const t = ac.currentTime
  const osc = ac.createOscillator()
  const gain = ac.createGain()
  osc.type = 'sawtooth'
  osc.frequency.setValueAtTime(180, t)
  osc.frequency.exponentialRampToValueAtTime(720, t + 0.35)
  gain.gain.setValueAtTime(0.0001, t)
  gain.gain.exponentialRampToValueAtTime(0.05, t + 0.05)
  gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.4)
  const filter = ac.createBiquadFilter()
  filter.type = 'lowpass'
  filter.frequency.value = 1400
  osc.connect(filter).connect(gain).connect(out())
  osc.start(t)
  osc.stop(t + 0.45)
}

/** Reels land: a bright two-note reveal chime. */
export function playReveal() {
  blip(784, 0.5, 0.12, 'sine')
  blip(1175, 0.7, 0.1, 'sine', 0.09)
  blip(1568, 0.9, 0.06, 'triangle', 0.18)
}

/** Buying an item: a quick double coin clink. */
export function playPurchase() {
  blip(1568, 0.12, 0.09, 'square')
  blip(2093, 0.18, 0.08, 'square', 0.07)
  blip(2637, 0.35, 0.06, 'sine', 0.12)
}

/** A champion getting eliminated: a short crack, then a low thud. `at` is seconds from now. */
export function playShatter(at = 0) {
  const ac = audio()
  if (!ac) return
  const t = ac.currentTime + at
  // Crack: a burst of filtered noise.
  const len = Math.floor(ac.sampleRate * 0.14)
  const buf = ac.createBuffer(1, len, ac.sampleRate)
  const data = buf.getChannelData(0)
  for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len) ** 3
  const noise = ac.createBufferSource()
  noise.buffer = buf
  const hp = ac.createBiquadFilter()
  hp.type = 'highpass'
  hp.frequency.value = 1800
  const ng = ac.createGain()
  ng.gain.value = 0.22
  noise.connect(hp).connect(ng).connect(out())
  noise.start(t)
  // Thud: a falling sine.
  const osc = ac.createOscillator()
  const gain = ac.createGain()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(140, t)
  osc.frequency.exponentialRampToValueAtTime(38, t + 0.45)
  gain.gain.setValueAtTime(0.0001, t)
  gain.gain.exponentialRampToValueAtTime(0.4, t + 0.01)
  gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.55)
  osc.connect(gain).connect(out())
  osc.start(t)
  osc.stop(t + 0.6)
}

/** A shield breaking instead of the champion: a bright metallic ting. */
export function playShieldSave(at = 0) {
  blip(1319, 0.5, 0.09, 'sine', at)
  blip(1976, 0.6, 0.06, 'triangle', at + 0.05)
  blip(2637, 0.8, 0.04, 'sine', at + 0.1)
}

/** One reel landing during a staggered spin; later reels ring a step higher. */
export function playLand(index = 0) {
  const step = 2 ** ((index * 2) / 12)
  blip(659 * step, 0.35, 0.1, 'sine')
  blip(988 * step, 0.45, 0.06, 'triangle', 0.05)
}

/** Everyone has picked: two low hits and a bright chord, like champ select's lock-in. */
export function playLockIn() {
  blip(196, 0.25, 0.22, 'triangle')
  blip(147, 0.3, 0.2, 'triangle', 0.12)
  for (const [f, at] of [[587, 0.28], [740, 0.3], [880, 0.32], [1175, 0.34]] as const) blip(f, 0.9, 0.06, 'sine', at)
}

/** A win: a quick rising fanfare. */
export function playVictory() {
  const notes = [523, 659, 784, 1047]
  notes.forEach((f, i) => blip(f, 0.35, 0.1, 'triangle', i * 0.09))
  blip(1568, 1.1, 0.07, 'sine', 0.38)
  blip(2093, 1.2, 0.05, 'sine', 0.42)
}

/** A streak milestone: a bigger fanfare on top of the victory one. */
export function playMilestone() {
  const notes = [784, 988, 1175, 1568, 1976]
  notes.forEach((f, i) => blip(f, 0.5, 0.08, 'square', 0.75 + i * 0.07))
  blip(2637, 1.5, 0.06, 'sine', 1.15)
}
