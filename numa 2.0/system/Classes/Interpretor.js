const Alias = require("./Alias")
const Command = require("./Command")
const Message = require("./Message")
/*
prefix command ...arguments ...|subcommand ...argument
hey, numa help.getAlias help.getAlias |print arguments[0]
.numa getAlias alias |> arguments[0]
*/



//.numa [getAlias, [alias]] [print, "arguments[0]"] [print, "'Hi'"]

/*
Interpreted Command From Message
 { 
     prefix: ".numa";
     command: Command help.getAlias;
     arguments: [alias];
     subcommands: [
         {command: Command _.print, arguments: "arguments[0]"},
         {command: Command _.print, arguments: "'Hi'"}
     ];

    Function execute
 }
*/ 
class Interpretor {
    #message
    constructor(message){
        this.message = message
    }

    set message(m){
        this.#message = m
        this.result = Interpretor.interpret(m)
    }

    get message(){
        return this.#message
    }

    static interpret(m, interpreted = {}, type = 0, excess = null){
        const interpret_r = Interpretor.interpret
        if(!m){
            return undefined
        }
            
        else if(m.length == 0)
            type += .5
        
        if(!interpreted.execute){
            interpreted.execute = function(m, check){
                let args = interpreted.arguments || []
                let r = (check?interpreted.command.chexecute(check, m, ...args):interpreted.command.execute(m, ...args)) || interpreted
                if(r instanceof Message){
                    r.send(m)
                    r = interpreted
                }
                if(interpreted.subcommands){
                    for(let subc of interpreted.subcommands){
                        args = subc.arguments || []
                        let ran = check?subc.command.chexecute(check, m, r, ...args):subc.command.execute(m, r, ...args)
                        if(ran instanceof Message)
                            ran.send(m)
                    }
                }
                
            }
        }
        
        switch(type){
            case 0: //init
                m = m.trim()
                if(m.slice(-1) == "|")
                    m = m.slice(0, -1)
                return interpret_r(m.split(" "), interpreted, type+=1, "")
            case 1: //prefix
                let approxPrefix = excess + m.shift()
                if(Alias.get(approxPrefix)){
                    interpreted.prefix = approxPrefix
                    return interpret_r(m, interpreted, type+=1)
                }
                else
                    return interpret_r(m, interpreted, type, approxPrefix + " ")
            case 1.5:
                return false
            case 2: //command
                var commandName = m.shift()
                var _cmd = Command.get(commandName)
                if(_cmd){
                    interpreted.command = _cmd
                    return interpret_r(m, interpreted, type+=1)
                }
                else
                    console.log("Not a valid command name")
                    return null, 0
            case 3: //main command arguments
                var argument = m.shift()
                if(argument.charAt(0) == "|"){
                    interpreted.arguments = excess || []
                    interpreted.subcommands = []
                    m.unshift(argument.slice(1))
                    return interpret_r(m, interpreted, type+=1, 0)
                }
                else {
                    excess && excess.push(argument)
                    return interpret_r(m, interpreted, 3, excess || [argument])
                }
            case 3.5:
                interpreted.arguments = excess || []
                return interpreted
            case 4: //sub command
                var commandName = m.shift()
                var _cmd = Command.get(commandName)

                if(_cmd && _cmd.base.name == "_"){
                    interpreted.subcommands.push({command: _cmd, arguments: []})
                    return interpret_r(m, interpreted, 5, excess)
                }
                else
                    return interpreted
            case 5: //sub command args
                var argument = m.shift()
                if(argument.charAt(0) == "|"){
                    m.unshift(argument.slice(1))
                    return interpret_r(m, interpreted, 4, excess+=1)
                }
                else {
                    interpreted.subcommands[excess].arguments.push(argument)
                    return interpret_r(m, interpreted, 5, excess)
                }
            default:
                return interpreted
    
        }
        
    }
}

module.exports = Interpretor