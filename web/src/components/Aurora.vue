<template>
  <div class="aurora" aria-hidden="true" />
</template>

<style scoped lang="less">
// Soft brand glow from plain radial gradients: no blur filters or animation,
// so it costs nothing next to the avatar renderer on low-end devices.
.aurora {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background:
    radial-gradient(60vmax 50vmax at 0% 0%, rgba(168, 85, 247, 0.28), transparent 70%),
    radial-gradient(55vmax 45vmax at 100% 100%, rgba(56, 189, 248, 0.16), transparent 70%),
    radial-gradient(120% 80% at 50% 0%, #10143a 0%, var(--space) 60%);
}
</style>
