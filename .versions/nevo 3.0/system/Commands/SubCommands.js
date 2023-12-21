const Command = require("../Classes/Command.js")
const Message = require("../Classes/Message")

const Sub = Command.newBase("_")

Sub.new("printArguments", function (message, command) {
    new Message({ description: command.arguments.join(", ") }, true).send(message)
}, [">arglen", ">al"])

Sub.new("printArgLen", function (message, command) {
    new Message({ description: "Argument Count: " + command.arguments.length }, true).send(message)
})

Sub.new("errorAliases", function (message, commandData) {
    var commandUsed = commandData.command
    Message
        .fromType("Error", "Test Error", "Command Aliases: " + commandUsed.aliases.join("\n"))
        .send(message, null, true)
})

module.exports = Sub
