<template>
  <div>
    <v-card>
      <v-card-title>Updatable recipes</v-card-title>
      <v-card-text>
        <p>
          Conan Center Bot attempts to auto-update the recipe, then to test the updated recipe.
          Tests are ran on a default Ubuntu 20.04 image as provided by GitHub Actions.
          <br />When the test passes, you can directly open a PR by clicking on "Open one".
          <br />When it doesn't, you can see the error by expanding the row.
        </p>
        <v-row>
          <v-col cols="4">
            <v-text-field v-model="search" label="Search" />
          </v-col>
          <v-col cols="8">
            <v-select
              v-model="enabledColumns"
              :items="availableColumns"
              label="Columns"
              attach
              multiple
            >
              <template v-slot:selection="{ item, index }">
                <v-chip label outlined small v-if="index <= 5">
                  <span v-if="index < 5">{{ item }}</span>
                  <span
                    v-if="index === 5"
                    class="grey--text caption"
                  >(+{{ enabledColumns.length - 4 }} others)</span>
                </v-chip>
              </template>
            </v-select>
          </v-col>
        </v-row>
      </v-card-text>
      <v-data-table
        :headers="selectedHeaders"
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

        <template v-slot:item.time_interval="{ item }">{{ formatDuration(item.time_interval) }}</template>
        <template v-slot:item.current.date="{ item }">{{ formatDate(item.current.date) }}</template>
        <template v-slot:item.new.date="{ item }">{{ formatDate(item.new.date) }}</template>

        <template v-slot:item.prs_opened="{ item }">
          <span v-for="link in prLinks(item)" :key="link.href">
            <a v-if="link.href" :href="link.href">{{ link.text }}</a>
            <span v-else>{{ link.text }}</span>
          </span>
        </template>

        <template v-slot:expanded-item="{ headers, item }">
          <td :colspan="headers.length">
            <span v-if="item.supported">
              <pre v-if="item.details">{{item.details}}</pre>
              <div v-else>No details</div>
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
      headers: [
        {
          text: 'Name',
          align: 'start',
          sortable: true,
          value: 'name'
        },
        {
          text: 'Current version',
          align: 'start',
          sortable: false,
          value: 'current.version'
        },
        {
          text: 'Current tag',
          align: 'start',
          sortable: false,
          value: 'current.tag'
        },
        {
          text: 'Current version date',
          align: 'start',
          sortable: true,
          value: 'current.date'
        },
        {
          text: 'Current commit count',
          align: 'start',
          sortable: true,
          value: 'current.commit_count'
        },
        {
          text: 'New version',
          align: 'start',
          sortable: false,
          value: 'new.version'
        },
        {
          text: 'New tag',
          align: 'start',
          sortable: false,
          value: 'new.tag'
        },
        {
          text: 'New version date',
          align: 'start',
          sortable: true,
          value: 'new.date'
        },
        {
          text: 'New commit count',
          align: 'start',
          sortable: true,
          value: 'new.commit_count'
        },
        {
          text: 'Time interval',
          align: 'start',
          sortable: true,
          value: 'time_interval'
        },
        {
          text: 'Commits difference',
          align: 'start',
          sortable: true,
          value: 'commits_count_difference'
        },
        {
          text: 'Pull requests',
          align: 'start',
          sortable: false,
          value: 'prs_opened'
        }
      ],
      enabledColumns: [
        'Name', 'Current version', 'New version', 'Time interval', 'Pull requests'
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
    },
    formatDuration (duration) {
      if (!duration && duration !== 0) {
        return 'Unknown'
      }

      const secPerDay = 24 * 3600
      const secPerYear = secPerDay * 365
      const secPerMonth = secPerYear / 12

      const years = Math.floor(duration / secPerYear)
      duration -= years * secPerYear
      const months = Math.floor(duration / secPerMonth)
      duration -= months * secPerMonth
      const days = Math.floor(duration / secPerDay)
      duration -= days * secPerDay
      const hours = Math.floor(duration / 3600)
      duration -= hours * 3600
      const minutes = Math.floor(duration / 60)
      duration -= minutes * 60
      const seconds = duration

      const fmt = function (count, name) {
        if (count === 1) {
          return `1 ${name}`
        }
        return `${count} ${name}s`
      }

      if (years > 0) {
        return fmt(years, 'year') + ' ' + fmt(months, 'month')
      }
      if (months > 0) {
        return fmt(months, 'month') + ' ' + fmt(days, 'day')
      }
      if (days > 0) {
        return fmt(days, 'day')
      }
      if (hours > 0) {
        return `${hours}h ${minutes}m`
      }
      if (minutes > 0) {
        return `${minutes}m ${Math.round(seconds)}s`
      }
      return `${seconds.toFixed(1)}s`
    },
    formatDate (dateString) {
      let date = new Date(dateString)
      return date.toLocaleString('en-GB', {timeZoneName: 'short'})
    }
  },
  computed: {
    selectedRecipes () {
      let recipes = this.$recipes.status.recipes
      recipes = recipes.filter(x => !x.deprecated && x.updatable)
      recipes = recipes.map(x => {
        if (x.current.date && x.new.date) {
          let currentDate = new Date(x.current.date)
          let newDate = new Date(x.new.date)
          x.time_interval = (newDate - currentDate) / 1000
        }
        if (x.current.commit_count && x.new.commit_count) {
          x.commits_count_difference = x.new.commit_count - x.current.commit_count
        }
        return x
      })
      return recipes
    },
    availableColumns () {
      return this.headers.map(x => x.text)
    },
    selectedHeaders () {
      let headers = this.headers.filter(x => this.enabledColumns.includes(x.text))
      headers.push({ text: '', value: 'data-table-expand' })
      return headers
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
