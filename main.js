/*
                                       ,---.      ,--.   
,--,--, ,--.,--.,--,--,--. ,--,--.    '.-.  \    /    \  
|      \|  ||  ||        |' ,-.  |     .-' .'   |  ()  | 
|  ||  |'  ''  '|  |  |  |\ '-'  |    /   '-..--.\    /  
`--''--' `----' `--`--`--' `--`--'    '-----''--' `--'  

                        ᵇʸ ᴬⁱᵈᵉⁿ ᴳʳᵉᵉⁿ
*/

const test_mode = false
var set_up = false

//requires
const Discord = require('discord.js')
const numa = require("./system/system")

//declarations
const client = new Discord.Client()
const {Alias, Color, Command, Interpretor, Message, Utility, Song} = numa.Classes

//main
client.once('ready', () => console.log("I'm ready baby~~"))

client.login(numa.config.token)

client.on("message", async message => {
    if(message.author.bot || test_mode && message.channel.id != "743280190452400159")
        return false

    if(!set_up){
        let m = await message.guild.members.fetch(client.user.id)
        m.setNickname((test_mode?"[TEST_MODE] ":"")+"BeepBot 3.0")
        set_up = true
    }
        
    let message_interpreter = new numa.Classes.Interpretor(message.content)
    let result = message_interpreter.result

    if(result)
        result.execute(message, {args_len: result.arguments.length})
})
