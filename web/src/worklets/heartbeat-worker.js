// heartbeat-worker.js - heartbeat timer that background tabs don't throttle

let heartbeatInterval = null

self.onmessage = function (e) {
  const { type, interval } = e.data

  switch (type) {
    case 'start':
      if (heartbeatInterval) {
        clearInterval(heartbeatInterval)
      }
      heartbeatInterval = setInterval(() => {
        self.postMessage({ type: 'heartbeat' })
      }, interval || 10000)
      break

    case 'stop':
      if (heartbeatInterval) {
        clearInterval(heartbeatInterval)
        heartbeatInterval = null
      }
      break
  }
}
