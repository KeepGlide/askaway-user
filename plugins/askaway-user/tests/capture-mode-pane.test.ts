import type { On } from 'claude-code'
import { expect, mock, test, type Engine } from 'claude-code/testing'

import { MODE_COLOR } from '../hooks/look'
import { t } from '../hooks/i18n'
import { captureModeFile, modeChangedText, modeCommandText } from '../hooks/model'

const HOME = '/test-home'
const STATE = `${HOME}/.claude/state/askaway-user`
const MODE_FILE = `${STATE}/mode.json`
const SESSION = { cwd: '/work/app', surface: 'terminal', isInteractive: true } as const
const PANE_PROPS = {
  title: 'AskAway User',
  isFocused: false,
  bodyColumns: 100,
  placement: 'inline',
  scroll: { offset: 0, bodyRows: 40 },
  view: {},
} as const
// The poll interval of the pane (register.tsx POLL_MS).
const POLL_MS = 5000
// A pane press within this many ms of the last accepted mode change is ignored (register.tsx MODE_PRESS_GUARD_MS).
const PRESS_GUARD_MS = 700

// A question as askaway.py writes it (SPEC.md), with the fields the pane reads.
function question(id: string, ts: number): string {
  return JSON.stringify({
    v: 1,
    id,
    ts,
    project: '/work/app',
    session: null,
    run_kind: 'main',
    title: `Title ${id}`,
    question: `Which way for ${id}?`,
    options: [
      { key: 'A', label: 'Keep', tradeoff: 'cheap', fit: 80 },
      { key: 'B', label: 'Rewrite', tradeoff: 'slow', fit: 40 },
    ],
    recommended: 'A',
    why: 'It is smaller.',
    risk: 'low',
    pause: false,
    source: 'cli',
  })
}

const cliReply = (stdout: string, exitCode = 0) => ({
  value: { exitCode, stdout: `${stdout}\n`, stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
})

// The engine's file, process and clock calls, answered from an in-memory folder: the mode file, the questions, and the shell
// calls the atomic write makes (test -d, mv, rm). Only what these tests reach is modelled.
// `gate` holds every move (`mv`) until it resolves, `failMove` makes the move fail, `failReadOf` makes the next read of that
// path fail, `moves` and `directWrites` record what ran.
type Hold = { gate?: Promise<void>; failMove?: boolean; failReadOf?: string }
function stubHost(on: On, files: Map<string, string>, env: Record<string, string> = {}) {
  const toasts: string[] = []
  const hold: Hold = {}
  const moves: string[][] = []
  const directWrites: string[] = []
  const clock = mock.clock(on)
  mock.env(on, { HOME, LANG: 'en_US.UTF-8', ...env })
  mock.store(on, {})
  on('command.register', (_$, event) => ({ value: { command: event.name } }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 'sess-self' }))
  on('config.list', () => ({ value: [{ key: 'theme', label: 'Theme', kind: 'choice', value: 'dark' }] }))
  on('config.set', (_$, e) => ({ value: e.value }))
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.log', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.focus', () => ({}))
  on('fs.list', (_$, e) => {
    const prefix = `${e.path}/`
    const names = [...files.keys()].filter(file => file.startsWith(prefix) && !file.slice(prefix.length).includes('/'))
    return { value: names.map(file => ({ name: file.slice(prefix.length), kind: 'file' as const, size: 0, mtimeMs: 0, isLink: false })) }
  })
  on('fs.read', (_$, e) => {
    if (hold.failReadOf === e.path) {
      hold.failReadOf = undefined
      throw new Error(`EIO: cannot read ${e.path}`)
    }
    const text = files.get(e.path)
    if (text === undefined) throw new Error(`ENOENT: ${e.path}`)
    return { value: text }
  })
  on('fs.exists', (_$, e) => ({ value: files.has(e.path) || [...files.keys()].some(file => file.startsWith(`${e.path}/`)) }))
  on('fs.write', (_$, e) => {
    directWrites.push(e.path)
    files.set(e.path, e.text)
    return { value: undefined }
  })
  on('process.run', async (_$, e) => {
    const [command, , from = '', to = ''] = e.argv
    if (e.argv[0] === 'python3') {
      // `list --open` names the question files, as the CLI does; the other CLI calls are not reached here.
      const items = [...files.keys()].filter(file => file.startsWith(`${STATE}/q/`)).map(file => ({ id: file.slice(`${STATE}/q/`.length, -5) }))
      return cliReply(JSON.stringify({ items }))
    }
    if (command === 'test') return cliReply('', 1)
    if (command === 'mv') {
      moves.push([...e.argv])
      await hold.gate
      if (hold.failMove) return cliReply('', 1)
      const text = files.get(from)
      if (text === undefined) return cliReply('', 1)
      files.delete(from)
      files.set(to, text)
      return cliReply('')
    }
    if (command === 'rm') {
      files.delete(from)
      return cliReply('')
    }
    return cliReply('')
  })
  return { toasts, clock, hold, moves, directWrites }
}

