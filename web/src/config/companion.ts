// Choices offered in onboarding. Avatar ids are file names served by the
// server at /download/lam_asset/<id>.zip; voice ids must be keys of `voices` in the server's
// configs (Edge_TTS / QwenOmni); vibe ids must match server/src/bwithu/persona.py.

export interface AvatarOption {
  id: string
  label: string
  preview: string
}

// Women first, then men. varshika.zip / varshika.jpg are real-person files kept out of git (see .gitignore).
export const AVATARS: AvatarOption[] = [
  { id: 'maya', label: 'Maya', preview: 'avatars/maya.jpg' },
  { id: 'elena', label: 'Elena', preview: 'avatars/elena.jpg' },
  { id: 'zara', label: 'Zara', preview: 'avatars/zara.jpg' },
  { id: 'aiko', label: 'Aiko', preview: 'avatars/aiko.jpg' },
  { id: 'varshika', label: 'Varshika', preview: 'avatars/varshika.jpg' },
  { id: 'leo', label: 'Leo', preview: 'avatars/leo.jpg' },
  { id: 'ravi', label: 'Ravi', preview: 'avatars/ravi.jpg' },
  { id: 'james', label: 'James', preview: 'avatars/james.jpg' },
  { id: 'vfhq_case1', label: 'Arthur', preview: 'avatars/vfhq_case1.jpg' },
]

export const VIBES = [
  { id: 'warm', label: 'Warm', hint: 'Calm, caring, a good listener' },
  { id: 'playful', label: 'Playful', hint: 'Witty, upbeat, a bit cheeky' },
  { id: 'focused', label: 'Focused', hint: 'A clear-headed coach' },
] as const

// Samples in public/voices/<id>.mp3 (same text in every voice).
export const VOICES = [
  { id: 'ava', label: 'Ava', gender: 'Female', accent: 'US' },
  { id: 'emma', label: 'Emma', gender: 'Female', accent: 'US' },
  { id: 'neerja', label: 'Neerja', gender: 'Female', accent: 'Indian' },
  { id: 'andrew', label: 'Andrew', gender: 'Male', accent: 'US' },
  { id: 'brian', label: 'Brian', gender: 'Male', accent: 'US' },
  { id: 'prabhat', label: 'Prabhat', gender: 'Male', accent: 'Indian' },
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
  avatar: 'maya',
  vibe: 'warm',
  voice: 'ava',
}

// Voice ids saved before the voice list changed.
export const LEGACY_VOICES: Record<string, VoiceId> = { Tina: 'ava', Cherry: 'emma', Serena: 'neerja', Ethan: 'andrew' }

// Free minutes per call before the call ends itself (server also enforces connection_ttl).
export const MAX_CALL_SECONDS = 10 * 60
