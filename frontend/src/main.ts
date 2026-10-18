import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import './submissions.css'
const router=createRouter({history:createWebHistory(import.meta.env.BASE_URL),routes:[{path:'/:pathMatch(.*)*',component:{template:'<span />'}}],scrollBehavior(to,from){return to.path===from.path?undefined:{top:0}}})
createApp(App).use(router).mount('#app')
