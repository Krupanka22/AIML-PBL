import {defineConfig} from 'vite'
export default defineConfig({server:{proxy:{'/comparison':'http://127.0.0.1:8000','/events':'http://127.0.0.1:8000','/control':'http://127.0.0.1:8000'}}})
