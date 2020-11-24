<template>
  <div>
    <v-card>
      <v-card-title>Updatable recipes</v-card-title>
      <v-card-text>
        These recipes are updatable.
        <br />When it's possible to auto-update them,
        you can directly open a PR by clicking on "Open one".
        <br />When it's not, you can see the error by expanding the row.
        <v-text-field v-model="search" label="Search" />
      </v-card-text>
      <v-data-table
        :headers="recipesHeaders"
        :items="selectedRecipes"
        :expanded.sync="expanded"
        :single-expand="true"
        :disable-pagination="true"
        :hide-default-footer="true"
        :search="search"
        item-key="name"
        show-expand
        dense
      >
        <template v-slot:item.name="{ item }">
          <a :href="item.homepage">{{ item.name }}</a>
        </template>

        <template v-slot:item.prs_opened="{ item }">
          <span v-for="link in prLinks(item)" :key="link.href">
            <a v-if="link.href" :href="link.href">{{ link.text }}</a>
            <span v-else>{{ link.text }}</span>
          </span>
        </template>

        <template v-slot:expanded-item="{ headers, item }">
          <td :colspan="headers.length">
            <span v-if="item.supported">
              <pre v-if="item.update_error">{{item.update_error}}</pre>
              <div v-else>No errors</div>
            </span>
            <span v-else>
              <v-icon dark>mdi-cancel</v-icon>Unsupported
            </span>
          </td>
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
      expanded: [],
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
          value: 'recipe_version'
        },
        {
          text: 'New version',
          align: 'start',
          sortable: false,
          value: 'upstream_version'
        },
        {
          text: 'Upstream tag',
          align: 'start',
          sortable: false,
          value: 'upstream_tag'
        },
        {
          text: 'Pull requests',
          align: 'start',
          sortable: false,
          value: 'prs_opened'
        },
        { text: '', value: 'data-table-expand' }
      ]
    }
  },
  methods: {
    canOpenPr (recipe) {
      return recipe.updated_branch.owner && recipe.updated_branch.repo && recipe.updated_branch.branch
    },
    prLinks (recipe) {
      if (recipe.prs_opened.length > 0) {
        return recipe.prs_opened.map(pr => ({
          text: `#${pr.number}`,
          href: pr.url
        }))
      }

      if (!this.canOpenPr(recipe)) {
        return [{text: 'No'}]
      }

      const branch = recipe.updated_branch
      return [{text: 'Open one', href: `https://github.com/${branch.owner}/${branch.repo}/pull/new/${branch.branch}`}]
    }
  },
  computed: {
    selectedRecipes () {
      let recipes = this.$recipes.status.recipes
      recipes = recipes.filter(x => x.updatable)
      return recipes
    }
  }
}
</script>

<style scoped>
pre {
  overflow-x: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 0.9em;
}
</style>
