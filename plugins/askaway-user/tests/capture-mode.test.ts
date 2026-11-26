import { expect, test } from 'claude-code/testing'
import {
  CAPTURE_MODES,
  captureModeFile,
  leadOf,
  modeChangedText,
  modeCommandText,
  modeSinceText,
  otherModes,
  parseCaptureMode,
  parseQuestion,
  pausedText,
  pausesSession,
} from '../hooks/model'
import { MODE_COLOR } from '../hooks/look'

const MINUTE = 60_000
const NOW = 1_800_000_000_000

const questionOf = (extra: Record<string, unknown>) => {
  const parsed = parseQuestion(
    {
      id: 'q-m-000001',
      ts: 1000,
      title: 'Title',
      question: 'Which way?',
      options: [
        { key: 'A', label: 'Keep', tradeoff: 'cheap', fit: 80 },
        { key: 'B', label: 'Rewrite', tradeoff: 'slow', fit: 40 },
      ],
      recommended: 'A',
      risk: 'low',
      ...extra,
    },
    'q-m-000001',
  )
  if (parsed === undefined) throw new Error('fixture q-m-000001 did not parse')
  return parsed
}

test('parseCaptureMode reads a known token and its time, and reads anything else as auto', () => {
  expect(parseCaptureMode(undefined)).toEqual({ mode: 'auto' })
  expect(parseCaptureMode(null)).toEqual({ mode: 'auto' })
  expect(parseCaptureMode('strict')).toEqual({ mode: 'auto' })
  expect(parseCaptureMode({})).toEqual({ mode: 'auto' })
  expect(parseCaptureMode({ mode: 'mirror', ts: 5 })).toEqual({ mode: 'auto' })
  expect(parseCaptureMode({ mode: 'x' })).toEqual({ mode: 'auto' })
  expect(parseCaptureMode({ mode: 'strict', ts: 5 })).toEqual({ mode: 'strict', since: 5 })
})

test('parseCaptureMode leaves since out when the time is not a finite number', () => {
  expect(Object.keys(parseCaptureMode({ mode: 'off' }))).toEqual(['mode'])
  expect(Object.keys(parseCaptureMode({ mode: 'off', ts: 'soon' }))).toEqual(['mode'])
  expect(Object.keys(parseCaptureMode({ mode: 'off', ts: Number.NaN }))).toEqual(['mode'])
})

test('the mode list is the three tokens in their fixed order, without the reserved mirror', () => {
  expect(CAPTURE_MODES).toEqual(['strict', 'auto', 'off'])
})

test('otherModes lists the modes that are not the given one, in the list order', () => {
  expect(otherModes('auto')).toEqual(['strict', 'off'])
  expect(otherModes('off')).toEqual(['strict', 'auto'])
  expect(otherModes('strict')).toEqual(['auto', 'off'])
})

test('captureModeFile writes the mode and its time as one JSON line that parseCaptureMode reads back', () => {
  expect(captureModeFile('off', 7)).toBe('{"mode":"off","ts":7}\n')
  expect(parseCaptureMode(JSON.parse(captureModeFile('off', 7)))).toEqual({ mode: 'off', since: 7 })
})

test('modeSinceText is undefined without a time, "now" under a minute, and the card age wording after', () => {
  expect(modeSinceText('en', undefined, NOW)).toBeUndefined()
  expect(modeSinceText('en', NOW - 59_000, NOW)).toBe('in effect now')
  expect(modeSinceText('pt', NOW - 59_000, NOW)).toBe('em vigor agora')
  expect(modeSinceText('en', NOW - 30 * MINUTE, NOW)).toBe('in effect since 30 min ago')
  expect(modeSinceText('pt', NOW - 30 * MINUTE, NOW)).toBe('em vigor há 30 min')
})

test('modeChangedText names the mode and says how many open questions stay, singular and plural', () => {
  expect(modeChangedText('pt', 'off', 5)).toBe('Captura desativada a partir de agora. As 5 perguntas abertas continuam no painel.')
  expect(modeChangedText('pt', 'off', 0)).toBe('Captura desativada a partir de agora.')
  expect(modeChangedText('en', 'strict', 1)).toBe('Strict capture from now on. The open question stays in the panel.')
  expect(modeChangedText('en', 'auto', 2)).toBe('Automatic capture from now on. The 2 open questions stay in the panel.')
})

test('modeCommandText names the mode and its description in the command reply', () => {
  expect(modeCommandText('en', 'auto')).toBe(
    'AskAway User capture mode: Auto. The session goes on with the recommended option; only a high-risk question pauses it.',
  )
  expect(modeCommandText('pt', 'off')).toBe('Modo de captura do AskAway User: Desativada. Não captura perguntas novas.')
})

test('pausesSession is true for a question with the pause flag or a high risk, and false for a low-risk one with no flag', () => {
  expect(pausesSession(questionOf({ pause: true, risk: 'low' }))).toBe(true)
  expect(pausesSession(questionOf({ risk: 'high' }))).toBe(true)
  expect(pausesSession(questionOf({ pause: false, risk: 'high' }))).toBe(true)
  expect(pausesSession(questionOf({ pause: false, risk: 'low' }))).toBe(false)
  expect(pausesSession(questionOf({ risk: 'low' }))).toBe(false)
})

test('a strict low-risk question that holds a pause counts as paused in the band count and the card lead', () => {
  const strict = questionOf({ pause: true, risk: 'low' })
  expect(pausedText('en', [strict])).toBe('1 paused')
  expect(leadOf('en', strict, NOW)).toMatch(/^Paused since /)
})

test('parseQuestion keeps a pause flag set to true', () => {
  expect(questionOf({ pause: true }).pause).toBe(true)
})

// WCAG 2.x relative luminance and contrast ratio, to check the mode marks against the surfaces look.ts cites.
const luminanceOf = (hex: string): number => {
  const [red, green, blue] = [1, 3, 5].map(index => {
    const channel = parseInt(hex.slice(index, index + 2), 16) / 255
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * (red ?? 0) + 0.7152 * (green ?? 0) + 0.0722 * (blue ?? 0)
}
const contrastOf = (foreground: string, background: string): number => {
  const first = luminanceOf(foreground)
  const second = luminanceOf(background)
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05)
}

test('each mode colour has at least 3:1 contrast on the light and the dark surfaces (WCAG 2.2 1.4.11)', () => {
  for (const mode of CAPTURE_MODES) {
    for (const surface of ['#FFFFFF', '#111827', '#0b0b0b']) {
      expect(contrastOf(MODE_COLOR[mode], surface)).toBeGreaterThanOrEqual(3)
    }
  }
})
