<template>
  <div>
    <v-card>
      <v-card-title>Unsupported recipes</v-card-title>
      <v-card-text>
        The following recipes are not supported.
        <v-text-field v-model="search" label="Search" />
      </v-card-text>
      <v-data-table
        :headers="headers"
        :items="selected"
        :single-expand="true"
        :disable-pagination="true"
        :hide-default-footer="true"
        :search="search"
        item-key="name"
        dense
      >
        <template v-slot:item.name="{ item }">
          <a :href="item.homepage">{{ item.name }}</a>
        </template>

        <template v-slot:item.details="{ headers, item }">
          <span>
            <pre v-if="item.details">{{item.details}}</pre>
            <div v-else>No details</div>
          </span>
        </template>
      </v-data-table>
    </v-card>
  </div>
</template>

<script>
export default {
  data () {
    return {
      search: '',
      headers: [
        {
          text: 'Name',
          align: 'start',
          sortable: true,
          value: 'name'
        },
        {
          text: 'Recipe version',
          align: 'start',
          sortable: false,
          value: 'current.version'
        },
        {
          text: 'Details',
          align: 'start',
          sortable: false,
          value: 'details'
        }
      ]
    }
  },
  computed: {
    selected () {
      let recipes = this.$recipes.status.recipes
      recipes = recipes.filter(x => !x.supported)
      return recipes
    }
  }
}
</script>

<style scoped>
</style>
