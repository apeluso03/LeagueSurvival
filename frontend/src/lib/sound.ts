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
