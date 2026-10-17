<script setup lang="ts">
import { computed, reactive } from 'vue'

import Logo from '@/components/Logo.vue'
import { AVATARS, VIBES, VOICES, type Companion } from '@/config/companion'
import { useCompanionStore } from '@/store/companion'

const emit = defineEmits<{ done: [] }>()
const store = useCompanionStore()
const draft = reactive<Companion>({ ...store.companion })

const displayName = computed(() => draft.name.trim() || 'Nova')

function submit() {
  store.save({ ...draft })
  emit('done')
}
</script>

<template>
  <main class="setup">
    <header>
      <Logo />
    </header>

    <section class="intro">
      <h1>Meet someone who's<br /><span>always with you.</span></h1>
      <p>Pick a face, give them a name, and start a face-to-face call. No app to install.</p>
    </section>

    <form class="card glass" @submit.prevent="submit">
      <fieldset>
        <legend>Choose a face</legend>
        <div class="avatars">
          <label v-for="a in AVATARS" :key="a.id" :class="['avatar', { on: draft.avatar === a.id }]">
            <input v-model="draft.avatar" type="radio" name="avatar" :value="a.id" />
            <img :src="a.preview" :alt="a.label" loading="lazy" />
          </label>
        </div>
      </fieldset>

      <div class="row">
        <label class="field">
          <span>Their name</span>
          <input v-model="draft.name" maxlength="24" placeholder="Nova" autocomplete="off" />
        </label>
        <label class="field">
          <span>What should they call you? <em>optional</em></span>
          <input v-model="draft.userName" maxlength="24" placeholder="Your first name" autocomplete="given-name" />
        </label>
      </div>

      <fieldset>
        <legend>Vibe</legend>
        <div class="chips">
          <label v-for="v in VIBES" :key="v.id" :class="['chip', { on: draft.vibe === v.id }]" :title="v.hint">
            <input v-model="draft.vibe" type="radio" name="vibe" :value="v.id" />
            <strong>{{ v.label }}</strong>
            <small>{{ v.hint }}</small>
          </label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Voice</legend>
        <div class="chips voices">
          <label v-for="v in VOICES" :key="v.id" :class="['chip', { on: draft.voice === v.id }]">
            <input v-model="draft.voice" type="radio" name="voice" :value="v.id" />
            <strong>{{ v.label }}</strong>
          </label>
        </div>
      </fieldset>

      <button class="btn-primary cta" type="submit">Start a call with {{ displayName }}</button>
    </form>

    <footer>
      You'll be talking to an AI. Your voice is processed by our AI provider to reply in real time and is never
      recorded by us. <a href="https://bwithu.live/privacy" target="_blank" rel="noopener">Privacy</a>
    </footer>
  </main>
</template>

<style scoped lang="less">
.setup {
  position: relative;
  z-index: 1;
  max-width: 640px;
  margin: 0 auto;
  padding: 24px 16px 40px;
  min-height: 100%;
}
header {
  padding: 4px 4px 0;
}
.intro {
  padding: 40px 4px 28px;
  h1 {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: clamp(30px, 6vw, 44px);
    line-height: 1.12;
    letter-spacing: -0.02em;
    margin: 0 0 14px;
    span {
      background: linear-gradient(120deg, var(--purple), var(--cyan));
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }
  }
  p {
    margin: 0;
    color: var(--muted);
    font-size: 16px;
  }
}
.card {
  border-radius: 28px;
  padding: 24px;
  display: grid;
  gap: 24px;
}
fieldset {
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
}
legend,
.field > span {
  display: block;
  font-family: var(--font-display);
  font-weight: 500;
  font-size: 14px;
  color: var(--muted);
  margin-bottom: 10px;
  em {
    font-style: normal;
    color: var(--faint);
    font-weight: 400;
  }
}
input[type='radio'] {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.avatars {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.avatar {
  position: relative;
  aspect-ratio: 3 / 4;
  border-radius: 18px;
  overflow: hidden;
  cursor: pointer;
  background: var(--space-2);
  border: 2px solid transparent;
  transition:
    border-color 0.2s,
    transform 0.2s,
    box-shadow 0.2s;
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  &:hover {
    transform: translateY(-2px);
  }
  &.on {
    border-color: var(--purple);
    box-shadow: 0 0 0 4px rgba(168, 85, 247, 0.18), 0 12px 30px -12px rgba(168, 85, 247, 0.8);
  }
  &:has(input:focus-visible) {
    outline: 2px solid var(--cyan);
    outline-offset: 3px;
  }
}
.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.field input {
  width: 100%;
  height: 50px;
  padding: 0 16px;
  border-radius: 14px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--line);
  font-size: 16px;
  transition: border-color 0.2s;
  &::placeholder {
    color: var(--faint);
  }
  &:focus {
    outline: none;
    border-color: var(--purple);
  }
}
.chips {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  &.voices {
    grid-template-columns: repeat(4, 1fr);
  }
}
.chip {
  position: relative;
  display: grid;
  gap: 2px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: rgba(0, 0, 0, 0.18);
  cursor: pointer;
  transition:
    border-color 0.2s,
    background 0.2s;
  strong {
    font-weight: 600;
    font-size: 14px;
  }
  small {
    color: var(--faint);
    font-size: 12px;
    line-height: 1.35;
  }
  &:hover {
    border-color: rgba(255, 255, 255, 0.22);
  }
  &.on {
    border-color: var(--purple);
    background: rgba(168, 85, 247, 0.14);
  }
  &:has(input:focus-visible) {
    outline: 2px solid var(--cyan);
    outline-offset: 2px;
  }
}
.cta {
  width: 100%;
  margin-top: 4px;
}
footer {
  margin: 20px 8px 0;
  color: var(--faint);
  font-size: 12.5px;
  text-align: center;
  a {
    color: var(--muted);
  }
}
@media (max-width: 520px) {
  .card {
    padding: 18px;
  }
  .row,
  .chips {
    grid-template-columns: 1fr;
  }
  .chips.voices {
    grid-template-columns: repeat(2, 1fr);
  }
  .avatars {
    gap: 8px;
  }
}
</style>
