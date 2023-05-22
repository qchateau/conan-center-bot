import axios from 'axios'

const user = window.location.host.split('.')[0];
const repo = window.location.pathname.split('/')[1];

const url = `https://raw.githubusercontent.com/${user}/${repo}/status/prod/v1-update.json`

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
