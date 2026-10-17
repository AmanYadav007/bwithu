import { defineStore } from 'pinia'

import { AVATARS, DEFAULT_COMPANION, VIBES, VOICES, type Companion } from '@/config/companion'

const STORAGE_KEY = 'bwithu.companion'

function load(): Companion | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const saved = JSON.parse(raw) as Partial<Companion>
    return {
      name: typeof saved.name === 'string' && saved.name.trim() ? saved.name : DEFAULT_COMPANION.name,
      userName: typeof saved.userName === 'string' ? saved.userName : '',
      avatar: AVATARS.some((a) => a.id === saved.avatar) ? saved.avatar! : DEFAULT_COMPANION.avatar,
      vibe: VIBES.some((v) => v.id === saved.vibe) ? saved.vibe! : DEFAULT_COMPANION.vibe,
      voice: VOICES.some((v) => v.id === saved.voice) ? saved.voice! : DEFAULT_COMPANION.voice,
    }
  } catch {
    return null
  }
}

export const useCompanionStore = defineStore('companion', {
  state: () => {
    const saved = load()
    return { companion: saved ?? { ...DEFAULT_COMPANION }, isSetUp: saved !== null }
  },
  actions: {
    save(next: Companion) {
      this.companion = { ...next, name: next.name.trim().slice(0, 24) || DEFAULT_COMPANION.name }
      this.isSetUp = true
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(this.companion))
      } catch {
        // Private mode: keep the choice for this visit only.
      }
    },
    edit() {
      this.isSetUp = false
    },
  },
})