const run = ($: Engine, args: string) =>
  $.command.run({ command: 'askaway', args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } })

const mountPane = ($: Engine, surface: 'terminal' | 'desktop' = 'terminal') =>
  $.ui.mount({ plugin: 'askaway-user', surface, component: 'Pane', requestId: 'askaway', props: PANE_PROPS })

type Mounted = Awaited<ReturnType<typeof mountPane>>

// Every node of a drawn tree, depth first.
const nodesOf = (node: unknown): Record<string, unknown>[] => {
  if (typeof node !== 'object' || node === null) return []
  const element = node as Record<string, unknown>
  const children = Array.isArray(element.children) ? element.children : []
  return [element, ...children.flatMap(nodesOf)]
}
const keyOf = (node: Record<string, unknown>): unknown => node.key ?? (node.props as Record<string, unknown> | undefined)?.key
const textOfNode = (node: unknown): string => {
  if (typeof node === 'string') return node
  if (typeof node !== 'object' || node === null) return ''
  const children = (node as Record<string, unknown>).children
  return Array.isArray(children) ? children.map(textOfNode).join('') : ''
}
const childrenOf = (node: Record<string, unknown> | undefined): Record<string, unknown>[] =>
  Array.isArray(node?.children) ? (node.children as Record<string, unknown>[]) : []
const drawnByKey = async (pane: Mounted, key: string) => nodesOf(await pane.drawn()).find(node => keyOf(node) === key)
// The engine keeps keys on Boxes and Buttons only, so the mode block's Texts are read by their place in it:
// mode-line = [Svg?, label, name, since?], then the description Text, then mode-actions = [change, ...buttons].
const modeParts = async (pane: Mounted) => {
  const [line, describe, actions] = childrenOf(await drawnByKey(pane, 'mode'))
  const lineTexts = childrenOf(line).filter(node => node.type === 'Text').map(textOfNode)
  return {
    marks: childrenOf(line).filter(node => node.type === 'Svg'),
    label: lineTexts[0],
    name: lineTexts[1],
    since: lineTexts[2],
    describe: textOfNode(describe),
    change: textOfNode(childrenOf(actions)[0]),
  }
}
// The counter line: the first Text of the header's end box.
const counterOf = async (pane: Mounted) => textOfNode(childrenOf(await drawnByKey(pane, 'header-end'))[0])
const buttonOf = async (pane: Mounted, key: string) => (await pane.find({ type: 'Button', key }))?.props

