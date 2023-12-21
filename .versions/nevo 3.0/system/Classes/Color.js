const Alias = require("./Alias")
const pad = strnum => strnum.length < 2 && "0" + strnum || strnum
const COLOR_TYPES = {
    //https://stackoverflow.com/questions/17242144/javascript-convert-hsb-hsv-color-to-rgb-accurately
    hsv: (h, s, v) => {
        s /= 100
        v /= 100
        let hsv2rgb = (n, k = (n + h / 60) % 6) => Math.round((v - v * s * Math.max(Math.min(k, 4 - k, 1), 0)) * 255);

        return COLOR_TYPES.rgb(hsv2rgb(5), hsv2rgb(3), hsv2rgb(1))
    },

    rgb: (r, g, b) => {
        return COLOR_TYPES.hex(pad(r.toString(16)) + pad(g.toString(16)) + pad(b.toString(16)))
    },

    hex: (string) => {
        return ((string.charAt(0) != "#" ? "#" : "") + string).toUpperCase()
    }
}
const newCI = (name, hex, link) => {
    link = link.split("/")
    link[2] = "i." + link[2]
    link[link.length - 1] += ".jpg"
    link = link.join("/")

    Color.new(name, "hex", hex);
    new Alias(link, name)
}

class Color {
    static colors = new Map();
    constructor(color_type, ...ct_args) {
        let color = COLOR_TYPES[color_type](...ct_args)
        this.color = color
        this.name = "Color_" + color.slice(1)
    }

    static new(name, ...c) {
        let color = new Color(...c)
        color.name = name
        Color.colors.set(name, color)
    }

    static get(name) {
        return Color.colors.get(name)
    }

    static fromHSV = (h, s, v) => new Color("hsv", h, s, v)
    static fromRGB = (r, g, b) => new Color("rgb", r, g, b)
    static fromHex = (string) => new Color("hex", string)

    toString() {
        return this.color_hex;
    }
}

newCI("default", "A806FA", "https://imgur.com/TZ0ETeG")
newCI("pink", "FF00C5", "https://imgur.com/8jfGTWR")
newCI("purple", "7800FF", "https://imgur.com/ir4Ped9")
newCI("blue", "0150FF", "https://imgur.com/MFDFANi")
newCI("light blue", "00A5FF", "https://imgur.com/BPuAZKT")
newCI("cyan", "01E0FF", "https://imgur.com/jGf9uC2")
newCI("teal", "01FFD2", "https://imgur.com/oXKfMxm")
newCI("turquoise", "00FE87", "https://imgur.com/YIANZkE")
newCI("green", "65FF00", "https://imgur.com/2DbhABQ")
newCI("violet", "D100FF", "https://imgur.com/NQumUJt")
newCI("red", "FF0046", "https://imgur.com/EfNG6Fy")
newCI("orange", "FF5301", "https://imgur.com/gYypY0U")
newCI("gold", "FF9F01", "https://imgur.com/Ayv7buf")
newCI("yellow", "FFD400", "https://imgur.com/GVMwcBq")
newCI("lime", "CBFF00", "https://imgur.com/uIKlQeX")
newCI("light grey", "C4C4C4", "https://imgur.com/SR4nh6P")
newCI("dark grey", "494949", "https://imgur.com/nrFdoAi")
newCI("Modbox", "51FB4A", "https://imgur.com/hPTFoAP")
newCI("Sandbox 3.0", "FC8994", "https://imgur.com/9sk4bFW")
newCI("Sandbox", "5BE0FE", "https://imgur.com/1UEc0im")
newCI("Beepbox", "7747FD", "https://imgur.com/nrFdoAi")
newCI("Blubox", "0247C1", "https://imgur.com/mczXPSN")
newCI("Synthbox", "143CEE", "https://imgur.com/Pkalrsm")
newCI("Jummbox", "BE70F3", "https://imgur.com/vUK45tL")
newCI("Cardboardbox", "693C1E", "https://imgur.com/Lz2HySy")


module.exports = Color