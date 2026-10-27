import { defineStore } from 'pinia'
import { markRaw } from 'vue'

import { createWS, initConfig, makeURL } from '@/apis'
import { MAX_CALL_SECONDS, type Companion } from '@/config/companion'
import { AvatarHandler } from '@/handlers/avatarHandler'
import { getAudioContext, unlockAudio } from '@/helpers/audioContext'
import type { WS } from '@/helpers/ws'
import { EventTypes, WsEventTypes, type SignalBody, type TextPayload } from '@/interface/eventType'
import { TYVoiceChatState } from '@/interface/voiceChat'

export type CallStatus = 'idle' | 'connecting' | 'live' | 'ended' | 'error'

interface Caption {
  key: string
  text: string
}

interface Runtime {
  ws: WS | null
  avatar: AvatarHandler | null
  stream: MediaStream | null
  micSource: AudioNode | null
  micNode: AudioNode | null
  timer: number | null
}

// Non-reactive handles for the live call; kept outside Pinia state on purpose.
const rt: Runtime = { ws: null, avatar: null, stream: null, micSource: null, micNode: null, timer: null }
// Bumped on every start/teardown so async steps from an older call can tell they are stale.
let generation = 0

let serverConfig: { wsRoute: string; assetRoute: string } | null = null

// Voice barge-in: the user talking over the avatar for ~0.3 s stops it. Echo of the avatar's own
// voice is removed by the browser's echo canceller, so a sustained level above this is the user.
const BARGE_IN_DB = -33
const BARGE_IN_MS = 300
const barge = { speechMs: 0, cooldownUntil: 0 }

// Must match GREETING_CUE in server/src/bwithu/persona.py.
const GREETING_CUE = '[call connected]'
let greeted = false
let callStartedAt = 0

function levelDb(pcm: Int16Array): number {
  let sum = 0
  for (let i = 0; i < pcm.length; i++) sum += pcm[i] * pcm[i]
  const rms = Math.sqrt(sum / Math.max(1, pcm.length)) / 32768
  return 20 * Math.log10(rms + 1e-9)
}

// Close codes sent by server/src/bwithu/gate.py.
const REFUSALS: Record<number, string> = {
  4001: 'Lots of people are calling right now. Please try again in a minute.',
  4002: "You've used today's free minutes. Come back tomorrow — we'll be here.",
  4003: 'BwithU is taking a short break. Please try again soon.',
}

// Anonymous per-browser id so the server can count free minutes per person.
function clientId(): string {
  try {
    let id = localStorage.getItem('bwithu.cid')
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem('bwithu.cid', id)
    }
    return id
  } catch {
    return ''
  }
}

async function loadServerConfig() {
  if (serverConfig) return serverConfig
  const config = await (await initConfig()).json()
  const avatarConfig = config.avatar_config || {}
  const assetsPath: string = avatarConfig.avatar_assets_path || '/download/lam_asset/james.zip'
  serverConfig = {
    wsRoute: avatarConfig.ws_session_route || config.ws_session_route || '/ws/session',
    assetRoute: assetsPath.slice(0, assetsPath.lastIndexOf('/')),
  }
  return serverConfig
}

