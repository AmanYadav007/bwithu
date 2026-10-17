<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onBeforeUnmount, ref } from 'vue'

import Logo from '@/components/Logo.vue'
import { AVATARS } from '@/config/companion'
import { TYVoiceChatState } from '@/interface/voiceChat'
import { useCallStore } from '@/store/call'
import { useCompanionStore } from '@/store/companion'

const emit = defineEmits<{ edit: [] }>()
const call = useCallStore()
const { companion } = storeToRefs(useCompanionStore())
const stage = ref<HTMLDivElement>()

const preview = computed(() => AVATARS.find((a) => a.id === companion.value.avatar)?.preview)
const ready = computed(() => call.status === 'live' && call.loadPercent >= 100)

const statusText = computed(() => {
  if (call.status === 'connecting' || (call.status === 'live' && !ready.value)) return 'Connecting…'
  if (call.status !== 'live') return ''
  if (call.micMuted) return 'You are muted'
  if (call.avatarSpeaking || call.avatarState === TYVoiceChatState.Responding) return 'Speaking'
  return 'Listening'
})

const clock = computed(() => {
  const s = call.seconds
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
})

const endedText = computed(() => {
  if (call.endReason === 'limit') return `That's the free time for this call. ${companion.value.name} will be here next time.`
  if (call.endReason === 'dropped') return 'The call dropped. It happens — try again.'
  return `Call with ${companion.value.name} ended.`
})

function start() {
  if (stage.value) call.start(stage.value, companion.value)
}

function editCompanion() {
  call.reset()
  emit('edit')
}

onBeforeUnmount(() => call.reset())
</script>

<template>
  <main class="call">
    <header class="top">
      <Logo />
      <button v-if="call.status === 'idle' || call.status === 'ended' || call.status === 'error'" class="btn-ghost" @click="editCompanion">
        Change companion
      </button>
      <span v-else class="timer" :class="{ warn: call.secondsLeft <= 60 }">{{ clock }}</span>
    </header>

    <div class="frame" :class="{ live: call.status === 'live', speaking: call.avatarSpeaking }">
      <div ref="stage" class="stage" :class="{ visible: ready }" />

      <!-- Before / after the call: portrait + one big action -->
      <div v-if="!ready" class="cover">
        <img v-if="preview" :src="preview" alt="" class="portrait" :class="{ dim: call.status !== 'idle' }" />
        <div class="cover-body">
          <template v-if="call.status === 'idle'">
            <h2>{{ companion.name }}</h2>
            <p>Ready when you are.</p>
            <button class="btn-primary" @click="start">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15.6 11.6 22 7v10l-6.4-4.5" /><rect x="2" y="6" width="14" height="12" rx="3" /></svg>
              Start call
            </button>
          </template>
          <template v-else-if="call.status === 'connecting' || call.status === 'live'">
            <div class="ring" :style="{ '--p': call.loadPercent }"><span>{{ call.loadPercent }}%</span></div>
            <p>Waking {{ companion.name }} up…</p>
          </template>
          <template v-else-if="call.status === 'ended'">
            <h2>{{ endedText }}</h2>
            <button class="btn-primary" @click="start">Call again</button>
          </template>
          <template v-else-if="call.status === 'error'">
            <h2>Couldn't start the call</h2>
            <p>{{ call.error }}</p>
            <button class="btn-primary" @click="start">Try again</button>
          </template>
        </div>
      </div>

      <!-- Live overlay -->
      <template v-if="ready">
        <div class="name-tag">
          <span class="dot" :class="{ speaking: call.avatarSpeaking }" />
          <strong>{{ companion.name }}</strong>
          <span class="status">{{ statusText }}</span>
        </div>
        <Transition name="caption">
          <p v-if="call.avatarCaption" :key="call.avatarCaption.key" class="caption">
            {{ call.avatarCaption.text }}
          </p>
        </Transition>
      </template>
    </div>

    <nav v-if="call.status === 'live'" class="controls">
      <button class="ctl glass" :class="{ off: call.micMuted }" :aria-label="call.micMuted ? 'Unmute microphone' : 'Mute microphone'" @click="call.toggleMic()">
        <svg v-if="!call.micMuted" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
        <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M15 9.3V6a3 3 0 0 0-5.7-1.3M9 9v2a3 3 0 0 0 4.9 2.3M19 11a7 7 0 0 1-1.1 3.8M5 11a7 7 0 0 0 10.6 6M12 18v3M3 3l18 18" /></svg>
      </button>
      <button class="ctl end" aria-label="End call" @click="call.end()">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor"><path d="M12 9c-3.2 0-6.2.9-8.6 2.6-.6.4-.8 1.2-.5 1.9l1.1 2.2c.3.6 1 .9 1.7.7l2.6-.8c.6-.2 1-.7 1-1.3v-1.8c1.7-.5 3.6-.5 5.4 0v1.8c0 .6.4 1.1 1 1.3l2.6.8c.7.2 1.4-.1 1.7-.7l1.1-2.2c.3-.7.1-1.5-.5-1.9C18.2 9.9 15.2 9 12 9z" /></svg>
      </button>
      <button class="ctl glass" :class="{ off: call.speakerMuted }" :aria-label="call.speakerMuted ? 'Unmute speaker' : 'Mute speaker'" @click="call.toggleSpeaker()">
        <svg v-if="!call.speakerMuted" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4V5zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" /></svg>
        <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4V5zM22 9l-6 6M16 9l6 6" /></svg>
      </button>
    </nav>
    <p v-else class="hint">Use headphones for the smoothest conversation. You can interrupt any time — just talk.</p>
  </main>
