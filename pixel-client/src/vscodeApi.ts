/**
 * Standalone web replacement for the VSCode API bridge.
 * Instead of communicating with a VSCode extension, this dispatches
 * messages internally to be handled by the browser-side bridge.
 */

type MessageHandler = (msg: Record<string, unknown>) => void

const handlers: MessageHandler[] = []

export function onWebviewMessage(handler: MessageHandler): () => void {
  handlers.push(handler)
  return () => {
    const idx = handlers.indexOf(handler)
    if (idx >= 0) handlers.splice(idx, 1)
  }
}

export function postToWebview(msg: Record<string, unknown>): void {
  window.dispatchEvent(new MessageEvent('message', { data: msg }))
}

export const vscode = {
  postMessage(msg: unknown): void {
    const message = msg as Record<string, unknown>
    for (const handler of handlers) {
      handler(message)
    }
  },
}