export const useCallStore = defineStore('call', {
  state: () => ({
    status: 'idle' as CallStatus,
    avatarState: TYVoiceChatState.Idle,
    avatarSpeaking: false,
    loadPercent: 0,
    micPending: false,
    micMuted: false,
    speakerMuted: false,
    seconds: 0,
    endReason: '' as '' | 'user' | 'limit' | 'dropped',
    error: '',
    avatarCaption: null as Caption | null,
    interruptedAt: 0,
    humanCaption: null as Caption | null,
  }),
  getters: {
    secondsLeft: (s) => Math.max(0, MAX_CALL_SECONDS - s.seconds),
  },
  actions: {
    async start(container: HTMLDivElement, companion: Companion) {
      if (this.status === 'connecting' || this.status === 'live') return
      // Must run synchronously inside the tap, before any await (iOS Safari audio policy).
      unlockAudio()
      this.$reset()
      const gen = ++generation
      callStartedAt = performance.now()
      this.status = 'connecting'
      try {
        this.micPending = true
        const [{ wsRoute, assetRoute }, stream] = await Promise.all([
          loadServerConfig(),
          navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
          }),
        ]).finally(() => (this.micPending = false))
        if (gen !== generation) {
          // The user left or hung up while the permission prompt was open.
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        rt.stream = stream

        const ws = createWS(wsRoute, crypto.randomUUID(), {
          name: companion.name,
          user: companion.userName,
          vibe: companion.vibe,
          voice: companion.voice,
          lang: companion.language,
          cid: clientId(),
        })
        rt.ws = markRaw(ws)
        greeted = false
        ws.on(WsEventTypes.WS_OPEN, () => {
          this.status = 'live'
          this._startMic()
          this._startTimer()
          this._maybeGreet()
        })
        ws.on(WsEventTypes.WS_CLOSE, (code?: number) => {
          // Refusals arrive right after the socket opens, so they win over the 'live' state.
          if (code && REFUSALS[code]) return this._fail(REFUSALS[code])
          if (code === 4002 || code === 4004) return this._finish('limit')
          this._finish(this.endReason || 'dropped')
        })
        ws.on(WsEventTypes.WS_ERROR, () => {
          if (this.status === 'connecting') this._fail('We could not reach your companion. Please try again.')
        })

        const avatar = new AvatarHandler({
          container,
          assetsPath: makeURL(`${assetRoute}/${companion.avatar}.zip`),
          ws,
          rendererType: 'lam',
          // The renderer reports progress as a 0..1 fraction: download is the first 60%, scene load the rest.
          downloadProgress: (p) => (this.loadPercent = Math.round(p * 60)),
          loadProgress: (p) => {
            this.loadPercent = 60 + Math.round(p * 40)
            this._maybeGreet()
          },
        })
        rt.avatar = markRaw(avatar)
        avatar.on(EventTypes.StateChanged, (state: TYVoiceChatState) => (this.avatarState = state))
        avatar.on(EventTypes.MessageReceived, (data: { role?: string; payload?: TextPayload }) =>
          this._onText(data?.role === 'human' ? 'human' : 'avatar', data?.payload)
        )
        avatar.on(EventTypes.SignalReceived, (signal?: SignalBody) => {
          if (signal?.stream_type !== 'client_playback') return
          if (signal.type === 'stream_begin') this.avatarSpeaking = true
          if (signal.type === 'stream_end' || signal.type === 'stream_cancel') this.avatarSpeaking = false
        })
        avatar.on(EventTypes.ErrorReceived, (payload: unknown) => console.warn('[call] server error', payload))
      } catch (e) {
        const name = e instanceof DOMException ? e.name : ''
        this._fail(
          name === 'NotAllowedError' || name === 'SecurityError'
            ? 'Microphone access is needed for a call. Allow it in your browser and try again.'
            : name === 'NotFoundError'
              ? 'No microphone found. Plug one in and try again.'
              : 'Something went wrong starting the call. Please try again.'
        )
      }
    },

    end() {
      this._finish('user')
    },

    toggleMic() {
      this.micMuted = !this.micMuted
      rt.stream?.getAudioTracks().forEach((t) => (t.enabled = !this.micMuted))
    },

    toggleSpeaker() {
      this.speakerMuted = !this.speakerMuted
      rt.avatar?.setAvatarMute(this.speakerMuted)
    },

    interrupt() {
      if (!rt.avatar || !this.avatarSpeaking) return
      rt.avatar.interrupt()
      this.interruptedAt = Date.now()
      this.avatarSpeaking = false
      barge.speechMs = 0
      barge.cooldownUntil = performance.now() + 1500
    },

    // Once the face is on screen and the line is open, the companion says hello first.
    _maybeGreet() {
      if (greeted || this.status !== 'live' || this.loadPercent < 100 || !rt.avatar) return
      greeted = true
      console.info(`[bwithu] face ready ${Math.round(performance.now() - callStartedAt)} ms after Start call`)
      rt.avatar.sendSpeech(GREETING_CUE)
    },

    _detectBargeIn(pcm: Int16Array) {
      if (!this.avatarSpeaking || performance.now() < barge.cooldownUntil) {
        barge.speechMs = 0
        return
      }
      const ms = (pcm.length / 16000) * 1000
      barge.speechMs = levelDb(pcm) > BARGE_IN_DB ? barge.speechMs + ms : Math.max(0, barge.speechMs - ms / 2)
      if (barge.speechMs >= BARGE_IN_MS) this.interrupt()
    },

    _onText(role: 'human' | 'avatar', payload?: TextPayload) {
      if (!payload || typeof payload.text !== 'string' || payload.text === GREETING_CUE) return
      const key = payload.stream_key || payload.request_id
      const current = role === 'human' ? this.humanCaption : this.avatarCaption
      const text =
        current && current.key === key && payload.mode === 'increment' ? current.text + payload.text : payload.text
      if (!text.trim()) return
      if (role === 'human') this.humanCaption = { key, text }
      else this.avatarCaption = { key, text }
    },

    async _startMic() {
      if (!rt.stream || !rt.avatar) return
      const gen = generation
      const ctx = getAudioContext()
      const source = ctx.createMediaStreamSource(rt.stream)
      rt.micSource = source
      const send = (pcm: Int16Array) => {
        if (this.micMuted || rt.ws?.engine?.readyState !== WebSocket.OPEN) return
        this._detectBargeIn(pcm)
        rt.avatar?.sendAudio(pcm, 'base64')
      }
      try {
        // Served from public/ as a real file: Safari rejects data: URLs for worklets.
        await ctx.audioWorklet.addModule(new URL('worklets/mic-processor.js', document.baseURI).href)
        if (gen !== generation) return // call ended while the worklet was loading
        const node = new AudioWorkletNode(ctx, 'mic-processor', { processorOptions: { targetSampleRate: 16000 } })
        node.port.onmessage = ({ data }) => data?.pcm && send(new Int16Array(data.pcm))
        source.connect(node)
        node.connect(ctx.destination)
        rt.micNode = node
      } catch (e) {
        if (gen !== generation) return
        console.warn('[call] AudioWorklet unavailable', e)
        this._fail('Your browser cannot stream audio. Please use the latest Chrome, Edge or Safari.')
      }
    },

    _startTimer() {
      const startedAt = Date.now()
      rt.timer = window.setInterval(() => {
        this.seconds = Math.floor((Date.now() - startedAt) / 1000)
        if (this.seconds >= MAX_CALL_SECONDS) this._finish('limit')
      }, 1000)
    },

    _teardown() {
      generation++
      if (rt.timer) clearInterval(rt.timer)
      rt.micSource?.disconnect()
      rt.micNode?.disconnect()
      rt.stream?.getTracks().forEach((t) => t.stop())
      const { avatar, ws } = rt
      Object.assign(rt, { ws: null, avatar: null, stream: null, micSource: null, micNode: null, timer: null })
      if (avatar) {
        avatar.removeAllListeners()
        avatar.exit()
      }
      if (ws) {
        ws.removeAllListeners()
        ws.stop()
      }
    },

    _finish(reason: 'user' | 'limit' | 'dropped') {
      if (this.status === 'ended' || this.status === 'idle' || this.status === 'error') return
      this.endReason = reason
      this.status = 'ended'
      this.avatarSpeaking = false
      this._teardown()
    },

    _fail(message: string) {
      this.error = message
      this.status = 'error'
      this._teardown()
    },

    reset() {
      this._teardown()
      this.$reset()
    },
  },
})
