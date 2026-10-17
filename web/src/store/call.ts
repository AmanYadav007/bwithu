import { defineStore } from 'pinia'
import { markRaw } from 'vue'

import { createWS, initConfig, makeURL } from '@/apis'
import { MAX_CALL_SECONDS, type Companion } from '@/config/companion'
import { AvatarHandler } from '@/handlers/avatarHandler'
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
  audioContext: AudioContext | null
  micNode: AudioNode | null
  timer: number | null
}

// Non-reactive handles for the live call; kept outside Pinia state on purpose.
const rt: Runtime = { ws: null, avatar: null, stream: null, audioContext: null, micNode: null, timer: null }

let serverConfig: { wsRoute: string; assetRoute: string } | null = null

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
    micMuted: false,
    speakerMuted: false,
    seconds: 0,
    endReason: '' as '' | 'user' | 'limit' | 'dropped',
    error: '',
    avatarCaption: null as Caption | null,
    humanCaption: null as Caption | null,
  }),
  getters: {
    secondsLeft: (s) => Math.max(0, MAX_CALL_SECONDS - s.seconds),
  },
  actions: {
    async start(container: HTMLDivElement, companion: Companion) {
      if (this.status === 'connecting' || this.status === 'live') return
      this.$reset()
      this.status = 'connecting'
      try {
        const [{ wsRoute, assetRoute }, stream] = await Promise.all([
          loadServerConfig(),
          navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
          }),
        ])
        rt.stream = stream

        const ws = createWS(wsRoute, crypto.randomUUID(), {
          name: companion.name,
          user: companion.userName,
          vibe: companion.vibe,
          voice: companion.voice,
        })
        rt.ws = markRaw(ws)
        ws.on(WsEventTypes.WS_OPEN, () => {
          this.status = 'live'
          this._startMic()
          this._startTimer()
        })
        ws.on(WsEventTypes.WS_CLOSE, () => this._finish(this.endReason || 'dropped'))
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
          loadProgress: (p) => (this.loadPercent = 60 + Math.round(p * 40)),
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
      rt.avatar?.interrupt()
    },

    _onText(role: 'human' | 'avatar', payload?: TextPayload) {
      if (!payload || typeof payload.text !== 'string') return
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
      const ctx = new AudioContext()
      rt.audioContext = ctx
      const source = ctx.createMediaStreamSource(rt.stream)
      const send = (pcm: Int16Array) => {
        if (this.micMuted || rt.ws?.engine?.readyState !== WebSocket.OPEN) return
        rt.avatar?.sendAudio(pcm, 'base64')
      }
      try {
        // Served from public/ as a real file: Safari rejects data: URLs for worklets.
        await ctx.audioWorklet.addModule(new URL('worklets/mic-processor.js', document.baseURI).href)
        const node = new AudioWorkletNode(ctx, 'mic-processor', { processorOptions: { targetSampleRate: 16000 } })
        node.port.onmessage = ({ data }) => data?.pcm && send(new Int16Array(data.pcm))
        source.connect(node)
        node.connect(ctx.destination)
        rt.micNode = node
      } catch (e) {
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
      if (rt.timer) clearInterval(rt.timer)
      rt.micNode?.disconnect()
      if (rt.audioContext && rt.audioContext.state !== 'closed') rt.audioContext.close()
      rt.stream?.getTracks().forEach((t) => t.stop())
      const { avatar, ws } = rt
      Object.assign(rt, { ws: null, avatar: null, stream: null, audioContext: null, micNode: null, timer: null })
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
