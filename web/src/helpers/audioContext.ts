// One AudioContext for the whole app (mic capture + avatar voice).
// iOS Safari only lets audio run if the context is created/resumed inside a user gesture, and it
// limits how many contexts a page may open, so we create it once on the "Start call" tap and reuse it.
let shared: AudioContext | null = null

export function getAudioContext(): AudioContext {
  if (!shared || shared.state === 'closed') {
    // @ts-expect-error webkitAudioContext for older Safari
    const Ctor: typeof AudioContext = window.AudioContext || window.webkitAudioContext
    shared = new Ctor()
  }
  return shared
}

/** Call synchronously from a click/tap handler. */
export function unlockAudio(): AudioContext {
  const ctx = getAudioContext()
  void ctx.resume()
  // Playing one silent frame is the most reliable unlock on iOS.
  const src = ctx.createBufferSource()
  src.buffer = ctx.createBuffer(1, 1, ctx.sampleRate)
  src.connect(ctx.destination)
  src.start(0)
  return ctx
}
