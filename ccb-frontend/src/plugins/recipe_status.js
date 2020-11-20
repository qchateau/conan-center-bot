import axios from 'axios'

const url = 'https://raw.githubusercontent.com/qchateau/conan-center-bot/status/prod/v1-update.json'

export default {
  install (Vue) {
    Vue.prototype.$recipes = {
      status: Vue.observable({}),
      url: url,
      async refresh () {
        let data = (await axios.get(url)).data

        for (let key in this.status) {
          delete this.status[key]
        }

        for (let key in data) {
          this.status[key] = data[key]
        }
      }
    }
  }
}
