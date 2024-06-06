module.exports = {
    "prefix": [".bb","beepbot"],
    "token": "NzQ2Nzk5Mzk4OTk0MDUxMTYy.X0FlIw.i9nRtQKmxfXIROFxxLQMOfvF_R8",
    "ids": new Map([
            [";>", {alias:"store", execute:(message, command, args) => console.log(args)}],
            ["|>", {alias:"print", execute:(message, command, args) => console.log(args)}],
            [":>", {alias:"execute", execute:(message, command, args) => {
                try {
                    console.log(args)
                    message.channel.send(new Function(["message", "command", "arg"], args)(message, command, args))
                }
                catch (err) {
                    message.channel.send("ERROR:\n`" + err + "`")
                }
                
            }}]
    ])
        
}