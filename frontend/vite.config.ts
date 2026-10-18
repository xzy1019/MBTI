import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig(({mode})=>{
  const apiTarget=loadEnv(mode,'.','ATLAS_').ATLAS_API_TARGET||'http://127.0.0.1:8091'
  return {plugins:[vue()],server:{proxy:{'/api':apiTarget,'/healthz':apiTarget}},build:{target:'es2022'}}
})
