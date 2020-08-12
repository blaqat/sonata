/* eslint-disable no-undef */
const version = "2.3.4"
const updates = [
	"Added searchBeep command",
	"Added playRandomBeep command",
	"Added searchBeepByAuthor command",
	"Fixed results for searchBeep functions",
	"Made it so avatar argument for changePersona can be shorthand"
]

process.on('unhandledRejection', error => console.error('Uncaught Promise Rejection', error));
var print = console.log;
let testMode = false;

//requires
const Discord = require('discord.js');
const client = new Discord.Client();
const {GoogleSpreadsheet} = require('google-spreadsheet');
const reSheet = new GoogleSpreadsheet('1giT3jyAr5cHLE-9SjwPavdOG8TUpXgqx4ngwHNuJHJk');
const originalSheet = new GoogleSpreadsheet('1Qd1fW3_S299z5WXrS1RldP4OggV4fvLBteazr_Ru0vM');
const config = require('./config.json');
const soundcloudl = require('soundcloud-downloader')
const fs = require('fs');
const ytdl = require('ytdl-core');
const sqlite = require('sqlite3').verbose();
var request = require("request");
const jb = require("./beepbox.js");
const beepbox = jb.beepbox
const exprt = new beepbox.ExportPrompt(jb.doc, jb.editor)
reSheet.useApiKey(config.sheets)
originalSheet.useApiKey(config.sheets)
var storage;
//storage.on('error', err => console.log('Connection Error', err));

