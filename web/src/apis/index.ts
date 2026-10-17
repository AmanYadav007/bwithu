import { WS } from '@/helpers/ws'
import { fetch, serverHost, serverOrigin, useSSL } from './base'

export { fetch }

export function initConfig(): Promise<Response> {
  return fetch('/openavatarchat/initconfig')
}

export function createWS(wsRoute: string, sessionId: string, params: Record<string, string> = {}): WS {
  const query = new URLSearchParams(params).toString()
  const url = `${useSSL ? 'wss' : 'ws'}://${serverHost}${wsRoute}/${sessionId}${query ? `?${query}` : ''}`
  return new WS(url)
}

export function makeURL(path: string): string {
  return path.startsWith('http') ? path : `${serverOrigin}${path}`
}