test('the mode block sits between the header and the header rule, with Auto, its description and two buttons, on both surfaces', async ($, on) => {
  const files = new Map<string, string>()
  stubHost(on, files)
  await $.session.start(SESSION)
  for (const surface of ['terminal', 'desktop'] as const) {
    const pane = await mountPane($, surface)
    // The pane's own children, in order: the header, the mode block, then the header rule (a Text or an Svg, drawn with no key).
    const [root] = nodesOf(await pane.drawn())
    const order = childrenOf(root).map(keyOf)
    expect(order.slice(0, 2)).toEqual(['header', 'mode'])
    const rule = childrenOf(root)[2]
    expect(rule?.type).toBe(surface === 'desktop' ? 'Svg' : 'Text')
    if (surface === 'terminal') expect(textOfNode(rule)).toMatch(/^─+$/)
    const parts = await modeParts(pane)
    expect(parts.label).toBe('New questions:')
    expect(parts.name).toBe('Auto')
    expect(parts.describe).toBe(t('en', 'mode.describe.auto'))
    expect(parts.change).toBe('Change to:')
    expect(parts.since).toBeUndefined()
    const strict = await buttonOf(pane, 'mode-strict')
    const off = await buttonOf(pane, 'mode-off')
    expect(strict).toMatchObject({ label: 'Strict', variant: 'secondary' })
    expect(off).toMatchObject({ label: 'Turn off', variant: 'secondary' })
    expect(strict?.hotkey).toBeUndefined()
    expect(off?.hotkey).toBeUndefined()
    expect(await buttonOf(pane, 'mode-auto')).toBeUndefined()
    await pane.unmount()
  }
})

test('the desktop draws the mode mark as an Svg in the mode colour with empty alt text; the terminal draws none', async ($, on) => {
  const files = new Map<string, string>()
  stubHost(on, files)
  await $.session.start(SESSION)
  const desktop = await mountPane($, 'desktop')
  const [mark] = (await modeParts(desktop)).marks
  expect((mark?.props as Record<string, unknown> | undefined)?.alt).toBe('')
  expect(String((mark?.props as Record<string, unknown> | undefined)?.source)).toContain(MODE_COLOR.auto)
  await desktop.unmount()
  const terminal = await mountPane($, 'terminal')
  expect((await modeParts(terminal)).marks).toEqual([])
  await terminal.unmount()
})

test('pressing Off writes mode.json once, shows Off and one toast, and leaves the counter and the open questions as they were', async ($, on) => {
  const files = new Map([[`${STATE}/q/q-m-000001.json`, question('q-m-000001', 1000)]])
  const { toasts, clock, moves } = stubHost(on, files)
  await $.session.start(SESSION)
  await clock.advance(POLL_MS)
  toasts.length = 0
  const pane = await mountPane($)
  const counterBefore = await counterOf(pane)
  const treeBefore = JSON.stringify(await drawnByKey(pane, 'tree'))
  await pane.press({ key: 'mode-off' })
  const now = JSON.parse(files.get(MODE_FILE) ?? '{}').ts
  expect(typeof now).toBe('number')
  expect(files.get(MODE_FILE)).toBe(captureModeFile('off', now))
  expect(moves.filter(move => move[3] === MODE_FILE)).toHaveLength(1)
  expect(toasts).toEqual([modeChangedText('en', 'off', 1)])
  const parts = await modeParts(pane)
  expect(parts.name).toBe('Off')
  expect(parts.since).toBe(`· ${t('en', 'mode.sinceNow')}`)
  expect(await buttonOf(pane, 'mode-strict')).toMatchObject({ label: 'Strict' })
  expect(await buttonOf(pane, 'mode-auto')).toMatchObject({ label: 'Auto' })
  expect(await buttonOf(pane, 'mode-off')).toBeUndefined()
  expect(await counterOf(pane)).toBe(counterBefore)
  expect(JSON.stringify(await drawnByKey(pane, 'tree'))).toBe(treeBefore)
  expect(await pane.find({ type: 'Text', text: 'Which way for q-m-000001?' })).toBeDefined()
  await pane.unmount()
})