//test stuff
if(testMode){
	const beepTypes = [["Original", "Remix", "Collab", "Beep Remake", "Transcription"], ["Jummbox", "ModBox", "Vanilla", "Unofficial"]]
	const getBeeps = async function(type, weird, auth){
		let doc;
		let beeps = [], random;
		let [search, amount] = (typeof(weird) == 'string')?[weird.toLowerCase(), false]:[false, weird]
		auth = auth?auth.toLowerCase():""
		if(amount && amount < 0){
			random = true
			amount = Math.abs(amount)
		}

		if(type=="")
			type = false
		if(weird=="")
			weird = false
		if(auth == "")
			auth = false	
	
		if(beepTypes[0].includes(type))
			doc = reSheet
		else if(beepTypes[1].includes(type))
			doc = originalSheet
		else {
			doc = reSheet
			type = "All Beeps"
		}
	
		await doc.loadInfo()
	
		const sheets = doc.sheetsByIndex;
		let sheet;
	
		for(let i = 0; i < sheets.length; i++){
			let sht = sheets[i]
			if(sht.title == type){
				sheet = sht
				break;
			}
		}
	
		await sheet.loadCells(['B2:C', 'F:F'])	
	
		let availableRows = sheet.cellStats.nonEmpty/3
		let sheetLength = 0
	
		for(let r = 1; r < sheet.rowCount; r++){
			let got = sheet.getCell(r, 1)
			if(got && got.value != "")
				sheetLength = r;
			else
				break;
				//print(r)
		}

		//print(auth, search, amount, random, type)
		let tries = 0
		do {
			tries++
			//print(sheetLength, beeps.length < (amount || beeps.length+1), auth&&!(auth&&amount), (!(auth&&amount)?(amount-beeps.length):sheetLength))
			for(let r = 1; beeps.length < (amount || beeps.length+1) && r <= (amount&&!(auth&&amount)?amount-beeps.length:sheetLength); r++){
				if(random)
					random = Math.floor(Math.random()*(availableRows-1+1)+1)
				let i = random || r

				let got = sheet.getCell(i, 1).value
				if(got){
					let beepName = "" + (sheet.getCell(i, 5).value || "Unnamed")
					let aut = sheet.getCell(i, 2).value
					//print(i)
					//print(beepName, !search, beepName.toLowerCase().includes(search), (auth && aut && aut.toLowerCase().includes(auth)), !search || beepName.toLowerCase().includes(search) || (auth && aut && aut.toLowerCase().includes(auth)))
					//print(!search, beepName)
					if((!search || beepName.toLowerCase().includes(search)) && (!auth || aut && aut.toLowerCase().includes(auth))){
						beeps.push([beepName, got, aut]);
					}
					else {
						//print(beepName.toLowerCase(), search,beepName.toLowerCase().includes(search) )
					}
				}
			}
		}
		while(beeps.length < (random&&amount || beeps.length) && tries < 5)

		return beeps//.slice(0, amount || beeps.length-1);
	};
	(async () => { print(await getBeeps("Vanilla", "", "za")) })()
	
//var test = `7n94sbkal01e0vt44m0a7g0wjpi0r3o3402332230000T1v0u01q3d0f8y1z0C0c2AbF6B2V3Q0572P9995E0001T1v5u01q1d1fay1z7C0c0A6F2B7V1Q2ee7Pff85E0161T1v2u01q0d1f8y1z6C0c0A1F3B2V1Q241aPf459E0k26T0v0u00q0d0fay0z1C0w2c0h0T1v0u01q1d1f9y4z1C0c2A0F0B9V8Q0000Pf860E0661T1v0u01q1d1fay3z1C0c0A2F0BaV1Q0159Pf479E0006T0v0u00q0d0fay0z1C0w4c2h0T1v0u01q1d1f9y4z1C0c2A0F0B9V8Q0000Pf860E0661T1v3u01q3d0f8y1z0C0c2AbF6B2V3Q0572P9995E0001T4v2uf0q1z6666ji8k8k3jSBKSJJAArriiiiii07JCABrzrrrrrrr00YrkqHrsrrrrjr005zrAqzrjzrrqr1jRjrqGGrrzsrsA099ijrABJJJIAzrrtirqrqjqixzsrAjrqjiqaqqysttAJqjikikrizrHtBJJAzArzrIsRCITKSS099ijrAJS____Qg99habbCAYrDzh00T4v0uf0q1z6666ji8k8k3jSBKSJJAArriiiiii07JCABrzrrrrrrr00YrkqHrsrrrrjr005zrAqzrjzrrqr1jRjrqGGrrzsrsA099ijrABJJJIAzrrtirqrqjqixzsrAjrqjiqaqqysttAJqjikikrizrHtBJJAzArzrIsRCITKSS099ijrAJS____Qg99habbCAYrDzh00T2v1u02q0d1fay0z1C2w1T4v0uf0q1z6666ji8k8k3jSBKSJJAArriiiiii07JCABrzrrrrrrr00YrkqHrsrrrrjr005zrAqzrjzrrqr1jRjrqGGrrzsrsA099ijrABJJJIAzrrtirqrqjqixzsrAjrqjiqaqqysttAJqjikikrizrHtBJJAzArzrIsRCITKSS099ijrAJS____Qg99habbCAYrDzh00b04gO1aoW4G8xr3Js-3oODiJbkHv00y2c8y5288My8k0000000y2c8y504gix4cMh1a4gO7gt9Qac4gix4cM0y288xB288wy6g8wy28pgy288xB000h00cw01400O000E00000h00cw0y288xA288wy608wy28p0y288xA00000000h144gO00000004gh14cw002801A008w06g005000000000004gM18kNQ90tiPcqVY8ODiJHUHDg0x248gx248gx288gx248gx248gy448gx24wgx248hx24wgx648gx24g0y288wy248gx2cx248gxgy288ww04000000g0000010000004000000p2pBBWoJ1d1OhFE-2ddvNAV5c3wddBY4uhKsw9Hc3qRbsTueQ4qadj8U4zG8V15uTnjyl5VuMn-e8W2ewzwKVX0XDkJ0R3xbghZ8At97lTtJkxAYwLpE-apH-HHIVKnINtwcQ7tAv4OhYjenCjdtR1pgtCO-p8YCtEbA2mqPI7sLkJTKT-UhPj97Ua4s2hRAsxUnnjynt38Wp8Wp8XM-H2W0TGZj5Fq1KErOBmCifF4zG8WKZIGAcCn-m4t16CLUOICgGOZ17ghQ4tDwyCI-UKW_yt17ghQ4tn277YnpGmwsjjuzYsUzY828Wp8W0L40aEeweKIyJcAuQhS4tTifg7tnXuTNtdSv6h8icz8idddBZochVdm34tfmZXi0zOtHi0zNj20zXCqhVeXKAutDAvlY82f9JPif9OxV6jnpJv4omrFZ1xIT7UiYM3WhI7dT8BCO-pJSq-3c5lCLPC2gocKPzM001jpuGCzO4zOp324zFjnUfgt78YDqQszNj20zWOog4ujrCAujRnuOs7OifawpaShAauTx0hVeVF0hVC3Avmb1OfpMuCG--hLAquRwV7jjjBoehQN3jPY82eCCD4s8OeC8qunC4tddeRCpepjrQ324zFFFOYMzFSg00BXd7zSnQOnMa9vj9vj97bWXbWpbXpbW9bWp8VviAnQOnQQnQOnQOhO-CieCrp8WFeDBZcBZ4BZcBZcBZcAo000BWqfR97hwehBp689H-WWsiFLb-2-nVf4pmhCs0MdlSjOdwzSdD9S3CVvCV6rAplKhCV60p6PA0002nKq-l2FNhJlmllp4RywgbAzGGIGGO9H8CFvpKrllBlmjloztrllARmllpllbWKPpCIyGOFHaOZCGOqHaGDjmgGGGnXlpNcRAlmllpllNdlARmllsll0001sTjUZGi0amPqG-JSppdndSvBSsS0004LjhYF8Wc1OcL8N1dvTnjyldVvMnO_9UzaOcPw61GKOuhI4uNIVeMsTbYT8PszaJOcT8M38Ssw000jnj5E9Eeidd7MhFH-cD8FM7gCRY4zOdPA1dpwrmFrD6Weef8-jB4ughQ4tD4Y0sjG6VNKzx8YzD7IQvBcR_q6npNYRSoKw6q3GOfpAzUCsLcCqXOwtcISLQ6hVcXgn84IRDoeVuFrLtN_qpUhMYzVtVm4uj97j97k3Nvs0rNuWzm_L25WpUiEYzCLUihQ4vx60VcxBqcIzO2ewzIYLYLUKXx3hAAughQ4tn277YnpGiq30YMCYXVYMnXp7ghV6pAO6lEPOfMwczFAzE2Y00GwW0YKJcV54v54tx7tSxU0tlvJ-5-ojt_TAi4z8O6hFjpvm34ujlwN7jWTuQw8YDqQw8YkUg4uIC417AO63AtfvQ7i0zOtHi0zPeqhXSuhVdumhQUA8YLc8YCXe8WuNGxUnjnEd5555555dBIk9K_o0000FEN0OQQt9vAAt517AAuihPFYAzkQ29SySxjgapLN17NuihVeinF5pjaMCzokOFmWaWa_c6nRpvAAt517AQpei0005d614t17ghQ4t16CLoO2ewzQ4t17ghQkk4uhA4uhO2dd7hA4ugt_Sdz8Ocyz8Ocz8Qp6hAp2pi1q1kRV6gbgbA0002CZ7Z00000`
//exprt.exportToWav(test, "mb_3_3")
//var test = "j1N07Unnamednk4s0k3l19e07t3nm6a7g1sj1fi2r2o344020242333200433200000T1v08u01q0L00d0fay0z1C0c0A5F4B0V1Q000dPc696E0018T7v0pu07q0L00d1f8y1z2C1w2c0h0Mnnkkddaa774400000000444477ddggkkqqttAADDGGJJMMMMMMMMJJJJGGAAwwttT7v08u07q2L00d0f7y0zhC1w2c0h0M08cgkoswwAEEEIIIMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMIIIIEEEAwwsokgc80T5v0nu05q1L00d5fay0z7C1c0h0HU7000U0006000ET7v0su07q0L00d0fay0z1C2w2c2h0M0479bbdddffffhhhhhjjjjjjllllllllMIFDBBzzzxxxxvvvvvttttttrrrrrrrrT5v0eu05q1L00d5f0y0z7C1c0h0HU7000U0006000ET7v0pu07q0L00d0fay0z0C2w2c2h6MoxEJLJHGFFHIJIHGGGHIJIGFFGIKKICtkb5224677654456776444567753237foT5v0pu05q1L00d2fay0z0C0c2h0HM0450530020000T0v0ru00q0L06d0fay0z1C0w2c0h6T1v0qu01q0L00d1f8y2z1C0c0AcF0B0VaQ1950Pf000E1112T1v0pu84q1L00d4f9y3z1C0c0AcF8B5V1Q0259P8998E0000T0v0hu00q2L00d7fay0zdC0w9c1h6T7v0fu07q2L00d1fay2z1C0w2c2h6MMMMMIIIIIEEEEEEAccccccccccccccccccccccccccccccccccc8888884444400T7v0fu07q2L00d1fay2z1C0w2c2h6MMMMMIIIIIEEEEEEAccccccccccccccccccccccccccccccccccc8888884444400T7v06u07q3L00d1f7y0z1C1w2c2h6MMMMMIIIIIEEEEEEAccccccccccccccccccccccccccccccccccc8888884444400T0v0pu00q0L00d1f0y0z1C0w0c0h0T0v0su00q0L00d0f0y0z0C0w0c0h0T0v0nu00q0L00d0fay0z1C0w0c0h0T0v0su00q3L00d0fay0z1C0w5c2h1T7v0nu07q3L00d1fay0z1C0w2c2h6M0479bbdddffffhhhhhjjjjjjllllllllMIFDBBzzzxxxxvvvvvttttttrrrrrrrrT1v0pue3q3L00d6f8y5z1C0c0AbF8B5VaQ024bPa871E0002T5v08u05q2L0Qd1fay0zjC0c0h3HM0450030020000T7v0ku07q1L4d0fay0z1C0w2c2h6M000111222333444555666777888999aaabbbMMMLLLKKKJJJIIIHHHGGGFFFEEDDT0v0pu22q1L00d5f6y1z8C0w4c0h1T7v0ku07q1L00d1f9y4z5C2w2c2h0MoxEJLJHGFFHIJIHGGGHIJIGFFGIKKICtkb5224677654456776444567753237foT7v0ou07q2L00d0fay3z1C0w2c4h0MMMLKJJIHGGFEDDCBAAzyxxwvuutsrrqpoonmllkjiihgffedccba998766543321T7v0bu07q0L00d1f9y2zjC1w2c4h0MMMLKJJIHGGFEDDCBAAzyxxwvuutsrrqpoonmllkjiihgffedccba998766543321T5v05u05q1L0Ed0f7y1z2C0c0h0HU0000000000000T5v0hu05q1L0Ed0f7y1z2C0c0h0HU0000000000000T5v0puc9q1L00d2f5y1z1C0c0h0HXQRRJJHJAAArq8T1v08uaaq1L00d4f6y6zgC0c0A2F0BcVeQ2d00Pc550E0111T1v0mu01q1L00d3fay5z1C0c2A0F0B9V8Q2010Pf6c0E0211T6v0ju06q0L00d3fay0zfC0c4WzfT5v0hu05q1Lmd0f7y1z2C0c0h0HU0000000000000T5v05u05q1Lqd0f7y1z2C0c0h0HU0000000000000T5v01u05q1Lqd0f7y1z2C0c0h0HU0000000000000T0v0qu00q0L00d0fay0z1C0w2c0h0T5v0pu28q1L00d5f9y1z7C1c0h1H_--D---ZBLRS-ST0v09u00q0L00d4f7y4zhC0w2c4h0T1v07ue0q3L00d5fay3z8C0c0A1F4B3VbQ217cPe433E0a81T1v0bu01q1L00d1f2y0z1C3c0A1F0B0V1Q200ePb700E0000T0v0ku00q0L00d0fay0z1C2w1c0h6T3v05uaeq1L00d2f8y2z9C0Sp99f9c9Vppbaa9gT5v0vu05q1L00d3f7y1z1C0c2h0HUUUUUUUUUUUUUUT5v0pud1q1L00d2f8y2zaC0c0h0HXzzrrrqiii9998T1v06u01q0L00d3fay0z1C0c2A0F0B4V8Q2010Pf780E0211T6v0pu06q1L0ud3f8y4z1C0c4W4hT6v0iu06q1L0ud3f7y3z1C0c4W4hT7v0su1dq0L00d0fay0z1C2w2c0h0M000111222333444555666777888999aaabbbMMMLLLKKKJJJIIIHHHGGGFFFEEDDT7v0pu1dq0L00d0fay0z1C2w2c0h0M000111222333444555666777888999aaabbbMMMLLLKKKJJJIIIHHHGGGFFFEEDDT5v0ju05q0L00d0fay0z0C0c2h0HUny00000000000T1v0mu01q0L00d1fay0z6C0c0A0F0B0V1Q002dPf220E076bT1v0pu01q0L00d4f7y1z1C0c1AcFhB2V2Q2ae1Pa514E0001T1v0pu18q1L00d2fay0z1C0c0A0F0B0V1Q0000Pf600E0711T0v0mu00q0L00d0fay0z1C0wgc0h0T5v0pu85q1L00d2f6y2z1C0c0h0HK-LBJrttAAAyqhT1v0pu62q1L00d5fay4z7C1c0A0F0B0V1Q00adPfe39E088bT1v0vu01q0L00d1f7y3z0C3c0A5FdBfV1Q2101PffffE1221T5v0pua2q3L00d7f7y6z1C0c4h0HKTTz99irrqih90T7v0pu1aq0L00d1f8y0z1C2w2c0h0M00001111222233334444555566667777MMMMLLLLKKKKJJJJIIIIHHHHGGGGFFFFT3v0qu03q1L00d5f5y2z6C1SqiirrqiikE00000T4v0ru04q1L00z6666ji8k8k11SBKSJJAArriiiiii07JCABrzrrrrrrr00YrkqHrsrrrrjr005zrAqzrjzrrqr1jRjrqGGrrzsrsA099ijrABJJJIAzrrtirqrqjqixzsrAjrqjiqaqqysttAJqjikikrizrHtBJJAzArzrIsRCITKSSsA9jjHAJQDYDL__99habbCAYrDzh00T2v06u02q1L00d1fay0z0C2w1T4v0uu04q1L00z66611i1k8k3jSBKSJJAArriiiiii07JCABrzrrrrrrr00YrkqHrsrrrrjr005zrAqzrjzrrrr1jRjrqGGrrzsrsA099ijrABJJJIAzrrtirqrqjqixzsrAjrqjiqaqqysttAJqjikikrizrHtBJJAzArzrIsRCITKSS099ijrAJS____Qg99habbCAYrDzh00T2v0Nu15q0L00d1f8y0z1C2w0T2v0Nu15q0L00d1f8y0z1C2w0T3v0pu03q0L00d0fay0z1C0SkyAiqjiAccJCDSTT3v0pu03q0L00d0fay0z1C0SkyAiqjiAccJCDSTT3v0puf5q1L00d5f7y1z6C1S1jsSIzsSrIAASJJT4v0mu04q1L00z6666ji8k113jSBKSJJAArsiiiiii07JCABrzrrrrrrr00YrkqHrsrrrrjr005zrAqzrjzrrqr1jRjrqGGrrzsrsA099ijrABJJJIAzrrtirqrqjqixzsrAjrqjiqaqqysttAJqjikikrizrHtBJ-AzArzrIsRCITKS_099ijrAJS____Qg99habbCAYrDzh00T3v0puf8q1L00d5f8y3ziC0S-IqiiiiiiiiiiiiT3v0puf8q1L00d5f8y3ziC0S-Iqiiiiiiiiiiiib0000000000U44310ggcgb63hMIod72NwQsb63O14Awa5ihcKqfD3800000ggc81gwQg0od72NwQsb63hMIod764GoiajG5800000000ezi00000110M044406zos0q3y00kc701gMw000018Emc6zxVs00g8g000kaC21Ays8Di9Uyv01gMs0532000000000000000000000ggc01110000000ggc8531N0Emc6yhMYwa5z1EAsf80014Aj0001gGmbC39EWrfE3M00000koc85jxN0Emc6yhMYwa5z1EAsf806g1C0q00044321gMsg0kw0000000000000wg84210wwEoe62xwUoa63xwEog96000000001gEka0000000000842b0xwUoa642gEoe62xx0Aqd6zhEQqd600000000000000000000001844310gEc8742Nwsgb61N0Io743hM0000000000000000004OxkIjgBiU0gb61N0Io742Nwsgb6639ESae7jM00000000if800000000000000ww8c220wMUwia3y18Ie84ywUwic6zxV0qe7AhEUug9B2Fo00000000iby18Ee84yMUwia3y18IQseDzW12y00000000031A000000000000044321gMsm110Mwkc75w00Mqe0000000000000000000000000000000044321gMsmf84igYwh9BP1AQre7h1g00000000lb00000000000060wwo8221xMEAkb2yhgIa952MEAod042h4CkaByVwOqdw00000000000002hgIa952MEAkb2yhgIgseDzW12y000000001xMY0001gMki531hM0u0801U0eqdyxpESa5AOxwOja5iNs000000000000000001gMki531jw0Sa5CzoEmqdyxpESa5y3FU-wgEAokc54xgMks00000000000000000wo00000000041w000854yxokc740000000000000000000000000000000g60000000000001qKnI6bJUZ00000000000000000000000000000ww000321gMsg95000Iod000000000000Ae7A2800000000000000c8531N0AkwgEAq12yiblOZwNtL7E00000000000000000000000000wo00000000021w000854ywwkc74000000000000c00000000000000000086000000000000000000000000000000000160000000000000000000064000000001wE0000000UA7a5ihcKqfD39QSuc0000000000g000000000000000000ggwia5z1E0000000000090000000000000wwow221y0wkc721gMs8531Mwkia6zxV0qe7A1EUur9B2Fo00000000001gMs8531Mwkc721gMsyibC39EUt0000000001oM000000000000044110gg44531N0kc74xgMsg531NhgGb6639EW0003M00008AqhaCjG580c741gMsi531N0kc744ihssvg8lg000000000re0000ia5z1EUug0wwoga63y088642xwUw009Aig0000001s00002xkWu00000Mpd6P20Qv0wwoga63y088642xwUx8Bj9R1NiG4yxoMqe7A4ic000000000000044321gMsg110Mwkc74000Mkb00000sf000000073jo0000000000000044321gMsg110Mwkc7400000000000000000000000000000000000000000000g84210wg84210"+
//	"wg84200000000000000000000000000001wwg84210wg84210wg80000000000000000000000030ggc8110MUkg941h0Ak00000000000000000000000000000000000000000000000000000000000000000000000000044320ggceb600000000000000wg84210wwEoe62xwUoa63xwEog90000000001gEka0000000000842b0xwUoa642gEoe62xx0A0000000000000000000000010g84210wg8c631xMUsc73xMUse73xMUse73xN8c631wMoc631wMw00000g84210wg00e73xMUse73xMUse74yNoImb5yNo4210wg8420000000000000000wg84210ww84210wg84210wg8421000000000000000000000000000030g84210wg84210wg84e73xMUse7000000000000000000000000Msg00000447400000111N000031gMw0000000000008w000y0000000gg0e800004474000sg5320000800000000w000c74000000000000000000210ww84210wg84210wg842200000000000000000000000000000wg84210wg84210wg8800000000000000000000000p32OIbStfx0I3wQkh32rTCKZCLAtGPyRlI8y9pER48RYhgiQV_VpHUzRmjFTM33EUyyDFf5YPIILpTU_MkzzOZCKSA8ca0212KXwoxob2bSnPNaluNZsTpzRTtAXSoWg_NnIORtTttTpuOL00-6jRTtAXSpuV54czOqKOuKXIDcfLujRTtA-8XlAuntF5rClWGEzbSnW9PivrKX8TIDRTtzLp7Lh4K7i62uO-__vjtFKpvoCzPqEigttTottTorSjPKU4uKXIuKXItXdu3F8EBXdtHPlRTtVTZt5SAnPefjzZv0ECKkO_aLpMuyMtjcfmZDbWHEgYuZCLEU87buPFZsxECi121G2h1cDlFRjoFK203H5J4SRwA0CC8p845iMwkhbSnNz322uNZ4RpzRTtAXSoWwuQDIORtntsTtXk5h2wggwo49ce3ghhLqvB0g0ip7HYqKxbNLctUelI18FRXerOg0gbStDGId6XuW7mbqdAIX8h49eYhP5nunJx8mr0wMGx4JeAanv88F8O22a5tF05Uf5IFl16MnIZ7tTtBVLhNtTpuO-axaFfo-KrINWXKOtXctg42GZCmHCXHKXf0ai0D5RtCfldSjYu4xv5TtRTtDyOlhjyXKP7HKX9-2ddx5uOZntTrJT0FnpURchzUKXINWrGOvw5lF9KrKXHKXf2y8zjNtTpzRTu4_4TusnlTntS00000000000000000002qWo-ajfwjfKcYQAZ8Z9fsjQBZgZ9fknCiffPiF1NPowWsCLCagspozbOcP8eiF1N68Ol8e34peNBV6iF1Nm8OK8Ou8OK8epR1QXOswWuBWoXYuG07FAhWV0uj9U4DAX1XbifloflqfujM9fj83SnzTg8ZRjbS3jvvj8RllnerSfefQSCnX2zuzy2teAnw58D06iAoUI-muk7jLfc-wu1w1QOL0xS1FA-AvqT0WChWWGFdChWlWBGFBpA0F6GFwqwrwrwZwKqpvFW0jbVcACsCLcdFCDAw-dVEdcMZSPV1srGeWT6QTTU6V6vb4UtOI-w283KpDU0c0tCvO1uf0g8Y10zMd8WpzWyv8qpHHv15cHTFD9GANU2CnM0YFZVAUyCnV5cCRFA6JcUZgnLEvE6AugL7AyvOEfbF7Ap0uhJ7AmCs_cj3M5aCrWpUg9HY26v0Cv06uqiuAuADAyuALG7F9Wy-FAuyiJACp7FmGnGBCtC5pKX9mOmOHlRkWFdQFLAHZ1mAlWFEiAwqkGqwVwkU5i3W2WIPLYIesujnhHSezjKsiAkrvuB6Z70800000000000000000000000qo-9k3fkoyweEP42thBshBr6kwnG7y6NAYNAX6rN6jIpn4peNBsgYPCcPCcPCcV0RR68YMYP8hdsgteZzoPeEPeEPe8OZz9XxU3Ipa16Ej3Sq1N6jT6qE5qly3vurUhBshBsNy7B68Yhyfz3OeEkjb3IN1RboN7CchXzbUzbScDG3AYhBYNBYNBV68V6pApJSNDCDoOtz9ScTCcjSc_ycDoM78i3y5pS-EO-oOKoOL2chUz4uUe9tgyqUwWsWgZNya16Ej3TW1N6jUhyawlFm8dYU3UhBshBsNy7B68YhyfB1OeEkjb3IN1bQ3O-49Ux0Dso8wjOc1OchOchg7ApdChBielAiehwFwAzPYgkjnR9A-hjaYyCsCGj7D9BYUFB-DGtCPB4MOCqWzx5jaZf8Eu44qCkMGzx5cNUysxcvjAUzV89ASJj8UR5pHDO8eAv55cVdkCf0kO-07NDGkOZ0GphGMh9cVhgjFAswFBX0j9TeptnnroCfFqpHHf55cHOapOqFcu0FBYQFCe_7j7oqpcM0cD4gcL404OVW0ClI4fxaMuMFCuH7j9Z2o-BcDB9DnHmCpum8Xie08U0zqpvEW0jbVdypOqicdGqup-gAfw1jaZfmwCouIfq7X3PQNYy7286uEOQ1R6mwjGcHycHoOA2ZgYgScDCcDoPu8PuodtVKhCYNCYNwy1HGchVxVCgyqUwWtX6NCthCthCshBX6jT3j3Qq2whGcDCecQ3ycDKcRgaQH46-YTMzaUzaXz4fachUz4v6atezhJa0FEFhEPa5688M0uvYoP-UP_6c1Y8OA33kpmgsgUz9Vz9Sc_CclSc0Uz9g8R69Zgs9uUP-oP-EMjychgdtgsPoOYz4cz4IwVuhDsNCsNwfx6rT6rAkWtcDSINZAKpfHBdXdYhlaQYnWlIJj3S1Q4te_OAqtNy6hAV0001M3Oz9g8R7amwshAE3GcZgaQH4p-gesZ0PR68YhBsNy21HGchUz4k2ZgszG54OMXcg0000000002CDyZGf8WmEMPj9W6ldf34Osfj9PZcQPj9FADFANWpFAUuChWp9Wpej9NskOptcCTj9mqFcKCj3GAOWpaWpceCieCgPl9BQOotkCnj9JQOlCGjjFAQWpdeCiKGieCgPj9nj9nj9nj9nj9nj9nj9BQO6qFdeCjjFAQWpdcQOu9QUqpHIZ3cjWptcxQOptcxQOptcxQOptcxO000000000202000000000000000000001LCLDfU4c48aGYY5MnZMhHLCLCvALi11uc7wwxnE2ExdXf4M3WfCSYKXh2dvkAv11rSqYm3Z9VD4PlQjlRTtLpT-h44QLpnwr129WXKOtXcLoyA8hVdnpfntSjC7TL9WXKOv4tGOfbKQyJPaZlkhAWtUeDRozFuO-saEGZzWVKP7HKX9TINQw9UHSpqKXKKXILpvB_229_2XKOdX9ZtToXShUfxrxQxwDILL_TQTqrCnS9EYSG4A7ntS7ntS6ZAYXK17HKX7HKX7uPnwWia9uPnGYRttTtTZt5SAnPefjzZv0ECKTPnPPZHxpwburQshgnRcf2LpO-wc8dXePQRoZuPFZE8gdlxERYjnznnx00Mi2gtxdXPnv4LyZ8XlRYjfzviRlHUCT6Cx4hbL4qy4q_2a2mBUf5IPxx1CMnILBTtLo-yqINWXKOtXctgfqjSpqKHKKrIY1wF8YndSoZtTpfN082D5PtRTtDw590jyWKP7GCX9-f2gLyXKWXKOZCKQsLbdUaXK1y5wI8YYhFFsTtSoZtTpfOhqM2LpuHKXJSXwkHIYqC8NYntSoZdRpfM2GQATlTtRTtDxh4hFUKXINWXL2vyrLebGXHKX0HOqY6ijhA4kAp1151Vdvnqg000000000000000000000000aIs_cst7142Atn0zjibVsckzFVhQVjdvmnFCnAkOf2XapvFqpzXgW0Yg8W2djcLoZGbUXDUfFwMvpVAOF6ClW2tjdv9NGoYxcLCkBj7NV-OChOidcDArNeCoY0WSOUSXoZdgZCn1oCfjufhDCYDOcgGU37I7jc-ketMDUzcGjdup0BjefrzZxHBcZ729Icyp4GpQUZfEIE7y-wRWCnW2tcvgCjUjex1Yh7AhZLktD9LzfBheCfp7jaWE6CjPx-8I7EOIoI6MaYSjV6RyuwVw-x3M0-tDpJjeDD97jH2unYSkPQtw56Z74ljaYcgFxUoQDOUegGAHmFFpApc0zw02ew0zE08XAq2jU6HFU-60gcDoN6OWTMtsz8mmmmL99YFj8YciFC7xyJhIGJL6A-0Msx2idtAco2v18e1JwoeOea4-0RidlRBAck9Y1FAF6C000000000000000000000000aKPVfI-9044MYwChWkO_sFFVnyhyy1xy1wj7MiCLzU0302FIuhWGj9ZnkFCfAldv9YK3M1NeE0-i5xkP3SLpCmChXeskO_svpLsu29jeDOhQVlRYHSLq3f4ttU19CDwdNj8ZHQE5jnOv009BuLH-geVkP7Sv8HC-ldDP7RwrD6apzXvA4txcNYyYZcv8Ve0sPJapxVOoBGpDW-5lbQPnMyCDCfypwxlTRQ39O17ghFxGaaaaa5cvpZ29msXdcJjgNPMyJ9bQ3O-4hkQYHN7cjIlb14b4FFV7Gij7RpLpumBBViu2BjpYYT7xDOri6jWj4I4kRYDM8fi55cDRZqCnXIh7R4tcTYAFHVDU8kZ9_91s0YOjX0m0rejAVuny9kQYUL9_BQZuFFVFVggYrD6TY2s03BcZ745czPjdImkNlj5cDl4RdRdRdNFKKGKFKFKFKFKKGKvvttAU1AU1w2pzUdcOY1iZHzsTeOsBjjOf0nPvacwQPnOtlnntkFHU-PsBYn9mGq-p-H7Crlc30MiCLB-01XhADTT268ozye9ozyWpvwqFaFWxE60VKvwe0ucYlno00000000000000000000000002ZDjVkawUh58gMCZVHLpHV7qIUJlr28ymqdh2dv4k4JbSsveKAnIX-a0wwAWtY0MWejlSnYszxYu8YzxYu8YDDY2AtenILze646ZzW9GP7HKX9TINR0ZFfpBGWKWVKPU5j246ZCL4qIdXc-nd9KpzO9ELpQYTrPxg7gv6qJ9PbV4QuXiZ2XK1UQ448YPlFp_XRdmAnPefjzZv0F6KnIZ7qJwWnCZ75TtIUZAf0Fw0So-EdQQYzsx1UFxUr5kMYzsepuRK37LQ5FA-xcv0peqCnOQMZip5Hj8dapJG3jrztecKzbge3AcWtcRTtzpDjyJp7jzarcRTukvlJKdCteUCSmCte_WSFFDfLQMTtfidQSSpPrKAPbOqpfw4P7QFB-huG9zUbbPIlPsX0IlM70c2Nn0s0M9FDwU1e7bSnNC2liuNZsTpzRTtAXSoWw85lXcJndTntSu0kA1ebGXcuGrIDUY92-bKXHKXbSqXhOYITwHKU68m2MzPUBaYTdSoZtTpfOx_yYTtTntSu5id9byXKP7HKX9-299w5uOZntTrJT0FnpURchzUKXINWrGOvw5lF9KrKXHKXf2y8zjNtTpzRTu4_4TusnlTntS00000000000000000000000TILMwm1RTtRTtRTtMqa8BdnttTttTrxZXWXKWXKWpKWpKWXKV7qKKWJOIRJ4RttTttTtW8DkPtRTtRTtKHkgGVKWXKWXKWXKWXKV517aXGOC5ym3wEd8annnmy4HHHHe3RwwE61SWWWZKKKIUcXRRQ5JRRRXunBRD3ja50xg8k7vv0Mh7JRRRXtttuTnnmhRYqe8UQH1GfIhM-6XGXvszxYentTTtTttTttTpHRXbULgmLo-yqINWXKOtXctgbqjSpqKHKKrIFxoIwUa2i2BRRRExaYLbHcJ4580O8tx3qgOosAf83OgsC7NI50gn5RRRYnnnmhRXeDziCACZCL5gt2YFGQDcLAjluPzVqnEntMf6wwx5cv3E6uEM90thya1eEOA3nkozN6885WwUzR29Hy3FOC5ya2wU98annnmy4HOYKIU91Wxd1cjGIpwE0a12wUa2wrPwOsuy2w0p4eg8ry6i3AxV0ui3APrrVB-UuphwwQOJXdvryaJtTrSnWaGS-pvHXfPQgTPaZzSpCo7IZyh7hdmhQjlLoWyqKKXKKXJBWoXaxUe07FAhWV0uj9U4DAX1X7ifloflqfujM9fj83SnzTg8ZPjbS3jvvj8RldnerSfefQSCnX6zuzy6CjKeFANWX1WrhWV0ui9U4DAX1X7RdY38WzIVClCVmvwJuPzUMFF9LpTYo0wgrw_u4ZCL4qLnIPVsQAVCf8CGY7ySTrMSaZBY_kQnIvndSoZtTpeZCeE10juPblPtRTtTw590jyWKP7GCX9-f2gLyXKWXKWZCKQsLbdUaXK1y5wIaY-9iLdPtCfntSjYEvULdTtRTtTxkziiUKXINWXKOvwyio1nILlTtSXtMalTudj4o-bKXcuCWIDU1lqirCXKWXKXMEy8QYntSoZtTxfNdTD5RtRTtw0000000000000000000000DzWCDHUEoicMSt-CeUwUi1FGAX4NYAQPFM0teO_r7Iw1Wp4uKUuUDK9VeMuNQzRm3RmzTAY2jQO0ZBUZQ2fsQOZwQTTQOdljlPCZzPzZdFB-NETEUxFAXzGpcuKMuCQuKg7Ayu19VeMuNZjv0OeEXepBpKlDUaZ2ONXE0uCYuKYui9U4DAX1X40000000000000000v3A3fkpO0Wzbg9R60E5WzagcdhBp1Pe8OuoOtzfVz5Jz0e8Ok2dhyvk72nKc_Cc_Gc4Uz4k3nk7cScL8N38Nb8enApTcpDco3UhCZNCV00000e0shy7x2oukQ3ycDKchk2JaN62V0VMfNz4u8OKoN3Oz4u8N7OwV7ka9BxSow0000000004WtjnPfqLao-pXAGo-uvzSHI-jXfyc11cf89AuBcLTGqulUBoEwoowo4NY4FHU-00M1Gr7AuGAOvlRapzV5jnOvbwY0sjG0fAxoRcMZHSpBFAuPD5cLT7SrT7wyQPFYAteRtvaZHSwPN7nu0ipFU3skOfqZa3kRYDM02pnHW_A3KlcNZDOaVLJjpYNZo6VNyCo-TV17ojcv8JpPIQORd37f4aOOZ0YLCdjjOLhkgGQV3c2CDAuF9cvlCZBVqmnB9UaRdDPPsu7v8hXefQ1x1LpQ-CH7KGLpHW0gwsLr2hKLpPui121uPIZlxETBavKPv-12j3wQ4kq-1PuNW9GZvdfezP2AeBZWh223H6JaZEsNU8elI189Si021wQgBaZDEUlLbK1_WBN0EzskOBbNtRtM8gc24C71E8ETxfNw80bCqIiXL4tUelI18FTNi021YqId6XuW7mbqdAIX8h49eYhP5nunJx8mRdfcvch192m1m1Gq-jU45jjOL8kQOvmCfJXX4hZh7jd_9aq-p-25vivOgn0fcA-M5w6PAVenBUyRdfebOvVtfnGququk4v6VNJ_0D00Yw003RxgcZhC83GcR0Dko2wnGcF0MR6lAffUz9Vz9ScjVz5Zz0e8Ok2dhyvkf2nKc_Cc_Gc4Uz4k3nkfcScL8N38Nb8unApTcpDco3UhCZNCV00000u0shy7x2oukQ3ycDKchk2JaN62V0XMfNz4u8OKoN3Oz4u8N7OxV7ka9BxSow000000000cYnkQZf5aV0pVe_j7sgs90QRityo-iapQUYWsB-Sfp03QO8ZtMZNfsjOtwZxF7GI7GJ7L9U4DFA1XbNXE4uUFBX1FLLFAqGyHDdX7D7WrjbZxhLhN1j9T7kOoZtwZdEZswf94Y2jOtwZxWC-1AthSsPaPsHfMk54ROIzqVFaRO0CqYQ00000000000LhWe7763l00000000000000000000001uO-21o6ZzW9GP7HKX9TINR0RFfpBGWKWVKPM42AzNsTpzRTtA_40wasndTntSjNtcv5Yd25U9NWdTUwDB-lllnIWves263k8BFXTaTKWKP7GCX9-Y3W-XKXHKXbSqXhOYITwHKU68m2MzPUBaYTdSoZtTpfOx_yYTtTntSu5id9byXKP7HKX9-299w5uOZntTrJT0FnpURchzUKXINWrGOvw5lF9KrKXHKXf2y8zjNtTpzRTu4_4TusnlTntTnPjPEYU0ggh0hLpPu6iEs0lYPCZzOE8ga7Bu28Si021G2h1IDlFRjoJK203H5J6SRwA0CC9p845iMwkhbQuzxjakHSq-KWKU48612j3wQ4kqCnVdXefQ101sPly56LmLhHGeY58LlfdQVw95eLpPui021uPIZlxEDrTgWNrhbQtekIX8h49e-kfpHWaKYLOI92M02ZBYZ94hX7RRtCfldSjLpzHf2huPblTtRTtw0000000000000000000005YRYV_5EogollUc2ob-U8RTPnPfOnF0wD63MggHQ1kgyZD7MBjijuPLUM10wD1-Y9Xdu8RuLpDOVF9Pcuhd5XeDCXus9wW2ZBYCHisO-hd7KQLgKXwud112bXDyWC6Cfm3kwZrTFWG3EldmAnPefjzZv0F6KnIZ7rg65VurQsntSQPnPuCjoyj8cD91lAOpMuxczMdbVgjbZioKIzEM7KAP8Rtn8dcQYw6CjWANZRx2CgqOdcU3hRtbUh7EF7EG9-rjd_sCq-OGpnxzlcf35A-0Msxl9mSgM4DM5njNYc00peNy5AzkO_c9fUhU3o51zVEYyfJWxIVdjbVaoYEDj7IzFBtj3j9VM_4m3QpmbU7wlVIDOdHbQ7c7Q8uYvePISFDjPAzFRBkOL37MQz8O5BBBHkMYcijViChUoBjcf35rJBlJUQDMa3A8ihHIxz0jU91MdI31JjiP8Pa0hQ04t017g0hT2fliv0GF6GgIIzD4-0QOkzj000000000000000000000000000FDjUigcGtekPnQBWpBV5czM-OCnWiCo-Qewf42ewzkPbSf28D4idcHQ4WCq-jzQNV2pv1WiFzUYPpj8V96CjOd19QP7w7mSgxJSNWqxXcK1NcuCYuz9dNfAox8Y1zSzFCva7eUjYhCl9CLcwiFD7JN-MRSFFVFUSw4Ov8apnFV51cHQ4qhuEUhjcv8L8j7QVe8FB-gj9Jqp1Hjefk5Xj8YNMs5rjln9gc50Rllll5jaYceoFxUo29Y1kOf34GpxUoHkU6FLpQ-cA88e4h6JQqy4qXSq-hgiQWV_gpfwk78lilFAc19Y1lQYv3006jIoxp8JcOYs0hM9704s0hJcRRipfHjaYyCsCGj7BFBY0qpvFWDpIVhcdZHs8ZEYlS3Q0v5ToqhAp2OONZ_SzSzTnofo3Y9WBcLgaCkqI4ijekk4Wp78qpuM4OtPCnlRSS9zWiCuzJT2zuzy6CpWAtcDQsSCjP4PHRPicKc1704s0hM16lcHMMWOC7xwcDMa3A8ihHcxz0jU91MdI31ChNgDM6GhGKIvhFCv8zO9fkpZhfknKg9WhWiujbU4VZSCvqfqjMxHO9DKMY_t1DS3S4ZxDRAZ9uQMZ60At9fCo0hQzSDjKQPWxWyugduh7AiZQ86uEkjb3IN1VtbFgDM6CiAqo00000000000000000001FzUBjcZhyaoWzcj9R6lN6lIpipuEu8r6jP6jIpL4peNBshAX6lN3PeoPeoPeoPK87N78uoCs-EeDebX68YNyfco9N6nIpfk70tz9j8R0u9r6rR6qCqUwRPCFCu8OANN6kCjycgVz4u8N5cL478jeT477D2l0PR68E3Gchg9R6lN6lIpi1uEe8r6jP6jIoDN6jIpn4peNBsgsPCcPCcPCc4gdthyfc7cO4jn47jDoScPGcPGcPycLoOuUe0X6iwhG4MZCwshAZNCG1mBowTPC-4pn4pncoxVhyf4ozUMszG54OMXcgtJ0Dso2wjOc1Oc_8PQ1V6jpApl-lAnV62C2iffN1bQ3O_nkPnlFA-hjaYyCsCGj7D9BYOFB-DGtCPB4MOFFVFV2u45cHQYyxUghF5Wzx5cNYykyu42gY0OshibUyAjiQzC4wnBXeDP7Ugs8yA8ojuYRTIRYzJmsmGJx4hbd6Ex6Lya2mLNBcv8oxye8UByebFB-1GAGGFFVDUH03U0kOLjMa2pxWMZHEjE7pRaFCnH8Wie08U0zHMubrAQAPofz-pAwyAz888ElSA0-1kOthw2oWz9ScjjctgAf0kzBN5j8Y9bMIJvbmSSSSSMQLnnqWUinHHJJHHJJjdtAHj9YQtEVe0pe0pGpzXQPbM5bSKdPsX9Oldf8Y1vdYEO3jdv9RlttRiCLzXdOnNsBqFHVDWIupJkMc31aq-nU07J6ivrhM3wm0U3we0u4FB-GKNWxNSjBreQFC7D9yg0000000000000000002CfyZ0PR68E3GcV0Dko9AozApChwk3Io0qtz9ScDoPk2ZhyuNDYhAX60V2gsgHeTR6nP6lP6kwqWz4u8N7K3ynk8CK8eDeyX6tP6tT61YhBX6jR1M7oOk2dgC7IQ3ycDKcRgaQH46-sTMzaUzaVz4fachUz4v63AtgECm7py7UxFCDwiZcLO1fRQ4Af8OaszfLOcYOO1eUMh0DApmhyehya0Yz9IOcGhOIyhOcYMihV-89uwunOWFFVFw7QOvuFBuDHZcHk4qhuEUZcNQzjFZ8kyt0pahzFeF6K4zNuZoCfJOshjbYwCjqQO3mCsuEbSFFVFUruQ5cHQYywClW2d8LkssCo-VV2o-D9N5cLO2p7HjerlBUqpHEwWhYkkPARioY1jbU0_6uFSrekj3FQWhu2l8D06iAoUjLk9zU79N7Mgj9JqChNGaPn05jcLdN704s0hM16000000000000000000000000002ubGq6n0zqqp9HNh9NZcBVfbXF0003kQYQYkw9A-RjaZf889BuwzibR72apzV5V2o-D9N5cLO2p7HjerlBU000qpHEwWhYkkPARioY1jbU0_6uFSrekj30000qpFVcfw7CAP7OmOCfLUTktQ0000000000000000000000000LpQ-42Me3hh4c9LuqXSq-hSHeblmMy8BCzkgznN51bjw8ogs8yA8jFTM33EUKACenYszxYu8YzxYu8YDCG196LMy2DVU9AAQznN56HebRmMy8BBXe_4q2ysunIZ7rg646nCZ75Ttw0000000000000000000000000000000005c0sujk6cq3Qo0Q77k6tgrR1sq3eEcqwPG2WwNG2qwoQ6tgoR1Dk6Zgn6wRG3mEdqwKE9G1zgnk5R1tgnk5R1tgpR0NEdqwRG3mEdoQ7yR1H00000000000000000000000000000000000Ggs60yuwuywDE7E9W2uywDE7E9SWgowHE3EaW2dcsgV0DE7EE9W1W2uwDEE9W1W6C688W0W2ewdcfghV0t17g7ghQ1Q4t0ughV0t0t0t0rpCK8ALFB2ci6y683hz41Q1-41Zg7g7g6C6U3vz1fgfgP3IilV8Z1fgjQcOYh9uYADE7ES9aYAuwDE9WcyiL97Evc4t0t17g6C7E8YwewzE3E8W0W2ewf88YweyyyyyxX1fgfhN4BuifgjQ4Z6h9BVbE9W1Wa2uwuwDE9Wa3fqlu_izs4t0uhA4t0uhA4t0uhA4t0o00000000000000000000000000000000009HJsu8UMN4CKRNUHqIj9dv9AWsQUWUsf4qA2YGSC71Oq7FBZMUzxPcTrXxNeNCXKOqWp7berEcICLgs7j89BUEL9VuRNUu74oiZH1EVhypbWpbWpbWp0000000000000000000000000000000000001u3Qt_S0BVL5Z5TqquJ0QOsuY7vWsP0TIRTtTttRttRttRru3QvntmTIZ7BTtJWfhNtTpuO-n"
//	+"tTntnntnntnntnntmZCKbKH000000000000000000000000000000000001bSC7BoQ0LFALFALFABZ4BZ4BZ4Lpu0kaILbSqUyqILGKXo77WHbcLcPjdcQPjdcQPj9b-oALFAWs00000000000000000000000000000000000000"
//exprt.exportToWav(test)

//'<title>', '</title>'
//`<pre id="body-display" class="body-display" style="white-space: pre-line"><a href="`, '</a>'

}
///client stuff

