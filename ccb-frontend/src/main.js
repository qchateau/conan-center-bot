import Vue from 'vue'

import Vuetify from 'vuetify'
import 'vuetify/dist/vuetify.min.css'

import JsonViewer from 'vue-json-viewer'

import App from './App'
import router from './router'

import RecipePlugin from './plugins/recipe_status.js'

const vuetify = new Vuetify({theme: { dark: true }})

Vue.config.productionTip = false
Vue.use(Vuetify)
Vue.use(JsonViewer)
Vue.use(RecipePlugin)

/* eslint-disable no-new */
new Vue({
  el: '#app',
  vuetify: vuetify,
  router,
  components: { App },
  template: '<App/>'
})
