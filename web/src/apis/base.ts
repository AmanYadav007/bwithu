// The web app is served by the BwithU server (or proxied to it by Vite in dev),
// so every API and WebSocket call goes to the page's own origin.
export const useSSL = location.protocol === 'https:'
export const serverHost = location.host
export const serverOrigin = location.origin

export function fetch(input: string, init?: RequestInit): Promise<Response> {
  return window.fetch(`${serverOrigin}${input}`, init)
}
