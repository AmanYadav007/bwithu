<script setup lang="ts">
// Served from public/, relative to the page so it works under any mount path.
const icon = 'favicon.svg'
</script>

<template>
  <div class="logo">
    <img :src="icon" alt="" width="30" height="30" />
    <span>Bwith<b>U</b></span>
  </div>
</template>

<style scoped>
.logo {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 20px;
  letter-spacing: -0.01em;
}
b {
  font-weight: 700;
  background: linear-gradient(135deg, var(--purple), var(--cyan));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
img {
  border-radius: 9px;
}
</style>
