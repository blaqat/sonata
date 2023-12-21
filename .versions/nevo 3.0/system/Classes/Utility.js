const resolver = require("shortened-url-resolver")
const axios = require("axios")


class Utility {
    #getShortened = (url, b) => {
        url = url.replace("snip.ml", "api.snip.ml")
        return resolver(url, (e, f) => b(f))
    }
    #getPasetelink = async (url) => {
        let data = await this.#httpget(url);
        let title;
        let body = `<pre id="body-display" class="body-display" style="white-space: pre-line">`;

        title = data.slice(data.indexOf('id="title-display">') + 19, data.indexOf("</h2>"))
        body = data.substring(data.indexOf(body) + body.length)
        body = body.slice(0, body.indexOf(`" target="blank"`))
        body = body.slice(body.indexOf("https"))

        return [title, body]
    }
    #httpget = async (url) => {
        let a = await axios.get(url);
        return a.data
    }
    getBaseLink(url, callback) {
        if (url.includes("pastelink.net"))
            return this.#getPasetelink(url).then(a => callback(a[1]))
        else
            return this.#getShortened(url, callback)
    }
    round = (number, dec) => {
        let d = 10 ** dec
        return Math.floor(number * d + .5) / d;
    }
    emptyString = "\u200B";

}


module.exports = Utility