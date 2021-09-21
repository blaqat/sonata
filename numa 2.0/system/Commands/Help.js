const Command = require("../Classes/Command.js")
const Message = require("../Classes/Message")

const Help = Command.newBase("help")

//Help.getAlias
Help.new("getAlias", function(message, commandName){
    let command = Command.get(commandName)
    if(command){
        let aliases = `Aliases For ${command.name}:\n` + command.aliases.join("\n")
        new Message({description: aliases}, false).send(message)
    }
},["alias", "showAlias", "alts"], "Shows the alternate names for a command", {args_len: 1})

module.exports = Help