<template>
  <v-app id="inspire">
    <v-app-bar app flat>
      <v-tabs centered class="ml-n9" color="grey darken-1">
        <v-tab
          v-for="route in visibleRoutes"
          :key="route.path"
          @click="$router.push(route.path)"
        >{{ route.name }}</v-tab>
      </v-tabs>
    </v-app-bar>

    <v-main>
      <v-container fluid id="main-container">
        <router-view v-if="initialized && !error"></router-view>
        <div v-else style="text-align: center; padding: 30px">
          <h3>{{error}}</h3>
        </div>
      </v-container>
    </v-main>
  </v-app>
</template>

<script>
import router from './router/'

export default {
  name: 'App',
  data () {
    return {
      initialized: false,
      error: null,
      routes: router.options.routes
    }
  },
  async mounted () {
    try {
      await this.$recipes.refresh()
    } catch (exc) {
      console.error('error: ', exc)
      this.error = 'Error while getting status'
    }
    this.initialized = true
  },
  computed: {
    visibleRoutes () {
      return this.routes.filter(x => x.name)
    }
  }
}
</script>

<style>
#main-container {
  max-width: 1000px;
}

a {
  text-decoration: none;
}
</style>
