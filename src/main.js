import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ConfigProvider, Button, Segmented, Select, Checkbox } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import './styles/main.css'
import './styles/workspace.css'
import App from './App.vue'
import router from './router'
const app = createApp(App).use(createPinia()).use(router)
const components = [ConfigProvider, Button, Segmented, Select, Checkbox]
components.forEach((component) => app.use(component))
app.mount('#app')
