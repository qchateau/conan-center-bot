import Vue from 'vue'
import Router from 'vue-router'
import Status from '@/components/Status'
import Updatable from '@/components/Updatable'
import Inconsistent from '@/components/Inconsistent'
import Unsupported from '@/components/Unsupported'
import Api from '@/components/Api'

Vue.use(Router)

export default new Router({
  routes: [
    {
      path: '/',
      redirect: '/status',
      meta: {
        title: 'Conan Center Bot'
      }
    },
    {
      path: '/status',
      name: 'Status',
      component: Status,
      meta: {
        title: 'Conan Center Bot - Status'
      }
    },
    {
      path: '/updatable',
      name: 'Updatable',
      component: Updatable,
      meta: {
        title: 'Conan Center Bot - Updatable'
      }
    },
    {
      path: '/inconsistent',
      name: 'Inconsistent',
      component: Inconsistent,
      meta: {
        title: 'Conan Center Bot - Inconsistent'
      }
    },
    {
      path: '/unsupported',
      name: 'Unsupported',
      component: Unsupported,
      meta: {
        title: 'Conan Center Bot - Unsupported'
      }
    },
    {
      path: '/api',
      name: 'Api',
      component: Api,
      meta: {
        title: 'Conan Center Bot - Api'
      }
    }
  ]
})
