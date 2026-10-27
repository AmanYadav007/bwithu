import { defineStore } from 'pinia'

import { AVATARS, DEFAULT_COMPANION, LANGUAGES, LEGACY_VOICES, VIBES, VOICES, type Companion } from '@/config/companion'

const STORAGE_KEY = 'bwithu.companion'

function load(): Companion | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const saved = JSON.parse(raw) as Partial<Companion>
    const voice = LEGACY_VOICES[saved.voice ?? ''] ?? saved.voice
    return {
      name: typeof saved.name === 'string' && saved.name.trim() ? saved.name : DEFAULT_COMPANION.name,
      userName: typeof saved.userName === 'string' ? saved.userName : '',
      avatar: AVATARS.some((a) => a.id === saved.avatar) ? saved.avatar! : DEFAULT_COMPANION.avatar,
      vibe: VIBES.some((v) => v.id === saved.vibe) ? saved.vibe! : DEFAULT_COMPANION.vibe,
      voice: VOICES.some((v) => v.id === voice) ? voice! : DEFAULT_COMPANION.voice,
      language: LANGUAGES.some((l) => l.id === saved.language) ? saved.language! : DEFAULT_COMPANION.language,
    }
  } catch {
    return null
  }
}

/** Links from bwithu.live preselect a face and/or voice: app.bwithu.live/?face=leo&voice=andrew */
function fromLink(): Partial<Companion> {
  const params = new URLSearchParams(window.location.search)
  const face = params.get('face')
  const voice = params.get('voice')
  const picked: Partial<Companion> = {}
  if (face && AVATARS.some((a) => a.id === face)) picked.avatar = face
  if (voice && VOICES.some((v) => v.id === voice)) picked.voice = voice as Companion['voice']
  if (params.has('face') || params.has('voice')) window.history.replaceState(null, '', window.location.pathname)
  return picked
}

export const useCompanionStore = defineStore('companion', {
  state: () => {
    const saved = load()
    const picked = fromLink()
    const linked = Object.keys(picked).length > 0
    // A link lands on the setup screen with its pick selected, so the visitor can name them first.
    return { companion: { ...(saved ?? DEFAULT_COMPANION), ...picked }, isSetUp: saved !== null && !linked }
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
