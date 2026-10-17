// Choices offered in onboarding. Avatar ids are file names served by the
// server at /download/lam_asset/<id>.zip; voice ids must be in the server's
// QwenOmni.allowed_voices; vibe ids must match server/src/bwithu/persona.py.

export interface AvatarOption {
  id: string
  label: string
  preview: string
}

export const AVATARS: AvatarOption[] = [
  { id: 'james', label: 'James', preview: 'avatars/james.webp' },
  { id: 'vfhq_case1', label: 'Arthur', preview: 'avatars/vfhq_case1.webp' },
  { id: 'barbara', label: 'Sketch', preview: 'avatars/barbara.webp' },
  { id: 'status', label: 'Marble', preview: 'avatars/status.webp' },
]

export const VIBES = [
  { id: 'warm', label: 'Warm', hint: 'Calm, caring, a good listener' },
  { id: 'playful', label: 'Playful', hint: 'Witty, upbeat, a bit cheeky' },
  { id: 'focused', label: 'Focused', hint: 'A clear-headed coach' },
] as const

export const VOICES = [
  { id: 'Tina', label: 'Tina' },
  { id: 'Cherry', label: 'Cherry' },
  { id: 'Ethan', label: 'Ethan' },
  { id: 'Serena', label: 'Serena' },
] as const

export type VibeId = (typeof VIBES)[number]['id']
export type VoiceId = (typeof VOICES)[number]['id']

export interface Companion {
  name: string
  userName: string
  avatar: string
  vibe: VibeId
  voice: VoiceId
}

export const DEFAULT_COMPANION: Companion = {
  name: 'Nova',
  userName: '',
  avatar: 'james',
  vibe: 'warm',
  voice: 'Tina',
}

// Free minutes per call before the call ends itself (server also enforces connection_ttl).
export const MAX_CALL_SECONDS = 10 * 60
