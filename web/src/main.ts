import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './style.less'

createApp(App).use(createPinia()).mount('#app')
