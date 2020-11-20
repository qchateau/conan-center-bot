<template>
  <div>
    <v-card>
      <v-card-title>Api</v-card-title>
      <v-card-text>
        This website data comes from
        <a :href="apiUrl">this JSON file</a>. Feel free to use it.
        <json-viewer :value="$recipes.status" theme="jv-dark"></json-viewer>
      </v-card-text>
    </v-card>
  </div>
</template>

<script>
export default {
  data () {
    return {
      apiUrl: this.$recipes.url
    }
  }
}
</script>

<style scoped>
pre {
  overflow-x: auto;
  white-space: pre-wrap;
  white-space: -moz-pre-wrap;
  white-space: -pre-wrap;
  white-space: -o-pre-wrap;
  word-wrap: break-word;
}
</style>