</template>

<style scoped lang="less">
.call {
  position: relative;
  z-index: 1;
  height: 100%;
  min-height: 100dvh;
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 16px;
  padding: 16px 16px max(20px, env(safe-area-inset-bottom));
  max-width: 560px;
  margin: 0 auto;
}
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 46px;
}
.timer {
  font-variant-numeric: tabular-nums;
  color: var(--muted);
  font-weight: 500;
  &.warn {
    color: #fbbf24;
  }
}
.frame {
  position: relative;
  border-radius: 32px;
  overflow: hidden;
  background: var(--space-2);
  border: 1px solid var(--line);
  min-height: 0;
  box-shadow: 0 30px 80px -30px rgba(0, 0, 0, 0.8);
  transition: box-shadow 0.6s ease;
  &.live.speaking {
    box-shadow:
      0 0 0 1px rgba(168, 85, 247, 0.5),
      0 0 60px -10px rgba(168, 85, 247, 0.55),
      0 30px 80px -30px rgba(0, 0, 0, 0.8);
  }
}
.frame::after {
  // Blend the bottom of the avatar bust into the background.
  content: '';
  position: absolute;
  inset: auto 0 0 0;
  height: 38%;
  background: linear-gradient(to top, var(--space-2) 25%, rgba(11, 14, 34, 0));
  pointer-events: none;
}
.stage {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.8s ease;
  &.visible {
    opacity: 1;
  }
  :deep(canvas) {
    width: 100% !important;
    height: 100% !important;
    display: block;
    // Frame the head and shoulders like a video call instead of a distant bust.
    transform: scale(1.3);
    transform-origin: 50% 42%;
  }
}
.cover {
  z-index: 1;
  position: absolute;
  inset: 0;
  display: grid;
  place-items: end center;
}
.portrait {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition:
    filter 0.6s,
    transform 0.6s;
  &.dim {
    filter: blur(14px) brightness(0.45);
    transform: scale(1.06);
  }
}
.cover-body {
  position: relative;
  width: 100%;
  padding: 120px 24px 32px;
  text-align: center;
  display: grid;
  justify-items: center;
  gap: 10px;
  background: linear-gradient(to top, rgba(6, 8, 22, 0.95) 30%, rgba(6, 8, 22, 0));
  h2 {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: 26px;
    margin: 0;
    max-width: 22ch;
    line-height: 1.25;
  }
  p {
    margin: 0 0 8px;
    color: var(--muted);
    max-width: 36ch;
  }
}
.ring {
  --p: 0;
  width: 84px;
  height: 84px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: conic-gradient(var(--purple) calc(var(--p) * 1%), rgba(255, 255, 255, 0.08) 0);
  mask: radial-gradient(circle, transparent 34px, #000 35px);
  -webkit-mask: radial-gradient(circle, transparent 34px, #000 35px);
  span {
    display: none;
  }
}
.name-tag {
  z-index: 1;
  background: rgba(6, 8, 22, 0.6);
  border: 1px solid var(--line);
  position: absolute;
  top: 16px;
  left: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px 8px 12px;
  border-radius: 999px;
  font-size: 14px;
  .status {
    color: var(--muted);
  }
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--cyan);
  box-shadow: 0 0 10px var(--cyan);
  &.speaking {
    background: var(--purple);
    box-shadow: 0 0 12px var(--purple);
    animation: pulse 1.1s ease-in-out infinite;
  }
}
@keyframes pulse {
  50% {
    transform: scale(1.5);
    opacity: 0.6;
  }
}
.caption {
  z-index: 1;
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 16px;
  margin: 0;
  padding: 12px 16px;
  border-radius: 18px;
  background: rgba(6, 8, 22, 0.72);
  font-size: 15px;
  line-height: 1.45;
  text-align: center;
  max-height: 30%;
  overflow: hidden;
}
.caption-enter-active,
.caption-leave-active {
  transition: opacity 0.3s;
}
.caption-enter-from,
.caption-leave-to {
  opacity: 0;
}
.controls {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 22px;
  padding: 4px 0;
}
.ctl {
  width: 58px;
  height: 58px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  transition:
    background 0.2s,
    transform 0.15s;
  &:hover {
    background: var(--glass-strong);
  }
  &:active {
    transform: scale(0.94);
  }
  &.off {
    background: var(--white);
    color: var(--space);
  }
  &.end {
    width: 70px;
    height: 70px;
    background: var(--danger);
    color: #fff;
    box-shadow: 0 10px 30px -8px rgba(244, 63, 94, 0.7);
  }
}
.hint {
  margin: 0;
  text-align: center;
  color: var(--faint);
  font-size: 13px;
}
</style>
