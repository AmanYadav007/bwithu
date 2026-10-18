<script setup lang="ts">
// Served from public/, relative to the page so it works under any mount path.
const icon = 'favicon.svg'
// The logo is the home link: parents decide what "home" means (scroll up, or leave the call).
const emit = defineEmits<{ home: [] }>()
</script>

<template>
  <a class="logo" href="./" aria-label="BwithU home" @click.prevent="emit('home')">
    <img :src="icon" alt="" width="30" height="30" />
    <span>Bwith<b>U</b></span>
  </a>
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
  color: inherit;
  text-decoration: none;
  border-radius: 10px;
  transition: opacity 0.2s;
}
.logo:hover {
  opacity: 0.85;
}
.logo:focus-visible {
  outline: 2px solid var(--cyan);
  outline-offset: 4px;
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
