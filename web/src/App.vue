<script setup lang="ts">
import { ref } from 'vue'

import Aurora from '@/components/Aurora.vue'
import { useCompanionStore } from '@/store/companion'
import Call from '@/views/Call.vue'
import Setup from '@/views/Setup.vue'

const companionStore = useCompanionStore()
// Returning visitors land on the call screen with their saved companion; first-timers see setup.
const screen = ref<'setup' | 'call'>(companionStore.isSetUp ? 'call' : 'setup')
</script>

<template>
  <Aurora />
  <Transition name="fade" mode="out-in">
    <Setup v-if="screen === 'setup'" @done="screen = 'call'" />
    <Call v-else @edit="screen = 'setup'" />
  </Transition>
</template>

<style>
.fade-enter-active,
.fade-leave-active {
  transition:
    opacity 0.35s ease,
    transform 0.35s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