client.once('ready', () => {
	storage = new sqlite.Database('./testdb.sqlite', sqlite.OPEN_READWRITE | sqlite.OPEN_CREATE)
	storage.run(
		`CREATE TABLE IF NOT EXISTS savedCommands(cmd TEXT NOT NULL, name TEXT NOT NULL, args TEXT NOT NULL)`
	)
	storage.run(
		`CREATE TABLE IF NOT EXISTS savedBeepbox(id TEXT NOT NULL, dir TEXT NOT NULL)`
	)
	console.log('Ready!');
});

if(!testMode){

client.login(config.token);


client.on('message', async message => {
	if (message.guild) {
		runCommand(message, message.content)
	}
});

}

///i hate java script
random = (min,max) => {
    return Math.floor(Math.random()*(max-min+1)+min);
}

print = (...str) => {
	console.log(...str);
}

nl = (...str) => {
	let ns = ""
	str.forEach(t=>{
		ns += (t + "\n");
	})
	return ns;
}

printnl = (...str) => {
	console.log(nl(str));
}

ec = (string, full) => {
	return (full?"```\n":"`") + string + (full?"\n```":"`");
}

quote = (...str) => {
	let ns = ""

	str.forEach(t=>{
		ns += ("> "+t + "\n");
	})

	return ns;
}

