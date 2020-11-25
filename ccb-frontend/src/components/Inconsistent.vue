<template>
  <div>
    <v-card>
      <v-card-title>Inconsistent recipes</v-card-title>
      <v-card-text>
        The following recipes are not consistent with their
        upstream versioning scheme.
        <br />Most of the times it
        means the recipe version is not related to
        any upstream tag.
        <v-text-field v-model="search" label="Search" />
      </v-card-text>
      <v-data-table
        :headers="recipesHeaders"
        :items="selectedRecipes"
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
      </v-data-table>
    </v-card>
  </div>
</template>

<script>
export default {
  data () {
    return {
      search: '',
      recipesHeaders: [
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
          text: 'Most recent upstream tag',
          align: 'start',
          sortable: false,
          value: 'new.tag'
        }
      ]
    }
  },
  computed: {
    selectedRecipes () {
      let recipes = this.$recipes.status.recipes
      recipes = recipes.filter(x => x.inconsistent_versioning)
      return recipes
    }
  }
}
</script>

<style scoped>
</style>