test('a second press within 700 ms is ignored; a press 700 ms after the accepted one is taken', async ($, on) => {
  const files = new Map<string, string>()
  const { toasts, clock } = stubHost(on, files)
  await $.session.start(SESSION)
  const pane = await mountPane($)
  await pane.press({ key: 'mode-off' })
  const offFile = files.get(MODE_FILE)
  await pane.press({ key: 'mode-strict' })
  expect(files.get(MODE_FILE)).toBe(offFile)
  await clock.advance(PRESS_GUARD_MS - 1)
  await pane.press({ key: 'mode-strict' })
  expect(files.get(MODE_FILE)).toBe(offFile)
  expect(toasts).toHaveLength(1)
  await clock.advance(1)
  await pane.press({ key: 'mode-strict' })
  expect(JSON.parse(files.get(MODE_FILE) ?? '{}')).toMatchObject({ mode: 'strict' })
  expect(toasts).toHaveLength(2)
  await pane.unmount()
})

test('the poll shows the mode mode.json holds: strict shows Strict, a mirror or garbage shows Auto, a removed file shows Auto', async ($, on) => {
  const files = new Map<string, string>()
  const { clock } = stubHost(on, files)
  await $.session.start(SESSION)
  const pane = await mountPane($)
  files.set(MODE_FILE, `${JSON.stringify({ mode: 'strict', ts: 1 })}\n`)
  await clock.advance(POLL_MS)
  expect((await modeParts(pane)).name).toBe('Strict')
  files.set(MODE_FILE, `${JSON.stringify({ mode: 'mirror' })}\n`)
  await clock.advance(POLL_MS)
  expect((await modeParts(pane)).name).toBe('Auto')
  files.set(MODE_FILE, 'not json {')
  await clock.advance(POLL_MS)
  expect((await modeParts(pane)).name).toBe('Auto')
  files.set(MODE_FILE, `${JSON.stringify({ mode: 'strict', ts: 2 })}\n`)
  await clock.advance(POLL_MS)
  expect((await modeParts(pane)).name).toBe('Strict')
  files.delete(MODE_FILE)
  await clock.advance(POLL_MS)
  expect((await modeParts(pane)).name).toBe('Auto')
  await pane.unmount()
})

test('/askaway mode with no value says the current mode and writes nothing', async ($, on) => {
  const files = new Map<string, string>()
  stubHost(on, files)
  await $.session.start(SESSION)
  const reply = await run($, 'mode')
  expect(reply.text).toBe(modeCommandText('en', 'auto'))
  expect(files.has(MODE_FILE)).toBe(false)
})

test('/askaway mode strict writes the file and says so with no toast; repeating it keeps the file and its time', async ($, on) => {
  const files = new Map<string, string>()
  const { toasts, clock } = stubHost(on, files)
  await $.session.start(SESSION)
  const first = await run($, 'mode strict')
  expect(first.text).toBe(modeChangedText('en', 'strict', 0))
  const now = JSON.parse(files.get(MODE_FILE) ?? '{}').ts
  expect(typeof now).toBe('number')
  expect(files.get(MODE_FILE)).toBe(captureModeFile('strict', now))
  expect(toasts).toEqual([])
  await clock.advance(1000)
  const before = files.get(MODE_FILE)
  const second = await run($, 'mode strict')
  expect(second.text).toBe(modeCommandText('en', 'strict'))
  expect(files.get(MODE_FILE)).toBe(before)
  expect(toasts).toEqual([])
})

test('/askaway mode accepts STRICT in any case, and refuses an unknown value without touching the file', async ($, on) => {
  const files = new Map<string, string>()
  stubHost(on, files)
  await $.session.start(SESSION)
  await run($, 'mode STRICT')
  expect(JSON.parse(files.get(MODE_FILE) ?? '{}')).toMatchObject({ mode: 'strict' })
  const before = files.get(MODE_FILE)
  const reply = await run($, 'mode x')
  expect(reply.text).toBe(t('en', 'command.modeInvalid'))
  expect(files.get(MODE_FILE)).toBe(before)
})

