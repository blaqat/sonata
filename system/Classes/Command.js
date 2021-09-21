const Alias = require("./Alias")
const Message = require("../Classes/Message")
const en = Object.entries

class Command {
    static commands = new Map();
    static currentSet = []
    #alias
    #exec
    #desc
    name

    constructor(name = "Command", execute = (...args) => args, aliases = [], description = "Default Description", meta = {}){
        if(typeof(aliases) == "string")
            aliases = [aliases]

        for( const [index, key] of en(meta) ){
            if(!Array.isArray(key))
                meta[index] = [key]
        }
        
        this.#alias = new Alias(name, ...aliases)
        this.name = this.#alias.base
        this.#exec = execute
        this.#desc = description
        this._meta = meta

        Command.currentSet.push(this)
    }

    get name(){
        return this.#alias.base
    }

    get aliases(){
        return this.#alias.aliases
    }

    get execute(){
        return this.#exec
    }

    set execute(func){
        this.#exec = func
    }

    get description(){
        return this.#desc
    }

    addMeta = function(key, value){
        if(!this._meta[key])
            this._meta[key] = []

        this._meta[key] = value
    }

    checkCommand(m = this._meta){
        let tm = arguments[1] || this._meta

        for(const [i, tmv] of en(tm)){
            const v = m[i]
            const t = typeof(v), tt = typeof(tmv)
            if(!(tmv && ( ( t != tt && tmv.includes(v) ) || (Array.isArray(v) && (i.charAt(0) == "_" && !tmv.some(i => v.includes(i)) || i.charAt(0) != "_" && tmv.some(i => v.includes(i)))) || ( tmv == v ))))
                return  `${i} was "${v}" instead of "${tmv}"`
        }

        return true
    }

    chexecute(meta, ...args){
        var check = this.checkCommand(meta)
        if(check===true)
            return this.execute(...args)
        else{
            console.log("Not executed because " + check)
            return Message.fromType("Error", "Argument Mismatch", check) 
        }
    }

    static newBase(name){
        let newBase = {name:name}
        newBase.set = (k, v) => newBase[k] = v
        newBase.get = k => {
            let key = Alias.get(k)
            return key && newBase[key.base] || newBase[k]
        }

        newBase.set("push", function(){
            for(const command of Command.currentSet){
                newBase.set(new Alias(command.name, name + "." + command.name).base, command)
            }

            Command.currentSet.length = 0           
        })

        newBase.set("getCommands", function(){
            let cmds = {}

            for (const key in newBase) {
                let value = newBase[key]

                if(value instanceof Command)
                    cmds[key] = value
            }

            return cmds
        })

        newBase.set("new", function(){
            let cmd = new Command(...arguments)
            newBase.push()
            cmd.base = this
            return cmd
        })

        Command.commands.set(name, newBase)

        return newBase
    }

    static pushToBase(name){
        let base = Command.commands.get(name)

        if(!base)
            base = Command.createBase(name)

        base.push()
    }

    static get(name){
        let possibleName = Alias.get(name)
        name = possibleName && possibleName.base || name

        for(const [key, value] of Command.commands){
            let got = value[name]
            if(got)
                return got
        }

        return false
    }
}

module.exports = Command