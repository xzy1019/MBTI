import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
const router=createRouter({history:createWebHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<span />'}}],scrollBehavior(to,from){return to.path===from.path?undefined:{top:0}}})
createApp(App).use(router).mount('#app')