test('with no state folder, a pane press and the command say the mode is unavailable and write nothing', async ($, on) => {
  const files = new Map<string, string>()
  const { toasts } = stubHost(on, files, { HOME: '' })
  await $.session.start(SESSION)
  const pane = await mountPane($)
  await pane.press({ key: 'mode-off' })
  expect(toasts).toEqual([t('en', 'command.modeUnavailable')])
  expect(files.has(MODE_FILE)).toBe(false)
  const reply = await run($, 'mode strict')
  expect(reply.text).toBe(t('en', 'command.modeUnavailable'))
  expect(files.has(MODE_FILE)).toBe(false)
  await pane.unmount()
})

test('in pt-BR the block reads Novas perguntas, Automática, Mudar para, and the buttons Rígida and Desativar', async ($, on) => {
  const files = new Map<string, string>()
  stubHost(on, files, { LANG: 'pt_BR.UTF-8' })
  await $.session.start(SESSION)
  const pane = await mountPane($)
  const parts = await modeParts(pane)
  expect(parts.label).toBe('Novas perguntas:')
  expect(parts.name).toBe('Automática')
  expect(parts.change).toBe('Mudar para:')
  expect(await buttonOf(pane, 'mode-strict')).toMatchObject({ label: 'Rígida' })
  expect(await buttonOf(pane, 'mode-off')).toMatchObject({ label: 'Desativar' })
  await pane.unmount()
})

const modeNameOf = async (pane: Mounted) => (await modeParts(pane)).name

test('two presses started together write once and toast once (the in-flight lock)', async ($, on) => {
  const files = new Map<string, string>()
  const { toasts, hold, moves } = stubHost(on, files)
  await $.session.start(SESSION)
  const pane = await mountPane($)
  let release = () => {}
  hold.gate = new Promise<void>(resolve => {
    release = resolve
  })
  const first = pane.press({ key: 'mode-off' })
  const second = pane.press({ key: 'mode-off' })
  release()
  await Promise.all([first, second])
  expect(moves.filter(move => move[3] === MODE_FILE)).toHaveLength(1)
  expect(toasts).toHaveLength(1)
  await pane.unmount()
})

test('a failed write on a pane press leaves the shown mode and the file as they were, with no change toast', async ($, on) => {
  const files = new Map<string, string>()
  const { toasts, hold } = stubHost(on, files)
  await $.session.start(SESSION)
  const pane = await mountPane($)
  hold.failMove = true
  await pane.press({ key: 'mode-off' })
  expect(files.has(MODE_FILE)).toBe(false)
  expect(await modeNameOf(pane)).toBe('Auto')
  expect(toasts).toEqual([])
  await pane.unmount()
})

test('a mode file stamped ahead of the clock does not lock the buttons', async ($, on) => {
  const files = new Map<string, string>()
  const { toasts, clock } = stubHost(on, files)
  await $.session.start(SESSION)
  const pane = await mountPane($)
  // The clock's own now, learned from a mode the command writes, then a file stamped ten minutes ahead of it.
  await run($, 'mode strict')
  const now = JSON.parse(files.get(MODE_FILE) ?? '{}').ts
  files.set(MODE_FILE, captureModeFile('strict', now + 10 * 60_000))
  await clock.advance(POLL_MS)
  expect(await modeNameOf(pane)).toBe('Strict')
  await pane.press({ key: 'mode-off' })
  expect(JSON.parse(files.get(MODE_FILE) ?? '{}')).toMatchObject({ mode: 'off' })
  expect(toasts).toHaveLength(1)
  await pane.unmount()
})

test('a new ts on the same mode updates the in-effect text after the next poll', async ($, on) => {
  const files = new Map<string, string>()
  const { clock } = stubHost(on, files)
  await $.session.start(SESSION)
  const pane = await mountPane($)
  await run($, 'mode strict')
  const now = JSON.parse(files.get(MODE_FILE) ?? '{}').ts
  await clock.advance(POLL_MS)
  const before = (await modeParts(pane)).since
  files.set(MODE_FILE, captureModeFile('strict', now - 3 * 3_600_000))
  await clock.advance(POLL_MS)
  const after = (await modeParts(pane)).since
  expect(before).toBeDefined()
  expect(after).toBeDefined()
  expect(after).not.toBe(before)
  await pane.unmount()
})

