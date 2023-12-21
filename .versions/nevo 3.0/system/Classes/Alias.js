class Alias {
    static aliases = new Map()
    base
    aliases

    constructor(base, ...aliases) {
        let alias = Alias.aliases.get(base)

        if (alias) {
            alias.aliases.concat(aliases)
        }
        else {
            this.base = base
            this.aliases = aliases

            Alias.aliases.set(base, this)

            alias = this
        }

        for (const al of aliases) {
            Alias.aliases.set(al, alias)
        }

        return alias
    }

    get aliases() {
        return this.aliases
    }

    get base() {
        return this.base
    }

    hasAlias(string) {
        return this.aliases.includes(string) || this.base == string
    }

    static get(string) {
        return Alias.aliases.get(string) || false
    }
}

module.exports = Alias
