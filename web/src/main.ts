import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './fonts.css'
import './style.less'

createApp(App).use(createPinia()).mount('#app')
