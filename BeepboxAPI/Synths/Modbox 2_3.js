var FFT;
(function (FFT) {
function scaleElementsByFactor(array, factor) {
    for (var i = 0; i < array.length; i++) {
        array[i] *= factor;
    }
}
FFT.scaleElementsByFactor = scaleElementsByFactor;
function isPowerOf2(n) {
    return !!n && !(n & (n - 1));
}
function countBits(n) {
    if (!isPowerOf2(n))
        throw new Error("FFT array length must be a power of 2.");
    return Math.round(Math.log(n) / Math.log(2));
}
function reverseIndexBits(array) {
    var fullArrayLength = array.length;
    var bitCount = countBits(fullArrayLength);
    if (bitCount > 16)
        throw new Error("FFT array length must not be greater than 2^16.");
    var finalShift = 16 - bitCount;
    for (var i = 0; i < fullArrayLength; i++) {
        var j = void 0;
        j = ((i & 0xaaaa) >> 1) | ((i & 0x5555) << 1);
        j = ((j & 0xcccc) >> 2) | ((j & 0x3333) << 2);
        j = ((j & 0xf0f0) >> 4) | ((j & 0x0f0f) << 4);
        j = ((j >> 8) | ((j & 0xff) << 8)) >> finalShift;
        if (j > i) {
            var temp = array[i];
            array[i] = array[j];
            array[j] = temp;
        }
    }
}
function inverseRealFourierTransform(array) {
    var fullArrayLength = array.length;
    var totalPasses = countBits(fullArrayLength);
    if (fullArrayLength < 4)
        throw new Error("FFT array length must be at least 4.");
    for (var pass = totalPasses - 1; pass >= 2; pass--) {
        var subStride = 1 << pass;
        var midSubStride = subStride >> 1;
        var stride = subStride << 1;
        var radiansIncrement = Math.PI * 2.0 / stride;
        var cosIncrement = Math.cos(radiansIncrement);
        var sinIncrement = Math.sin(radiansIncrement);
        var oscillatorMultiplier = 2.0 * cosIncrement;
        for (var startIndex = 0; startIndex < fullArrayLength; startIndex += stride) {
            var startIndexA = startIndex;
            var midIndexA = startIndexA + midSubStride;
            var startIndexB = startIndexA + subStride;
            var midIndexB = startIndexB + midSubStride;
            var stopIndex = startIndexB + subStride;
            var realStartA = array[startIndexA];
            var imagStartB = array[startIndexB];
            array[startIndexA] = realStartA + imagStartB;
            array[midIndexA] *= 2;
            array[startIndexB] = realStartA - imagStartB;
            array[midIndexB] *= 2;
            var c = cosIncrement;
            var s = -sinIncrement;
            var cPrev = 1.0;
            var sPrev = 0.0;
            for (var index = 1; index < midSubStride; index++) {
                var indexA0 = startIndexA + index;
                var indexA1 = startIndexB - index;
                var indexB0 = startIndexB + index;
                var indexB1 = stopIndex - index;
                var real0 = array[indexA0];
                var real1 = array[indexA1];
                var imag0 = array[indexB0];
                var imag1 = array[indexB1];
                var tempA = real0 - real1;
                var tempB = imag0 + imag1;
                array[indexA0] = real0 + real1;
                array[indexA1] = imag1 - imag0;
                array[indexB0] = tempA * c - tempB * s;
                array[indexB1] = tempB * c + tempA * s;
                var cTemp = oscillatorMultiplier * c - cPrev;
                var sTemp = oscillatorMultiplier * s - sPrev;
                cPrev = c;
                sPrev = s;
                c = cTemp;
                s = sTemp;
            }
        }
    }
    for (var index = 0; index < fullArrayLength; index += 4) {
        var index1 = index + 1;
        var index2 = index + 2;
        var index3 = index + 3;
        var real0 = array[index];
        var real1 = array[index1] * 2;
        var imag2 = array[index2];
        var imag3 = array[index3] * 2;
        var tempA = real0 + imag2;
        var tempB = real0 - imag2;
        array[index] = tempA + real1;
        array[index1] = tempA - real1;
        array[index2] = tempB + imag3;
        array[index3] = tempB - imag3;
    }
    reverseIndexBits(array);
}
FFT.inverseRealFourierTransform = inverseRealFourierTransform;
})(FFT || (FFT = {}));

var beepbox = {};
global.beepbox = beepbox;


const exportToWav = async function(thelink) {
    const synth = typeof(thelink) == "string" && new (beepbox).Synth(thelink) || thelink;
    synth.enableIntro = true
    synth.enableOutro = true
    synth.loopCount = 1
    var sampleFrames = synth.totalSamples;
    var recordedSamples = new Float32Array(sampleFrames);
    synth.synthesize(recordedSamples, sampleFrames);
    var srcChannelCount = 1;
    var wavChannelCount = 1;
    var sampleRate = 44100;
    var bytesPerSample = 2;
    var bitsPerSample = 8 * bytesPerSample;
    var sampleCount = wavChannelCount * sampleFrames;
    var totalFileSize = 44 + sampleCount * bytesPerSample;
    var index = 0;
    var arrayBuffer = new ArrayBuffer(totalFileSize);
    var data = new DataView(arrayBuffer);
    data.setUint32(index, 0x52494646, false);
    index += 4;
    data.setUint32(index, 36 + sampleCount * bytesPerSample, true);
    index += 4;
    data.setUint32(index, 0x57415645, false);
    index += 4;
    data.setUint32(index, 0x666D7420, false);
    index += 4;
    data.setUint32(index, 0x00000010, true);
    index += 4;
    data.setUint16(index, 0x0001, true);
    index += 2;
    data.setUint16(index, wavChannelCount, true);
    index += 2;
    data.setUint32(index, sampleRate, true);
    index += 4;
    data.setUint32(index, sampleRate * bytesPerSample * wavChannelCount, true);
    index += 4;
    data.setUint16(index, bytesPerSample, true);
    index += 2;
    data.setUint16(index, bitsPerSample, true);
    index += 2;
    data.setUint32(index, 0x64617461, false);
    index += 4;
    data.setUint32(index, sampleCount * bytesPerSample, true);
    index += 4;
    var stride;
    var repeat;
    if (srcChannelCount == wavChannelCount) {
        stride = 1;
        repeat = 1;
    }
    else {
        stride = srcChannelCount;
        repeat = wavChannelCount;
    }
    var val;
    if (bytesPerSample > 1) {
        for (var i = 0; i < sampleFrames; i++) {
            val = Math.floor(recordedSamples[i * stride] * ((1 << (bitsPerSample - 1)) - 1));
            for (var k = 0; k < repeat; k++) {
                if (bytesPerSample == 2) {
                    data.setInt16(index, val, true);
                    index += 2;
                }
                else if (bytesPerSample == 4) {
                    data.setInt32(index, val, true);
                    index += 4;
                }
                else {
                    throw new Error("unsupported sample size");
                }
            }
        }
    }
    else {
        for (var i = 0; i < sampleFrames; i++) {
            val = Math.floor(recordedSamples[i * stride] * 127 + 128);
            for (var k = 0; k < repeat; k++) {
                data.setUint8(index, val > 255 ? 255 : (val < 0 ? 0 : val));
                index++;
            }
        }
    }
    return Buffer.from(arrayBuffer)
};