promise = (...vals) => {
	return new Promise(r => {
		r(...vals)
	});
}

waitFor = function(test, expectedValue, msec, count, source, callback) {
    // Check if condition met. If not, re-check later (msec).
    while (test() !== expectedValue) {
        count++;
        setTimeout(function() {
            waitFor(test, expectedValue, msec, count, source, callback);
        }, msec);
        return;
    }
    // Condition finally met. callback() can be executed.
    console.log(source + ': ' + test() + ', expected: ' + expectedValue + ', ' + count + ' loops.');
    callback();
}

var scdl = (url) => {
	return  soundcloudl.download(url, config.scid).then((stream) => {
		return stream
	})
}


if(!testMode){


//numa reply stuff
author = (m) => ADMIN && typeof(ADMIN) == "boolean"?client.user:m.author;
numsm = (m, title, ...str) => m.channel.send(quote(ec(title.toUpperCase()),"",...str));
numm = (m, ...str) => m.channel.send(...str);
nummd = (m, time, reason) => m.delete({ timeout: time || 1000, reason: reason || 'It had to be done.' })
numr = (m, str) => {
	numm(m, `<@${author(m).id}>, ` + str)
}
numsmp = async (m, title, max, ...str) => {
	let pages = [], pagen = 0, i = 0, emojis = ["◀️", "▶️"], aid = author(m).id
	let filter = (reaction ,user) => {
		//print(user.id, aid, reaction.name, emojis.includes(reaction.name))
		return aid == user.id && emojis.includes(reaction.emoji.name);
	}
	title = ec(title.toUpperCase())
	m = await m.channel.send(quote(title,""))

	let reset = async () => {
		m.edit(quote(title,  "", ...pages[pagen], "`(Page "+(pagen+1)+")`"))

		await m.reactions.removeAll()
		if(pagen>0)
			await m.react(emojis[0])
		if(pagen<pages.length-1)
			await m.react(emojis[1])

		m.awaitReactions(filter, {max: 1, time: 60000 }).then(collected => {
			switch(collected.first().emoji.name){
				case emojis[0]: 
					pagen--
					reset()
					break;
				case emojis[1]:
					pagen++
					reset()
					break;
			}
		})
	}

	while(i < str.length){
		if(!pages[pagen])
			pages.push([])

		pages[pagen].push(str[i])
		i++;
		if(i - max * pagen > max-1)
			pagen++
	}

	pagen = 0
	reset()

	return m
}
numq = async (m, question, responce, failed, ...answers) => {
	let aid = author(m).id

	const filter = (res) => {
		return answers.includes(res.content.toLowerCase())
	}

	m = await m.channel.send(question)

	m.channel.awaitMessages(filter, { max: 1, time: 60000}).then( async (collected) => {
		let c = await collected.first()
		if(c.author.id==aid)
			responce(c, m)
	}).catch( () => {
		//m.channel.send(failed)
	})

	return m
}
// Initialization for numa
var ADMIN = false;
var prefix = [".", ".numa ", config.prefix];
var cmds = [];
var defaultData = {
	names: ["Name"],
	description: "Default Description",
	arguments: "None",
	whitelist: false,
	blacklist: [],
	cooldown: 0,
	timeLeft: 0
}
const boxes = ["moddedbeepbox.github.io/3.3", "jummbus.bitbucket.io/1_2","beepbox.co", "jummbus.bitbucket.io/", "moddedbeepbox.github.io", "theepicosity.github.io", "parad0xstuff.github.io", "fillygroove.github.io", "bluaxolotlbox.neocities.org", "synthbox.co", "hidden-realm.github.io/cardboardbox","synthboxtest.neocities.org"]
const boxid = ["mb_3_3",false, "jb_2_0", "jb_2_0", "mb_beta","mb_2_3","sb_3_0","sb_3_1","jb_2_0","sb","cb","sb"]
const linkTypes = {
	"box": boxes,
	"sc" : ["soundcloud.com"],
	"yt" : ["youtube.com", "youtu.be"],
	"sfpy":["open.spotify.com"]
}
var defaultProfile = ['3AD1CA', 'NumaBot', 'the cat behind the avatar', ["VUPA.jpg"]]
var Profiles = {//color, nickname, status, images
	Allumna : ['AE0A27', 'The All Seyeing',`Before I got my eye put out, I liked as well to see, As other creatures that have eyes, And know no other way.`, 
		["Allure.png", "alunis.jpg", "icublurbloody.png", "showoff.png", "icudidstort.png", "icublurbw.png"]],
	Karma : ['F003F9', 'Purple Eyes', "It's bad luck to step on the cracks in the sidewalk, you know",
		["blaqat.png","Darkarmaid.png","Karma.png","meow2.png"	]],
	bubly: ['ABC1E8', ".｡:+*", ".｡:+* by Snailhouse",
		["bubly.png","boobly.png"	]],
	Canary: ['F04F60', "Original Sun Bird", "",
		["Canary.png", "Canaryy.png", "chromecanary.jpg", "Yellow_Canary.png"]],
	Carma : ['CED0F8', 'Beyond Lucky', "meow",
		["Carma.png", "carmax.png"	]],
	Trigectory : ['820A00', "Triggasaurus Rex", "see me in phantom forces",
		["Trigectory.jpg","Trigectory.png"	]],
	Rouge : ['E63232', "The best.", "-_-",
		["Rouge.png","Roug.png", "teamblaze.png"	]],
	Rougism : ['FF484D', "the best!", "o-o",
		["Rougism.png", "rbean2.png"	]],
	rouge : ['FD3E6F', "Its a hood", "All the better to eat you up with.",
		["rouge.jpg","gato de negro.jpg"	]],
	RoyaleRuby: ['C43141', "KOTW!", "o-o",
		["RoyaleRuby.png", "royale.png", "auts.png"	]],
	Velocity: ['C62D32', "Botty Allen The Fas-", "My name is barry allen and I'm the fasest man alive, accorind to the ou-",
		["Velocity.jpg"	]],
	["meh-gan"]: ['EC76CE', "Ghost", "Hi bye 👋",
		["meghan.png","meh-gan.jpg"	]],
	Moirae: ['B423F2', "Not Real", "If you got money hmu",
		["Moirae.png", "Muse.jpg", "magic.png", "iconm.png", "magiikmoon2.png"]],
	MagikMagiik: ['B64FDE', 'Better Maark', "the lights stay hushed; fixed on invading the umbra around me. MY umbra...",
		["Nemesis.png","Moira.png"	]],
	nobo: ['CCD4E2', "Karma's alt","nose goes",
		["nobo.png"	]],
	nevo: ['7131ce', "Social Butterfly","the stars weave into the umbra around me",
		["butterfly.png"]],
	bananaqat: ['FFF7B2', "🍌😺🍌", "mrow ima qt ;3", ['bananacat.png']],
	[".𝗯 𝗼 𝘅"]: ['7744FF', "beepbox only.", "beepbox music.",
		['layers.png', 'box.png', 'haloweeon2asd.png',  'discord.png', 'asdijsdfj.png', 'thunderstorm.png', '262462.png'  ]]
}

const beepTypes = [["Original", "Remake", "Collab", "Beep Remake", "Transcription"], ["Jummbox", "Modbox", "Vanilla", "Unofficial"]]
const getBeeps = async function(type, weird, auth){
	let doc;
	let beeps = [], random;
	let [search, amount] = (typeof(weird) == 'string')?[weird.toLowerCase(), false]:[false, weird]
	auth = auth?auth.toLowerCase():""
	if(amount && amount < 0){
		random = true
		amount = Math.abs(amount)
	}

	if(type=="")
		type = false
	if(weird=="")
		weird = false
	if(auth == "")
		auth = false	

	if(beepTypes[0].includes(type))
		doc = reSheet
	else if(beepTypes[1].includes(type))
		doc = originalSheet
	else {
		doc = originalSheet
		type = "Index"
	}

	await doc.loadInfo()

	const sheets = doc.sheetsByIndex;
	let sheet;

	for(let i = 0; i < sheets.length; i++){
		let sht = sheets[i]
		if(sht.title == type){
			sheet = sht
			break;
		}
	}

	await sheet.loadCells(['B2:C', 'F:F'])	

	let availableRows = sheet.cellStats.nonEmpty/3
	let sheetLength = 0

	for(let r = 1; r < sheet.rowCount; r++){
		let got = sheet.getCell(r, 1)
		if(got && got.value != "")
			sheetLength = r;
		else
			break;
			//print(r)
	}

	//print(auth, search, amount, random, type)
	let tries = 0
	do {
		tries++
		//print(sheetLength, beeps.length < (amount || beeps.length+1), auth&&!(auth&&amount), (!(auth&&amount)?(amount-beeps.length):sheetLength))
		for(let r = 1; beeps.length < (amount || beeps.length+1) && r <= (amount&&!(auth&&amount)?amount-beeps.length:sheetLength); r++){
			if(random)
				random = Math.floor(Math.random()*(availableRows-1+1)+1)
			let i = random || r

			let got = sheet.getCell(i, 1).value
			if(got){
				let beepName = "" + (sheet.getCell(i, 5).value || "Unnamed")
				let aut = sheet.getCell(i, 2).value
				//print(i)
				//print(beepName, !search, beepName.toLowerCase().includes(search), (auth && aut && aut.toLowerCase().includes(auth)), !search || beepName.toLowerCase().includes(search) || (auth && aut && aut.toLowerCase().includes(auth)))
				//print(!search, beepName)
				if((!search || beepName.toLowerCase().includes(search)) && (!auth || aut && aut.toLowerCase().includes(auth))){
					beeps.push([beepName, got.trim(), aut]);
				}
				else {
					//print(beepName.toLowerCase(), search,beepName.toLowerCase().includes(search) )
				}
			}
		}
	}
	while(beeps.length < (random&&amount || beeps.length) && tries < 5)

	return beeps//.slice(0, amount || beeps.length-1);
};

//numa parser
var wantsnuma = function(message){

	for(let i = 0; i < prefix.length; i++){
		let pf = prefix[i];

		if (message.startsWith(pf) && !(pf == "." && message.startsWith(".numa"))){
			return [true, pf];
		}
	}

	return [false, null];
}

var parseMessage = function(message, usedPrefix){
	message = message.replace(usedPrefix, "");

	let cmd, args, saveas;

	if(message.search("=>")){
		[message, saveas] = message.split("=>")
	}

	if(saveas && saveas.charAt(0) === ' ')
		saveas = saveas.slice(1);

	if(message.search(" ")<=0){
		cmd = message;
		args = [];
	}
	else {
		cmd = message.slice(0,message.indexOf(" ")).toLowerCase();
		args = message.slice(message.indexOf(" ")+1).split(", ").join(",").split(",");
	}

	for(let i = 0; i < args.length; i++){
		args[i].slice(-1)===" "?args[i] = args[i].slice(0,-1):args[i]
	}

	return [cmd, args, saveas?saveas.toLowerCase():null];
}

//command runner
var runCommand = function(message, m){
	let [numa, prefix] = wantsnuma(m)

	if(numa){
		let [command, args, saveas] = parseMessage(m, prefix);

		let cd = getCommand(command)

		//client.user.setActivity('the stars weave into the umbra around me...', { type: 'WATCHING' });
		if(commandChecker(message, cd)){

			if(saveas) {
				storage.get(`SELECT * FROM savedCommands WHERE cmd = ?`, [cd[1].names[0]], () => {
					let setsave = storage.prepare(`INSERT OR REPLACE INTO savedCommands VALUES(?,?,?)`)
					setsave.run(cd[1].names[0], saveas.toLowerCase(), args.toString());
					setsave.finalize();
				})
			}

			let [real,counter] = [0,0]
			let temp = args.slice(0)

			for(let i = 0; i < temp.length; i++){
				storage.all(`SELECT * FROM savedCommands WHERE cmd = ?`, [cd[1].names[0]], (err, rows) => {
					rows.forEach(row => {
						if(row){
							let [argstring, saved] = [row.args, row.name]
							if(saved == args[i].toLowerCase()){
								let newArgs = argstring.split(",")
								args.splice(real, 1, ...newArgs)
								real+=newArgs.length+i
							}
						}
					})
					counter++
				})
			}

			waitFor(()=>counter, temp.length, 10, 0, "ARG STORAGE", ()=> {
				print(author(message).username," used:", cd[1].names[0], ...args)

				try{
					cd[0](message, ...args)

					if(ADMIN && !(typeof(ADMIN)=="boolean") && ADMIN>0)
						ADMIN--
					else if(ADMIN<=0 || ADMIN == true)
						ADMIN = false

				}
				catch(err){
					print("CAUGHT ERROR:\n",err)
					numm(message,"<@383851442341019658> Theres an error bro :facepalm:")
				}
			})
		}
	}
}

var commandChecker = (message, command) => {
	if(!command) return false;

	let commandData = command[1]

	let failed = false

	if(!(ADMIN&&(ADMIN == true ||ADMIN>0))){
		if (!(!commandData.whitelist||commandData.whitelist.includes(author(message).id))) {
			numm(message,"You are not whitelisted for this command >:)))))")
			failed = true
		}
		else if (!( commandData.timeLeft <= 0 )) {
			numm(message,`Please wait ${commandData.timeLeft} more second${commandData.timeLeft==1?'':'s'} to use this command :0`)
			failed = true
		}
		else if (commandData.blacklist.includes(author(message).id)) {
			numm(message,"HAHAHAHHAH LOSER You are blacklisted from this command")
			failed = true
		}
	}

	if(!failed){
		commandData.timeLeft += commandData.cooldown;
		return true;
	}
	else
		return false;
}

//command setup
var getCommand = function(name){
	let command;

	cmds.forEach(cma=>{
		cma[1].names.forEach(cName=>{

			if(name.toLowerCase() == cName.toLowerCase()){
				command = cma;
				return true;
			}
		})
	})

	return command?command:null;
}

var newCommand = function(name, func, data, ...aliases){
	data = data||[]
	data.names = [name,...aliases]
	cmds.push([func, commandData(data)])
};

var commandData = (given)=>{ 
	let def = JSON.parse(JSON.stringify(defaultData));

	for ([i, v] of Object.entries(def)){
		if(given[i] == true)
			given[i] = config[i]
		else if(given[i] == null)
			given[i] = def[i]
	}

	setInterval(function () {
		if(given.timeLeft > 0)
			given.timeLeft--;
	}, 1000)

	return given;
}


//thing to get correct link for music player hehe
linkChecker = (link, next) => {
	if(link.search("http")>=0){
		let tester = [false, link]
		getBaseLink(tester)

		waitFor(()=>tester[0], true, 100, 0, "LINKCHECKER", () => next(tester[1], getLinkType(tester[1])))
	}
	else {
		if(fs.existsSync(link))
			next(link, "numa")
	}
}

var getBaseLink = function(thing){
	link = thing[1].replace("snip.ml","api.snip.ml")

	if(!link.includes("pastelink.net")){
		request({url: link, followRedirect: false}, function(error, response) {

		if (response.statusCode >= 300 && response.statusCode < 400) {
			thing[1] = response.headers.location;
		}

		thing[0] = true;

		});
	}
	else {
		readURL(link).then(data=>{
			//let title;
			let body = `<pre id="body-display" class="body-display" style="white-space: pre-line">`;

			//title = thing.slice(thing.indexOf("<title>")+7, thing.indexOf(" - Pastelink.ne"))
			body = data.substring(data.indexOf(body)+body.length)
			body = body.slice(0, body.indexOf(`" target="blank"`))
			body = body.slice(body.indexOf("https"))

			thing[1] = body;
			thing[0] = true;
		})
	}
}

getLinkType = (link) => {
	let vals = Object.values(linkTypes)
	for(let i = 0; i < vals.length; i++){
		for(let x = 0; x < vals[i].length; x++){
			if(link.includes(vals[i][x]))
				return [Object.keys(linkTypes)[i], boxid[x] || false]
		}			
	}
	return [false, false]
}

const readURL = (url) => {
    return new Promise((resolve, reject) => {
        const http      = require('http'),
              https     = require('https');

        let client = http;

        if (url.toString().indexOf("https") === 0) {
            client = https;
        }

        client.get(url, (resp) => {
            let data = '';

            // A chunk of data has been recieved.
            resp.on('data', (chunk) => {
                data += chunk;
            });

            // The whole response has been received. Print out the result.
            resp.on('end', () => {
                resolve(data);
            });

        }).on("error", (err) => {
            reject(err);
        });
    });
}

//QUEUEUEUUEUEUEUEUEUEUEUEUEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE
class Queue {
	constructor(){
		this.queue = []
		this.isPlaying = false;
		this.now = null;
		this.lock = false;
	}

	get length(){
		return this.queue.length
	}

	get isEmpty(){
		return this.length == 0;
	}

	get first(){
		return this.queue[0]
	}

	get locked(){
		return this.lock
	}

	get queue(){
		return this.quee
	}

	set queue(n){
		this.quee = n || []
	}

	get isPlaying(){
		return this.playing
	}

	set isPlaying(n){
		this.playing = n;
	}

	get nowPlaying(){
		return `${this.now[3]} *(requested by ${this.now[2]})*`
	}

	get now(){
		return this.n
	}

	set now(ne){
		this.n = ne
	}

	get requests(){
		var links = []
		let i = 0;
		this.queue.forEach(qd => {i++; links.push(i+". `"+qd[2]+":`  <"+qd[3]+">")})

		return links
	}

	toggleLocked(bool){
		this.lock = bool==null?(!this.lock):bool
	}

	add(...e){
		e.forEach(ad => this.queue.push(ad))
	}

	dequeue(){
		if(this.locked)
			this.requeue()
		this.queue.shift()
	}

	shuffle(){
		let newa = [];
		let index;

		do {
			index = random(0, this.quee.length-1)
			newa.push(this.quee[index])
			this.quee.splice(index, 1)
		}
		while(this.length > 0)

		this.quee = newa
	}

	requeue(){
		let first = this.now.slice(0)
		first[1] = this.now[1].slice(0)
		this.add(first)
	}

	remove(index){
		let rem = this.queue[index]

		this.queue.splice(index, 1)

		return rem
	}

	clear(){
		let c = 0;
		
		while(this.length>0&&!this.locked){
			this.dequeue();
			c++
		}

		return c;
	}

	moveItem(from, to){
		let moved = this.queue[from]
		this.queue.splice(from, 1)
		this.queue.splice(to, 0, moved)
		return moved
	}

	async play(message, bot, vc){
		if(!this.isPlaying)
			this.isPlaying = true	

		if(!vc) {
			this.isPlaying = false 
			return
		}

		let data = this.first[1]
		const connection = bot.play(await data[0](...data[1]))
		this.now = this.first.slice(0)
		this.now[1] = this.first[1].slice(0)

		numsm(message, "playing", `<${this.first[3]}> requested by ${this.first[2]}`)
		this.dequeue();

		connection.on('finish', () => {
			this.isPlaying = false
			if(!this.isEmpty){
				this.play(message, bot, vc)
			}
		})
	}
}

const queue = new Queue();

// Commands

newCommand("alias", function(message, commandName){
	let command = getCommand(commandName);
	if(command){
		let commandNames = getCommand(commandName)[1].names;

		//numm(message,quote(ec("Alternate Command Names for " + commandNames[0]).toUpperCase(),"",...commandNames))
		numsm(message, "Alternate Command Names for " + commandNames[0], ...commandNames);
	}
}, {description: "Used to find the alternate names for a command.", arguments: "CommandName"}, "a", "alt");

newCommand("help", function(message, commandName){
	let command = getCommand(commandName?commandName:"");
	let m;

	if(command){
		m = ["HELP FOR " + command[1].names[0], "**Names**","\t"+command[1].names,"**Arguments**","\t"+command[1].arguments,"**Description:**","\t"+command[1].description];
	}

	else if (!commandName) {
		let list = [];
		cmds.forEach(cmd=>{
			list.push([ec(cmd[1].names[0]+":"), "\t"+cmd[1].description]);
		})

		m = ["List of Commands:", ...list];
	}

	numsm(message, ...(m?m:["ERROR","This command doens't exist"]));

},{description: "Used to get help with the bot or with specific commands.", arguments: "CommandName (Optional)"},"h", "whats")

newCommand("viewPersonas", function(message){
	let names = Object.keys(Profiles)

	numsmp(message, "Personas", 9, ...names)
},{}, "alts", "personas", "vp")

newCommand("changePersona", function(message, name, pic){
	let k = Object.keys(Profiles)

	name = name?(name=="Default"?".ᑎᑌᗰᗩ":name):k[Math.floor(k.length*Math.random())]

	let pf = name==".ᑎᑌᗰᗩ"?defaultProfile:Profiles[name]
	const avatars = pf[3]
	if(!(avatars)) return 0;

	let id = random(0, avatars.length-1)
	if(pic){
		for(let i = 0; i < avatars.length; i++){
			let avatar = avatars[i].toLowerCase()
			if(avatar.startsWith(pic.toLowerCase()))
				id = i
		}
	}

	client.user.setAvatar("./Media/Avatars/"+(avatars[id]));

	// client.user.setUsername(name)
	let bot = message.guild.members.fetch('740013958106447882').then(user => user.setNickname(name))
	bot.catch()
	client.user.setActivity(pf[2])

	let role = message.guild.roles.fetch('740019521762361426').then(role => role.setName(pf[1])).then(role => role.setColor(pf[0]))
	role.catch()

	numm(message,"Changing persona... o-o")
},{description: "who am i? am i not unique? maybe i'm not here at all", arguments: "PersonaName (Optional), AvatarName (Optional)", whitelist: true, cooldown: 60},"persona", "cp", "newAlt","PERSONA!")

newCommand("ping", function(message){
	numr(message, 'pong')
},{description: "PING PONG PING PONG PING", cooldown: 5}, "hey")

newCommand("blacklist", function(message, user, ...commands){
	user = user.slice(3,-1)
	let m = "";
	let counter = 0;
	(commands.length>0?commands:[null]).forEach(command => {
		cmds.filter(cmd => cmd[1].names.includes(command?command:cmd[1].names[0])).forEach(
			c => {
				if (c[1].blacklist.includes(user)){
					m+= `${message.mentions.users.first().username} is already blacklisted for ` + c[1].names[0]
				}
				else {
					c[1].blacklist.push(user)
					//m += "User blacklisted for " + c[1].names[0]
					counter++;
				}

				m+="\n"
			}
		)
	})
	numm(message, m + `\n ${message.mentions.users.first().username} was blacklisted on ${counter} commands.`)
},{description: "Makes you black", arguments: "User, CommandName (Optional)"}, "blackface", "bl")

newCommand("unblacklist", function(message, user, ...commands){
	user = user.slice(3,-1)
	let m = "";
	let counter = 0;
	(commands.length>0?commands:[null]).forEach(command => {
		cmds.filter(cmd => cmd[1].names.includes(command?command:cmd[1].names[0]) && cmd[1].blacklist.includes(user)).forEach(
			c => {
				c[1].blacklist.splice(c[1].blacklist.indexOf(user),1);
				counter++;
				/*
				m+= `${message.mentions.users.first().username}  unblacklisted for ` + c[1].names[0]
				m+="\n"
				*/
			}
		)
	})
	numm(message, m + `\n ${message.mentions.users.first().username} was unblacklisted on ${counter} commands.`)
},{description: "Washes your black face", arguments: "User, CommandName (Optional)"}, "unbl", "washface")

newCommand("whitelist", function(message, user, ...commands){
	user = user.slice(3,-1)
	let m = "";
	(commands.length>0?commands:[null]).forEach(command => {
		cmds.filter(cmd => cmd[1].names.includes(command?command:cmd[1].names[0])).forEach(
			cmd => {
				if (!cmd[1].whitelist.includes(user)){
					cmd[1].whitelist.push(user)
					m += `${message.mentions.users.first().username} whitelisted for ` + cmd[1].names[0]
				}
				else
					m += `${message.mentions.users.first().username} is already whitelisted for ` + cmd[1].names[0]

				m+="\n"
			}
		)
	})
	numm(message, m)
},{description: "Makes you normal", arguments: "User, CommandName (Optional)"}, "whiten", "wl", "normalize")

newCommand("unwhitelist", function(message, user, ...commands){
	user = user.slice(3,-1)
	let m = "";
	(commands.length>0?commands:[null]).forEach(command => {
		cmds.filter(cmd => cmd[1].names.includes(command?command:cmd[1].names[0]) && cmd[1].whitelist.includes(user)).forEach(
			cmd => {
				cmd[1].whitelist.splice(cmd[1].whitelist.indexOf(user),1);
				m += `${message.mentions.users.first().username}  unwhitelisted for ` + cmd[1].names[0]

				m+="\n"
			}
		)
	})
	numm(message, m)
},{description: "Makes society against you", arguments: "User, CommandName (Optional)"}, "ice", "unwl")

const getPlayData = async (url, type) => {
	switch(type[0]){
		case "yt":
			return [[ytdl, [url, { filter: 'audioonly' }]], false]
		case "numa":
			return [[], true]
		case "box":
			beep = url.slice(url.indexOf("#")+1)
			beep = beep.slice(beep.indexOf("=")+1)
			dire = new Promise((re) =>{
				storage.get(`SELECT * FROM savedBeepbox WHERE id = ?`, [url], async (e, r) => {
					let thing = ""
					if(!r){
						let setsave = storage.prepare(`INSERT OR REPLACE INTO savedBeepbox VALUES(?,?)`)
						let beepData = await exprt.exportToWav(beep,type[1])
						thing = beepData[1]
						setsave.run(url, thing);
						setsave.finalize();
					}
					else
						thing = r.dir	
					re(thing)
				})
			})
			return [[fs.createReadStream, [await dire]], false]
		case "sc":
			return [[scdl, [url]], false]
		default:
			return [[fs.createReadStream, [url]], false]
	}
}

newCommand("playMusic", function(message, original){
	const vc = message.member.voice.channel
	if(!vc) return numr(message, "Please join a vc idiot!");

	linkChecker(original,(url, typ) => {

		vc.join().then(bot => {
			let data = [null, null, [true]];

			if(typ == "numa"){
				data[0] = fs.createReadStream
				data[1] = [url]

				queue.add([url, data, author(message).username, original])
				numm(message, `added <${original}> to the quee :3`);

				if(!queue.isPlaying)
					queue.play(message, bot, vc)
			}
		})

	})

	nummd(message, 1000)

},{description:"plays music directly from numa's storage", arguments: "Link", whitelist: ["383851442341019658"]},"m","pm","music")

newCommand("searchBeepByTitle", async function(message, text, type, auth){
	const vc = message.member.voice.channel
	if(!vc) return numr(message, "Please join a vc idiot!");

	let loadingMessage = await numm(message, "Searching... :weary:")

	let beeps = await getBeeps(type, text, auth)
	let beepNames = [], indexes = [], counter = 0

	beeps.forEach(beep => {
		counter++
		indexes.push(""+counter)
		beepNames.push(counter+". "+beep.join('> | <'))
	})

	nummd(loadingMessage, 500)
	if(beeps.length==0)
		return numm(message, "No beep was found :pensive:")

	let doBeep = (bot, beeps, index) => {
		let beep = beeps[index]
		counter++;
		linkChecker(beep[1], async (url, typ) => {
			let lb = beep
			let [data, num] = await getPlayData(url, typ)

			if(!num){
				queue.add([url, data, author(message).username, lb[0]+" *by: "+lb[2]+"* <" + lb[1] +">"])

				if(!queue.isPlaying)
					queue.play(message, bot, vc)

				if(counter){
					numm(message, `added ${lb[0]} by ${lb[2]} to the quee :3 `+"`(spot "+queue.length+")`");
					counter = null
				}
					
			}
			else
				numm(message, "Please use `playMusic` for this kind of link")
			
			if(index+1 < beeps.length)
				doBeep(bot, beeps, index+1)
		})			
	}

	if(beeps.length > 1){
		numsmp(message, "Beeps Found", 6, ...beepNames)
		numq(message, "Type the number of the beep you want", (res) => {
			let beep = [beeps[parseInt(res.content)-1]]
			vc.join().then(bot => {
				doBeep(bot, beep, 0)
			})
		}, "Ok guess i wont play a beep :shrug:", ...indexes)
	}
	else{
		let beep = [beeps[0]]
		vc.join().then(bot => {
			doBeep(bot, beep, 0)
		})
	}

},{},"search", "pb", "searchByTitle")

newCommand("searchBeepByAuthor", async function(message, auth, type, text){
	const vc = message.member.voice.channel
	if(!vc) return numr(message, "Please join a vc idiot!");

	let loadingMessage = await numm(message, "Searching... :weary:")

	let beeps = await getBeeps(type, text, auth)
	//print(beeps)
	let beepNames = [], indexes = [], counter = 0

	beeps.forEach(beep => {
		counter++
		indexes.push(""+counter)
		let joined  = beep.join('> | <')
		if(joined.length > 200)
			joined = joined.slice(0, 200)

		beepNames.push(counter+". "+joined)
	})

	nummd(loadingMessage, 500)
	if(beeps.length==0)
		return numm(message, "No beep was found :pensive:")

	let doBeep = (bot, beeps, index) => {
		let beep = beeps[index]
		counter++;
		linkChecker(beep[1], async (url, typ) => {
			let lb = beep
			let [data, num] = await getPlayData(url, typ)

			if(!num){
				queue.add([url, data, author(message).username, lb[0]+" *by: "+lb[2]+"* <" + lb[1] +">"])

				if(!queue.isPlaying)
					queue.play(message, bot, vc)

				if(counter){
					numm(message, `added ${lb[0]} by ${lb[2]} to the quee :3 `+"`(spot "+queue.length+")`");
					counter = null
				}
					
			}
			else
				numm(message, "Please use `playMusic` for this kind of link")
			
			if(index+1 < beeps.length)
				doBeep(bot, beeps, index+1)
		})			
	}

	if(beeps.length > 1){
		numsmp(message, beeps.length+" Beeps Found", 8, ...beepNames)
		numq(message, "Type the number of the beep you want", (res) => {
			let beep = [beeps[parseInt(res.content)-1]]
			vc.join().then(bot => {
				doBeep(bot, beep, 0)
			})
		}, "Ok guess i wont play a beep :shrug:", ...indexes)
	}
	else{
		let beep = [beeps[0]]
		vc.join().then(bot => {
			doBeep(bot, beep, 0)
		})
	}
},{}, "searcha", "pba", "searchByAuthor")


newCommand("playRandomBeep", async (message, amount, type, auth) => {
	const vc = message.member.voice.channel
	if(!vc) return numr(message, "Please join a vc idiot!");
	
	let loadingMessage = await numm(message, "Getting the beeps >:)))")

	let beeps = await getBeeps(type, -parseInt(amount), auth)
	let counter = 0;

	let doBeep = (bot, beeps, index) => {
		//print(beeps, index)
		let beep = beeps[index]
		if(counter)
			counter++;
		linkChecker(beep[1], async (url, typ) => {
			let lb = beep
			let [data, num] = await getPlayData(url, typ)

			if(!num){
				queue.add([url, data, author(message).username, lb[0]+" *by: "+lb[2]+"* <" + lb[1] +">"])

				if(!queue.isPlaying)
					queue.play(message, bot, vc)

				if(counter){
					numm(message, `added ${lb[0]} by ${lb[2]} to the quee :3 `+"`(spot "+queue.length+")`");
					counter = false
				}
					
			}
			else
				numm(message, "Please use `playMusic` for this kind of link")
			
			if(index+1 < beeps.length)
				doBeep(bot, beeps, index+1)
		})			
	}

	vc.join().then(bot => {
		doBeep(bot, beeps, 0)
		if(counter > 1)
			numm(message, `added ${counter} songs to the quee >:3`)
		nummd(loadingMessage, 1000)
	})

},{},"rb", "randomBeep", "playRandomBeep")

newCommand("play", function(message, ...urls){
	if(!urls) return numr(message, "The heck am I supposed to play?");
	const vc = message.member.voice.channel
	if(!vc) return numr(message, "Please join a vc idiot!");
	let counter = 0;

	vc.join().then(bot => {
		urls.forEach(original => {
			counter++;
			linkChecker(original, async (url, typ) => {
				let [data, num] = await getPlayData(url, typ)
				let og = original
				if(!num){
					queue.add([url, data, author(message).username, og])

					if(!queue.isPlaying)
						queue.play(message, bot, vc)

					if(counter){
						numm(message, `added <${og}> to the quee :3 `+"`(spot "+queue.length+")`");
						nummd(message, 1000)
						counter = null
					}
						
				}
				else
					numm(message, "Please use `playMusic` for this kind of link")
			})

		})

		if(counter > 1)
			numm(message, `added ${counter} songs to the quee >:3`)
	
		if(urls.length == 0 && queue.isPlaying)
			queue.play(message, bot, vc)
	})
	
},{description: "Plays a song from youtube", arguments: "Youtube Link", cooldown: 5}, "pl", "p","qa")

newCommand("playFirst", function(message, original){
	if(!original) return numr(message, "The heck am I supposed to play?");
	const vc = message.member.voice.channel
	if(!vc) return numr(message, "Please join a vc idiot!");

	linkChecker(original, (url, typ) => {
		vc.join().then(async bot => {
			let [data, num] = await getPlayData(url, typ)

			if(!num){
				queue.queue.unshift([url, data, author(message).username, original])

				if(!queue.isPlaying)
					queue.play(message, bot, vc)

				nummd(message, 1000)
			}
			else
				numm(message, "Please use `playMusic` for this kind of link")
		})
	})

},{description: "Plays a song from youtube first in queue", arguments: "Youtube Link", cooldown: 5}, "pf")

newCommand("playNow", function(message, original){
	if(!original) return numr(message, "The heck am I supposed to play?");
	const vc = message.member.voice.channel
	if(!vc) return numr(message, "Please join a vc idiot!");

	linkChecker(original, (url, typ) => {
		vc.join().then(async bot =>  {
			let [data, num] = await getPlayData(url, typ)

			if(!num){	
				numsm(message, "playing:", `<${original}>`)
				bot.play(await data[0](...data[1]))
				queue.isPlaying = true

				bot.on('finish', () => queue.play(message,bot,vc))
				nummd(message, 1000)
			}
			else
				numm(message, "Please use `playMusic` for this kind of link")
		})
	})
},{description: "Plays a song from youtube at the begining of the queue", arguments: "Youtube Link", cooldown: 5}, "pn", "forcePlay")

newCommand("stop", function(message){
	const vc = message.member.voice.channel

	if(!vc) return numr(message, "Please join a vc, idiot!");

	vc.join().then(async () =>  {
		vc.leave();
	})

	queue.isPlaying = false

	numm(message,"Sorry, was I too loud? :(")
},{description: "Kills the music", cooldown: 5}, "st", "killmusic", "leave","l", "shutup")

newCommand("viewQueue", function(message){
	if (queue.isEmpty)
		numm(message, "Theres nothing in the quee >.<")
	else
		numsm(message,"queue", ...queue.requests)
},{description: "Shows the list of songs waiting to be played"},"queue","vq","q")

newCommand("clearQueue", function(message){
	let c = queue.clear();
	numm(message, `${c} songs cleared from queue.`)

},{description: "removes all the songs from the quee"},"cq","removeAll", "clear", "cl")

newCommand("lockQueue", function(message){
	queue.toggleLocked(true)
	numm(message, `Queue is now ${queue.locked?"locked":"unlocked"}`)
},{cooldown: 5},"lq","lock")

newCommand("unlockQueue", function(message){
	queue.toggleLocked(false)
	numm(message, `Queue is now ${queue.locked?"locked":"unlocked"}`)
},{cooldown: 5},"ulq","unlock")

newCommand("toggleQueueLock", function(message){
	queue.toggleLocked()
	numm(message, `Queue is now ${queue.locked?"locked":"unlocked"}`)
},{cooldown: 5},"ql","queuelock")

newCommand("moveSong", function(message, from, to){
	from = parseInt(from)
	to = parseInt(to)

	if(from<=0||to<=0||from>queue.length||to>queue.length){
		numm(message, "There aren't that many songs playing lmao")
		return;
	}
	let moved = queue.moveItem(from-1, to-1)
	numm(message, `Moved <${moved[3]}> (*requested by ${moved[2]}*) from position ${from} to position ${to}`)
},{arguments: "Index From #, Index To #", description:"Sifts a song's placement on the quee"},"move")

newCommand("removeFromQueue", function(message, index){
	index = parseInt(index)

	if(0 >= index > queue.length) {
		numm(message, "There aren't that many songs playing lmao")
		return;
	}

	let removed = queue.remove(index-1)
	numm(message, `Removed <${removed[3]}> (*requested by ${removed[2]}*) from queue`)

},{description: "removes a song from the quee", arguments:"Index #"},"qd", "remove", "r")

newCommand("skipSong", function(message){
	const vc = message.member.voice.channel

	if(!vc) return numr(message, "Please join a vc idiot!");

	vc.join().then(bot => {
		queue.isPlaying = false
		if(queue.isEmpty){
			vc.leave();
		}
		else
			queue.play(message,bot,vc)
	})
	
	numm(message,"get destroyed jajajaj")

},{cooldown: 10, description: "Skips over a losers song that is currently playing"},"s","skip")

newCommand("repeatSong", function(message){
	const vc = message.member.voice.channel
	if(!vc) return numr(message, "Please join a vc idiot!");
	if(!queue.now) return numm(message,"Repeating: LITERALLY NOTHING U TWAT THERES NOTHING PLAYING >:(")
	queue.requeue();

	if(!queue.isPlaying){
		vc.join().then(bot => {	
				queue.play(message, bot, vc)
		})
	}

	let text = queue.nowPlaying
	text = text.split(" ")
	text[0] = "<"+text[0]+">"

	numm(message,"Repeating: " + text.join(" "))
},{cooldown:10},"repeat", "re","r", "playAgain")

newCommand("nowPlaying", function(message){
	if(queue.isPlaying)
		numsm(message, "Currently Playing:", queue.nowPlaying)
	else
		numm(message, "Theres nothing in the quee >.<")
},{description: "Shows what song is currently playing"},"np","what song is playing?")

newCommand("shuffleQueue", function(message){
	queue.shuffle();
	numm(message, "quee has been shuffled uwu~")
},{},"shuffle")

newCommand("args", function(message, ...args){
	let a = ""
	args.forEach(arg=>a+=`|${arg}|\t`)
	numm(message, a)
})

newCommand("forceNext:", function(message, count){
	count = count?parseInt(count):1;
	ADMIN = count
	numm(message, `I am under your absolute control for ${count} command${count>1?"s":''}`)
},{whitelist: "383851442341019658"}, "free:", "adminNext:")

newCommand("useCommand:", function(message, ...args){
	ADMIN = true
	let m = args[0]+" "

	args.shift()
	args.forEach(arg => m+=arg+", ")

	numm(message, `I will use: ${m}`)
	runCommand(message, "."+m)
},{whitelist: "383851442341019658"}, "force:", "do:", "use:")

newCommand("say:", function(message, ...args){
	let m = ""
	args.forEach(arg => (m+=arg))
	numm(message, m)
},{whitelist: true},"say")

newCommand("version", function(message){
	numm(message, ".nevo Version: " + ec(version))
})

newCommand("updates", function(message){
	for(let i = 0; i < updates.length; i++){
		updates[i] = "•\t"+updates[i]
	}
	numm(message, "Updates for version " + ec(version) + "\n" + ec(updates.join("\n"), true))
})
}