test('the command reads mode.json fresh: a strict file with no poll since is the current mode, and naming it writes nothing', async ($, on) => {
  const files = new Map<string, string>()
  const { moves, directWrites } = stubHost(on, files)
  await $.session.start(SESSION)
  files.set(MODE_FILE, captureModeFile('strict', 1))
  expect((await run($, 'mode')).text).toBe(modeCommandText('en', 'strict'))
  expect((await run($, 'mode strict')).text).toBe(modeCommandText('en', 'strict'))
  expect(moves).toEqual([])
  expect(directWrites.filter(path => path === MODE_FILE)).toEqual([])
  expect(files.get(MODE_FILE)).toBe(captureModeFile('strict', 1))
})

test('mode.json is written atomically: a temp file in the folder moved over it, never a direct write', async ($, on) => {
  const files = new Map<string, string>()
  const { moves, directWrites } = stubHost(on, files)
  await $.session.start(SESSION)
  await run($, 'mode off')
  expect(directWrites).not.toContain(MODE_FILE)
  const move = moves.find(candidate => candidate[3] === MODE_FILE)
  expect(move).toEqual(['mv', '-f', expect.stringMatching(new RegExp(`^${STATE}/\\..*\\.tmp$`)), MODE_FILE])
  expect(directWrites.some(path => path === move?.[2])).toBe(true)
})

test('the mode colours are never a text colour on the drawn pane, in each mode', async ($, on) => {
  const files = new Map<string, string>()
  const { clock } = stubHost(on, files)
  await $.session.start(SESSION)
  const colours = new Set<unknown>(Object.values(MODE_COLOR))
  const pane = await mountPane($, 'desktop')
  for (const mode of ['strict', 'off', 'auto']) {
    files.set(MODE_FILE, captureModeFile(mode as 'strict' | 'off' | 'auto', 1))
    await clock.advance(POLL_MS)
    expect((await modeParts(pane)).name).toBe(t('en', `mode.name.${mode}` as 'mode.name.auto'))
    const texts = nodesOf(await pane.drawn()).filter(node => node.type === 'Text')
    expect(texts.length).toBeGreaterThan(0)
    for (const text of texts) expect(colours.has((text.props as Record<string, unknown> | undefined)?.color)).toBe(false)
  }
  await pane.unmount()
})

test('/askaway away is no longer a verb: it gets the verbs help and writes no away.json', async ($, on) => {
  const files = new Map<string, string>()
  stubHost(on, files)
  await $.session.start(SESSION)
  const reply = await run($, 'away')
  expect(reply.text).toBe(t('en', 'command.verbsHelp'))
  expect(files.has(`${STATE}/away.json`)).toBe(false)
})

test('a leftover away.json is never read: the pane counter line carries no away mark, on both surfaces', async ($, on) => {
  const files = new Map<string, string>([[`${STATE}/away.json`, '{"on":true,"ts":1}']])
  const { clock } = stubHost(on, files)
  await $.session.start(SESSION)
  for (const surface of ['terminal', 'desktop'] as const) {
    const pane = await mountPane($, surface)
    await clock.advance(POLL_MS)
    expect(await counterOf(pane)).toBe('Nothing pending')
    await pane.unmount()
  }
})

test('a failed read of mode.json keeps the mode the pane shows: the poll does not flip a strict pane to auto', async ($, on) => {
  const files = new Map<string, string>()
  const { clock, hold } = stubHost(on, files)
  await $.session.start(SESSION)
  const pane = await mountPane($)
  files.set(MODE_FILE, `${JSON.stringify({ mode: 'strict', ts: 1 })}\n`)
  await clock.advance(POLL_MS)
  expect(await modeNameOf(pane)).toBe('Strict')
  hold.failReadOf = MODE_FILE
  await clock.advance(POLL_MS)
  expect(hold.failReadOf).toBeUndefined()
  expect(await modeNameOf(pane)).toBe('Strict')
  await pane.unmount()
})
