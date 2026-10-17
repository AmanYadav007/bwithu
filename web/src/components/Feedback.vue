<script setup lang="ts">
import { ref } from 'vue'

import { fetch } from '@/apis'
import type { Companion } from '@/config/companion'

const props = defineProps<{ companion: Companion; seconds: number }>()
const rating = ref<'good' | 'bad' | null>(null)
const text = ref('')
const state = ref<'ask' | 'detail' | 'sent'>('ask')

function pick(value: 'good' | 'bad') {
  rating.value = value
  state.value = 'detail'
}

async function send() {
  state.value = 'sent'
  try {
    await fetch('/bwithu/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rating: rating.value,
        text: text.value.trim(),
        seconds: props.seconds,
        avatar: props.companion.avatar,
        vibe: props.companion.vibe,
        voice: props.companion.voice,
      }),
    })
  } catch {
    // Feedback is best effort; never bother the user about it.
  }
}
</script>

<template>
  <div class="feedback" @click.stop>
    <template v-if="state === 'ask'">
      <p>How did that feel?</p>
      <div class="choices">
        <button class="choice" @click="pick('good')">Felt natural</button>
        <button class="choice" @click="pick('bad')">Not quite</button>
      </div>
    </template>
    <form v-else-if="state === 'detail'" @submit.prevent="send">
      <textarea
        v-model="text"
        rows="2"
        maxlength="1000"
        :placeholder="rating === 'good' ? 'What did you like? (optional)' : 'What felt off? (optional)'"
      />
      <button class="choice send" type="submit">Send</button>
    </form>
    <p v-else class="thanks">Thank you — this really helps.</p>
  </div>
</template>

<style scoped lang="less">
.feedback {
  width: 100%;
  max-width: 320px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  p {
    margin: 0 0 10px;
    color: var(--muted);
    font-size: 14px;
  }
}
.choices {
  display: flex;
  gap: 8px;
  justify-content: center;
}
.choice {
  height: 38px;
  padding: 0 16px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--glass);
  font-size: 14px;
  transition: border-color 0.2s;
  &:hover {
    border-color: rgba(255, 255, 255, 0.3);
  }
}
form {
  display: grid;
  gap: 8px;
}
textarea {
  width: 100%;
  resize: none;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--line);
  font: inherit;
  font-size: 14px;
  &:focus {
    outline: none;
    border-color: var(--purple);
  }
}
.send {
  justify-self: center;
}
.thanks {
  text-align: center;
}
</style>