var Config = (function () {
    function Config() {
    }
    Config._centerWave = function (wave) {
        var sum = 0.0;
        for (var i = 0; i < wave.length; i++)
            sum += wave[i];
        var average = sum / wave.length;
        for (var i = 0; i < wave.length; i++)
            wave[i] -= average;
        return new Float64Array(wave);
    };
    Config.getDrumWave = function (index) {
        var wave = Config._drumWaves[index];
        if (wave == null) {
            wave = new Float32Array(32768);
            Config._drumWaves[index] = wave;
            if (index == 0) {
                var drumBuffer = 1;
                for (var i = 0; i < 32768; i++) {
                    wave[i] = (drumBuffer & 1) * 2.0 - 1.0;
                    var newBuffer = drumBuffer >> 1;
                    if (((drumBuffer + newBuffer) & 1) == 1) {
                        newBuffer += 1 << 14;
                    }
                    drumBuffer = newBuffer;
                }
            }
            else if (index == 1) {
                for (var i = 0; i < 32768; i++) {
                    wave[i] = Math.random() * 2.0 - 1.0;
                }
            }
            else if (index == 2) {
                var drumBuffer = 1;
                for (var i = 0; i < 32768; i++) {
                    wave[i] = (drumBuffer & 1) * 2.0 - 1.0;
                    var newBuffer = drumBuffer >> 1;
                    if (((drumBuffer + newBuffer) & 1) == 1) {
                        newBuffer += 2 << 14;
                    }
                    drumBuffer = newBuffer;
                }
            }
			else if (index == 3) {
                var drumBuffer = 1;
                for (var i = 0; i < 32767; i++) {
                    wave[i] = (drumBuffer & 1) * 2.0 - 1.0;
                    var newBuffer = drumBuffer >> 2;
                    if (((drumBuffer + newBuffer) & 1) == 1) {
                        newBuffer += 4 << 14;
                    }
                    drumBuffer = newBuffer;
                }
            }
            else if (index == 4) {
                var drumBuffer = 1;
                for (var i = 0; i < 32768; i++) {
                    wave[i] = (drumBuffer & 1) * 2.0 - 1.0;
                    var newBuffer = drumBuffer >> 1;
                    if (((drumBuffer + newBuffer) & 1) == 1) {
                        newBuffer += 10 << 2;
                    }
                    drumBuffer = newBuffer;
                }
            }
            else if (index == 5) {
                for (var i = 1 << 10; i < (1 << 11); i++) {
                    var amplitude = 2.0;
                    var radians = Math.random() * Math.PI * 2.0;
                    wave[i] = Math.cos(radians) * amplitude;
                    wave[32768 - i] = Math.sin(radians) * amplitude;
                }
                for (var i = 1 << 11; i < (1 << 14); i++) {
                    var amplitude = 0.25;
                    var radians = Math.random() * Math.PI * 2.0;
                    wave[i] = Math.cos(radians) * amplitude;
                    wave[32768 - i] = Math.sin(radians) * amplitude;
                }
                FFT.inverseRealFourierTransform(wave);
                FFT.scaleElementsByFactor(wave, 1.0 / Math.sqrt(wave.length));
            }
			else if (index == 6) {
                for (var i = 1 << 1; i < (1 << 10); i++) {
                    var amplitude = 2.0;
                    var radians = Math.random() * Math.PI * 2.0;
                    wave[i] = Math.cos(radians) * amplitude;
                    wave[32768 - i] = Math.sin(radians) * amplitude;
                }
                for (var i = 1 << 110; i < (0 << 14); i++) {
                    var amplitude = 0.5;
                    var radians = Math.random() * Math.PI * 2.0;
                    wave[i] = Math.cos(radians) * amplitude;
                    wave[32768 - i] = Math.sin(radians) * amplitude;
                }
                FFT.inverseRealFourierTransform(wave);
                FFT.scaleElementsByFactor(wave, 1.0 / Math.sqrt(wave.length));
            }
            else {
                throw new Error("Unrecognized drum index: " + index);
            }
        }
        return wave;
    };
    return Config;
}());
Config.scaleNames = ["easy :)", "easy :(", "island :)", "island :(", "blues :)", "blues :(", "normal :)", "normal :(", "dbl harmonic :)", "dbl harmonic :(", "enigma", "expert", "base note", "beep bishop", "challenge", "enigma+"];
Config.scaleFlags = [
    [true, false, true, false, true, false, false, true, false, true, false, false],
    [true, false, false, true, false, true, false, true, false, false, true, false],
    [true, false, false, false, true, true, false, true, false, false, false, true],
    [true, true, false, true, false, false, false, true, true, false, false, false],
    [true, false, true, true, true, false, false, true, false, true, false, false],
    [true, false, false, true, false, true, true, true, false, false, true, false],
    [true, false, true, false, true, true, false, true, false, true, false, true],
    [true, false, true, true, false, true, false, true, true, false, true, false],
    [true, true, false, false, true, true, false, true, true, false, false, true],
    [true, false, true, true, false, false, true, true, true, false, false, true],
    [true, false, true, false, true, false, true, false, true, false, true, false],
    [true, true, true, true, true, true, true, true, true, true, true, true],
	[true, false, false, false, false, false, false, false, false, false, false, false],
	[true, true, false, true, true, true, true, true, true, false, true, false],
	[false, true, true, true, true, true, true, true, true, true, true, true],
	[true, true, false, true, true, false, true, true, false, true, true, false],
];
Config.pianoScaleFlags = [true, false, true, false, true, true, false, true, false, true, false, true];
Config.blackKeyNameParents = [-1, 1, -1, 1, -1, 1, -1, -1, 1, -1, 1, -1];
Config.pitchNames = ["C", null, "D", null, "E", "F", null, "G", null, "A", null, "B"];
Config.keyNames = ["B", "A#", "A", "G#", "G", "F#", "F", "E", "D#", "D", "C#", "C"];
Config.keyTransposes = [23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12];
Config.tempoNames = ["speed1", "speed2", "speed3", "speed4", "speed5", "speed6", "speed7", "speed8", "speed9", "speed10", "speed11", "speed12", "speed13", "speed14", "speed15", "speed16", "speed17", "speed18", "speed19", "speed20", "speed21", ];
Config.reverbRange = 5;
Config.blendRange = 4;
Config.riffRange = 11;
Config.beatsPerBarMin = 1;
Config.beatsPerBarMax = 16;
Config.barCountMin = 1;
Config.barCountMax = 255;
Config.patternsPerChannelMin = 1;
Config.patternsPerChannelMax = 64;
Config.instrumentsPerChannelMin = 1;
Config.instrumentsPerChannelMax = 64;
Config.partNames = ["÷·3 (triplets)", "÷·4 (standard)", "÷·6", "÷·8", "÷·16 (arpfest)", "÷·12 (smaller arpfest)", "÷·9 (ninths)", "÷·5 (fifths)", "÷·50 (fiftieths)"];
Config.partCounts = [3, 4, 6, 8, 16, 12, 9, 5, 50];
Config.waveNames = ["triangle", "square", "pulse wide", "pulse narrow", "sawtooth", "double saw", "double pulse", "spiky", "plateau", "glitch", "10% pulse", "sunsoft bass", "loud pulse", "sax", "guitar", "sine", "atari bass", "atari pulse", "1% pulse", "curved sawtooth", "viola", "brass", "acoustic bass"];
Config.waveVolumes = [1.0, 0.5, 0.5, 0.5, 0.65, 0.5, 0.4, 0.4, 0.94, 0.5, 0.5, 1.0, 0.6, 0.2, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0];
Config.drumNames = ["retro", "white", "periodic", "detuned periodic", "shine", "hollow", "deep"];
Config.drumVolumes = [0.25, 1.0, 0.4, 0.3, 0.3, 1.5, 1.5];
Config.drumPitchRoots = [69, 69, 69, 69, 69, 96, 120];
Config.drumPitchFilterMult = [100.0, 8.0, 100.0, 100.0, 100.0, 1.0, 100.0];
Config.drumWaveIsSoft = [false, true, false, false, false, true];
Config.filterNames = ["sustain sharp", "sustain medium", "sustain soft", "decay sharp", "decay medium", "decay soft", "ring", "muffled", "submerged", "shift", "overtone"];
Config.filterBases = [2.0, 3.5, 5.0, 1.0, 2.5, 4.0, -1.0, 4.0, 6.0, 0.0, 1.0];
Config.filterDecays = [0.0, 0.0, 0.0, 10.0, 7.0, 4.0, 0.2, 0.2, 0.3, 0.0, 0.0];
Config.filterVolumes = [0.4, 0.7, 1.0, 0.5, 0.75, 1.0, 0.5, 0.75, 0.4, 0.4, 1.0];
Config.envelopeNames = ["seamless", "sudden", "smooth", "slide","trill","click","bow"];
Config.effectNames = ["none", "vibrato light", "vibrato delayed", "vibrato heavy", "tremelo light", "tremelo heavy", "alien", "stutter", "strum"];
Config.effectVibratos = [0.0, 0.15, 0.3, 0.45, 0.0, 0.0, 1.0, 0.0, 0.05];
Config.effectTremolos = [0.0, 0.0, 0.0, 0.0, 0.25, 0.5, 0.0, 1.0, 0.025];
Config.effectVibratoDelays = [0, 0, 3, 0, 0, 0, 0, 0, 0];
Config.chorusNames = ["union", "shimmer", "hum", "honky tonk", "dissonant", "fifths", "octaves", "spinner", "detune", "bowed", "rising", "vibrate", "fourths", "bass", "dirty", "stationary", "custom harmony", "detuned custom harmony"];
Config.chorusIntervals = [0.0, 0.02, 0.05, 0.1, 0.25, 3.5, 6, 0.02, 0.0, 0.02, 1.0, 3.5, 4, 0, 0.0, 3.5, 0.0, 0.05];
Config.chorusOffsets = [0.0, 0.0, 0.0, 0.0, 0.0, 3.5, 6, 0.0, 0.25, 0.0, 0.7, 7, 4, -7, 0.1, 0.0, 0.0, 0.25];
Config.chorusVolumes = [0.9, 0.9, 1.0, 1.0, 0.95, 0.95, 0.9, 1.0, 1.0, 1.0, 0.95, 0.975, 0.95, 1.0, 0.975, 0.9, 1.0, 1.0];
Config.chorusHarmonizes = [false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false,true, true];
Config.volumeNames = ["loudest", "loud", "medium", "quiet", "quietest", "mute"];
Config.volumeValues = [0.0, 0.5, 1.0, 1.5, 2.0, -1.0];
Config.pitchChannelColorsDim = ["#0099a1", "#439143", "#a1a100", "#c75000", "#d020d0", "#492184"];
Config.pitchChannelColorsBright = ["#25f3ff", "#44ff44", "#ffff25", "#ff9752", "#ff90ff", "#9147ff"];
Config.pitchNoteColorsDim = ["#0099a1", "#439143", "#a1a100", "#c75000", "#d020d0", "#492184"];
Config.pitchNoteColorsBright = ["#25f3ff", "#44ff44", "#ffff25", "#ff9752", "#ff90ff", "#9147ff"];
Config.drumChannelColorsDim = ["#991010", "#aaaaaa"];
Config.drumChannelColorsBright = ["#ff1616", "#ffffff"];
Config.drumNoteColorsDim = ["#991010", "#aaaaaa"];
Config.drumNoteColorsBright = ["#ff1616", "#ffffff"];
Config.drumInterval = 6;
Config.drumCount = 12;
Config.pitchCount = 37;
Config.maxPitch = 84;
Config.pitchChannelCountMin = 1;
Config.pitchChannelCountMax = 6;
Config.drumChannelCountMin = 0;
Config.drumChannelCountMax = 2;
Config.waves = [
    Config._centerWave([1.0 / 15.0, 3.0 / 15.0, 5.0 / 15.0, 7.0 / 15.0, 9.0 / 15.0, 11.0 / 15.0, 13.0 / 15.0, 15.0 / 15.0, 15.0 / 15.0, 13.0 / 15.0, 11.0 / 15.0, 9.0 / 15.0, 7.0 / 15.0, 5.0 / 15.0, 3.0 / 15.0, 1.0 / 15.0, -1.0 / 15.0, -3.0 / 15.0, -5.0 / 15.0, -7.0 / 15.0, -9.0 / 15.0, -11.0 / 15.0, -13.0 / 15.0, -15.0 / 15.0, -15.0 / 15.0, -13.0 / 15.0, -11.0 / 15.0, -9.0 / 15.0, -7.0 / 15.0, -5.0 / 15.0, -3.0 / 15.0, -1.0 / 15.0]),
    Config._centerWave([1.0, -1.0]),
    Config._centerWave([1.0, -1.0, -1.0, -1.0]),
    Config._centerWave([1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0]),
    Config._centerWave([1.0 / 31.0, 3.0 / 31.0, 5.0 / 31.0, 7.0 / 31.0, 9.0 / 31.0, 11.0 / 31.0, 13.0 / 31.0, 15.0 / 31.0, 17.0 / 31.0, 19.0 / 31.0, 21.0 / 31.0, 23.0 / 31.0, 25.0 / 31.0, 27.0 / 31.0, 29.0 / 31.0, 31.0 / 31.0, -31.0 / 31.0, -29.0 / 31.0, -27.0 / 31.0, -25.0 / 31.0, -23.0 / 31.0, -21.0 / 31.0, -19.0 / 31.0, -17.0 / 31.0, -15.0 / 31.0, -13.0 / 31.0, -11.0 / 31.0, -9.0 / 31.0, -7.0 / 31.0, -5.0 / 31.0, -3.0 / 31.0, -1.0 / 31.0]),
    Config._centerWave([0.0, -0.2, -0.4, -0.6, -0.8, -1.0, 1.0, -0.8, -0.6, -0.4, -0.2, 1.0, 0.8, 0.6, 0.4, 0.2]),
    Config._centerWave([1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0]),
    Config._centerWave([1.0, -1.0, 1.0, -1.0, 1.0, 0.0]),
    Config._centerWave([0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.95, 0.9, 0.85, 0.8, 0.7, 0.6, 0.5, 0.4, 0.2, 0.0, -0.2, -0.4, -0.5, -0.6, -0.7, -0.8, -0.85, -0.9, -0.95, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -0.95, -0.9, -0.85, -0.8, -0.7, -0.6, -0.5, -0.4, -0.2]),
	Config._centerWave([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0,1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0]),
	Config._centerWave([1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0]),
	Config._centerWave([0.0, 0.1875, 0.3125, 0.5625, 0.5, 0.75, 0.875, 1.0, 1.0, 0.6875, 0.5, 0.625, 0.625, 0.5, 0.375, 0.5625, 0.4375, 0.5625, 0.4375, 0.4375, 0.3125, 0.1875, 0.1875, 0.375, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.4375, 0.25, 0.0]),
	Config._centerWave([1.0, 0.7, 0.1, 0.1, 0, 0, 0, 0, 0, 0.1, 0.2, 0.15, 0.25, 0.125, 0.215, 0.345, 4.0]),
	Config._centerWave([1.0 / 15.0, 3.0 / 15.0, 5.0 / 15.0, 9.0, 0.06]),
	Config._centerWave([-0.5, 3.5, 3.0, -0.5, -0.25, -1.0]),
	Config._centerWave([0.0, 0.05, 0.125, 0.2, 0.25, 0.3, 0.425, 0.475, 0.525, 0.625, 0.675, 0.725, 0.775, 0.8, 0.825, 0.875, 0.9, 0.925, 0.95, 0.975, 0.98, 0.99, 0.995, 1, 0.995, 0.99, 0.98, 0.975, 0.95, 0.925, 0.9, 0.875, 0.825, 0.8, 0.775, 0.725, 0.675, 0.625, 0.525, 0.475, 0.425, 0.3, 0.25, 0.2, 0.125, 0.05, 0.0, -0.05, -0.125, -0.2, -0.25, -0.3, -0.425, -0.475, -0.525, -0.625, -0.675, -0.725, -0.775, -0.8, -0.825, -0.875, -0.9, -0.925, -0.95, -0.975, -0.98, -0.99, -0.995, -1, -0.995, -0.99, -0.98, -0.975, -0.95, -0.925, -0.9, -0.875, -0.825, -0.8, -0.775, -0.725, -0.675, -0.625, -0.525, -0.475, -0.425, -0.3, -0.25, -0.2, -0.125, -0.05]),
	Config._centerWave([1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]),
	Config._centerWave([0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]),
	Config._centerWave([1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0]),
	Config._centerWave([1.0, 1.0 / 2.0, 1.0 / 3.0, 1.0 / 4.0]),
	Config._centerWave([-0.9, -1.0, -0.85, -0.775, -0.7, -0.6, -0.5, -0.4, -0.325, -0.225, -0.2, -0.125, -0.1, -0.11, -0.125, -0.15, -0.175, -0.18, -0.2, -0.21, -0.22, -0.21, -0.2, -0.175, -0.15, -0.1, -0.5, 0.75, 0.11, 0.175, 0.2, 0.25, 0.26, 0.275, 0.26, 0.25, 0.225, 0.2, 0.19, 0.18, 0.19, 0.2, 0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.275, 0.28, 0.29, 0.3, 0.29, 0.28, 0.27, 0.26, 0.25, 0.225, 0.2, 0.175, 0.15, 0.1, 0.075, 0.0, -0.01, -0.025, 0.025, 0.075, 0.2, 0.3, 0.475, 0.6, 0.75, 0.85, 0.85, 1.0, 0.99, 0.95, 0.8, 0.675, 0.475, 0.275, 0.01, -0.15, -0.3, -0.475, -0.5, -0.6, -0.71, -0.81, -0.9, -1.0, -0.9]),
	Config._centerWave([-1.0, -0.95, -0.975, -0.9, -0.85, -0.8, -0.775, -0.65, -0.6, -0.5, -0.475, -0.35, -0.275, -0.2, -0.125, -0.05, 0.0, 0.075, 0.125, 0.15, 0.20, 0.21, 0.225, 0.25, 0.225, 0.21, 0.20, 0.19, 0.175, 0.125, 0.10, 0.075, 0.06, 0.05, 0.04, 0.025, 0.04, 0.05, 0.10, 0.15, 0.225, 0.325, 0.425, 0.575, 0.70, 0.85, 0.95, 1.0, 0.9, 0.675, 0.375, 0.2, 0.275, 0.4, 0.5, 0.55, 0.6, 0.625, 0.65, 0.65, 0.65, 0.65, 0.64, 0.6, 0.55, 0.5, 0.4, 0.325, 0.25, 0.15, 0.05, -0.05, -0.15, -0.275, -0.35, -0.45, -0.55, -0.65, -0.7, -0.78, -0.825, -0.9, -0.925, -0.95, -0.975]),
	Config._centerWave([1.0, 0.0, 0.1, -0.1, -0.2, -0.4, -0.3, -1.0]),
];
Config._drumWaves = [null, null, null, null, null];
beepbox.Config = Config;
var BitFieldReader = (function () {
    function BitFieldReader(base64CharCodeToInt, source, startIndex, stopIndex) {
        this._bits = [];
        this._readIndex = 0;
        for (var i = startIndex; i < stopIndex; i++) {
            var value = base64CharCodeToInt[source.charCodeAt(i)];
            this._bits.push((value >> 5) & 0x1);
            this._bits.push((value >> 4) & 0x1);
            this._bits.push((value >> 3) & 0x1);
            this._bits.push((value >> 2) & 0x1);
            this._bits.push((value >> 1) & 0x1);
            this._bits.push(value & 0x1);
        }
    }
    BitFieldReader.prototype.read = function (bitCount) {
        var result = 0;
        while (bitCount > 0) {
            result = result << 1;
            result += this._bits[this._readIndex++];
            bitCount--;
        }
        return result;
    };
    BitFieldReader.prototype.readLongTail = function (minValue, minBits) {
        var result = minValue;
        var numBits = minBits;
        while (this._bits[this._readIndex++]) {
            result += 1 << numBits;
            numBits++;
        }
        while (numBits > 0) {
            numBits--;
            if (this._bits[this._readIndex++]) {
                result += 1 << numBits;
            }
        }
        return result;
    };
    BitFieldReader.prototype.readPartDuration = function () {
        return this.readLongTail(1, 2);
    };
    BitFieldReader.prototype.readPinCount = function () {
        return this.readLongTail(1, 0);
    };
    BitFieldReader.prototype.readPitchInterval = function () {
        if (this.read(1)) {
            return -this.readLongTail(1, 3);
        }
        else {
            return this.readLongTail(1, 3);
        }
    };
    return BitFieldReader;
}());
var BitFieldWriter = (function () {
    function BitFieldWriter() {
        this._bits = [];
    }
    BitFieldWriter.prototype.write = function (bitCount, value) {
        bitCount--;
        while (bitCount >= 0) {
            this._bits.push((value >>> bitCount) & 1);
            bitCount--;
        }
    };
    BitFieldWriter.prototype.writeLongTail = function (minValue, minBits, value) {
        if (value < minValue)
            throw new Error("value out of bounds");
        value -= minValue;
        var numBits = minBits;
        while (value >= (1 << numBits)) {
            this._bits.push(1);
            value -= 1 << numBits;
            numBits++;
        }
        this._bits.push(0);
        while (numBits > 0) {
            numBits--;
            this._bits.push((value >>> numBits) & 1);
        }
    };
    BitFieldWriter.prototype.writePartDuration = function (value) {
        this.writeLongTail(1, 2, value);
    };
    BitFieldWriter.prototype.writePinCount = function (value) {
        this.writeLongTail(1, 0, value);
    };
    BitFieldWriter.prototype.writePitchInterval = function (value) {
        if (value < 0) {
            this.write(1, 1);
            this.writeLongTail(1, 3, -value);
        }
        else {
            this.write(1, 0);
            this.writeLongTail(1, 3, value);
        }
    };
    BitFieldWriter.prototype.concat = function (other) {
        this._bits = this._bits.concat(other._bits);
    };
    BitFieldWriter.prototype.encodeBase64 = function (base64IntToCharCode, buffer) {
        for (var i = 0; i < this._bits.length; i += 6) {
            var value = (this._bits[i] << 5) | (this._bits[i + 1] << 4) | (this._bits[i + 2] << 3) | (this._bits[i + 3] << 2) | (this._bits[i + 4] << 1) | this._bits[i + 5];
            buffer.push(base64IntToCharCode[value]);
        }
        return buffer;
    };
    BitFieldWriter.prototype.lengthBase64 = function () {
        return Math.ceil(this._bits.length / 6);
    };
    return BitFieldWriter;
}());
function makeNotePin(interval, time, volume) {
    return { interval: interval, time: time, volume: volume };
}
beepbox.makeNotePin = makeNotePin;
function makeNote(pitch, start, end, volume, fadeout) {
    if (fadeout === void 0) { fadeout = false; }
    return {
        pitches: [pitch],
        pins: [makeNotePin(0, 0, volume), makeNotePin(0, end - start, fadeout ? 0 : volume)],
        start: start,
        end: end,
    };
}
beepbox.makeNote = makeNote;
function filledArray(count, value) {
    var array = [];
    for (var i = 0; i < count; i++)
        array[i] = value;
    return array;
}
beepbox.filledArray = filledArray;
var BarPattern = (function () {
    function BarPattern() {
        this.notes = [];
        this.instrument = 0;
    }
    BarPattern.prototype.cloneNotes = function () {
        var result = [];
        for (var _i = 0, _a = this.notes; _i < _a.length; _i++) {
            var oldNote = _a[_i];
            var newNote = makeNote(-1, oldNote.start, oldNote.end, 3);
            newNote.pitches = oldNote.pitches.concat();
            newNote.pins = [];
            for (var _b = 0, _c = oldNote.pins; _b < _c.length; _b++) {
                var oldPin = _c[_b];
                newNote.pins.push(makeNotePin(oldPin.interval, oldPin.time, oldPin.volume));
            }
            result.push(newNote);
        }
        return result;
    };
    return BarPattern;
}());
beepbox.BarPattern = BarPattern;
var Song = (function () {
    function Song(string) {
        if (string != undefined) {
            this.fromBase64String(string);
        }
        else {
            this.initToDefault();
        }
    }
    Song.prototype.getChannelCount = function () {
        return this.pitchChannelCount + this.drumChannelCount;
    };
    Song.prototype.getChannelIsDrum = function (channel) {
        return (channel >= this.pitchChannelCount);
    };
    Song.prototype.getChannelColorDim = function (channel) {
        return channel < this.pitchChannelCount ? Config.pitchChannelColorsDim[channel] : Config.drumChannelColorsDim[channel - this.pitchChannelCount];
    };
    Song.prototype.getChannelColorBright = function (channel) {
        return channel < this.pitchChannelCount ? Config.pitchChannelColorsBright[channel] : Config.drumChannelColorsBright[channel - this.pitchChannelCount];
    };
    Song.prototype.getNoteColorDim = function (channel) {
        return channel < this.pitchChannelCount ? Config.pitchNoteColorsDim[channel] : Config.drumNoteColorsDim[channel - this.pitchChannelCount];
    };
    Song.prototype.getNoteColorBright = function (channel) {
        return channel < this.pitchChannelCount ? Config.pitchNoteColorsBright[channel] : Config.drumNoteColorsBright[channel - this.pitchChannelCount];
    };
    Song.prototype.initToDefault = function () {
        this.channelPatterns = [
            [new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern()],
            [new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern()],
            [new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern()],
            [new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern()],
            [new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern(), new BarPattern()],
        ];
        this.channelBars = [
            [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        ];
        this.channelOctaves = [4, 3, 2, 1, 0];
        this.instrumentVolumes = [[0], [0], [0], [0], [0]];
        this.instrumentWaves = [[1], [1], [1], [1], [1]];
        this.instrumentFilters = [[0], [0], [0], [0], [0]];
        this.instrumentEnvelopes = [[1], [1], [1], [1], [1]];
        this.instrumentEffects = [[0], [0], [0], [0], [0]];
        this.instrumentChorus = [[0], [0], [0], [0], [0]];
        this.scale = 0;
        this.key = Config.keyNames.length - 1;
        this.loopStart = 0;
        this.loopLength = 4;
        this.tempo = 7;
        this.reverb = 0;
		this.blend = 0;
		this.riff = 0;
        this.beatsPerBar = 8;
        this.barCount = 16;
        this.patternsPerChannel = 8;
        this.partsPerBeat = 4;
        this.instrumentsPerChannel = 1;
        this.pitchChannelCount = 4;
        this.drumChannelCount = 1;
    };
    Song.prototype.toBase64String = function () {
        var bits;
        var buffer = [];
        var base64IntToCharCode = Song._base64IntToCharCode;
        buffer.push(base64IntToCharCode[Song._latestVersion]);
        buffer.push(110, base64IntToCharCode[this.pitchChannelCount], base64IntToCharCode[this.drumChannelCount]);
        buffer.push(115, base64IntToCharCode[this.scale]);
        buffer.push(107, base64IntToCharCode[this.key]);
        buffer.push(108, base64IntToCharCode[this.loopStart >> 6], base64IntToCharCode[this.loopStart & 0x3f]);
        buffer.push(101, base64IntToCharCode[(this.loopLength - 1) >> 6], base64IntToCharCode[(this.loopLength - 1) & 0x3f]);
        buffer.push(116, base64IntToCharCode[this.tempo]);
        buffer.push(109, base64IntToCharCode[this.reverb]);
		buffer.push(120, base64IntToCharCode[this.blend]);
		buffer.push(121, base64IntToCharCode[this.riff]);
        buffer.push(97, base64IntToCharCode[this.beatsPerBar - 1]);
        buffer.push(103, base64IntToCharCode[(this.barCount - 1) >> 6], base64IntToCharCode[(this.barCount - 1) & 0x3f]);
        buffer.push(106, base64IntToCharCode[this.patternsPerChannel - 1]);
        buffer.push(105, base64IntToCharCode[this.instrumentsPerChannel - 1]);
        buffer.push(114, base64IntToCharCode[Config.partCounts.indexOf(this.partsPerBeat)]);
        buffer.push(119);
        for (var channel = 0; channel < this.getChannelCount(); channel++)
            for (var i = 0; i < this.instrumentsPerChannel; i++) {
                buffer.push(base64IntToCharCode[this.instrumentWaves[channel][i]]);
            }
        buffer.push(102);
        for (var channel = 0; channel < this.getChannelCount(); channel++)
            for (var i = 0; i < this.instrumentsPerChannel; i++) {
                buffer.push(base64IntToCharCode[this.instrumentFilters[channel][i]]);
            }
        buffer.push(100);
        for (var channel = 0; channel < this.getChannelCount(); channel++)
            for (var i = 0; i < this.instrumentsPerChannel; i++) {
                buffer.push(base64IntToCharCode[this.instrumentEnvelopes[channel][i]]);
            }
        buffer.push(99);
        for (var channel = 0; channel < this.getChannelCount(); channel++)
            for (var i = 0; i < this.instrumentsPerChannel; i++) {
                buffer.push(base64IntToCharCode[this.instrumentEffects[channel][i]]);
            }
        buffer.push(104);
        for (var channel = 0; channel < this.getChannelCount(); channel++)
            for (var i = 0; i < this.instrumentsPerChannel; i++) {
                buffer.push(base64IntToCharCode[this.instrumentChorus[channel][i]]);
            }
        buffer.push(118);
        for (var channel = 0; channel < this.getChannelCount(); channel++)
            for (var i = 0; i < this.instrumentsPerChannel; i++) {
                buffer.push(base64IntToCharCode[this.instrumentVolumes[channel][i]]);
            }
        buffer.push(111);
        for (var channel = 0; channel < this.getChannelCount(); channel++) {
            buffer.push(base64IntToCharCode[this.channelOctaves[channel]]);
        }
        buffer.push(98);
        bits = new BitFieldWriter();
        var neededBits = 0;
        while ((1 << neededBits) < this.patternsPerChannel + 1)
            neededBits++;
        for (var channel = 0; channel < this.getChannelCount(); channel++)
            for (var i = 0; i < this.barCount; i++) {
                bits.write(neededBits, this.channelBars[channel][i]);
            }
        bits.encodeBase64(base64IntToCharCode, buffer);
        buffer.push(112);
        bits = new BitFieldWriter();
        var neededInstrumentBits = 0;
        while ((1 << neededInstrumentBits) < this.instrumentsPerChannel)
            neededInstrumentBits++;
        for (var channel = 0; channel < this.getChannelCount(); channel++) {
            var isDrum = this.getChannelIsDrum(channel);
            var octaveOffset = isDrum ? 0 : this.channelOctaves[channel] * 12;
            var lastPitch = (isDrum ? 4 : 12) + octaveOffset;
            var recentPitches = isDrum ? [4, 6, 7, 2, 3, 8, 0, 10] : [12, 19, 24, 31, 36, 7, 0];
            var recentShapes = [];
            for (var i = 0; i < recentPitches.length; i++) {
                recentPitches[i] += octaveOffset;
            }
            for (var _i = 0, _a = this.channelPatterns[channel]; _i < _a.length; _i++) {
                var p = _a[_i];
                bits.write(neededInstrumentBits, p.instrument);
                if (p.notes.length > 0) {
                    bits.write(1, 1);
                    var curPart = 0;
                    for (var _b = 0, _c = p.notes; _b < _c.length; _b++) {
                        var t = _c[_b];
                        if (t.start > curPart) {
                            bits.write(2, 0);
                            bits.writePartDuration(t.start - curPart);
                        }
                        var shapeBits = new BitFieldWriter();
                        for (var i = 1; i < t.pitches.length; i++)
                            shapeBits.write(1, 1);
                        if (t.pitches.length < 4)
                            shapeBits.write(1, 0);
                        shapeBits.writePinCount(t.pins.length - 1);
                        shapeBits.write(2, t.pins[0].volume);
                        var shapePart = 0;
                        var startPitch = t.pitches[0];
                        var currentPitch = startPitch;
                        var pitchBends = [];
                        for (var i = 1; i < t.pins.length; i++) {
                            var pin = t.pins[i];
                            var nextPitch = startPitch + pin.interval;
                            if (currentPitch != nextPitch) {
                                shapeBits.write(1, 1);
                                pitchBends.push(nextPitch);
                                currentPitch = nextPitch;
                            }
                            else {
                                shapeBits.write(1, 0);
                            }
                            shapeBits.writePartDuration(pin.time - shapePart);
                            shapePart = pin.time;
                            shapeBits.write(2, pin.volume);
                        }
                        var shapeString = String.fromCharCode.apply(null, shapeBits.encodeBase64(base64IntToCharCode, []));
                        var shapeIndex = recentShapes.indexOf(shapeString);
                        if (shapeIndex == -1) {
                            bits.write(2, 1);
                            bits.concat(shapeBits);
                        }
                        else {
                            bits.write(1, 1);
                            bits.writeLongTail(0, 0, shapeIndex);
                            recentShapes.splice(shapeIndex, 1);
                        }
                        recentShapes.unshift(shapeString);
                        if (recentShapes.length > 10)
                            recentShapes.pop();
                        var allPitches = t.pitches.concat(pitchBends);
                        for (var i = 0; i < allPitches.length; i++) {
                            var pitch = allPitches[i];
                            var pitchIndex = recentPitches.indexOf(pitch);
                            if (pitchIndex == -1) {
                                var interval = 0;
                                var pitchIter = lastPitch;
                                if (pitchIter < pitch) {
                                    while (pitchIter != pitch) {
                                        pitchIter++;
                                        if (recentPitches.indexOf(pitchIter) == -1)
                                            interval++;
                                    }
                                }
                                else {
                                    while (pitchIter != pitch) {
                                        pitchIter--;
                                        if (recentPitches.indexOf(pitchIter) == -1)
                                            interval--;
                                    }
                                }
                                bits.write(1, 0);
                                bits.writePitchInterval(interval);
                            }
                            else {
                                bits.write(1, 1);
                                bits.write(3, pitchIndex);
                                recentPitches.splice(pitchIndex, 1);
                            }
                            recentPitches.unshift(pitch);
                            if (recentPitches.length > 8)
                                recentPitches.pop();
                            if (i == t.pitches.length - 1) {
                                lastPitch = t.pitches[0];
                            }
                            else {
                                lastPitch = pitch;
                            }
                        }
                        curPart = t.end;
                    }
                    if (curPart < this.beatsPerBar * this.partsPerBeat) {
                        bits.write(2, 0);
                        bits.writePartDuration(this.beatsPerBar * this.partsPerBeat - curPart);
                    }
                }
                else {
                    bits.write(1, 0);
                }
            }
        }
        var stringLength = bits.lengthBase64();
        var digits = [];
        while (stringLength > 0) {
            digits.unshift(base64IntToCharCode[stringLength & 0x3f]);
            stringLength = stringLength >> 6;
        }
        buffer.push(base64IntToCharCode[digits.length]);
        Array.prototype.push.apply(buffer, digits);
        bits.encodeBase64(base64IntToCharCode, buffer);
        return String.fromCharCode.apply(null, buffer);
    };
    Song.prototype.fromBase64String = function (compressed) {
        if (compressed == null) {
            this.initToDefault();
            return;
        }
        var charIndex = 0;
        while (compressed.charCodeAt(charIndex) <= 32)
            charIndex++;
        if (compressed.charCodeAt(charIndex) == 35)
            charIndex++;
        if (compressed.charCodeAt(charIndex) == 123) {
            this.fromJsonObject(JSON.parse(charIndex == 0 ? compressed : compressed.substring(charIndex)));
            return;
        }
        this.initToDefault();
        var version = Song._base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
        if (version == -1 || version > Song._latestVersion || version < Song._oldestVersion)
            return;
        var beforeThree = version < 3;
        var beforeFour = version < 4;
        var beforeFive = version < 5;
        var base64CharCodeToInt = Song._base64CharCodeToInt;
        if (beforeThree)
            this.instrumentEnvelopes = [[0], [0], [0], [0]];
        if (beforeThree)
            this.instrumentWaves = [[1], [1], [1], [0]];
        while (charIndex < compressed.length) {
            var command = compressed.charCodeAt(charIndex++);
            var channel = void 0;
            if (command == 110) {
                this.pitchChannelCount = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                this.drumChannelCount = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                this.pitchChannelCount = this._clip(Config.pitchChannelCountMin, Config.pitchChannelCountMax + 1, this.pitchChannelCount);
                this.drumChannelCount = this._clip(Config.drumChannelCountMin, Config.drumChannelCountMax + 1, this.drumChannelCount);
                var channelCount = this.pitchChannelCount + this.drumChannelCount;
                for (var channel_1 = 0; channel_1 < channelCount; channel_1++) {
                    this.channelPatterns[channel_1] = [];
                    this.channelBars[channel_1] = [];
                    this.instrumentWaves[channel_1] = [];
                    this.instrumentFilters[channel_1] = [];
                    this.instrumentEnvelopes[channel_1] = [];
                    this.instrumentEffects[channel_1] = [];
                    this.instrumentChorus[channel_1] = [];
                    this.instrumentVolumes[channel_1] = [];
                }
                this.channelPatterns.length = channelCount;
                this.channelBars.length = channelCount;
                this.channelOctaves.length = channelCount;
                this.instrumentWaves.length = channelCount;
                this.instrumentFilters.length = channelCount;
                this.instrumentEnvelopes.length = channelCount;
                this.instrumentEffects.length = channelCount;
                this.instrumentChorus.length = channelCount;
                this.instrumentVolumes.length = channelCount;
            }
            else if (command == 115) {
                this.scale = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                if (beforeThree && this.scale == 10)
                    this.scale = 11;
            }
            else if (command == 107) {
                this.key = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
            }
            else if (command == 108) {
                if (beforeFive) {
                    this.loopStart = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                }
                else {
                    this.loopStart = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) + base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                }
            }
            else if (command == 101) {
                if (beforeFive) {
                    this.loopLength = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                }
                else {
                    this.loopLength = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) + base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                }
            }
            else if (command == 116) {
                if (beforeFour) {
                    this.tempo = [1, 4, 7, 10][base64CharCodeToInt[compressed.charCodeAt(charIndex++)]];
                }
                else {
                    this.tempo = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                }
                this.tempo = this._clip(0, Config.tempoNames.length, this.tempo);
            }
            else if (command == 109) {
                this.reverb = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                this.reverb = this._clip(0, Config.reverbRange, this.reverb);
            }
			else if (command == 120) {
                this.blend = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                this.blend = this._clip(0, Config.blendRange, this.blend);
            }
			else if (command == 121) {
                this.riff = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                this.riff = this._clip(0, Config.riffRange, this.riff);
            }
            else if (command == 97) {
                if (beforeThree) {
                    this.beatsPerBar = [6, 7, 8, 9, 10][base64CharCodeToInt[compressed.charCodeAt(charIndex++)]];
                }
                else {
                    this.beatsPerBar = base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                }
                this.beatsPerBar = Math.max(Config.beatsPerBarMin, Math.min(Config.beatsPerBarMax, this.beatsPerBar));
            }
            else if (command == 103) {
                this.barCount = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) + base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                this.barCount = Math.max(Config.barCountMin, Math.min(Config.barCountMax, this.barCount));
            }
            else if (command == 106) {
                this.patternsPerChannel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                this.patternsPerChannel = Math.max(Config.patternsPerChannelMin, Math.min(Config.patternsPerChannelMax, this.patternsPerChannel));
            }
            else if (command == 105) {
                this.instrumentsPerChannel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                this.instrumentsPerChannel = Math.max(Config.instrumentsPerChannelMin, Math.min(Config.instrumentsPerChannelMax, this.instrumentsPerChannel));
            }
            else if (command == 114) {
                this.partsPerBeat = Config.partCounts[base64CharCodeToInt[compressed.charCodeAt(charIndex++)]];
            }
            else if (command == 119) {
                if (beforeThree) {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.instrumentWaves[channel][0] = this._clip(0, Config.waveNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (var i = 0; i < this.instrumentsPerChannel; i++) {
                            this.instrumentWaves[channel][i] = this._clip(0, i < this.pitchChannelCount ? Config.waveNames.length : Config.drumNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                        }
                    }
                }
            }
            else if (command == 102) {
                if (beforeThree) {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.instrumentFilters[channel][0] = [0, 2, 3, 5][this._clip(0, Config.filterNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)])];
                }
                else {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (var i = 0; i < this.instrumentsPerChannel; i++) {
                            this.instrumentFilters[channel][i] = this._clip(0, Config.filterNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                        }
                    }
                }
            }
            else if (command == 100) {
                if (beforeThree) {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.instrumentEnvelopes[channel][0] = this._clip(0, Config.envelopeNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (var i = 0; i < this.instrumentsPerChannel; i++) {
                            this.instrumentEnvelopes[channel][i] = this._clip(0, Config.envelopeNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                        }
                    }
                }
            }
            else if (command == 99) {
                if (beforeThree) {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.instrumentEffects[channel][0] = this._clip(0, Config.effectNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    if (this.instrumentEffects[channel][0] == 1)
                        this.instrumentEffects[channel][0] = 3;
                    else if (this.instrumentEffects[channel][0] == 3)
                        this.instrumentEffects[channel][0] = 5;
                }
                else {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (var i = 0; i < this.instrumentsPerChannel; i++) {
                            this.instrumentEffects[channel][i] = this._clip(0, Config.effectNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                        }
                    }
                }
            }
            else if (command == 104) {
                if (beforeThree) {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.instrumentChorus[channel][0] = this._clip(0, Config.chorusNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (var i = 0; i < this.instrumentsPerChannel; i++) {
                            this.instrumentChorus[channel][i] = this._clip(0, Config.chorusNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                        }
                    }
                }
            }
            else if (command == 118) {
                if (beforeThree) {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.instrumentVolumes[channel][0] = this._clip(0, Config.volumeNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (var i = 0; i < this.instrumentsPerChannel; i++) {
                            this.instrumentVolumes[channel][i] = this._clip(0, Config.volumeNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                        }
                    }
                }
            }
            else if (command == 111) {
                if (beforeThree) {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.channelOctaves[channel] = this._clip(0, 5, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        this.channelOctaves[channel] = this._clip(0, 5, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    }
                }
            }
            else if (command == 98) {
                var subStringLength = void 0;
                if (beforeThree) {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    var barCount = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    subStringLength = Math.ceil(barCount * 0.5);
                    var bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + subStringLength);
                    for (var i = 0; i < barCount; i++) {
                        this.channelBars[channel][i] = bits.read(3) + 1;
                    }
                }
                else if (beforeFive) {
                    var neededBits = 0;
                    while ((1 << neededBits) < this.patternsPerChannel)
                        neededBits++;
                    subStringLength = Math.ceil(this.getChannelCount() * this.barCount * neededBits / 6);
                    var bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + subStringLength);
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        this.channelBars[channel].length = this.barCount;
                        for (var i = 0; i < this.barCount; i++) {
                            this.channelBars[channel][i] = bits.read(neededBits) + 1;
                        }
                    }
                }
                else {
                    var neededBits2 = 0;
                    while ((1 << neededBits2) < this.patternsPerChannel + 1)
                        neededBits2++;
                    subStringLength = Math.ceil(this.getChannelCount() * this.barCount * neededBits2 / 6);
                    var bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + subStringLength);
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        this.channelBars[channel].length = this.barCount;
                        for (var i = 0; i < this.barCount; i++) {
                            this.channelBars[channel][i] = bits.read(neededBits2);
                        }
                    }
                }
                charIndex += subStringLength;
            }
            else if (command == 112) {
                var bitStringLength = 0;
                if (beforeThree) {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    charIndex++;
                    bitStringLength = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    bitStringLength = bitStringLength << 6;
                    bitStringLength += base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                }
                else {
                    channel = 0;
                    var bitStringLengthLength = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    while (bitStringLengthLength > 0) {
                        bitStringLength = bitStringLength << 6;
                        bitStringLength += base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                        bitStringLengthLength--;
                    }
                }
                var bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + bitStringLength);
                charIndex += bitStringLength;
                var neededInstrumentBits = 0;
                while ((1 << neededInstrumentBits) < this.instrumentsPerChannel)
                    neededInstrumentBits++;
                while (true) {
                    this.channelPatterns[channel] = [];
                    var isDrum = this.getChannelIsDrum(channel);
                    var octaveOffset = isDrum ? 0 : this.channelOctaves[channel] * 12;
                    var note = null;
                    var pin = null;
                    var lastPitch = (isDrum ? 4 : 12) + octaveOffset;
                    var recentPitches = isDrum ? [4, 6, 7, 2, 3, 8, 0, 10] : [12, 19, 24, 31, 36, 7, 0];
                    var recentShapes = [];
                    for (var i = 0; i < recentPitches.length; i++) {
                        recentPitches[i] += octaveOffset;
                    }
                    for (var i = 0; i < this.patternsPerChannel; i++) {
                        var newPattern = new BarPattern();
                        newPattern.instrument = bits.read(neededInstrumentBits);
                        this.channelPatterns[channel][i] = newPattern;
                        if (!beforeThree && bits.read(1) == 0)
                            continue;
                        var curPart = 0;
                        var newNotes = [];
                        while (curPart < this.beatsPerBar * this.partsPerBeat) {
                            var useOldShape = bits.read(1) == 1;
                            var newNote = false;
                            var shapeIndex = 0;
                            if (useOldShape) {
                                shapeIndex = bits.readLongTail(0, 0);
                            }
                            else {
                                newNote = bits.read(1) == 1;
                            }
                            if (!useOldShape && !newNote) {
                                var restLength = bits.readPartDuration();
                                curPart += restLength;
                            }
                            else {
                                var shape = void 0;
                                var pinObj = void 0;
                                var pitch = void 0;
                                if (useOldShape) {
                                    shape = recentShapes[shapeIndex];
                                    recentShapes.splice(shapeIndex, 1);
                                }
                                else {
                                    shape = {};
                                    shape.pitchCount = 1;
                                    while (shape.pitchCount < 4 && bits.read(1) == 1)
                                        shape.pitchCount++;
                                    shape.pinCount = bits.readPinCount();
                                    shape.initialVolume = bits.read(2);
                                    shape.pins = [];
                                    shape.length = 0;
                                    shape.bendCount = 0;
                                    for (var j = 0; j < shape.pinCount; j++) {
                                        pinObj = {};
                                        pinObj.pitchBend = bits.read(1) == 1;
                                        if (pinObj.pitchBend)
                                            shape.bendCount++;
                                        shape.length += bits.readPartDuration();
                                        pinObj.time = shape.length;
                                        pinObj.volume = bits.read(2);
                                        shape.pins.push(pinObj);
                                    }
                                }
                                recentShapes.unshift(shape);
                                if (recentShapes.length > 10)
                                    recentShapes.pop();
                                note = makeNote(0, curPart, curPart + shape.length, shape.initialVolume);
                                note.pitches = [];
                                note.pins.length = 1;
                                var pitchBends = [];
                                for (var j = 0; j < shape.pitchCount + shape.bendCount; j++) {
                                    var useOldPitch = bits.read(1) == 1;
                                    if (!useOldPitch) {
                                        var interval = bits.readPitchInterval();
                                        pitch = lastPitch;
                                        var intervalIter = interval;
                                        while (intervalIter > 0) {
                                            pitch++;
                                            while (recentPitches.indexOf(pitch) != -1)
                                                pitch++;
                                            intervalIter--;
                                        }
                                        while (intervalIter < 0) {
                                            pitch--;
                                            while (recentPitches.indexOf(pitch) != -1)
                                                pitch--;
                                            intervalIter++;
                                        }
                                    }
                                    else {
                                        var pitchIndex = bits.read(3);
                                        pitch = recentPitches[pitchIndex];
                                        recentPitches.splice(pitchIndex, 1);
                                    }
                                    recentPitches.unshift(pitch);
                                    if (recentPitches.length > 8)
                                        recentPitches.pop();
                                    if (j < shape.pitchCount) {
                                        note.pitches.push(pitch);
                                    }
                                    else {
                                        pitchBends.push(pitch);
                                    }
                                    if (j == shape.pitchCount - 1) {
                                        lastPitch = note.pitches[0];
                                    }
                                    else {
                                        lastPitch = pitch;
                                    }
                                }
                                pitchBends.unshift(note.pitches[0]);
                                for (var _i = 0, _a = shape.pins; _i < _a.length; _i++) {
                                    var pinObj_1 = _a[_i];
                                    if (pinObj_1.pitchBend)
                                        pitchBends.shift();
                                    pin = makeNotePin(pitchBends[0] - note.pitches[0], pinObj_1.time, pinObj_1.volume);
                                    note.pins.push(pin);
                                }
                                curPart = note.end;
                                newNotes.push(note);
                            }
                        }
                        newPattern.notes = newNotes;
                    }
                    if (beforeThree) {
                        break;
                    }
                    else {
                        channel++;
                        if (channel >= this.getChannelCount())
                            break;
                    }
                }
            }
        }
    };
    Song.prototype.toJsonObject = function (enableIntro, loopCount, enableOutro) {
        if (enableIntro === void 0) { enableIntro = true; }
        if (loopCount === void 0) { loopCount = 1; }
        if (enableOutro === void 0) { enableOutro = true; }
        var channelArray = [];
        for (var channel = 0; channel < this.getChannelCount(); channel++) {
            var instrumentArray = [];
            var isDrum = this.getChannelIsDrum(channel);
            for (var i = 0; i < this.instrumentsPerChannel; i++) {
                if (isDrum) {
                    instrumentArray.push({
                        volume: (5 - this.instrumentVolumes[channel][i]) * 20,
                        wave: Config.drumNames[this.instrumentWaves[channel][i]],
                        envelope: Config.envelopeNames[this.instrumentEnvelopes[channel][i]],
                    });
                }
                else {
                    instrumentArray.push({
                        volume: (5 - this.instrumentVolumes[channel][i]) * 20,
                        wave: Config.waveNames[this.instrumentWaves[channel][i]],
                        envelope: Config.envelopeNames[this.instrumentEnvelopes[channel][i]],
                        filter: Config.filterNames[this.instrumentFilters[channel][i]],
                        chorus: Config.chorusNames[this.instrumentChorus[channel][i]],
                        effect: Config.effectNames[this.instrumentEffects[channel][i]],
                    });
                }
            }
            var patternArray = [];
            for (var _i = 0, _a = this.channelPatterns[channel]; _i < _a.length; _i++) {
                var pattern = _a[_i];
                var noteArray = [];
                for (var _b = 0, _c = pattern.notes; _b < _c.length; _b++) {
                    var note = _c[_b];
                    var pointArray = [];
                    for (var _d = 0, _e = note.pins; _d < _e.length; _d++) {
                        var pin = _e[_d];
                        pointArray.push({
                            tick: pin.time + note.start,
                            pitchBend: pin.interval,
                            volume: Math.round(pin.volume * 100 / 3),
                        });
                    }
                    noteArray.push({
                        pitches: note.pitches,
                        points: pointArray,
                    });
                }
                patternArray.push({
                    instrument: pattern.instrument + 1,
                    notes: noteArray,
                });
            }
            var sequenceArray = [];
            if (enableIntro)
                for (var i = 0; i < this.loopStart; i++) {
                    sequenceArray.push(this.channelBars[channel][i]);
                }
            for (var l = 0; l < loopCount; l++)
                for (var i = this.loopStart; i < this.loopStart + this.loopLength; i++) {
                    sequenceArray.push(this.channelBars[channel][i]);
                }
            if (enableOutro)
                for (var i = this.loopStart + this.loopLength; i < this.barCount; i++) {
                    sequenceArray.push(this.channelBars[channel][i]);
                }
            channelArray.push({
                octaveScrollBar: this.channelOctaves[channel],
                instruments: instrumentArray,
                patterns: patternArray,
                sequence: sequenceArray,
                type: isDrum ? "drum" : "pitch",
            });
        }
        return {
            version: Song._latestVersion,
            scale: Config.scaleNames[this.scale],
            key: Config.keyNames[this.key],
            introBars: this.loopStart,
            loopBars: this.loopLength,
            beatsPerBar: this.beatsPerBar,
            ticksPerBeat: this.partsPerBeat,
            beatsPerMinute: this.getBeatsPerMinute(),
            reverb: this.reverb,
			blend: this.blend,
			riff: this.riff,
            channels: channelArray,
        };
    };
    Song.prototype.fromJsonObject = function (jsonObject) {
        this.initToDefault();
        if (!jsonObject)
            return;
        var version = jsonObject.version;
        if (version !== 5)
            return;
        this.scale = 11;
        if (jsonObject.scale != undefined) {
            var oldScaleNames = { "romani :)": 8, "romani :(": 9 };
            var scale = oldScaleNames[jsonObject.scale] != undefined ? oldScaleNames[jsonObject.scale] : Config.scaleNames.indexOf(jsonObject.scale);
            if (scale != -1)
                this.scale = scale;
        }
        if (jsonObject.key != undefined) {
            if (typeof (jsonObject.key) == "number") {
                this.key = Config.keyNames.length - 1 - (((jsonObject.key + 1200) >>> 0) % Config.keyNames.length);
            }
            else if (typeof (jsonObject.key) == "string") {
                var key = jsonObject.key;
                var letter = key.charAt(0).toUpperCase();
                var symbol = key.charAt(1).toLowerCase();
                var letterMap = { "C": 11, "D": 9, "E": 7, "F": 6, "G": 4, "A": 2, "B": 0 };
                var accidentalMap = { "♭": -1, "♭": -1, "#": 1, "♭": 1 };
                var index = letterMap[letter];
                var offset = accidentalMap[symbol];
                if (index != undefined) {
                    if (offset != undefined)
                        index += offset;
                    if (index < 0)
                        index += 12;
                    index = index % 12;
                    this.key = index;
                }
            }
        }
        if (jsonObject.beatsPerMinute != undefined) {
            var bpm = jsonObject.beatsPerMinute | 0;
            this.tempo = Math.round(4.0 + 9.0 * Math.log(bpm / 120) / Math.LN2);
            this.tempo = this._clip(0, Config.tempoNames.length, this.tempo);
        }
        if (jsonObject.reverb != undefined) {
            this.reverb = this._clip(0, Config.reverbRange, jsonObject.reverb | 0);
        }
		if (jsonObject.blend != undefined) {
            this.blend = this._clip(0, Config.blendRange, jsonObject.blend | 0);
        }
		if (jsonObject.riff != undefined) {
            this.riff = this._clip(0, Config.riffRange, jsonObject.riff | 0);
        }
        if (jsonObject.beatsPerBar != undefined) {
            this.beatsPerBar = Math.max(Config.beatsPerBarMin, Math.min(Config.beatsPerBarMax, jsonObject.beatsPerBar | 0));
        }
        if (jsonObject.ticksPerBeat != undefined) {
            this.partsPerBeat = Math.max(3, Math.min(4, jsonObject.ticksPerBeat | 0));
        }
        var maxInstruments = 1;
        var maxPatterns = 1;
        var maxBars = 1;
        if (jsonObject.channels) {
            for (var _i = 0, _a = jsonObject.channels; _i < _a.length; _i++) {
                var channelObject = _a[_i];
                if (channelObject.instruments)
                    maxInstruments = Math.max(maxInstruments, channelObject.instruments.length | 0);
                if (channelObject.patterns)
                    maxPatterns = Math.max(maxPatterns, channelObject.patterns.length | 0);
                if (channelObject.sequence)
                    maxBars = Math.max(maxBars, channelObject.sequence.length | 0);
            }
        }
        this.instrumentsPerChannel = maxInstruments;
        this.patternsPerChannel = maxPatterns;
        this.barCount = maxBars;
        if (jsonObject.introBars != undefined) {
            this.loopStart = this._clip(0, this.barCount, jsonObject.introBars | 0);
        }
        if (jsonObject.loopBars != undefined) {
            this.loopLength = this._clip(1, this.barCount - this.loopStart + 1, jsonObject.loopBars | 0);
        }
        var pitchChannelCount = 0;
        var drumChannelCount = 0;
        if (jsonObject.channels) {
            this.instrumentVolumes.length = jsonObject.channels.length;
            this.instrumentWaves.length = jsonObject.channels.length;
            this.instrumentEnvelopes.length = jsonObject.channels.length;
            this.instrumentFilters.length = jsonObject.channels.length;
            this.instrumentChorus.length = jsonObject.channels.length;
            this.instrumentEffects.length = jsonObject.channels.length;
            this.channelPatterns.length = jsonObject.channels.length;
            this.channelOctaves.length = jsonObject.channels.length;
            this.channelBars.length = jsonObject.channels.length;
            for (var channel = 0; channel < jsonObject.channels.length; channel++) {
                var channelObject = jsonObject.channels[channel];
                if (channelObject.octaveScrollBar != undefined) {
                    this.channelOctaves[channel] = this._clip(0, 5, channelObject.octaveScrollBar | 0);
                }
                this.instrumentVolumes[channel] = [];
                this.instrumentWaves[channel] = [];
                this.instrumentEnvelopes[channel] = [];
                this.instrumentFilters[channel] = [];
                this.instrumentChorus[channel] = [];
                this.instrumentEffects[channel] = [];
                this.channelPatterns[channel] = [];
                this.channelBars[channel] = [];
                this.instrumentVolumes[channel].length = this.instrumentsPerChannel;
                this.instrumentWaves[channel].length = this.instrumentsPerChannel;
                this.instrumentEnvelopes[channel].length = this.instrumentsPerChannel;
                this.instrumentFilters[channel].length = this.instrumentsPerChannel;
                this.instrumentChorus[channel].length = this.instrumentsPerChannel;
                this.instrumentEffects[channel].length = this.instrumentsPerChannel;
                this.channelPatterns[channel].length = this.patternsPerChannel;
                this.channelBars[channel].length = this.barCount;
                var isDrum = false;
                if (channelObject.type) {
                    isDrum = (channelObject.type == "drum");
                }
                else {
                    isDrum = (channel >= 3);
                }
                if (isDrum)
                    drumChannelCount++;
                else
                    pitchChannelCount++;
                for (var i = 0; i < this.instrumentsPerChannel; i++) {
                    var instrumentObject = undefined;
                    if (channelObject.instruments)
                        instrumentObject = channelObject.instruments[i];
                    if (instrumentObject == undefined)
                        instrumentObject = {};
                    if (instrumentObject.volume != undefined) {
                        this.instrumentVolumes[channel][i] = this._clip(0, Config.volumeNames.length, Math.round(5 - (instrumentObject.volume | 0) / 20));
                    }
                    else {
                        this.instrumentVolumes[channel][i] = 0;
                    }
                    var oldEnvelopeNames = { "binary": 0 };
                    this.instrumentEnvelopes[channel][i] = oldEnvelopeNames[instrumentObject.envelope] != undefined ? oldEnvelopeNames[instrumentObject.envelope] : Config.envelopeNames.indexOf(instrumentObject.envelope);
                    if (this.instrumentEnvelopes[channel][i] == -1)
                        this.instrumentEnvelopes[channel][i] = 1;
                    if (isDrum) {
                        this.instrumentWaves[channel][i] = Config.drumNames.indexOf(instrumentObject.wave);
                        if (this.instrumentWaves[channel][i] == -1)
                            this.instrumentWaves[channel][i] = 1;
                        this.instrumentFilters[channel][i] = 0;
                        this.instrumentChorus[channel][i] = 0;
                        this.instrumentEffects[channel][i] = 0;
                    }
                    else {
                        this.instrumentWaves[channel][i] = Config.waveNames.indexOf(instrumentObject.wave);
                        if (this.instrumentWaves[channel][i] == -1)
                            this.instrumentWaves[channel][i] = 1;
                        this.instrumentFilters[channel][i] = Config.filterNames.indexOf(instrumentObject.filter);
                        if (this.instrumentFilters[channel][i] == -1)
                            this.instrumentFilters[channel][i] = 0;
                        this.instrumentChorus[channel][i] = Config.chorusNames.indexOf(instrumentObject.chorus);
                        if (this.instrumentChorus[channel][i] == -1)
                            this.instrumentChorus[channel][i] = 0;
                        this.instrumentEffects[channel][i] = Config.effectNames.indexOf(instrumentObject.effect);
                        if (this.instrumentEffects[channel][i] == -1)
                            this.instrumentEffects[channel][i] = 0;
                    }
                }
                for (var i = 0; i < this.patternsPerChannel; i++) {
                    var pattern = new BarPattern();
                    this.channelPatterns[channel][i] = pattern;
                    var patternObject = undefined;
                    if (channelObject.patterns)
                        patternObject = channelObject.patterns[i];
                    if (patternObject == undefined)
                        continue;
                    pattern.instrument = this._clip(0, this.instrumentsPerChannel, (patternObject.instrument | 0) - 1);
                    if (patternObject.notes && patternObject.notes.length > 0) {
                        var maxNoteCount = Math.min(this.beatsPerBar * this.partsPerBeat, patternObject.notes.length >>> 0);
                        var tickClock = 0;
                        for (var j = 0; j < patternObject.notes.length; j++) {
                            if (j >= maxNoteCount)
                                break;
                            var noteObject = patternObject.notes[j];
                            if (!noteObject || !noteObject.pitches || !(noteObject.pitches.length >= 1) || !noteObject.points || !(noteObject.points.length >= 2)) {
                                continue;
                            }
                            var note = makeNote(0, 0, 0, 0);
                            note.pitches = [];
                            note.pins = [];
                            for (var k = 0; k < noteObject.pitches.length; k++) {
                                var pitch = noteObject.pitches[k] | 0;
                                if (note.pitches.indexOf(pitch) != -1)
                                    continue;
                                note.pitches.push(pitch);
                                if (note.pitches.length >= 4)
                                    break;
                            }
                            if (note.pitches.length < 1)
                                continue;
                            var noteClock = tickClock;
                            var startInterval = 0;
                            for (var k = 0; k < noteObject.points.length; k++) {
                                var pointObject = noteObject.points[k];
                                if (pointObject == undefined || pointObject.tick == undefined)
                                    continue;
                                var interval = (pointObject.pitchBend == undefined) ? 0 : (pointObject.pitchBend | 0);
                                var time = pointObject.tick | 0;
                                var volume = (pointObject.volume == undefined) ? 3 : Math.max(0, Math.min(3, Math.round((pointObject.volume | 0) * 3 / 100)));
                                if (time > this.beatsPerBar * this.partsPerBeat)
                                    continue;
                                if (note.pins.length == 0) {
                                    if (time < noteClock)
                                        continue;
                                    note.start = time;
                                    startInterval = interval;
                                }
                                else {
                                    if (time <= noteClock)
                                        continue;
                                }
                                noteClock = time;
                                note.pins.push(makeNotePin(interval - startInterval, time - note.start, volume));
                            }
                            if (note.pins.length < 2)
                                continue;
                            note.end = note.pins[note.pins.length - 1].time + note.start;
                            var maxPitch = isDrum ? Config.drumCount - 1 : Config.maxPitch;
                            var lowestPitch = maxPitch;
                            var highestPitch = 0;
                            for (var k = 0; k < note.pitches.length; k++) {
                                note.pitches[k] += startInterval;
                                if (note.pitches[k] < 0 || note.pitches[k] > maxPitch) {
                                    note.pitches.splice(k, 1);
                                    k--;
                                }
                                if (note.pitches[k] < lowestPitch)
                                    lowestPitch = note.pitches[k];
                                if (note.pitches[k] > highestPitch)
                                    highestPitch = note.pitches[k];
                            }
                            if (note.pitches.length < 1)
                                continue;
                            for (var k = 0; k < note.pins.length; k++) {
                                var pin = note.pins[k];
                                if (pin.interval + lowestPitch < 0)
                                    pin.interval = -lowestPitch;
                                if (pin.interval + highestPitch > maxPitch)
                                    pin.interval = maxPitch - highestPitch;
                                if (k >= 2) {
                                    if (pin.interval == note.pins[k - 1].interval &&
                                        pin.interval == note.pins[k - 2].interval &&
                                        pin.volume == note.pins[k - 1].volume &&
                                        pin.volume == note.pins[k - 2].volume) {
                                        note.pins.splice(k - 1, 1);
                                        k--;
                                    }
                                }
                            }
                            pattern.notes.push(note);
                            tickClock = note.end;
                        }
                    }
                }
                for (var i = 0; i < this.barCount; i++) {
                    this.channelBars[channel][i] = channelObject.sequence ? Math.min(this.patternsPerChannel, channelObject.sequence[i] >>> 0) : 0;
                }
            }
        }
        this.pitchChannelCount = pitchChannelCount;
        this.drumChannelCount = drumChannelCount;
    };
    Song.prototype._clip = function (min, max, val) {
        max = max - 1;
        if (val <= max) {
            if (val >= min)
                return val;
            else
                return min;
        }
        else {
            return max;
        }
    };
    Song.prototype.getPattern = function (channel, bar) {
        var patternIndex = this.channelBars[channel][bar];
        if (patternIndex == 0)
            return null;
        return this.channelPatterns[channel][patternIndex - 1];
    };
    Song.prototype.getPatternInstrument = function (channel, bar) {
        var pattern = this.getPattern(channel, bar);
        return pattern == null ? 0 : pattern.instrument;
    };
    Song.prototype.getBeatsPerMinute = function () {
        return Math.round(120.0 * Math.pow(2.0, (-4.0 + this.tempo) / 9.0));
    };
    return Song;
}());
Song._oldestVersion = 2;
Song._latestVersion = 5;
Song._base64CharCodeToInt = [151, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 62, 62, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 0, 0, 0, 0, 0, 0, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 0, 0, 0, 0, 63, 0, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 0, 0, 0, 0, 0];
Song._base64IntToCharCode = [48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 45, 95, 0];
beepbox.Song = Song;
var Synth = (function () {
    function Synth(song) {
        var _this = this;
        this.samplesPerSecond = 44100;
        this.effectDuration = 0.14;
        this.effectAngle = Math.PI * 2.0 / (this.effectDuration * this.samplesPerSecond);
        this.effectYMult = 2.0 * Math.cos(this.effectAngle);
        this.limitDecay = 1.0 / (2.0 * this.samplesPerSecond);
        this.song = new Song(song);
        this.pianoPressed = false;
        this.pianoPitch = 0;
        this.pianoChannel = 0;
        this.enableIntro = true;
        this.enableOutro = true;
        this.loopCount = 1;
        this.volume = 1.0;
        this.playheadInternal = 0.0;
        this.bar = 0;
        this.beat = 0;
        this.part = 0;
        this.arpeggio = 0;
        this.arpeggioSampleCountdown = 0;
        this.paused = true;
        this.channelPlayheadA = [0.0, 0.0, 0.0, 0.0];
        this.channelPlayheadB = [0.0, 0.0, 0.0, 0.0];
        this.channelSample = [0.0, 0.0, 0.0, 0.0];
        this.drumPlayhead = 0.0;
        this.drumSample = 0.0;
        this.stillGoing = false;
        this.effectPlayhead = 0.0;
        this.limit = 0.0;
        this.delayLine = new Float32Array(16384);
        this.delayPos = 0;
        this.delayFeedback0 = 0.0;
        this.delayFeedback1 = 0.0;
        this.delayFeedback2 = 0.0;
        this.delayFeedback3 = 0.0;
        this.audioProcessCallback = function (audioProcessingEvent) {
            var outputBuffer = audioProcessingEvent.outputBuffer;
            var outputData = outputBuffer.getChannelData(0);
            _this.synthesize(outputData, outputBuffer.length);
        };
        if (song != null)
            this.setSong(song);
    }
    Synth.ensureGeneratedSynthesizerAndDrumWavesExist = function (song) {
        if (song != null) {
            for (var i = 0; i < song.instrumentsPerChannel; i++) {
                for (var j = song.pitchChannelCount; j < song.pitchChannelCount + song.drumChannelCount; j++) {
                    Config.getDrumWave(song.instrumentWaves[j][i]);
                }
            }
            Synth.getGeneratedSynthesizer(song.pitchChannelCount, song.drumChannelCount);
        }
    };
    Object.defineProperty(Synth.prototype, "playing", {
        get: function () {
            return !this.paused;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Synth.prototype, "playhead", {
        get: function () {
            return this.playheadInternal;
        },
        set: function (value) {
            if (this.song != null) {
                this.playheadInternal = Math.max(0, Math.min(this.song.barCount, value));
                var remainder = this.playheadInternal;
                this.bar = Math.floor(remainder);
                remainder = this.song.beatsPerBar * (remainder - this.bar);
                this.beat = Math.floor(remainder);
                remainder = this.song.partsPerBeat * (remainder - this.beat);
                this.part = Math.floor(remainder);
                remainder = 4 * (remainder - this.part);
                this.arpeggio = Math.floor(remainder);
                var samplesPerArpeggio = this.getSamplesPerArpeggio();
                remainder = samplesPerArpeggio * (remainder - this.arpeggio);
                this.arpeggioSampleCountdown = Math.floor(samplesPerArpeggio - remainder);
                if (this.bar < this.song.loopStart) {
                    this.enableIntro = true;
                }
                if (this.bar > this.song.loopStart + this.song.loopLength) {
                    this.enableOutro = true;
                }
            }
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Synth.prototype, "totalSamples", {
        get: function () {
            if (this.song == null)
                return 0;
            var samplesPerBar = this.getSamplesPerArpeggio() * 4 * this.song.partsPerBeat * this.song.beatsPerBar;
            var loopMinCount = this.loopCount;
            if (loopMinCount < 0)
                loopMinCount = 1;
            var bars = this.song.loopLength * loopMinCount;
            if (this.enableIntro)
                bars += this.song.loopStart;
            if (this.enableOutro)
                bars += this.song.barCount - (this.song.loopStart + this.song.loopLength);
            return bars * samplesPerBar;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Synth.prototype, "totalSeconds", {
        get: function () {
            return this.totalSamples / this.samplesPerSecond;
        },
        enumerable: true,
        configurable: true
    });
    Object.defineProperty(Synth.prototype, "totalBars", {
        get: function () {
            if (this.song == null)
                return 0.0;
            return this.song.barCount;
        },
        enumerable: true,
        configurable: true
    });
    Synth.prototype.setSong = function (song) {
        if (typeof (song) == "string") {
            this.song = new Song(song);
        }
        else if (song instanceof Song) {
            this.song = song;
        }
    };
    Synth.prototype.pause = function () {
        if (this.paused)
            return;
        this.paused = true;
        this.scriptNode.disconnect(this.audioCtx.destination);
        if (this.audioCtx.close) {
            this.audioCtx.close();
            this.audioCtx = null;
        }
        this.scriptNode = null;
    };
    Synth.prototype.snapToStart = function () {
        this.bar = 0;
        this.enableIntro = true;
        this.snapToBar();
    };
    Synth.prototype.snapToBar = function () {
        this.playheadInternal = this.bar;
        this.beat = 0;
        this.part = 0;
        this.arpeggio = 0;
        this.arpeggioSampleCountdown = 0;
        this.effectPlayhead = 0.0;
        this.channelSample[0] = 0.0;
        this.channelSample[1] = 0.0;
        this.channelSample[2] = 0.0;
        this.drumSample = 0.0;
        this.delayPos = 0;
        this.delayFeedback0 = 0.0;
        this.delayFeedback1 = 0.0;
        this.delayFeedback2 = 0.0;
        this.delayFeedback3 = 0.0;
        for (var i = 0; i < this.delayLine.length; i++)
            this.delayLine[i] = 0.0;
    };
    Synth.prototype.nextBar = function () {
        if (!this.song)
            return;
        var oldBar = this.bar;
        this.bar++;
        if (this.enableOutro) {
            if (this.bar >= this.song.barCount) {
                this.bar = this.enableIntro ? 0 : this.song.loopStart;
            }
        }
        else {
            if (this.bar >= this.song.loopStart + this.song.loopLength || this.bar >= this.song.barCount) {
                this.bar = this.song.loopStart;
            }
        }
        this.playheadInternal += this.bar - oldBar;
    };
    Synth.prototype.prevBar = function () {
        if (!this.song)
            return;
        var oldBar = this.bar;
        this.bar--;
        if (this.bar < 0) {
            this.bar = this.song.loopStart + this.song.loopLength - 1;
        }
        if (this.bar >= this.song.barCount) {
            this.bar = this.song.barCount - 1;
        }
        if (this.bar < this.song.loopStart) {
            this.enableIntro = true;
        }
        if (!this.enableOutro && this.bar >= this.song.loopStart + this.song.loopLength) {
            this.bar = this.song.loopStart + this.song.loopLength - 1;
        }
        this.playheadInternal += this.bar - oldBar;
    };
    Synth.prototype.synthesize = function (data, totalSamples) {
        if (this.song == null) {
            for (var i = 0; i < totalSamples; i++) {
                data[i] = 0.0;
            }
            return;
        }
        var channelCount = this.song.getChannelCount();
        if (this.channelPlayheadA.length != channelCount) {
            for (var i = 0; i < channelCount; i++)
                this.channelPlayheadA[i] = 0.0;
            this.channelPlayheadA.length = channelCount;
        }
        if (this.channelPlayheadB.length != channelCount) {
            for (var i = 0; i < channelCount; i++)
                this.channelPlayheadB[i] = 0.0;
            this.channelPlayheadB.length = channelCount;
        }
        if (this.channelSample.length != channelCount) {
            for (var i = 0; i < channelCount; i++)
                this.channelSample[i] = 0.0;
            this.channelSample.length = channelCount;
        }
        var generatedSynthesizer = Synth.getGeneratedSynthesizer(this.song.pitchChannelCount, this.song.drumChannelCount);
        generatedSynthesizer(this, this.song, data, totalSamples);
    };
    Synth.computeChannelInstrument = function (synth, song, channel, time, sampleTime, samplesPerArpeggio, samples, isDrum) {
        var pattern = song.getPattern(channel, synth.bar);
        var envelope = pattern == null ? 0 : song.instrumentEnvelopes[channel][pattern.instrument];
        var channelRoot = isDrum ? Config.drumPitchRoots[song.instrumentWaves[channel][pattern == null ? 0 : pattern.instrument]] : Config.keyTransposes[song.key];
        var intervalScale = isDrum ? Config.drumInterval : 1;
        var note = null;
        var prevNote = null;
        var nextNote = null;
        if (pattern != null) {
            for (var i = 0; i < pattern.notes.length; i++) {
                if (pattern.notes[i].end <= time) {
                    prevNote = pattern.notes[i];
                }
                else if (pattern.notes[i].start <= time && pattern.notes[i].end > time) {
                    note = pattern.notes[i];
                }
                else if (pattern.notes[i].start > time) {
                    nextNote = pattern.notes[i];
                    break;
                }
            }
        }
        if (note != null && prevNote != null && prevNote.end != note.start)
            prevNote = null;
        if (note != null && nextNote != null && nextNote.start != note.end)
            nextNote = null;
        var periodDelta;
        var periodDeltaScale = 1.0;
        var noteVolume;
        var volumeDelta = 0.0;
        var filter = 1.0;
        var filterScale = 1.0;
        var vibratoScale;
        var harmonyMult = 1.0;
        var resetPlayheads = false;
        if (synth.pianoPressed && channel == synth.pianoChannel) {
            var pianoFreq = synth.frequencyFromPitch(channelRoot + synth.pianoPitch * intervalScale);
            var instrument = pattern ? pattern.instrument : 0;
            var pianoPitchDamping = void 0;
            if (isDrum) {
                if (Config.drumWaveIsSoft[song.instrumentWaves[channel][instrument]]) {
                    filter = Math.min(1.0, pianoFreq * sampleTime * Config.drumPitchFilterMult[song.instrumentWaves[channel][pattern.instrument]]);
                    pianoPitchDamping = 24.0;
                }
                else {
                    pianoPitchDamping = 60.0;
                }
            }
            else {
                pianoPitchDamping = 48.0;
            }
            periodDelta = pianoFreq * sampleTime;
            noteVolume = Math.pow(2.0, -synth.pianoPitch * intervalScale / pianoPitchDamping);
            vibratoScale = Math.pow(2.0, Config.effectVibratos[song.instrumentEffects[channel][instrument]] / 12.0) - 1.0;
        }
        else if (note == null) {
            periodDelta = 0.0;
            periodDeltaScale = 0.0;
            noteVolume = 0.0;
            vibratoScale = 0.0;
            resetPlayheads = true;
        }
        else {
            var chorusHarmonizes = Config.chorusHarmonizes[song.instrumentChorus[channel][pattern.instrument]];
            var pitch = note.pitches[0];
            if (chorusHarmonizes) {
                var harmonyOffset = 0.0;
                if (note.pitches.length == 2) {
                    harmonyOffset = note.pitches[1] - note.pitches[0];
                }
                else if (note.pitches.length == 3) {
                    harmonyOffset = note.pitches[(synth.arpeggio >> 1) + 1] - note.pitches[0];
                }
                else if (note.pitches.length == 4) {
                    harmonyOffset = note.pitches[(synth.arpeggio == 3 ? 1 : synth.arpeggio) + 1] - note.pitches[0];
                }
                harmonyMult = Math.pow(2.0, harmonyOffset / 12.0);
            }
            else {
                if (note.pitches.length == 2) {
                    pitch = note.pitches[synth.arpeggio >> 1];
                }
                else if (note.pitches.length == 3) {
                    pitch = note.pitches[synth.arpeggio == 3 ? 1 : synth.arpeggio];
                }
                else if (note.pitches.length == 4) {
                    pitch = note.pitches[synth.arpeggio];
                }
            }
            var endPinIndex = void 0;
            for (endPinIndex = 1; endPinIndex < note.pins.length - 1; endPinIndex++) {
                if (note.pins[endPinIndex].time + note.start > time)
                    break;
            }
            var startPin = note.pins[endPinIndex - 1];
            var endPin = note.pins[endPinIndex];
            var noteStart = note.start * 4;
            var noteEnd = note.end * 4;
            var pinStart = (note.start + startPin.time) * 4;
            var pinEnd = (note.start + endPin.time) * 4;
            var arpeggioStart = time * 4 + synth.arpeggio;
            var arpeggioEnd = time * 4 + synth.arpeggio + 1;
            var arpeggioRatioStart = (arpeggioStart - pinStart) / (pinEnd - pinStart);
            var arpeggioRatioEnd = (arpeggioEnd - pinStart) / (pinEnd - pinStart);
            var arpeggioVolumeStart = startPin.volume * (1.0 - arpeggioRatioStart) + endPin.volume * arpeggioRatioStart;
            var arpeggioVolumeEnd = startPin.volume * (1.0 - arpeggioRatioEnd) + endPin.volume * arpeggioRatioEnd;
            var arpeggioIntervalStart = startPin.interval * (1.0 - arpeggioRatioStart) + endPin.interval * arpeggioRatioStart;
            var arpeggioIntervalEnd = startPin.interval * (1.0 - arpeggioRatioEnd) + endPin.interval * arpeggioRatioEnd;
            var arpeggioFilterTimeStart = startPin.time * (1.0 - arpeggioRatioStart) + endPin.time * arpeggioRatioStart;
            var arpeggioFilterTimeEnd = startPin.time * (1.0 - arpeggioRatioEnd) + endPin.time * arpeggioRatioEnd;
            var inhibitRestart = false;
            if (arpeggioStart == noteStart) {
                if (envelope == 0) {
                    inhibitRestart = true;
                }
                else if (envelope == 2) {
                    arpeggioVolumeStart = 0.0;
                }
				else if (envelope == 4) {
                    arpeggioVolumeEnd = 0.0
				}
                else if (envelope == 5) {
                    arpeggioIntervalStart = 100.0
				}
                else if (envelope == 6) {
                    arpeggioIntervalStart = -1.0
				}
                else if (envelope == 3) {
                    if (prevNote == null) {
                        arpeggioVolumeStart = 0.0;
                    }
                    else if (prevNote.pins[prevNote.pins.length - 1].volume == 0 || note.pins[0].volume == 0) {
                        arpeggioVolumeStart = 0.0;
                    }
                    else {
                        arpeggioIntervalStart = (prevNote.pitches[0] + prevNote.pins[prevNote.pins.length - 1].interval - pitch) * 0.5;
                        arpeggioFilterTimeStart = prevNote.pins[prevNote.pins.length - 1].time * 0.5;
                        inhibitRestart = true;
                    }
                }
            }
            if (arpeggioEnd == noteEnd) {
                if (envelope == 1 || envelope == 2) {
                    arpeggioVolumeEnd = 0.0;
                }
                else if (envelope == 3) {
                    if (nextNote == null) {
                        arpeggioVolumeEnd = 0.0;
                    }
                    else if (note.pins[note.pins.length - 1].volume == 0 || nextNote.pins[0].volume == 0) {
                        arpeggioVolumeEnd = 0.0;
                    }
                    else {
                        arpeggioIntervalEnd = (nextNote.pitches[0] + note.pins[note.pins.length - 1].interval - pitch) * 0.5;
                        arpeggioFilterTimeEnd *= 0.5;
                    }
                }
            }
            var startRatio = 1.0 - (synth.arpeggioSampleCountdown + samples) / samplesPerArpeggio;
            var endRatio = 1.0 - (synth.arpeggioSampleCountdown) / samplesPerArpeggio;
            var startInterval = arpeggioIntervalStart * (1.0 - startRatio) + arpeggioIntervalEnd * startRatio;
            var endInterval = arpeggioIntervalStart * (1.0 - endRatio) + arpeggioIntervalEnd * endRatio;
            var startFilterTime = arpeggioFilterTimeStart * (1.0 - startRatio) + arpeggioFilterTimeEnd * startRatio;
            var endFilterTime = arpeggioFilterTimeStart * (1.0 - endRatio) + arpeggioFilterTimeEnd * endRatio;
            var startFreq = synth.frequencyFromPitch(channelRoot + (pitch + startInterval) * intervalScale);
            var endFreq = synth.frequencyFromPitch(channelRoot + (pitch + endInterval) * intervalScale);
            var pitchDamping = void 0;
            if (isDrum) {
                if (Config.drumWaveIsSoft[song.instrumentWaves[channel][pattern.instrument]]) {
                    filter = Math.min(1.0, startFreq * sampleTime * Config.drumPitchFilterMult[song.instrumentWaves[channel][pattern.instrument]]);
                    pitchDamping = 24.0;
                }
                else {
                    pitchDamping = 60.0;
                }
            }
            else {
                pitchDamping = 48.0;
            }
            var startVol = Math.pow(2.0, -(pitch + startInterval) * intervalScale / pitchDamping);
            var endVol = Math.pow(2.0, -(pitch + endInterval) * intervalScale / pitchDamping);
            startVol *= synth.volumeConversion(arpeggioVolumeStart * (1.0 - startRatio) + arpeggioVolumeEnd * startRatio);
            endVol *= synth.volumeConversion(arpeggioVolumeStart * (1.0 - endRatio) + arpeggioVolumeEnd * endRatio);
            var freqScale = endFreq / startFreq;
            periodDelta = startFreq * sampleTime;
            periodDeltaScale = Math.pow(freqScale, 1.0 / samples);
            noteVolume = startVol;
            volumeDelta = (endVol - startVol) / samples;
            var timeSinceStart = (arpeggioStart + startRatio - noteStart) * samplesPerArpeggio / synth.samplesPerSecond;
            if (timeSinceStart == 0.0 && !inhibitRestart)
                resetPlayheads = true;
            if (!isDrum) {
                var filterScaleRate = Config.filterDecays[song.instrumentFilters[channel][pattern.instrument]];
                filter = Math.pow(2, -filterScaleRate * startFilterTime * 4.0 * samplesPerArpeggio / synth.samplesPerSecond);
                var endFilter = Math.pow(2, -filterScaleRate * endFilterTime * 4.0 * samplesPerArpeggio / synth.samplesPerSecond);
                filterScale = Math.pow(endFilter / filter, 1.0 / samples);
            }
            var vibratoDelay = Config.effectVibratoDelays[song.instrumentEffects[channel][pattern.instrument]];
            vibratoScale = (time - note.start < vibratoDelay) ? 0.0 : Math.pow(2.0, Config.effectVibratos[song.instrumentEffects[channel][pattern.instrument]] / 12.0) - 1.0;
        }
        return {
            periodDelta: periodDelta,
            periodDeltaScale: periodDeltaScale,
            noteVolume: noteVolume,
            volumeDelta: volumeDelta,
            filter: filter,
            filterScale: filterScale,
            vibratoScale: vibratoScale,
            harmonyMult: harmonyMult,
            resetPlayheads: resetPlayheads,
        };
    };
    Synth.getGeneratedSynthesizer = function (pitchChannelCount, drumChannelCount) {
        if (Synth.generatedSynthesizers[pitchChannelCount] == undefined) {
            Synth.generatedSynthesizers[pitchChannelCount] = [];
        }
        if (Synth.generatedSynthesizers[pitchChannelCount][drumChannelCount] == undefined) {
            var synthSource = [];
            for (var _i = 0, _a = Synth.synthSourceTemplate; _i < _a.length; _i++) {
                var line = _a[_i];
                if (line.indexOf("#") != -1) {
                    if (line.indexOf("// PITCH") != -1) {
                        for (var i = 0; i < pitchChannelCount; i++) {
                            synthSource.push(line.replace(/#/g, i + ""));
                        }
                    }
                    else if (line.indexOf("// DRUM") != -1) {
                        for (var i = pitchChannelCount; i < pitchChannelCount + drumChannelCount; i++) {
                            synthSource.push(line.replace(/#/g, i + ""));
                        }
                    }
                    else if (line.indexOf("// ALL") != -1) {
                        for (var i = 0; i < pitchChannelCount + drumChannelCount; i++) {
                            synthSource.push(line.replace(/#/g, i + ""));
                        }
                    }
                    else {
                        throw new Error("Missing channel type annotation for line: " + line);
                    }
                }
                else {
                    synthSource.push(line);
                }
            }

            global.beepbox = beepbox
            Synth.generatedSynthesizers[pitchChannelCount][drumChannelCount] = new Function("synth", "song", "data", "totalSamples", synthSource.join("\n"));
        }
        return Synth.generatedSynthesizers[pitchChannelCount][drumChannelCount];
    };
    Synth.prototype.frequencyFromPitch = function (pitch) {
        return 440.0 * Math.pow(2.0, (pitch - 69.0) / 12.0);
    };
    Synth.prototype.volumeConversion = function (noteVolume) {
        return Math.pow(noteVolume / 3.0, 1.5);
    };
    Synth.prototype.getSamplesPerArpeggio = function () {
        if (this.song == null)
            return 0;
        var beatsPerMinute = this.song.getBeatsPerMinute();
        var beatsPerSecond = beatsPerMinute / 60.0;
        var partsPerSecond = beatsPerSecond * this.song.partsPerBeat;
        var arpeggioPerSecond = partsPerSecond * 4.0;
        return Math.floor(this.samplesPerSecond / arpeggioPerSecond);
    };
    return Synth;
}());
Synth.generatedSynthesizers = [];
Synth.synthSourceTemplate = "\n\t\t\t\n\t\t\t var bufferIndex = 0;\n\t\t\t\n\t\t\t var sampleTime = 1.0 / synth.samplesPerSecond;\n\t\t\t var samplesPerArpeggio = synth.getSamplesPerArpeggio();\n\t\t\t var effectYMult = synth.effectYMult;\n\t\t\t var limitDecay = synth.limitDecay;\n\t\t\t var volume = synth.volume;\n\t\t\t var delayLine = synth.delayLine;\n\t\t\t var reverb = Math.pow(song.reverb / beepbox.Config.reverbRange, 0.667) * 0.425; \n\t\t\t var blend = Math.pow(song.blend / beepbox.Config.blendRange, 0.667) * 0.425; \n\t\t\t var riff = Math.pow(song.riff / beepbox.Config.riffRange, 0.667) * 0.425; \n\t\t\t var ended = false;\n\t\t\t\n\t\t\t // Check the bounds of the playhead:\n\t\t\t if (synth.arpeggioSampleCountdown == synth.arpeggioSampleCountdown > samplesPerArpeggio) {\n\t\t\t\t synth.arpeggioSampleCountdown = samplesPerArpeggio;\n\t\t\t }\n\t\t\t if (synth.part >= song.partsPerBeat) {\n\t\t\t\t synth.beat++;\n\t\t\t\t synth.part = 0;\n\t\t\t\t synth.arpeggio = 0;\n\t\t\t\t synth.arpeggioSampleCountdown = samplesPerArpeggio;\n\t\t\t }\n\t\t\t if (synth.beat >= song.beatsPerBar) {\n\t\t\t\t synth.bar++;\n\t\t\t\t synth.beat = 0;\n\t\t\t\t synth.part = 0;\n\t\t\t\t synth.arpeggio = 0;\n\t\t\t\t synth.arpeggioSampleCountdown = samplesPerArpeggio;\n\t\t\t\t\n\t\t\t\t if (synth.loopCount == -1) {\n\t\t\t\t\t if (synth.bar < song.loopStart && !synth.enableIntro) synth.bar = song.loopStart;\n\t\t\t\t\t if (synth.bar >= song.loopStart + song.loopLength && !synth.enableOutro) synth.bar = song.loopStart;\n\t\t\t\t }\n\t\t\t }\n\t\t\t if (synth.bar >= song.barCount) {\n\t\t\t\t if (synth.enableOutro) {\n\t\t\t\t\t synth.bar = 0;\n\t\t\t\t\t synth.enableIntro = true;\n\t\t\t\t\t ended = true;\n\t\t\t\t\t synth.pause();\n\t\t\t\t } else {\n\t\t\t\t\t synth.bar = song.loopStart;\n\t\t\t\t }\n\t\t\t }\n\t\t\t if (synth.bar >= song.loopStart) {\n\t\t\t\t synth.enableIntro = false;\n\t\t\t }\n\t\t\t\n\t\t\t while (totalSamples > 0) {\n\t\t\t\t if (ended) {\n\t\t\t\t\t while (totalSamples-- > 0) {\n\t\t\t\t\t\t data[bufferIndex] = 0.0;\n\t\t\t\t\t\t bufferIndex++;\n\t\t\t\t\t }\n\t\t\t\t\t break;\n\t\t\t\t }\n\t\t\t\t\n\t\t\t\t // Initialize instruments based on current pattern.\n\t\t\t\t var instrumentChannel# = song.getPatternInstrument(#, synth.bar); // ALL\n\t\t\t\t var maxChannel#Volume = 0.27 * (song.instrumentVolumes[#][instrumentChannel#] == 5 ? 0.0 : Math.pow(2, -beepbox.Config.volumeValues[song.instrumentVolumes[#][instrumentChannel#]])) * beepbox.Config.waveVolumes[song.instrumentWaves[#][instrumentChannel#]] * beepbox.Config.filterVolumes[song.instrumentFilters[#][instrumentChannel#]] * beepbox.Config.chorusVolumes[song.instrumentChorus[#][instrumentChannel#]] * 0.5; // PITCH\n\t\t\t\t var maxChannel#Volume = 0.19 * (song.instrumentVolumes[#][instrumentChannel#] == 5 ? 0.0 : Math.pow(2, -beepbox.Config.volumeValues[song.instrumentVolumes[#][instrumentChannel#]])) * beepbox.Config.drumVolumes[song.instrumentWaves[#][instrumentChannel#]]; // DRUM\n\t\t\t\t var channel#Wave = beepbox.Config.waves[song.instrumentWaves[#][instrumentChannel#]]; // PITCH\n\t\t\t\t var channel#Wave = beepbox.Config.getDrumWave(song.instrumentWaves[#][instrumentChannel#]); // DRUM\n\t\t\t\t var channel#WaveLength = channel#Wave.length; // PITCH\n\t\t\t\t var channel#FilterBase = Math.pow(2, -beepbox.Config.filterBases[song.instrumentFilters[#][instrumentChannel#]] + (blend * 4)); // PITCH\n\t\t\t\t var channel#TremoloScale = beepbox.Config.effectTremolos[song.instrumentEffects[#][instrumentChannel#]]; // PITCH\n\t\t\t\t\n\t\t\t\t // Reuse initialized instruments until getting to the end of the sample period or the end of the current bar.\n\t\t\t\t while (totalSamples > 0) {\n\t\t\t\t\t var samples;\n\t\t\t\t\t if (synth.arpeggioSampleCountdown <= totalSamples) {\n\t\t\t\t\t\t samples = synth.arpeggioSampleCountdown;\n\t\t\t\t\t } else {\n\t\t\t\t\t\t samples = totalSamples;\n\t\t\t\t\t }\n\t\t\t\t\t totalSamples -= samples;\n\t\t\t\t\t synth.arpeggioSampleCountdown -= samples;\n\t\t\t\t\t\n\t\t\t\t\t var time = synth.part + synth.beat * song.partsPerBeat;\n\t\t\t\t\n\t\t\t\t\t var channel#ChorusA = Math.pow(2.0, (beepbox.Config.chorusOffsets[song.instrumentChorus[#][instrumentChannel#]] + beepbox.Config.chorusIntervals[song.instrumentChorus[#][instrumentChannel#]] * (riff + 1)) / 12.0); // PITCH\n\t\t\t\t\t var channel#ChorusB = Math.pow(2.0, (beepbox.Config.chorusOffsets[song.instrumentChorus[#][instrumentChannel#]] - beepbox.Config.chorusIntervals[song.instrumentChorus[#][instrumentChannel#]] * (riff + 1)) / 12.0); // PITCH\n\t\t\t\t\t var channel#ChorusSign = (song.instrumentChorus[#][instrumentChannel#] == 7) ? -1.0 : 1.0; // PITCH\n\t\t\t\t\t if (song.instrumentChorus[#][instrumentChannel#] == 0) synth.channelPlayheadB[#] = synth.channelPlayheadA[#]; // PITCH\n\t\t\t\t\t\n\t\t\t\t\t var channel#PlayheadDelta = 0; // ALL\n\t\t\t\t\t var channel#PlayheadDeltaScale = 0; // ALL\n\t\t\t\t\t var channel#Volume = 0; // ALL\n\t\t\t\t\t var channel#VolumeDelta = 0; // ALL\n\t\t\t\t\t var channel#Filter = 0; // ALL\n\t\t\t\t\t var channel#FilterScale = 0; // PITCH\n\t\t\t\t\t var channel#VibratoScale = 0; // PITCH\n\t\t\t\t\t\n\t\t\t\t\t var instrument# = beepbox.Synth.computeChannelInstrument(synth, song, #, time, sampleTime, samplesPerArpeggio, samples, false); // PITCH\n\t\t\t\t\t var instrument# = beepbox.Synth.computeChannelInstrument(synth, song, #, time, sampleTime, samplesPerArpeggio, samples, true); // DRUM\n\t\t\t\t\t\n\t\t\t\t\t channel#PlayheadDelta = instrument#.periodDelta; // PITCH\n\t\t\t\t\t channel#PlayheadDelta = instrument#.periodDelta / 32768.0; // DRUM\n\t\t\t\t\t channel#PlayheadDeltaScale = instrument#.periodDeltaScale; // ALL\n\t\t\t\t\t channel#Volume = instrument#.noteVolume * maxChannel#Volume; // ALL\n\t\t\t\t\t channel#VolumeDelta = instrument#.volumeDelta * maxChannel#Volume; // ALL\n\t\t\t\t\t channel#Filter = instrument#.filter * channel#FilterBase; // PITCH\n\t\t\t\t\t channel#Filter = instrument#.filter; // DRUM\n\t\t\t\t\t channel#FilterScale = instrument#.filterScale; // PITCH\n\t\t\t\t\t channel#VibratoScale = instrument#.vibratoScale; // PITCH\n\t\t\t\t\t channel#ChorusB *= instrument#.harmonyMult; // PITCH\n\t\t\t\t\t if (instrument#.resetPlayheads) { synth.channelSample[#] = 0.0; synth.channelPlayheadA[#] = 0.0; synth.channelPlayheadB[#] = 0.0; } // PITCH\n\t\t\t\t\t\n\t\t\t\t\t var effectY = Math.sin(synth.effectPlayhead);\n\t\t\t\t\t var prevEffectY = Math.sin(synth.effectPlayhead - synth.effectAngle);\n\t\t\t\t\t\n\t\t\t\t\t var channel#PlayheadA = +synth.channelPlayheadA[#]; // PITCH\n\t\t\t\t\t var channel#PlayheadB = +synth.channelPlayheadB[#]; // PITCH\n\t\t\t\t\t var channel#Playhead  = +synth.channelPlayheadA[#]; // DRUM\n\t\t\t\t\t\n\t\t\t\t\t var channel#Sample = +synth.channelSample[#]; // ALL\n\t\t\t\t\t\n\t\t\t\t\t var delayPos = 0|synth.delayPos;\n\t\t\t\t\t var delayFeedback0 = +synth.delayFeedback0;\n\t\t\t\t\t var delayFeedback1 = +synth.delayFeedback1;\n\t\t\t\t\t var delayFeedback2 = +synth.delayFeedback2;\n\t\t\t\t\t var delayFeedback3 = +synth.delayFeedback3;\n\t\t\t\t\t var limit = +synth.limit;\n\t\t\t\t\t\n\t\t\t\t\t while (samples) {\n\t\t\t\t\t\t var channel#Vibrato = 1.0 + channel#VibratoScale * effectY; // PITCH\n\t\t\t\t\t\t var channel#Tremolo = 1.0 + channel#TremoloScale * (effectY - 1.0); // PITCH\n\t\t\t\t\t\t var temp = effectY;\n\t\t\t\t\t\t effectY = effectYMult * effectY - prevEffectY;\n\t\t\t\t\t\t prevEffectY = temp;\n\t\t\t\t\t\t\n\t\t\t\t\t\t channel#Sample += ((channel#Wave[0|(channel#PlayheadA * channel#WaveLength)] + channel#Wave[0|(channel#PlayheadB * channel#WaveLength)] * channel#ChorusSign) * channel#Volume * channel#Tremolo - channel#Sample) * channel#Filter; // PITCH\n\t\t\t\t\t\t channel#Sample += (channel#Wave[0|(channel#Playhead * 32768.0)] * channel#Volume - channel#Sample) * channel#Filter; // DRUM\n\t\t\t\t\t\t channel#Volume += channel#VolumeDelta; // ALL\n\t\t\t\t\t\t channel#PlayheadA += channel#PlayheadDelta * channel#Vibrato * channel#ChorusA; // PITCH\n\t\t\t\t\t\t channel#PlayheadB += channel#PlayheadDelta * channel#Vibrato * channel#ChorusB; // PITCH\n\t\t\t\t\t\t channel#Playhead += channel#PlayheadDelta; // DRUM\n\t\t\t\t\t\t channel#PlayheadDelta *= channel#PlayheadDeltaScale; // ALL\n\t\t\t\t\t\t channel#Filter *= channel#FilterScale; // PITCH\n\t\t\t\t\t\t channel#PlayheadA -= 0|channel#PlayheadA; // PITCH\n\t\t\t\t\t\t channel#PlayheadB -= 0|channel#PlayheadB; // PITCH\n\t\t\t\t\t\t channel#Playhead -= 0|channel#Playhead; // DRUM\n\t\t\t\t\t\t\n\t\t\t\t\t\t // Reverb, implemented using a feedback delay network with a Hadamard matrix and lowpass filters.\n\t\t\t\t\t\t // good ratios:    0.555235 + 0.618033 + 0.818 +   1.0 = 2.991268\n\t\t\t\t\t\t // Delay lengths:  3041     + 3385     + 4481  +  5477 = 16384 = 2^14\n\t\t\t\t\t\t // Buffer offsets: 3041    -> 6426   -> 10907 -> 16384\n\t\t\t\t\t\t var delayPos1 = (delayPos +  3041) & 0x3FFF;\n\t\t\t\t\t\t var delayPos2 = (delayPos +  6426) & 0x3FFF;\n\t\t\t\t\t\t var delayPos3 = (delayPos + 10907) & 0x3FFF;\n\t\t\t\t\t\t var delaySample0 = delayLine[delayPos]\n\t\t\t\t\t\t\t + channel#Sample // PITCH\n\t\t\t\t\t\t ;\n\t\t\t\t\t\t var delaySample1 = delayLine[delayPos1];\n\t\t\t\t\t\t var delaySample2 = delayLine[delayPos2];\n\t\t\t\t\t\t var delaySample3 = delayLine[delayPos3];\n\t\t\t\t\t\t var delayTemp0 = -delaySample0 + delaySample1;\n\t\t\t\t\t\t var delayTemp1 = -delaySample0 - delaySample1;\n\t\t\t\t\t\t var delayTemp2 = -delaySample2 + delaySample3;\n\t\t\t\t\t\t var delayTemp3 = -delaySample2 - delaySample3;\n\t\t\t\t\t\t delayFeedback0 += ((delayTemp0 + delayTemp2) * reverb - delayFeedback0) * 0.5;\n\t\t\t\t\t\t delayFeedback1 += ((delayTemp1 + delayTemp3) * reverb - delayFeedback1) * 0.5;\n\t\t\t\t\t\t delayFeedback2 += ((delayTemp0 - delayTemp2) * reverb - delayFeedback2) * 0.5;\n\t\t\t\t\t\t delayFeedback3 += ((delayTemp1 - delayTemp3) * reverb - delayFeedback3) * 0.5;\n\t\t\t\t\t\t delayLine[delayPos1] = delayFeedback0;\n\t\t\t\t\t\t delayLine[delayPos2] = delayFeedback1;\n\t\t\t\t\t\t delayLine[delayPos3] = delayFeedback2;\n\t\t\t\t\t\t delayLine[delayPos ] = delayFeedback3;\n\t\t\t\t\t\t delayPos = (delayPos + 1) & 0x3FFF;\n\t\t\t\t\t\t\n\t\t\t\t\t\t var sample = delaySample0 + delaySample1 + delaySample2 + delaySample3\n\t\t\t\t\t\t\t + channel#Sample // DRUM\n\t\t\t\t\t\t ;\n\t\t\t\t\t\t\n\t\t\t\t\t\t var abs = sample < 0.0 ? -sample : sample;\n\t\t\t\t\t\t limit -= limitDecay;\n\t\t\t\t\t\t if (limit < abs) limit = abs;\n\t\t\t\t\t\t sample /= limit * 0.75 + 0.25;\n\t\t\t\t\t\t sample *= volume;\n\t\t\t\t\t\t data[bufferIndex] = sample;\n\t\t\t\t\t\t bufferIndex = bufferIndex + 1;\n\t\t\t\t\t\t samples--;\n\t\t\t\t\t }\n\t\t\t\t\t\n\t\t\t\t\t synth.channelPlayheadA[#] = channel#PlayheadA; // PITCH\n\t\t\t\t\t synth.channelPlayheadB[#] = channel#PlayheadB; // PITCH\n\t\t\t\t\t synth.channelPlayheadA[#] = channel#Playhead; // DRUM\n\t\t\t\t\t synth.channelSample[#] = channel#Sample; // ALL\n\t\t\t\t\t\n\t\t\t\t\t synth.delayPos = delayPos;\n\t\t\t\t\t synth.delayFeedback0 = delayFeedback0;\n\t\t\t\t\t synth.delayFeedback1 = delayFeedback1;\n\t\t\t\t\t synth.delayFeedback2 = delayFeedback2;\n\t\t\t\t\t synth.delayFeedback3 = delayFeedback3;\n\t\t\t\t\t synth.limit = limit;\n\t\t\t\t\t\n\t\t\t\t\t if (effectYMult * effectY - prevEffectY > prevEffectY) {\n\t\t\t\t\t\t synth.effectPlayhead = Math.asin(effectY);\n\t\t\t\t\t } else {\n\t\t\t\t\t\t synth.effectPlayhead = Math.PI - Math.asin(effectY);\n\t\t\t\t\t }\n\t\t\t\t\t\n\t\t\t\t\t if (synth.arpeggioSampleCountdown == 0) {\n\t\t\t\t\t\t synth.arpeggio++;\n\t\t\t\t\t\t synth.arpeggioSampleCountdown = samplesPerArpeggio;\n\t\t\t\t\t\t if (synth.arpeggio == 4) {\n\t\t\t\t\t\t\t synth.arpeggio = 0;\n\t\t\t\t\t\t\t synth.part++;\n\t\t\t\t\t\t\t if (synth.part == song.partsPerBeat) {\n\t\t\t\t\t\t\t\t synth.part = 0;\n\t\t\t\t\t\t\t\t synth.beat++;\n\t\t\t\t\t\t\t\t if (synth.beat == song.beatsPerBar) {\n\t\t\t\t\t\t\t\t\t synth.beat = 0;\n\t\t\t\t\t\t\t\t\t synth.effectPlayhead = 0.0;\n\t\t\t\t\t\t\t\t\t synth.bar++;\n\t\t\t\t\t\t\t\t\t if (synth.bar < song.loopStart) {\n\t\t\t\t\t\t\t\t\t\t if (!synth.enableIntro) synth.bar = song.loopStart;\n\t\t\t\t\t\t\t\t\t } else {\n\t\t\t\t\t\t\t\t\t\t synth.enableIntro = false;\n\t\t\t\t\t\t\t\t\t }\n\t\t\t\t\t\t\t\t\t if (synth.bar >= song.loopStart + song.loopLength) {\n\t\t\t\t\t\t\t\t\t\t if (synth.loopCount > 0) synth.loopCount--;\n\t\t\t\t\t\t\t\t\t\t if (synth.loopCount > 0 || !synth.enableOutro) {\n\t\t\t\t\t\t\t\t\t\t\t synth.bar = song.loopStart;\n\t\t\t\t\t\t\t\t\t\t }\n\t\t\t\t\t\t\t\t\t }\n\t\t\t\t\t\t\t\t\t if (synth.bar >= song.barCount) {\n\t\t\t\t\t\t\t\t\t\t synth.bar = 0;\n\t\t\t\t\t\t\t\t\t\t synth.enableIntro = true;\n\t\t\t\t\t\t\t\t\t\t ended = true;\n\t\t\t\t\t\t\t\t\t\t synth.pause();\n\t\t\t\t\t\t\t\t\t }\n\t\t\t\t\t\t\t\t\t\n\t\t\t\t\t\t\t\t\t // The bar changed, may need to reinitialize instruments.\n\t\t\t\t\t\t\t\t\t break;\n\t\t\t\t\t\t\t\t }\n\t\t\t\t\t\t\t }\n\t\t\t\t\t\t }\n\t\t\t\t\t }\n\t\t\t\t }\n\t\t\t }\n\t\t\t\n\t\t\t synth.playheadInternal = (((synth.arpeggio + 1.0 - synth.arpeggioSampleCountdown / samplesPerArpeggio) / 4.0 + synth.part) / song.partsPerBeat + synth.beat) / song.beatsPerBar + synth.bar;\n\t\t ".split("\n");
beepbox.Synth = Synth;

module.exports = {
    getBuffer: exportToWav,
    "classes": beepbox
}