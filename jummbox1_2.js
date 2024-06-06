var beepbox = {};
global.beepbox = beepbox;

const exportToWav = async function(thelink) {
    const synth = typeof(thelink) == "string" && new (beepbox).Synth(thelink) || thelink;
    synth.enableIntro = true
    synth.enableOutro = true
    synth.loopCount = 1
    const sampleFrames = synth.totalSamples;
    const recordedSamplesL = new Float32Array(sampleFrames);
    const recordedSamplesR = new Float32Array(sampleFrames);
    synth.synthesize(recordedSamplesL, recordedSamplesR, sampleFrames);
    const srcChannelCount = 1;
    const wavChannelCount = 2;
    const sampleRate = 44100;
    const bytesPerSample = 2;
    const bitsPerSample = 8 * bytesPerSample;
    const sampleCount = wavChannelCount * sampleFrames;
    const totalFileSize = 44 + sampleCount * bytesPerSample;
    let index = 0;
    const arrayBuffer = new ArrayBuffer(totalFileSize);
    const data = new DataView(arrayBuffer);
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
    data.setUint16(index, bytesPerSample * wavChannelCount, true);
    index += 2;
    data.setUint16(index, bitsPerSample, true);
    index += 2;
    data.setUint32(index, 0x64617461, false);
    index += 4;
    data.setUint32(index, sampleCount * bytesPerSample, true);
    index += 4;
    let stride;
    let repeat;
    if (srcChannelCount == wavChannelCount) {
        stride = 1;
        repeat = 1;
    }
    else {
        stride = srcChannelCount;
        repeat = wavChannelCount;
    }
    let val = [];
    if (bytesPerSample > 1) {
        for (let i = 0; i < sampleFrames; i++) {
            val[0] = Math.floor(Math.max(-1, Math.min(1, recordedSamplesL[i * stride])) * ((1 << (bitsPerSample - 1)) - 1));
            val[1] = Math.floor(Math.max(-1, Math.min(1, recordedSamplesR[i * stride])) * ((1 << (bitsPerSample - 1)) - 1));
            for (let k = 0; k < repeat; k++) {
                if (bytesPerSample == 2) {
                    data.setInt16(index, val[k], true);
                    index += 2;
                }
                else if (bytesPerSample == 4) {
                    data.setInt32(index, val[k], true);
                    index += 4;
                }
                else {
                    throw new Error("unsupported sample size");
                }
            }
        }
    }
    else {
        for (let i = 0; i < sampleFrames; i++) {
            val[0] = Math.floor(Math.max(-1, Math.min(1, recordedSamplesL[i * stride])) * 127 + 128);
            val[1] = Math.floor(Math.max(-1, Math.min(1, recordedSamplesR[i * stride])) * 127 + 128);
            for (let k = 0; k < repeat; k++) {
                data.setUint8(index, val[k] > 255 ? 255 : (val[k] < 0 ? 0 : val[k]));
                index++;
            }
        }
    }
    //let beepName = ("jb_1_2")+"_"+randomString(7)
    //let buffer = Buffer.from(arbf);
    //const blob = new Blob([arrayBuffer], { type: "audio/wav" });
   // let saved = await save(buffer,  beepName);
    return Buffer.from(arrayBuffer) //[beepName, "./Media/Beepbox/"+beepName+".wav", saved];
}
class Deque {
    constructor() {
        this._capacity = 1;
        this._buffer = [undefined];
        this._mask = 0;
        this._offset = 0;
        this._count = 0;
    }
    pushFront(element) {
        if (this._count >= this._capacity)
            this._expandCapacity();
        this._offset = (this._offset - 1) & this._mask;
        this._buffer[this._offset] = element;
        this._count++;
    }
    pushBack(element) {
        if (this._count >= this._capacity)
            this._expandCapacity();
        this._buffer[(this._offset + this._count) & this._mask] = element;
        this._count++;
    }
    popFront() {
        if (this._count <= 0)
            throw new Error("No elements left to pop.");
        const element = this._buffer[this._offset];
        this._buffer[this._offset] = undefined;
        this._offset = (this._offset + 1) & this._mask;
        this._count--;
        return element;
    }
    popBack() {
        if (this._count <= 0)
            throw new Error("No elements left to pop.");
        this._count--;
        const index = (this._offset + this._count) & this._mask;
        const element = this._buffer[index];
        this._buffer[index] = undefined;
        return element;
    }
    peakFront() {
        if (this._count <= 0)
            throw new Error("No elements left to pop.");
        return this._buffer[this._offset];
    }
    peakBack() {
        if (this._count <= 0)
            throw new Error("No elements left to pop.");
        return this._buffer[(this._offset + this._count - 1) & this._mask];
    }
    count() {
        return this._count;
    }
    set(index, element) {
        if (index < 0 || index >= this._count)
            throw new Error("Invalid index");
        this._buffer[(this._offset + index) & this._mask] = element;
    }
    get(index) {
        if (index < 0 || index >= this._count)
            throw new Error("Invalid index");
        return this._buffer[(this._offset + index) & this._mask];
    }
    remove(index) {
        if (index < 0 || index >= this._count)
            throw new Error("Invalid index");
        if (index <= (this._count >> 1)) {
            while (index > 0) {
                this.set(index, this.get(index - 1));
                index--;
            }
            this.popFront();
        }
        else {
            index++;
            while (index < this._count) {
                this.set(index - 1, this.get(index));
                index++;
            }
            this.popBack();
        }
    }
    _expandCapacity() {
        if (this._capacity >= 0x40000000)
            throw new Error("Capacity too big.");
        this._capacity = this._capacity << 1;
        const oldBuffer = this._buffer;
        const newBuffer = new Array(this._capacity);
        const size = this._count | 0;
        const offset = this._offset | 0;
        for (let i = 0; i < size; i++) {
            newBuffer[i] = oldBuffer[(offset + i) & this._mask];
        }
        for (let i = size; i < this._capacity; i++) {
            newBuffer[i] = undefined;
        }
        this._offset = 0;
        this._buffer = newBuffer;
        this._mask = this._capacity - 1;
    }
}
beepbox.Deque = Deque;

let samplesAccumulated = 0;
let samplePerformance = 0;
class BitFieldReader {
    constructor(base64CharCodeToInt, source, startIndex, stopIndex) {
        this._bits = [];
        this._readIndex = 0;
        for (let i = startIndex; i < stopIndex; i++) {
            const value = base64CharCodeToInt[source.charCodeAt(i)];
            this._bits.push((value >> 5) & 0x1);
            this._bits.push((value >> 4) & 0x1);
            this._bits.push((value >> 3) & 0x1);
            this._bits.push((value >> 2) & 0x1);
            this._bits.push((value >> 1) & 0x1);
            this._bits.push(value & 0x1);
        }
    }
    read(bitCount) {
        let result = 0;
        while (bitCount > 0) {
            result = result << 1;
            result += this._bits[this._readIndex++];
            bitCount--;
        }
        return result;
    }
    readLongTail(minValue, minBits) {
        let result = minValue;
        let numBits = minBits;
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
    }
    readPartDuration() {
        return this.readLongTail(1, 3);
    }
    readLegacyPartDuration() {
        return this.readLongTail(1, 2);
    }
    readPinCount() {
        return this.readLongTail(1, 0);
    }
    readPitchInterval() {
        if (this.read(1)) {
            return -this.readLongTail(1, 3);
        }
        else {
            return this.readLongTail(1, 3);
        }
    }
}
class BitFieldWriter {
    constructor() {
        this._bits = [];
    }
    write(bitCount, value) {
        bitCount--;
        while (bitCount >= 0) {
            this._bits.push((value >>> bitCount) & 1);
            bitCount--;
        }
    }
    writeLongTail(minValue, minBits, value) {
        if (value < minValue)
            throw new Error("value out of bounds");
        value -= minValue;
        let numBits = minBits;
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
    }
    writePartDuration(value) {
        this.writeLongTail(1, 3, value);
    }
    writePinCount(value) {
        this.writeLongTail(1, 0, value);
    }
    writePitchInterval(value) {
        if (value < 0) {
            this.write(1, 1);
            this.writeLongTail(1, 3, -value);
        }
        else {
            this.write(1, 0);
            this.writeLongTail(1, 3, value);
        }
    }
    concat(other) {
        this._bits = this._bits.concat(other._bits);
    }
    encodeBase64(base64IntToCharCode, buffer) {
        for (let i = 0; i < this._bits.length; i += 6) {
            const value = (this._bits[i] << 5) | (this._bits[i + 1] << 4) | (this._bits[i + 2] << 3) | (this._bits[i + 3] << 2) | (this._bits[i + 4] << 1) | this._bits[i + 5];
            buffer.push(base64IntToCharCode[value]);
        }
        return buffer;
    }
    lengthBase64() {
        return Math.ceil(this._bits.length / 6);
    }
}
function makeNotePin(interval, time, volume) {
    return { interval: interval, time: time, volume: volume };
}
beepbox.makeNotePin = makeNotePin;
function clamp(min, max, val) {
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
}
class Note {
    constructor(pitch, start, end, volume, fadeout = false) {
        this.pitches = [pitch];
        this.pins = [makeNotePin(0, 0, volume), makeNotePin(0, end - start, fadeout ? 0 : volume)];
        this.start = start;
        this.end = end;
    }
    pickMainInterval() {
        let longestFlatIntervalDuration = 0;
        let mainInterval = 0;
        for (let pinIndex = 1; pinIndex < this.pins.length; pinIndex++) {
            const pinA = this.pins[pinIndex - 1];
            const pinB = this.pins[pinIndex];
            if (pinA.interval == pinB.interval) {
                const duration = pinB.time - pinA.time;
                if (longestFlatIntervalDuration < duration) {
                    longestFlatIntervalDuration = duration;
                    mainInterval = pinA.interval;
                }
            }
        }
        if (longestFlatIntervalDuration == 0) {
            let loudestVolume = 0;
            for (let pinIndex = 0; pinIndex < this.pins.length; pinIndex++) {
                const pin = this.pins[pinIndex];
                if (loudestVolume < pin.volume) {
                    loudestVolume = pin.volume;
                    mainInterval = pin.interval;
                }
            }
        }
        return mainInterval;
    }
}
beepbox.Note = Note;
class Pattern {
    constructor() {
        this.notes = [];
        this.instrument = 0;
    }
    cloneNotes() {
        const result = [];
        for (const oldNote of this.notes) {
            const newNote = new Note(-1, oldNote.start, oldNote.end, 6);
            newNote.pitches = oldNote.pitches.concat();
            newNote.pins = [];
            for (const oldPin of oldNote.pins) {
                newNote.pins.push(makeNotePin(oldPin.interval, oldPin.time, oldPin.volume));
            }
            result.push(newNote);
        }
        return result;
    }
    reset() {
        this.notes.length = 0;
        this.instrument = 0;
    }
}
beepbox.Pattern = Pattern;
class Operator {
    constructor(index) {
        this.frequency = 0;
        this.amplitude = 0;
        this.envelope = 0;
        this.reset(index);
    }
    reset(index) {
        this.frequency = 0;
        this.amplitude = (index <= 1) ? beepbox.Config.operatorAmplitudeMax : 0;
        this.envelope = (index == 0) ? 0 : 1;
    }
    copy(other) {
        this.frequency = other.frequency;
        this.amplitude = other.amplitude;
        this.envelope = other.envelope;
    }
}
beepbox.Operator = Operator;
class SpectrumWave {
    constructor(isNoiseChannel) {
        this.spectrum = [];
        this._wave = null;
        this._waveIsReady = false;
        this.reset(isNoiseChannel);
    }
    reset(isNoiseChannel) {
        for (let i = 0; i < beepbox.Config.spectrumControlPoints; i++) {
            if (isNoiseChannel) {
                this.spectrum[i] = Math.round(beepbox.Config.spectrumMax * (1 / Math.sqrt(1 + i / 3)));
            }
            else {
                const isHarmonic = i == 0 || i == 7 || i == 11 || i == 14 || i == 16 || i == 18 || i == 21 || i == 23 || i >= 25;
                this.spectrum[i] = isHarmonic ? Math.max(0, Math.round(beepbox.Config.spectrumMax * (1 - i / 30))) : 0;
            }
        }
        this._waveIsReady = false;
    }
    markCustomWaveDirty() {
        this._waveIsReady = false;
    }
    getCustomWave(lowestOctave) {
        if (!this._waveIsReady || this._wave == null) {
            let waveLength = beepbox.Config.chipNoiseLength;
            if (this._wave == null || this._wave.length != waveLength + 1) {
                this._wave = new Float32Array(waveLength + 1);
            }
            const wave = this._wave;
            for (let i = 0; i < waveLength; i++) {
                wave[i] = 0;
            }
            const highestOctave = 14;
            const falloffRatio = 0.25;
            const pitchTweak = [0, 1 / 7, Math.log(5 / 4) / Math.LN2, 3 / 7, Math.log(3 / 2) / Math.LN2, 5 / 7, 6 / 7];
            function controlPointToOctave(point) {
                return lowestOctave + Math.floor(point / beepbox.Config.spectrumControlPointsPerOctave) + pitchTweak[(point + beepbox.Config.spectrumControlPointsPerOctave) % beepbox.Config.spectrumControlPointsPerOctave];
            }
            let combinedAmplitude = 1;
            for (let i = 0; i < beepbox.Config.spectrumControlPoints + 1; i++) {
                const value1 = (i <= 0) ? 0 : this.spectrum[i - 1];
                const value2 = (i >= beepbox.Config.spectrumControlPoints) ? this.spectrum[beepbox.Config.spectrumControlPoints - 1] : this.spectrum[i];
                const octave1 = controlPointToOctave(i - 1);
                let octave2 = controlPointToOctave(i);
                if (i >= beepbox.Config.spectrumControlPoints)
                    octave2 = highestOctave + (octave2 - highestOctave) * falloffRatio;
                if (value1 == 0 && value2 == 0)
                    continue;
                combinedAmplitude += 0.02 * beepbox.drawNoiseSpectrum(wave, octave1, octave2, value1 / beepbox.Config.spectrumMax, value2 / beepbox.Config.spectrumMax, -0.5);
            }
            if (this.spectrum[beepbox.Config.spectrumControlPoints - 1] > 0) {
                combinedAmplitude += 0.02 * beepbox.drawNoiseSpectrum(wave, highestOctave + (controlPointToOctave(beepbox.Config.spectrumControlPoints) - highestOctave) * falloffRatio, highestOctave, this.spectrum[beepbox.Config.spectrumControlPoints - 1] / beepbox.Config.spectrumMax, 0, -0.5);
            }
            beepbox.inverseRealFourierTransform(wave, waveLength);
            beepbox.scaleElementsByFactor(wave, 5.0 / (Math.sqrt(waveLength) * Math.pow(combinedAmplitude, 0.75)));
            wave[waveLength] = wave[0];
            this._waveIsReady = true;
        }
        return this._wave;
    }
}
beepbox.SpectrumWave = SpectrumWave;
class HarmonicsWave {
    constructor() {
        this.harmonics = [];
        this._wave = null;
        this._waveIsReady = false;
        this.reset();
    }
    reset() {
        for (let i = 0; i < beepbox.Config.harmonicsControlPoints; i++) {
            this.harmonics[i] = 0;
        }
        this.harmonics[0] = beepbox.Config.harmonicsMax;
        this.harmonics[3] = beepbox.Config.harmonicsMax;
        this.harmonics[6] = beepbox.Config.harmonicsMax;
        this._waveIsReady = false;
    }
    markCustomWaveDirty() {
        this._waveIsReady = false;
    }
    getCustomWave() {
        if (!this._waveIsReady || this._wave == null) {
            let waveLength = beepbox.Config.harmonicsWavelength;
            const retroWave = beepbox.getDrumWave(0);
            if (this._wave == null || this._wave.length != waveLength + 1) {
                this._wave = new Float32Array(waveLength + 1);
            }
            const wave = this._wave;
            for (let i = 0; i < waveLength; i++) {
                wave[i] = 0;
            }
            const overallSlope = -0.25;
            let combinedControlPointAmplitude = 1;
            for (let harmonicIndex = 0; harmonicIndex < beepbox.Config.harmonicsRendered; harmonicIndex++) {
                const harmonicFreq = harmonicIndex + 1;
                let controlValue = harmonicIndex < beepbox.Config.harmonicsControlPoints ? this.harmonics[harmonicIndex] : this.harmonics[beepbox.Config.harmonicsControlPoints - 1];
                if (harmonicIndex >= beepbox.Config.harmonicsControlPoints) {
                    controlValue *= 1 - (harmonicIndex - beepbox.Config.harmonicsControlPoints) / (beepbox.Config.harmonicsRendered - beepbox.Config.harmonicsControlPoints);
                }
                const normalizedValue = controlValue / beepbox.Config.harmonicsMax;
                let amplitude = Math.pow(2, controlValue - beepbox.Config.harmonicsMax + 1) * Math.sqrt(normalizedValue);
                if (harmonicIndex < beepbox.Config.harmonicsControlPoints) {
                    combinedControlPointAmplitude += amplitude;
                }
                amplitude *= Math.pow(harmonicFreq, overallSlope);
                amplitude *= retroWave[harmonicIndex + 589];
                wave[waveLength - harmonicFreq] = amplitude;
            }
            beepbox.inverseRealFourierTransform(wave, waveLength);
            const mult = 1 / Math.pow(combinedControlPointAmplitude, 0.7);
            let cumulative = 0;
            let wavePrev = 0;
            for (let i = 0; i < wave.length; i++) {
                cumulative += wavePrev;
                wavePrev = wave[i] * mult;
                wave[i] = cumulative;
            }
            wave[waveLength] = wave[0];
            this._waveIsReady = true;
        }
        return this._wave;
    }
}
beepbox.HarmonicsWave = HarmonicsWave;
class Instrument {
    constructor(isNoiseChannel) {
        this.type = 0;
        this.preset = 0;
        this.chipWave = 2;
        this.chipNoise = 1;
        this.filterCutoff = 12;
        this.filterResonance = 0;
        this.filterEnvelope = 1;
        this.transition = 1;
        this.vibrato = 0;
        this.interval = 0;
        this.effects = 0;
        this.chord = 1;
        this.volume = 0;
        this.pan = 50;
        this.pulseWidth = 50;
        this.pulseEnvelope = 1;
        this.algorithm = 0;
        this.feedbackType = 0;
        this.feedbackAmplitude = 0;
        this.feedbackEnvelope = 1;
        this.customChipWave = new Float64Array(64);
        this.customChipWaveIntegral = new Float64Array(65);
        this.operators = [];
        this.harmonicsWave = new HarmonicsWave();
        this.drumsetEnvelopes = [];
        this.drumsetSpectrumWaves = [];
        this.spectrumWave = new SpectrumWave(isNoiseChannel);
        for (let i = 0; i < beepbox.Config.operatorCount; i++) {
            this.operators[i] = new Operator(i);
        }
        for (let i = 0; i < beepbox.Config.drumCount; i++) {
            this.drumsetEnvelopes[i] = beepbox.Config.envelopes.dictionary["twang 2"].index;
            this.drumsetSpectrumWaves[i] = new SpectrumWave(true);
        }
        for (let i = 0; i < 64; i++) {
            this.customChipWave[i] = 24 - Math.floor(i * (48 / 64));
        }
        let sum = 0.0;
        for (let i = 0; i < this.customChipWave.length; i++) {
            sum += this.customChipWave[i];
        }
        const average = sum / this.customChipWave.length;
        let cumulative = 0;
        let wavePrev = 0;
        for (let i = 0; i < this.customChipWave.length; i++) {
            cumulative += wavePrev;
            wavePrev = this.customChipWave[i] - average;
            this.customChipWaveIntegral[i] = cumulative;
        }
        this.customChipWaveIntegral[64] = 0.0;
    }
    setTypeAndReset(type, isNoiseChannel) {
        this.type = type;
        this.preset = type;
        this.volume = 0;
        switch (type) {
            case 0:
                this.chipWave = 2;
                this.filterCutoff = 6;
                this.filterResonance = 0;
                this.filterEnvelope = beepbox.Config.envelopes.dictionary["steady"].index;
                this.transition = 1;
                this.vibrato = 0;
                this.interval = 0;
                this.effects = 1;
                this.chord = 2;
                this.pan = 50;
                break;
            case 7:
                this.chipWave = 2;
                this.filterCutoff = 6;
                this.filterResonance = 0;
                this.filterEnvelope = beepbox.Config.envelopes.dictionary["steady"].index;
                this.transition = 1;
                this.vibrato = 0;
                this.interval = 0;
                this.effects = 1;
                this.chord = 2;
                this.pan = 50;
                for (let i = 0; i < 64; i++) {
                    this.customChipWave[i] = 24 - (Math.floor(i * (48 / 64)));
                }
                let sum = 0.0;
                for (let i = 0; i < this.customChipWave.length; i++) {
                    sum += this.customChipWave[i];
                }
                const average = sum / this.customChipWave.length;
                let cumulative = 0;
                let wavePrev = 0;
                for (let i = 0; i < this.customChipWave.length; i++) {
                    cumulative += wavePrev;
                    wavePrev = this.customChipWave[i] - average;
                    this.customChipWaveIntegral[i] = cumulative;
                }
                this.customChipWaveIntegral[64] = 0.0;
                break;
            case 1:
                this.transition = 1;
                this.vibrato = 0;
                this.effects = 1;
                this.chord = 3;
                this.filterCutoff = 10;
                this.filterResonance = 0;
                this.filterEnvelope = 1;
                this.algorithm = 0;
                this.feedbackType = 0;
                this.feedbackAmplitude = 0;
                this.feedbackEnvelope = beepbox.Config.envelopes.dictionary["steady"].index;
                this.pan = 50;
                for (let i = 0; i < this.operators.length; i++) {
                    this.operators[i].reset(i);
                }
                break;
            case 2:
                this.chipNoise = 1;
                this.transition = 1;
                this.effects = 0;
                this.chord = 2;
                this.filterCutoff = 10;
                this.filterResonance = 0;
                this.filterEnvelope = beepbox.Config.envelopes.dictionary["steady"].index;
                this.pan = 50;
                break;
            case 3:
                this.transition = 1;
                this.effects = 1;
                this.chord = 0;
                this.filterCutoff = 10;
                this.filterResonance = 0;
                this.filterEnvelope = beepbox.Config.envelopes.dictionary["steady"].index;
                this.spectrumWave.reset(isNoiseChannel);
                this.pan = 50;
                break;
            case 4:
                this.effects = 0;
                this.pan = 50;
                for (let i = 0; i < beepbox.Config.drumCount; i++) {
                    this.drumsetEnvelopes[i] = beepbox.Config.envelopes.dictionary["twang 2"].index;
                    this.drumsetSpectrumWaves[i].reset(isNoiseChannel);
                }
                break;
            case 5:
                this.filterCutoff = 10;
                this.filterResonance = 0;
                this.filterEnvelope = beepbox.Config.envelopes.dictionary["steady"].index;
                this.transition = 1;
                this.vibrato = 0;
                this.interval = 0;
                this.effects = 1;
                this.chord = 0;
                this.pan = 50;
                this.harmonicsWave.reset();
                break;
            case 6:
                this.filterCutoff = 10;
                this.filterResonance = 0;
                this.filterEnvelope = beepbox.Config.envelopes.dictionary["steady"].index;
                this.transition = 1;
                this.vibrato = 0;
                this.interval = 0;
                this.effects = 1;
                this.chord = 2;
                this.pan = 50;
                this.pulseWidth = 50;
                this.pulseEnvelope = beepbox.Config.envelopes.dictionary["twang 2"].index;
                break;
            default:
                throw new Error("Unrecognized instrument type: " + type);
        }
    }
    toJsonObject() {
        const instrumentObject = {
            "type": beepbox.Config.instrumentTypeNames[this.type],
            "volume": this.volume,
            "effects": beepbox.Config.effectsNames[this.effects],
            "pan": this.pan,
        };
        if (this.preset != this.type) {
            instrumentObject["preset"] = this.preset;
        }
        if (this.type != 4) {
            instrumentObject["transition"] = beepbox.Config.transitions[this.transition].name;
            instrumentObject["chord"] = this.getChord().name;
            instrumentObject["filterCutoffHz"] = Math.round(beepbox.Config.filterCutoffMaxHz * Math.pow(2.0, this.getFilterCutoffOctaves()));
            instrumentObject["filterResonance"] = Math.round(100 * this.filterResonance / (beepbox.Config.filterResonanceRange - 1));
            instrumentObject["filterEnvelope"] = this.getFilterEnvelope().name;
        }
        if (this.type == 2) {
            instrumentObject["wave"] = beepbox.Config.chipNoises[this.chipNoise].name;
        }
        else if (this.type == 3) {
            instrumentObject["spectrum"] = [];
            for (let i = 0; i < beepbox.Config.spectrumControlPoints; i++) {
                instrumentObject["spectrum"][i] = Math.round(100 * this.spectrumWave.spectrum[i] / beepbox.Config.spectrumMax);
            }
        }
        else if (this.type == 4) {
            instrumentObject["drums"] = [];
            for (let j = 0; j < beepbox.Config.drumCount; j++) {
                const spectrum = [];
                for (let i = 0; i < beepbox.Config.spectrumControlPoints; i++) {
                    spectrum[i] = Math.round(100 * this.drumsetSpectrumWaves[j].spectrum[i] / beepbox.Config.spectrumMax);
                }
                instrumentObject["drums"][j] = {
                    "filterEnvelope": this.getDrumsetEnvelope(j).name,
                    "spectrum": spectrum,
                };
            }
        }
        else if (this.type == 0) {
            instrumentObject["wave"] = beepbox.Config.chipWaves[this.chipWave].name;
            instrumentObject["interval"] = beepbox.Config.intervals[this.interval].name;
            instrumentObject["vibrato"] = beepbox.Config.vibratos[this.vibrato].name;
        }
        else if (this.type == 7) {
            instrumentObject["wave"] = beepbox.Config.chipWaves[this.chipWave].name;
            instrumentObject["interval"] = beepbox.Config.intervals[this.interval].name;
            instrumentObject["vibrato"] = beepbox.Config.vibratos[this.vibrato].name;
            instrumentObject["customChipWave"] = new Float64Array(64);
            instrumentObject["customChipWaveIntegral"] = new Float64Array(65);
            for (let i = 0; i < this.customChipWave.length; i++) {
                instrumentObject["customChipWave"][i] = this.customChipWave[i];
            }
            instrumentObject["customChipWaveIntegral"][64] = 0;
        }
        else if (this.type == 6) {
            instrumentObject["pulseWidth"] = this.pulseWidth;
            instrumentObject["pulseEnvelope"] = beepbox.Config.envelopes[this.pulseEnvelope].name;
            instrumentObject["vibrato"] = beepbox.Config.vibratos[this.vibrato].name;
        }
        else if (this.type == 5) {
            instrumentObject["interval"] = beepbox.Config.intervals[this.interval].name;
            instrumentObject["vibrato"] = beepbox.Config.vibratos[this.vibrato].name;
            instrumentObject["harmonics"] = [];
            for (let i = 0; i < beepbox.Config.harmonicsControlPoints; i++) {
                instrumentObject["harmonics"][i] = Math.round(100 * this.harmonicsWave.harmonics[i] / beepbox.Config.harmonicsMax);
            }
        }
        else if (this.type == 1) {
            const operatorArray = [];
            for (const operator of this.operators) {
                operatorArray.push({
                    "frequency": beepbox.Config.operatorFrequencies[operator.frequency].name,
                    "amplitude": operator.amplitude,
                    "envelope": beepbox.Config.envelopes[operator.envelope].name,
                });
            }
            instrumentObject["vibrato"] = beepbox.Config.vibratos[this.vibrato].name;
            instrumentObject["algorithm"] = beepbox.Config.algorithms[this.algorithm].name;
            instrumentObject["feedbackType"] = beepbox.Config.feedbacks[this.feedbackType].name;
            instrumentObject["feedbackAmplitude"] = this.feedbackAmplitude;
            instrumentObject["feedbackEnvelope"] = beepbox.Config.envelopes[this.feedbackEnvelope].name;
            instrumentObject["operators"] = operatorArray;
        }
        else {
            throw new Error("Unrecognized instrument type");
        }
        return instrumentObject;
    }
    fromJsonObject(instrumentObject, isNoiseChannel) {
        if (instrumentObject == undefined)
            instrumentObject = {};
        let type = beepbox.Config.instrumentTypeNames.indexOf(instrumentObject["type"]);
        if (type == -1)
            type = isNoiseChannel ? 2 : 0;
        this.setTypeAndReset(type, isNoiseChannel);
        if (instrumentObject["preset"] != undefined) {
            this.preset = instrumentObject["preset"] >>> 0;
        }
        if (instrumentObject["pan"] != undefined) {
            this.pan = instrumentObject["pan"] >>> 0;
        }
        if (instrumentObject["volume"] != undefined) {
            this.volume = clamp(-beepbox.Config.volumeRange / 2, beepbox.Config.volumeRange / 2, instrumentObject["volume"] | 0);
        }
        else {
            this.volume = 0;
        }
        const oldTransitionNames = { "binary": 0, "sudden": 1, "smooth": 2 };
        const transitionObject = instrumentObject["transition"] || instrumentObject["envelope"];
        this.transition = oldTransitionNames[transitionObject] != undefined ? oldTransitionNames[transitionObject] : beepbox.Config.transitions.findIndex(transition => transition.name == transitionObject);
        if (this.transition == -1)
            this.transition = 1;
        this.effects = beepbox.Config.effectsNames.indexOf(instrumentObject["effects"]);
        if (this.effects == -1)
            this.effects = (this.type == 2) ? 0 : 1;
        if (instrumentObject["filterCutoffHz"] != undefined) {
            this.filterCutoff = clamp(0, beepbox.Config.filterCutoffRange, Math.round((beepbox.Config.filterCutoffRange - 1) + 2.0 * Math.log((instrumentObject["filterCutoffHz"] | 0) / beepbox.Config.filterCutoffMaxHz) / Math.LN2));
        }
        else {
            this.filterCutoff = (this.type == 0) ? 6 : 10;
        }
        if (instrumentObject["filterResonance"] != undefined) {
            this.filterResonance = clamp(0, beepbox.Config.filterResonanceRange, Math.round((beepbox.Config.filterResonanceRange - 1) * (instrumentObject["filterResonance"] | 0) / 100));
        }
        else {
            this.filterResonance = 0;
        }
        this.filterEnvelope = beepbox.Config.envelopes.findIndex(envelope => envelope.name == instrumentObject["filterEnvelope"]);
        if (this.filterEnvelope == -1)
            this.filterEnvelope = beepbox.Config.envelopes.dictionary["steady"].index;
        if (instrumentObject["filter"] != undefined) {
            const legacyToCutoff = [20, 12, 6, 0, 16, 10, 4];
            const legacyToEnvelope = [1, 1, 1, 1, 18, 19, 20];
            const filterNames = ["none", "bright", "medium", "soft", "decay bright", "decay medium", "decay soft"];
            const oldFilterNames = { "sustain sharp": 1, "sustain medium": 2, "sustain soft": 3, "decay sharp": 4 };
            let legacyFilter = oldFilterNames[instrumentObject["filter"]] != undefined ? oldFilterNames[instrumentObject["filter"]] : filterNames.indexOf(instrumentObject["filter"]);
            if (legacyFilter == -1)
                legacyFilter = 0;
            this.filterCutoff = legacyToCutoff[legacyFilter];
            this.filterEnvelope = legacyToEnvelope[legacyFilter];
            this.filterResonance = 0;
        }
        const legacyEffectNames = ["none", "vibrato light", "vibrato delayed", "vibrato heavy"];
        if (this.type == 2) {
            this.chipNoise = beepbox.Config.chipNoises.findIndex(wave => wave.name == instrumentObject["wave"]);
            if (this.chipNoise == -1)
                this.chipNoise = 1;
            this.chord = beepbox.Config.chords.findIndex(chord => chord.name == instrumentObject["chord"]);
            if (this.chord == -1)
                this.chord = 2;
        }
        else if (this.type == 3) {
            if (instrumentObject["spectrum"] != undefined) {
                for (let i = 0; i < beepbox.Config.spectrumControlPoints; i++) {
                    this.spectrumWave.spectrum[i] = Math.max(0, Math.min(beepbox.Config.spectrumMax, Math.round(beepbox.Config.spectrumMax * (+instrumentObject["spectrum"][i]) / 100)));
                }
            }
            this.chord = beepbox.Config.chords.findIndex(chord => chord.name == instrumentObject["chord"]);
            if (this.chord == -1)
                this.chord = 0;
        }
        else if (this.type == 4) {
            if (instrumentObject["drums"] != undefined) {
                for (let j = 0; j < beepbox.Config.drumCount; j++) {
                    const drum = instrumentObject["drums"][j];
                    if (drum == undefined)
                        continue;
                    if (drum["filterEnvelope"] != undefined) {
                        this.drumsetEnvelopes[j] = beepbox.Config.envelopes.findIndex(envelope => envelope.name == drum["filterEnvelope"]);
                        if (this.drumsetEnvelopes[j] == -1)
                            this.drumsetEnvelopes[j] = beepbox.Config.envelopes.dictionary["twang 2"].index;
                    }
                    if (drum["spectrum"] != undefined) {
                        for (let i = 0; i < beepbox.Config.spectrumControlPoints; i++) {
                            this.drumsetSpectrumWaves[j].spectrum[i] = Math.max(0, Math.min(beepbox.Config.spectrumMax, Math.round(beepbox.Config.spectrumMax * (+drum["spectrum"][i]) / 100)));
                        }
                    }
                }
            }
        }
        else if (this.type == 5) {
            if (instrumentObject["harmonics"] != undefined) {
                for (let i = 0; i < beepbox.Config.harmonicsControlPoints; i++) {
                    this.harmonicsWave.harmonics[i] = Math.max(0, Math.min(beepbox.Config.harmonicsMax, Math.round(beepbox.Config.harmonicsMax * (+instrumentObject["harmonics"][i]) / 100)));
                }
            }
            if (instrumentObject["interval"] != undefined) {
                this.interval = beepbox.Config.intervals.findIndex(interval => interval.name == instrumentObject["interval"]);
                if (this.interval == -1)
                    this.interval = 0;
            }
            if (instrumentObject["vibrato"] != undefined) {
                this.vibrato = beepbox.Config.vibratos.findIndex(vibrato => vibrato.name == instrumentObject["vibrato"]);
                if (this.vibrato == -1)
                    this.vibrato = 0;
            }
            this.chord = beepbox.Config.chords.findIndex(chord => chord.name == instrumentObject["chord"]);
            if (this.chord == -1)
                this.chord = 0;
        }
        else if (this.type == 6) {
            if (instrumentObject["pulseWidth"] != undefined) {
                this.pulseWidth = instrumentObject["pulseWidth"];
            }
            else {
                this.pulseWidth = 50;
            }
            if (instrumentObject["pulseEnvelope"] != undefined) {
                this.pulseEnvelope = beepbox.Config.envelopes.findIndex(envelope => envelope.name == instrumentObject["pulseEnvelope"]);
                if (this.pulseEnvelope == -1)
                    this.pulseEnvelope = beepbox.Config.envelopes.dictionary["steady"].index;
            }
            if (instrumentObject["vibrato"] != undefined) {
                this.vibrato = beepbox.Config.vibratos.findIndex(vibrato => vibrato.name == instrumentObject["vibrato"]);
                if (this.vibrato == -1)
                    this.vibrato = 0;
            }
            this.chord = beepbox.Config.chords.findIndex(chord => chord.name == instrumentObject["chord"]);
            if (this.chord == -1)
                this.chord = 0;
        }
        else if (this.type == 0) {
            const legacyWaveNames = { "triangle": 1, "square": 2, "pulse wide": 3, "pulse narrow": 4, "sawtooth": 5, "double saw": 6, "double pulse": 7, "spiky": 8, "plateau": 0 };
            this.chipWave = legacyWaveNames[instrumentObject["wave"]] != undefined ? legacyWaveNames[instrumentObject["wave"]] : beepbox.Config.chipWaves.findIndex(wave => wave.name == instrumentObject["wave"]);
            if (this.chipWave == -1)
                this.chipWave = 1;
            if (instrumentObject["interval"] != undefined) {
                this.interval = beepbox.Config.intervals.findIndex(interval => interval.name == instrumentObject["interval"]);
                if (this.interval == -1)
                    this.interval = 0;
            }
            else if (instrumentObject["chorus"] != undefined) {
                const legacyChorusNames = { "fifths": 5, "octaves": 6 };
                this.interval = legacyChorusNames[instrumentObject["chorus"]] != undefined ? legacyChorusNames[instrumentObject["chorus"]] : beepbox.Config.intervals.findIndex(interval => interval.name == instrumentObject["chorus"]);
                if (this.interval == -1)
                    this.interval = 0;
            }
            if (instrumentObject["vibrato"] != undefined) {
                this.vibrato = beepbox.Config.vibratos.findIndex(vibrato => vibrato.name == instrumentObject["vibrato"]);
                if (this.vibrato == -1)
                    this.vibrato = 0;
            }
            else if (instrumentObject["effect"] != undefined) {
                this.vibrato = legacyEffectNames.indexOf(instrumentObject["effect"]);
                if (this.vibrato == -1)
                    this.vibrato = 0;
            }
            this.chord = beepbox.Config.chords.findIndex(chord => chord.name == instrumentObject["chord"]);
            if (this.chord == -1)
                this.chord = 2;
            if (instrumentObject["chorus"] == "custom harmony") {
                this.interval = 2;
                this.chord = 3;
            }
        }
        else if (this.type == 1) {
            if (instrumentObject["vibrato"] != undefined) {
                this.vibrato = beepbox.Config.vibratos.findIndex(vibrato => vibrato.name == instrumentObject["vibrato"]);
                if (this.vibrato == -1)
                    this.vibrato = 0;
            }
            else if (instrumentObject["effect"] != undefined) {
                this.vibrato = legacyEffectNames.indexOf(instrumentObject["effect"]);
                if (this.vibrato == -1)
                    this.vibrato = 0;
            }
            this.chord = beepbox.Config.chords.findIndex(chord => chord.name == instrumentObject["chord"]);
            if (this.chord == -1)
                this.chord = 3;
            this.algorithm = beepbox.Config.algorithms.findIndex(algorithm => algorithm.name == instrumentObject["algorithm"]);
            if (this.algorithm == -1)
                this.algorithm = 0;
            this.feedbackType = beepbox.Config.feedbacks.findIndex(feedback => feedback.name == instrumentObject["feedbackType"]);
            if (this.feedbackType == -1)
                this.feedbackType = 0;
            if (instrumentObject["feedbackAmplitude"] != undefined) {
                this.feedbackAmplitude = clamp(0, beepbox.Config.operatorAmplitudeMax + 1, instrumentObject["feedbackAmplitude"] | 0);
            }
            else {
                this.feedbackAmplitude = 0;
            }
            const legacyEnvelopeNames = { "pluck 1": 6, "pluck 2": 7, "pluck 3": 8 };
            this.feedbackEnvelope = legacyEnvelopeNames[instrumentObject["feedbackEnvelope"]] != undefined ? legacyEnvelopeNames[instrumentObject["feedbackEnvelope"]] : beepbox.Config.envelopes.findIndex(envelope => envelope.name == instrumentObject["feedbackEnvelope"]);
            if (this.feedbackEnvelope == -1)
                this.feedbackEnvelope = 0;
            for (let j = 0; j < beepbox.Config.operatorCount; j++) {
                const operator = this.operators[j];
                let operatorObject = undefined;
                if (instrumentObject["operators"])
                    operatorObject = instrumentObject["operators"][j];
                if (operatorObject == undefined)
                    operatorObject = {};
                operator.frequency = beepbox.Config.operatorFrequencies.findIndex(freq => freq.name == operatorObject["frequency"]);
                if (operator.frequency == -1)
                    operator.frequency = 0;
                if (operatorObject["amplitude"] != undefined) {
                    operator.amplitude = clamp(0, beepbox.Config.operatorAmplitudeMax + 1, operatorObject["amplitude"] | 0);
                }
                else {
                    operator.amplitude = 0;
                }
                operator.envelope = legacyEnvelopeNames[operatorObject["envelope"]] != undefined ? legacyEnvelopeNames[operatorObject["envelope"]] : beepbox.Config.envelopes.findIndex(envelope => envelope.name == operatorObject["envelope"]);
                if (operator.envelope == -1)
                    operator.envelope = 0;
            }
        }
        else if (this.type == 7) {
            if (instrumentObject["interval"] != undefined) {
                this.interval = beepbox.Config.intervals.findIndex(interval => interval.name == instrumentObject["interval"]);
                if (this.interval == -1)
                    this.interval = 0;
            }
            else if (instrumentObject["chorus"] != undefined) {
                const legacyChorusNames = { "fifths": 5, "octaves": 6 };
                this.interval = legacyChorusNames[instrumentObject["chorus"]] != undefined ? legacyChorusNames[instrumentObject["chorus"]] : beepbox.Config.intervals.findIndex(interval => interval.name == instrumentObject["chorus"]);
                if (this.interval == -1)
                    this.interval = 0;
            }
            if (instrumentObject["vibrato"] != undefined) {
                this.vibrato = beepbox.Config.vibratos.findIndex(vibrato => vibrato.name == instrumentObject["vibrato"]);
                if (this.vibrato == -1)
                    this.vibrato = 0;
            }
            else if (instrumentObject["effect"] != undefined) {
                this.vibrato = legacyEffectNames.indexOf(instrumentObject["effect"]);
                if (this.vibrato == -1)
                    this.vibrato = 0;
            }
            this.chord = beepbox.Config.chords.findIndex(chord => chord.name == instrumentObject["chord"]);
            if (this.chord == -1)
                this.chord = 2;
            if (instrumentObject["chorus"] == "custom harmony") {
                this.interval = 2;
                this.chord = 3;
            }
            if (instrumentObject["customChipWave"]) {
                for (let i = 0; i < 64; i++) {
                    this.customChipWave[i] = instrumentObject["customChipWave"][i];
                }
                let sum = 0.0;
                for (let i = 0; i < this.customChipWave.length; i++) {
                    sum += this.customChipWave[i];
                }
                const average = sum / this.customChipWave.length;
                let cumulative = 0;
                let wavePrev = 0;
                for (let i = 0; i < this.customChipWave.length; i++) {
                    cumulative += wavePrev;
                    wavePrev = this.customChipWave[i] - average;
                    this.customChipWaveIntegral[i] = cumulative;
                }
                this.customChipWaveIntegral[64] = 0.0;
            }
        }
        else {
            throw new Error("Unrecognized instrument type.");
        }
    }
    static frequencyFromPitch(pitch) {
        return 440.0 * Math.pow(2.0, (pitch - 69.0) / 12.0);
    }
    static drumsetIndexReferenceDelta(index) {
        return Instrument.frequencyFromPitch(beepbox.Config.spectrumBasePitch + index * 6) / 44100;
    }
    static _drumsetIndexToSpectrumOctave(index) {
        return 15 + Math.log(Instrument.drumsetIndexReferenceDelta(index)) / Math.LN2;
    }
    warmUp() {
        if (this.type == 2) {
            beepbox.getDrumWave(this.chipNoise);
        }
        else if (this.type == 5) {
            this.harmonicsWave.getCustomWave();
        }
        else if (this.type == 3) {
            this.spectrumWave.getCustomWave(8);
        }
        else if (this.type == 4) {
            for (let i = 0; i < beepbox.Config.drumCount; i++) {
                this.drumsetSpectrumWaves[i].getCustomWave(Instrument._drumsetIndexToSpectrumOctave(i));
            }
        }
    }
    getDrumWave() {
        if (this.type == 2) {
            return beepbox.getDrumWave(this.chipNoise);
        }
        else if (this.type == 3) {
            return this.spectrumWave.getCustomWave(8);
        }
        else {
            throw new Error("Unhandled instrument type in getDrumWave");
        }
    }
    getDrumsetWave(pitch) {
        if (this.type == 4) {
            return this.drumsetSpectrumWaves[pitch].getCustomWave(Instrument._drumsetIndexToSpectrumOctave(pitch));
        }
        else {
            throw new Error("Unhandled instrument type in getDrumWave");
        }
    }
    getTransition() {
        return this.type == 4 ? beepbox.Config.transitions.dictionary["hard fade"] : beepbox.Config.transitions[this.transition];
    }
    getChord() {
        return this.type == 4 ? beepbox.Config.chords.dictionary["harmony"] : beepbox.Config.chords[this.chord];
    }
    getFilterCutoffOctaves() {
        return this.type == 4 ? 0 : (this.filterCutoff - (beepbox.Config.filterCutoffRange - 1)) * 0.5;
    }
    getFilterIsFirstOrder() {
        return this.type == 4 ? false : this.filterResonance == 0;
    }
    getFilterResonance() {
        return this.type == 4 ? 1 : this.filterResonance;
    }
    getFilterEnvelope() {
        if (this.type == 4)
            throw new Error("Can't getFilterEnvelope() for drumset.");
        return beepbox.Config.envelopes[this.filterEnvelope];
    }
    getDrumsetEnvelope(pitch) {
        if (this.type != 4)
            throw new Error("Can't getDrumsetEnvelope() for non-drumset.");
        return beepbox.Config.envelopes[this.drumsetEnvelopes[pitch]];
    }
}
beepbox.Instrument = Instrument;
class Channel {
    constructor() {
        this.octave = 0;
        this.instruments = [];
        this.patterns = [];
        this.bars = [];
        this.muted = false;
    }
}
beepbox.Channel = Channel;
class Song {
    constructor(string) {
        this.muteButtons = [];
        this.channels = [];
        if (string != undefined) {
            this.fromBase64String(string);
        }
        else {
            this.initToDefault(true);
        }
    }
    getChannelCount() {
        return this.pitchChannelCount + this.noiseChannelCount;
    }
    getChannelIsNoise(channel) {
        return (channel >= this.pitchChannelCount);
    }
    initToDefault(andResetChannels = true) {
        this.scale = 0;
        this.key = 0;
        this.loopStart = 0;
        this.loopLength = 4;
        this.tempo = 150;
        this.reverb = 0;
        this.beatsPerBar = 8;
        this.barCount = 16;
        this.patternsPerChannel = 8;
        this.rhythm = 1;
        this.instrumentsPerChannel = 1;
        this.title = "Unnamed";
        //document.title = "JummBox 1.1";
        if (andResetChannels) {
            this.pitchChannelCount = 3;
            this.noiseChannelCount = 1;
            for (let channelIndex = 0; channelIndex < this.getChannelCount(); channelIndex++) {
                if (this.channels.length <= channelIndex) {
                    this.channels[channelIndex] = new Channel();
                }
                const channel = this.channels[channelIndex];
                channel.octave = 3 - channelIndex;
                for (let pattern = 0; pattern < this.patternsPerChannel; pattern++) {
                    if (channel.patterns.length <= pattern) {
                        channel.patterns[pattern] = new Pattern();
                    }
                    else {
                        channel.patterns[pattern].reset();
                    }
                }
                channel.patterns.length = this.patternsPerChannel;
                const isNoiseChannel = channelIndex >= this.pitchChannelCount;
                for (let instrument = 0; instrument < this.instrumentsPerChannel; instrument++) {
                    if (channel.instruments.length <= instrument) {
                        channel.instruments[instrument] = new Instrument(isNoiseChannel);
                    }
                    channel.instruments[instrument].setTypeAndReset(isNoiseChannel ? 2 : 0, isNoiseChannel);
                }
                channel.instruments.length = this.instrumentsPerChannel;
                for (let bar = 0; bar < this.barCount; bar++) {
                    channel.bars[bar] = (bar < 4) ? 1 : 0;
                }
                channel.bars.length = this.barCount;
            }
            this.channels.length = this.getChannelCount();
        }
    }
    toBase64String() {
        let bits;
        let buffer = [];
        const base64IntToCharCode = Song._base64IntToCharCode;
        buffer.push(Song._variant);
        buffer.push(base64IntToCharCode[Song._latestJummBoxVersion]);
        buffer.push(78);
        var encodedSongTitle = encodeURIComponent(this.title);
        buffer.push(base64IntToCharCode[encodedSongTitle.length >> 6], base64IntToCharCode[encodedSongTitle.length & 0x3f]);
        for (let i = 0; i < encodedSongTitle.length; i++) {
            buffer.push(encodedSongTitle.charCodeAt(i));
        }
        buffer.push(110, base64IntToCharCode[this.pitchChannelCount], base64IntToCharCode[this.noiseChannelCount]);
        buffer.push(115, base64IntToCharCode[this.scale]);
        buffer.push(107, base64IntToCharCode[this.key]);
        buffer.push(108, base64IntToCharCode[this.loopStart >> 6], base64IntToCharCode[this.loopStart & 0x3f]);
        buffer.push(101, base64IntToCharCode[(this.loopLength - 1) >> 6], base64IntToCharCode[(this.loopLength - 1) & 0x3f]);
        buffer.push(116, base64IntToCharCode[this.tempo >> 6], base64IntToCharCode[this.tempo & 0x3F]);
        buffer.push(109, base64IntToCharCode[this.reverb]);
        buffer.push(97, base64IntToCharCode[this.beatsPerBar - 1]);
        buffer.push(103, base64IntToCharCode[(this.barCount - 1) >> 6], base64IntToCharCode[(this.barCount - 1) & 0x3f]);
        buffer.push(106, base64IntToCharCode[(this.patternsPerChannel - 1) >> 6], base64IntToCharCode[(this.patternsPerChannel - 1) & 0x3f]);
        buffer.push(105, base64IntToCharCode[this.instrumentsPerChannel - 1]);
        buffer.push(114, base64IntToCharCode[this.rhythm]);
        buffer.push(111);
        for (let channel = 0; channel < this.getChannelCount(); channel++) {
            buffer.push(base64IntToCharCode[this.channels[channel].octave]);
        }
        for (let channel = 0; channel < this.getChannelCount(); channel++) {
            for (let i = 0; i < this.instrumentsPerChannel; i++) {
                const instrument = this.channels[channel].instruments[i];
                buffer.push(84, base64IntToCharCode[instrument.type]);
                buffer.push(118, base64IntToCharCode[(instrument.volume + beepbox.Config.volumeRange / 2) >> 6], base64IntToCharCode[(instrument.volume + beepbox.Config.volumeRange / 2) & 0x3f]);
                buffer.push(117, base64IntToCharCode[instrument.preset >> 6], base64IntToCharCode[instrument.preset & 63]);
                buffer.push(113, base64IntToCharCode[instrument.effects]);
                buffer.push(76, base64IntToCharCode[instrument.pan >> 6], base64IntToCharCode[instrument.pan & 0x3f]);
                if (instrument.type != 4) {
                    buffer.push(100, base64IntToCharCode[instrument.transition]);
                    buffer.push(102, base64IntToCharCode[instrument.filterCutoff]);
                    buffer.push(121, base64IntToCharCode[instrument.filterResonance]);
                    buffer.push(122, base64IntToCharCode[instrument.filterEnvelope]);
                    buffer.push(67, base64IntToCharCode[instrument.chord]);
                }
                if (instrument.type == 0) {
                    buffer.push(119, base64IntToCharCode[instrument.chipWave]);
                    buffer.push(99, base64IntToCharCode[instrument.vibrato]);
                    buffer.push(104, base64IntToCharCode[instrument.interval]);
                }
                else if (instrument.type == 1) {
                    buffer.push(99, base64IntToCharCode[instrument.vibrato]);
                    buffer.push(65, base64IntToCharCode[instrument.algorithm]);
                    buffer.push(70, base64IntToCharCode[instrument.feedbackType]);
                    buffer.push(66, base64IntToCharCode[instrument.feedbackAmplitude]);
                    buffer.push(86, base64IntToCharCode[instrument.feedbackEnvelope]);
                    buffer.push(81);
                    for (let o = 0; o < beepbox.Config.operatorCount; o++) {
                        buffer.push(base64IntToCharCode[instrument.operators[o].frequency]);
                    }
                    buffer.push(80);
                    for (let o = 0; o < beepbox.Config.operatorCount; o++) {
                        buffer.push(base64IntToCharCode[instrument.operators[o].amplitude]);
                    }
                    buffer.push(69);
                    for (let o = 0; o < beepbox.Config.operatorCount; o++) {
                        buffer.push(base64IntToCharCode[instrument.operators[o].envelope]);
                    }
                }
                else if (instrument.type == 7) {
                    buffer.push(119, base64IntToCharCode[instrument.chipWave]);
                    buffer.push(99, base64IntToCharCode[instrument.vibrato]);
                    buffer.push(104, base64IntToCharCode[instrument.interval]);
                    buffer.push(77);
                    for (let j = 0; j < 64; j++) {
                        buffer.push(base64IntToCharCode[(instrument.customChipWave[j] + 24)]);
                    }
                }
                else if (instrument.type == 2) {
                    buffer.push(119, base64IntToCharCode[instrument.chipNoise]);
                }
                else if (instrument.type == 3) {
                    buffer.push(83);
                    const spectrumBits = new BitFieldWriter();
                    for (let i = 0; i < beepbox.Config.spectrumControlPoints; i++) {
                        spectrumBits.write(beepbox.Config.spectrumControlPointBits, instrument.spectrumWave.spectrum[i]);
                    }
                    spectrumBits.encodeBase64(base64IntToCharCode, buffer);
                }
                else if (instrument.type == 4) {
                    buffer.push(122);
                    for (let j = 0; j < beepbox.Config.drumCount; j++) {
                        buffer.push(base64IntToCharCode[instrument.drumsetEnvelopes[j]]);
                    }
                    buffer.push(83);
                    const spectrumBits = new BitFieldWriter();
                    for (let j = 0; j < beepbox.Config.drumCount; j++) {
                        for (let i = 0; i < beepbox.Config.spectrumControlPoints; i++) {
                            spectrumBits.write(beepbox.Config.spectrumControlPointBits, instrument.drumsetSpectrumWaves[j].spectrum[i]);
                        }
                    }
                    spectrumBits.encodeBase64(base64IntToCharCode, buffer);
                }
                else if (instrument.type == 5) {
                    buffer.push(99, base64IntToCharCode[instrument.vibrato]);
                    buffer.push(104, base64IntToCharCode[instrument.interval]);
                    buffer.push(72);
                    const harmonicsBits = new BitFieldWriter();
                    for (let i = 0; i < beepbox.Config.harmonicsControlPoints; i++) {
                        harmonicsBits.write(beepbox.Config.harmonicsControlPointBits, instrument.harmonicsWave.harmonics[i]);
                    }
                    harmonicsBits.encodeBase64(base64IntToCharCode, buffer);
                }
                else if (instrument.type == 6) {
                    buffer.push(99, base64IntToCharCode[instrument.vibrato]);
                    buffer.push(87, base64IntToCharCode[instrument.pulseWidth], base64IntToCharCode[instrument.pulseEnvelope]);
                }
                else {
                    throw new Error("Unknown instrument type.");
                }
            }
        }
        buffer.push(98);
        bits = new BitFieldWriter();
        let neededBits = 0;
        while ((1 << neededBits) < this.patternsPerChannel + 1)
            neededBits++;
        for (let channel = 0; channel < this.getChannelCount(); channel++)
            for (let i = 0; i < this.barCount; i++) {
                bits.write(neededBits, this.channels[channel].bars[i]);
            }
        bits.encodeBase64(base64IntToCharCode, buffer);
        buffer.push(112);
        bits = new BitFieldWriter();
        let neededInstrumentBits = 0;
        while ((1 << neededInstrumentBits) < this.instrumentsPerChannel)
            neededInstrumentBits++;
        for (let channel = 0; channel < this.getChannelCount(); channel++) {
            const isNoiseChannel = this.getChannelIsNoise(channel);
            const octaveOffset = isNoiseChannel ? 0 : this.channels[channel].octave * 12;
            let lastPitch = (isNoiseChannel ? 4 : 12) + octaveOffset;
            const recentPitches = isNoiseChannel ? [4, 6, 7, 2, 3, 8, 0, 10] : [12, 19, 24, 31, 36, 7, 0];
            const recentShapes = [];
            for (let i = 0; i < recentPitches.length; i++) {
                recentPitches[i] += octaveOffset;
            }
            for (const pattern of this.channels[channel].patterns) {
                bits.write(neededInstrumentBits, pattern.instrument);
                if (pattern.notes.length > 0) {
                    bits.write(1, 1);
                    let curPart = 0;
                    for (const note of pattern.notes) {
                        if (note.start > curPart) {
                            bits.write(2, 0);
                            bits.writePartDuration(note.start - curPart);
                        }
                        const shapeBits = new BitFieldWriter();
                        for (let i = 1; i < note.pitches.length; i++)
                            shapeBits.write(1, 1);
                        if (note.pitches.length < 4)
                            shapeBits.write(1, 0);
                        shapeBits.writePinCount(note.pins.length - 1);
                        shapeBits.write(3, note.pins[0].volume);
                        let shapePart = 0;
                        let startPitch = note.pitches[0];
                        let currentPitch = startPitch;
                        const pitchBends = [];
                        for (let i = 1; i < note.pins.length; i++) {
                            const pin = note.pins[i];
                            const nextPitch = startPitch + pin.interval;
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
                            shapeBits.write(3, pin.volume);
                        }
                        const shapeString = String.fromCharCode.apply(null, shapeBits.encodeBase64(base64IntToCharCode, []));
                        const shapeIndex = recentShapes.indexOf(shapeString);
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
                        const allPitches = note.pitches.concat(pitchBends);
                        for (let i = 0; i < allPitches.length; i++) {
                            const pitch = allPitches[i];
                            const pitchIndex = recentPitches.indexOf(pitch);
                            if (pitchIndex == -1) {
                                let interval = 0;
                                let pitchIter = lastPitch;
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
                            if (i == note.pitches.length - 1) {
                                lastPitch = note.pitches[0];
                            }
                            else {
                                lastPitch = pitch;
                            }
                        }
                        curPart = note.end;
                    }
                    if (curPart < this.beatsPerBar * beepbox.Config.partsPerBeat) {
                        bits.write(2, 0);
                        bits.writePartDuration(this.beatsPerBar * beepbox.Config.partsPerBeat - curPart);
                    }
                }
                else {
                    bits.write(1, 0);
                }
            }
        }
        let stringLength = bits.lengthBase64();
        let digits = [];
        while (stringLength > 0) {
            digits.unshift(base64IntToCharCode[stringLength & 0x3f]);
            stringLength = stringLength >> 6;
        }
        buffer.push(base64IntToCharCode[digits.length]);
        Array.prototype.push.apply(buffer, digits);
        bits.encodeBase64(base64IntToCharCode, buffer);
        const maxApplyArgs = 64000;
        if (buffer.length < maxApplyArgs) {
            return String.fromCharCode.apply(null, buffer);
        }
        else {
            let result = "";
            for (let i = 0; i < buffer.length; i += maxApplyArgs) {
                result += String.fromCharCode.apply(null, buffer.slice(i, i + maxApplyArgs));
            }
            return result;
        }
    }
    fromBase64String(compressed) {
        if (compressed == null || compressed == "") {
            this.initToDefault(true);
            return;
        }
        let charIndex = 0;
        while (compressed.charCodeAt(charIndex) <= 32)
            charIndex++;
        if (compressed.charCodeAt(charIndex) == 35)
            charIndex++;
        if (compressed.charCodeAt(charIndex) == 123) {
            this.fromJsonObject(JSON.parse(charIndex == 0 ? compressed : compressed.substring(charIndex)));
            return;
        }
        const variantTest = compressed.charCodeAt(charIndex);
        var variant = "";
        if (variantTest == 0x6A) {
            variant = "jummbox";
            charIndex++;
        }
        else {
            variant = "beepbox";
        }
        const version = Song._base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
        if (variant == "beepbox" && (version == -1 || version > Song._latestBeepboxVersion || version < Song._oldestBeepboxVersion))
            return;
        if (variant == "jummbox" && (version == -1 || version > Song._latestJummBoxVersion || version < Song._oldestJummBoxVersion))
            return;
        const beforeTwo = version < 2;
        const beforeThree = version < 3;
        const beforeFour = version < 4;
        const beforeFive = version < 5;
        const beforeSix = version < 6;
        const beforeSeven = version < 7;
        const base64CharCodeToInt = Song._base64CharCodeToInt;
        this.initToDefault((variant == "beepbox" && beforeSix));
        if (beforeThree && variant == "beepbox") {
            for (const channel of this.channels)
                channel.instruments[0].transition = 0;
            this.channels[3].instruments[0].chipNoise = 0;
        }
        let instrumentChannelIterator = 0;
        let instrumentIndexIterator = -1;
        while (charIndex < compressed.length) {
            const command = compressed.charCodeAt(charIndex++);
            let channel;
            if (command == 78) {
                var songNameLength = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) + base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                this.title = decodeURIComponent(compressed.substring(charIndex, charIndex + songNameLength));
                //document.title = this.title + " - JummBox 1.1";
                charIndex += songNameLength;
            }
            else if (command == 110) {
                this.pitchChannelCount = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                this.noiseChannelCount = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                this.pitchChannelCount = clamp(beepbox.Config.pitchChannelCountMin, beepbox.Config.pitchChannelCountMax + 1, this.pitchChannelCount);
                this.noiseChannelCount = clamp(beepbox.Config.noiseChannelCountMin, beepbox.Config.noiseChannelCountMax + 1, this.noiseChannelCount);
                for (let channelIndex = this.channels.length; channelIndex < this.getChannelCount(); channelIndex++) {
                    this.channels[channelIndex] = new Channel();
                }
                this.channels.length = this.getChannelCount();
            }
            else if (command == 115) {
                this.scale = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                if (variant == "beepbox")
                    this.scale = 0;
            }
            else if (command == 107) {
                if (beforeSeven && variant == "beepbox") {
                    this.key = clamp(0, beepbox.Config.keys.length, 11 - base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else {
                    this.key = clamp(0, beepbox.Config.keys.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
            }
            else if (command == 108) {
                if (beforeFive && variant == "beepbox") {
                    this.loopStart = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                }
                else {
                    this.loopStart = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) + base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                }
            }
            else if (command == 101) {
                if (beforeFive && variant == "beepbox") {
                    this.loopLength = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                }
                else {
                    this.loopLength = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) + base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                }
            }
            else if (command == 116) {
                if (beforeFour && variant == "beepbox") {
                    this.tempo = [95, 120, 151, 190][base64CharCodeToInt[compressed.charCodeAt(charIndex++)]];
                }
                else if (beforeSeven && variant == "beepbox") {
                    this.tempo = [88, 95, 103, 111, 120, 130, 140, 151, 163, 176, 190, 206, 222, 240, 259][base64CharCodeToInt[compressed.charCodeAt(charIndex++)]];
                }
                else {
                    this.tempo = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) | (base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                this.tempo = clamp(beepbox.Config.tempoMin, beepbox.Config.tempoMax + 1, this.tempo);
            }
            else if (command == 109) {
                if (variant == "beepbox") {
                    this.reverb = base64CharCodeToInt[compressed.charCodeAt(charIndex++)] * 8;
                    this.reverb = clamp(0, beepbox.Config.reverbRange, this.reverb);
                }
                else {
                    this.reverb = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.reverb = clamp(0, beepbox.Config.reverbRange, this.reverb);
                }
            }
            else if (command == 97) {
                if (beforeThree && variant == "beepbox") {
                    this.beatsPerBar = [6, 7, 8, 9, 10][base64CharCodeToInt[compressed.charCodeAt(charIndex++)]];
                }
                else {
                    this.beatsPerBar = base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                }
                this.beatsPerBar = Math.max(beepbox.Config.beatsPerBarMin, Math.min(beepbox.Config.beatsPerBarMax, this.beatsPerBar));
            }
            else if (command == 103) {
                this.barCount = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) + base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                this.barCount = Math.max(beepbox.Config.barCountMin, Math.min(beepbox.Config.barCountMax, this.barCount));
                for (let channel = 0; channel < this.getChannelCount(); channel++) {
                    for (let bar = this.channels[channel].bars.length; bar < this.barCount; bar++) {
                        this.channels[channel].bars[bar] = (bar < 4) ? 1 : 0;
                    }
                    this.channels[channel].bars.length = this.barCount;
                }
            }
            else if (command == 106) {
                if (variant == "beepbox") {
                    this.patternsPerChannel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                }
                else {
                    this.patternsPerChannel = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) + base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                }
                this.patternsPerChannel = Math.max(beepbox.Config.patternsPerChannelMin, Math.min(beepbox.Config.patternsPerChannelMax, this.patternsPerChannel));
                for (let channel = 0; channel < this.getChannelCount(); channel++) {
                    for (let pattern = this.channels[channel].patterns.length; pattern < this.patternsPerChannel; pattern++) {
                        this.channels[channel].patterns[pattern] = new Pattern();
                    }
                    this.channels[channel].patterns.length = this.patternsPerChannel;
                }
            }
            else if (command == 105) {
                this.instrumentsPerChannel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1;
                this.instrumentsPerChannel = Math.max(beepbox.Config.instrumentsPerChannelMin, Math.min(beepbox.Config.instrumentsPerChannelMax, this.instrumentsPerChannel));
                for (let channel = 0; channel < this.getChannelCount(); channel++) {
                    const isNoiseChannel = channel >= this.pitchChannelCount;
                    for (let instrumentIndex = this.channels[channel].instruments.length; instrumentIndex < this.instrumentsPerChannel; instrumentIndex++) {
                        this.channels[channel].instruments[instrumentIndex] = new Instrument(isNoiseChannel);
                    }
                    this.channels[channel].instruments.length = this.instrumentsPerChannel;
                    if (beforeSix && variant == "beepbox") {
                        for (let instrumentIndex = 0; instrumentIndex < this.instrumentsPerChannel; instrumentIndex++) {
                            this.channels[channel].instruments[instrumentIndex].setTypeAndReset(isNoiseChannel ? 2 : 0, isNoiseChannel);
                        }
                    }
                }
            }
            else if (command == 114) {
                this.rhythm = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
            }
            else if (command == 111) {
                if (beforeThree && variant == "beepbox") {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.channels[channel].octave = clamp(0, beepbox.Config.scrollableOctaves + 1, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        this.channels[channel].octave = clamp(0, beepbox.Config.scrollableOctaves + 1, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    }
                }
            }
            else if (command == 84) {
                instrumentIndexIterator++;
                if (instrumentIndexIterator >= this.instrumentsPerChannel) {
                    instrumentChannelIterator++;
                    instrumentIndexIterator = 0;
                }
                const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                const instrumentType = clamp(0, 8, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                instrument.setTypeAndReset(instrumentType, instrumentChannelIterator >= this.pitchChannelCount);
            }
            else if (command == 117) {
                const presetValue = (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) | (base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].preset = presetValue;
            }
            else if (command == 119) {
                if (beforeThree && variant == "beepbox") {
                    const legacyWaves = [1, 2, 3, 4, 5, 6, 7, 8, 0];
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.channels[channel].instruments[0].chipWave = clamp(0, beepbox.Config.chipWaves.length, legacyWaves[base64CharCodeToInt[compressed.charCodeAt(charIndex++)]] | 0);
                }
                else if (beforeSix && variant == "beepbox") {
                    const legacyWaves = [1, 2, 3, 4, 5, 6, 7, 8, 0];
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (let i = 0; i < this.instrumentsPerChannel; i++) {
                            if (channel >= this.pitchChannelCount) {
                                this.channels[channel].instruments[i].chipNoise = clamp(0, beepbox.Config.chipNoises.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                            }
                            else {
                                this.channels[channel].instruments[i].chipWave = clamp(0, beepbox.Config.chipWaves.length, legacyWaves[base64CharCodeToInt[compressed.charCodeAt(charIndex++)]] | 0);
                            }
                        }
                    }
                }
                else if (beforeSeven && variant == "beepbox") {
                    const legacyWaves = [1, 2, 3, 4, 5, 6, 7, 8, 0];
                    if (instrumentChannelIterator >= this.pitchChannelCount) {
                        this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].chipNoise = clamp(0, beepbox.Config.chipNoises.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    }
                    else {
                        this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].chipWave = clamp(0, beepbox.Config.chipWaves.length, legacyWaves[base64CharCodeToInt[compressed.charCodeAt(charIndex++)]] | 0);
                    }
                }
                else {
                    if (instrumentChannelIterator >= this.pitchChannelCount) {
                        this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].chipNoise = clamp(0, beepbox.Config.chipNoises.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    }
                    else {
                        this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].chipWave = clamp(0, beepbox.Config.chipWaves.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    }
                }
            }
            else if (command == 102) {
                if (beforeSeven && variant == "beepbox") {
                    const legacyToCutoff = [10, 6, 3, 0, 8, 5, 2];
                    const legacyToEnvelope = [1, 1, 1, 1, 18, 19, 20];
                    const filterNames = ["none", "bright", "medium", "soft", "decay bright", "decay medium", "decay soft"];
                    if (beforeThree && variant == "beepbox") {
                        channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                        const instrument = this.channels[channel].instruments[0];
                        const legacyFilter = [1, 3, 4, 5][clamp(0, filterNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)])];
                        instrument.filterCutoff = legacyToCutoff[legacyFilter];
                        instrument.filterEnvelope = legacyToEnvelope[legacyFilter];
                        instrument.filterResonance = 0;
                    }
                    else if (beforeSix && variant == "beepbox") {
                        for (channel = 0; channel < this.getChannelCount(); channel++) {
                            for (let i = 0; i < this.instrumentsPerChannel; i++) {
                                const instrument = this.channels[channel].instruments[i];
                                if (channel < this.pitchChannelCount) {
                                    const legacyFilter = clamp(0, filterNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)] + 1);
                                    instrument.filterCutoff = legacyToCutoff[legacyFilter];
                                    instrument.filterEnvelope = legacyToEnvelope[legacyFilter];
                                    instrument.filterResonance = 0;
                                }
                                else {
                                    instrument.filterCutoff = 10;
                                    instrument.filterEnvelope = 1;
                                    instrument.filterResonance = 0;
                                }
                            }
                        }
                    }
                    else {
                        const legacyFilter = clamp(0, filterNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                        const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                        instrument.filterCutoff = legacyToCutoff[legacyFilter];
                        instrument.filterEnvelope = legacyToEnvelope[legacyFilter];
                        instrument.filterResonance = 0;
                    }
                }
                else {
                    const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                    instrument.filterCutoff = clamp(0, beepbox.Config.filterCutoffRange, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
            }
            else if (command == 121) {
                this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].filterResonance = clamp(0, beepbox.Config.filterResonanceRange, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
            }
            else if (command == 122) {
                const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                if (instrument.type == 4) {
                    for (let i = 0; i < beepbox.Config.drumCount; i++) {
                        instrument.drumsetEnvelopes[i] = clamp(0, beepbox.Config.envelopes.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    }
                }
                else {
                    instrument.filterEnvelope = clamp(0, beepbox.Config.envelopes.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
            }
            else if (command == 87) {
                if (variant == "beepbox") {
                    const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                    instrument.pulseWidth = Math.round(clamp(0, beepbox.Config.pulseWidthRange + 1, Math.pow(0.5, (7 - base64CharCodeToInt[compressed.charCodeAt(charIndex++)]) * 0.5) * 50));
                    instrument.pulseEnvelope = clamp(0, beepbox.Config.envelopes.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else {
                    const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                    instrument.pulseWidth = clamp(0, beepbox.Config.pulseWidthRange + 1, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    instrument.pulseEnvelope = clamp(0, beepbox.Config.envelopes.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
            }
            else if (command == 100) {
                if (beforeThree && variant == "beepbox") {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.channels[channel].instruments[0].transition = clamp(0, beepbox.Config.transitions.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else if (beforeSix && variant == "beepbox") {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (let i = 0; i < this.instrumentsPerChannel; i++) {
                            this.channels[channel].instruments[i].transition = clamp(0, beepbox.Config.transitions.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                        }
                    }
                }
                else {
                    this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].transition = clamp(0, beepbox.Config.transitions.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
            }
            else if (command == 99) {
                if (beforeThree && variant == "beepbox") {
                    const legacyEffects = [0, 3, 2, 0];
                    const legacyEnvelopes = [1, 1, 1, 13];
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    const effect = clamp(0, legacyEffects.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    const instrument = this.channels[channel].instruments[0];
                    instrument.vibrato = legacyEffects[effect];
                    instrument.filterEnvelope = (instrument.filterEnvelope == 1)
                        ? legacyEnvelopes[effect]
                        : instrument.filterEnvelope;
                }
                else if (beforeSix && variant == "beepbox") {
                    const legacyEffects = [0, 1, 2, 3, 0, 0];
                    const legacyEnvelopes = [1, 1, 1, 1, 16, 13];
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (let i = 0; i < this.instrumentsPerChannel; i++) {
                            const effect = clamp(0, legacyEffects.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                            const instrument = this.channels[channel].instruments[i];
                            instrument.vibrato = legacyEffects[effect];
                            instrument.filterEnvelope = (instrument.filterEnvelope == 1)
                                ? legacyEnvelopes[effect]
                                : instrument.filterEnvelope;
                        }
                    }
                }
                else if (beforeSeven && variant == "beepbox") {
                    const legacyEffects = [0, 1, 2, 3, 0, 0];
                    const legacyEnvelopes = [1, 1, 1, 1, 16, 13];
                    const effect = clamp(0, legacyEffects.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                    instrument.vibrato = legacyEffects[effect];
                    instrument.filterEnvelope = (instrument.filterEnvelope == 1)
                        ? legacyEnvelopes[effect]
                        : instrument.filterEnvelope;
                }
                else {
                    const vibrato = clamp(0, beepbox.Config.vibratos.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                    this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].vibrato = vibrato;
                }
            }
            else if (command == 104) {
                if (beforeThree && variant == "beepbox") {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    this.channels[channel].instruments[0].interval = clamp(0, beepbox.Config.intervals.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
                else if (beforeSix && variant == "beepbox") {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (let i = 0; i < this.instrumentsPerChannel; i++) {
                            const originalValue = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                            let interval = clamp(0, beepbox.Config.intervals.length, originalValue);
                            if (originalValue == 8) {
                                interval = 2;
                                this.channels[channel].instruments[i].chord = 3;
                            }
                            this.channels[channel].instruments[i].interval = interval;
                        }
                    }
                }
                else if (beforeSeven && variant == "beepbox") {
                    const originalValue = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    let interval = clamp(0, beepbox.Config.intervals.length, originalValue);
                    if (originalValue == 8) {
                        interval = 2;
                        this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].chord = 3;
                    }
                    this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].interval = interval;
                }
                else {
                    this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].interval = clamp(0, beepbox.Config.intervals.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
            }
            else if (command == 67) {
                this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].chord = clamp(0, beepbox.Config.chords.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
            }
            else if (command == 113) {
                this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].effects = clamp(0, beepbox.Config.effectsNames.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
            }
            else if (command == 118) {
                if (beforeThree && variant == "beepbox") {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    const instrument = this.channels[channel].instruments[0];
                    instrument.volume = Math.round(clamp(-beepbox.Config.volumeRange, 1, -base64CharCodeToInt[compressed.charCodeAt(charIndex++)] * 5.0));
                }
                else if (beforeSix && variant == "beepbox") {
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (let i = 0; i < this.instrumentsPerChannel; i++) {
                            const instrument = this.channels[channel].instruments[i];
                            instrument.volume = Math.round(clamp(-beepbox.Config.volumeRange, 1, -base64CharCodeToInt[compressed.charCodeAt(charIndex++)] * 5.0));
                        }
                    }
                }
                else if (beforeSeven && variant == "beepbox") {
                    const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                    instrument.volume = Math.round(clamp(-beepbox.Config.volumeRange, 1, -base64CharCodeToInt[compressed.charCodeAt(charIndex++)] * 5.0));
                }
                else if (variant == "beepbox") {
                    const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                    instrument.volume = Math.round(clamp(-beepbox.Config.volumeRange / 2, 1, -base64CharCodeToInt[compressed.charCodeAt(charIndex++)] * 25.0 / 7.0));
                }
                else {
                    const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                    instrument.volume = Math.round(clamp(-beepbox.Config.volumeRange / 2, beepbox.Config.volumeRange / 2 + 1, ((base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) | (base64CharCodeToInt[compressed.charCodeAt(charIndex++)])) - beepbox.Config.volumeRange / 2));
                }
            }
            else if (command == 76) {
                this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].pan = clamp(0, 101, (base64CharCodeToInt[compressed.charCodeAt(charIndex++)] << 6) + base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
            }
            else if (command == 77) {
                let instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                for (let j = 0; j < 64; j++) {
                    instrument.customChipWave[j]
                        = clamp(-24, 25, base64CharCodeToInt[compressed.charCodeAt(charIndex++)] - 24);
                }
                let sum = 0.0;
                for (let i = 0; i < instrument.customChipWave.length; i++) {
                    sum += instrument.customChipWave[i];
                }
                const average = sum / instrument.customChipWave.length;
                let cumulative = 0;
                let wavePrev = 0;
                for (let i = 0; i < instrument.customChipWave.length; i++) {
                    cumulative += wavePrev;
                    wavePrev = instrument.customChipWave[i] - average;
                    instrument.customChipWaveIntegral[i] = cumulative;
                }
                instrument.customChipWaveIntegral[64] = 0.0;
            }
            else if (command == 65) {
                this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].algorithm = clamp(0, beepbox.Config.algorithms.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
            }
            else if (command == 70) {
                this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].feedbackType = clamp(0, beepbox.Config.feedbacks.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
            }
            else if (command == 66) {
                this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].feedbackAmplitude = clamp(0, beepbox.Config.operatorAmplitudeMax + 1, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
            }
            else if (command == 86) {
                this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].feedbackEnvelope = clamp(0, beepbox.Config.envelopes.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
            }
            else if (command == 81) {
                for (let o = 0; o < beepbox.Config.operatorCount; o++) {
                    this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].operators[o].frequency = clamp(0, beepbox.Config.operatorFrequencies.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
            }
            else if (command == 80) {
                for (let o = 0; o < beepbox.Config.operatorCount; o++) {
                    this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].operators[o].amplitude = clamp(0, beepbox.Config.operatorAmplitudeMax + 1, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
            }
            else if (command == 69) {
                for (let o = 0; o < beepbox.Config.operatorCount; o++) {
                    this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator].operators[o].envelope = clamp(0, beepbox.Config.envelopes.length, base64CharCodeToInt[compressed.charCodeAt(charIndex++)]);
                }
            }
            else if (command == 83) {
                const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                if (instrument.type == 3) {
                    const byteCount = Math.ceil(beepbox.Config.spectrumControlPoints * beepbox.Config.spectrumControlPointBits / 6);
                    const bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + byteCount);
                    for (let i = 0; i < beepbox.Config.spectrumControlPoints; i++) {
                        instrument.spectrumWave.spectrum[i] = bits.read(beepbox.Config.spectrumControlPointBits);
                    }
                    instrument.spectrumWave.markCustomWaveDirty();
                    charIndex += byteCount;
                }
                else if (instrument.type == 4) {
                    const byteCount = Math.ceil(beepbox.Config.drumCount * beepbox.Config.spectrumControlPoints * beepbox.Config.spectrumControlPointBits / 6);
                    const bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + byteCount);
                    for (let j = 0; j < beepbox.Config.drumCount; j++) {
                        for (let i = 0; i < beepbox.Config.spectrumControlPoints; i++) {
                            instrument.drumsetSpectrumWaves[j].spectrum[i] = bits.read(beepbox.Config.spectrumControlPointBits);
                        }
                        instrument.drumsetSpectrumWaves[j].markCustomWaveDirty();
                    }
                    charIndex += byteCount;
                }
                else {
                    throw new Error("Unhandled instrument type for spectrum song tag code.");
                }
            }
            else if (command == 72) {
                const instrument = this.channels[instrumentChannelIterator].instruments[instrumentIndexIterator];
                const byteCount = Math.ceil(beepbox.Config.harmonicsControlPoints * beepbox.Config.harmonicsControlPointBits / 6);
                const bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + byteCount);
                for (let i = 0; i < beepbox.Config.harmonicsControlPoints; i++) {
                    instrument.harmonicsWave.harmonics[i] = bits.read(beepbox.Config.harmonicsControlPointBits);
                }
                instrument.harmonicsWave.markCustomWaveDirty();
                charIndex += byteCount;
            }
            else if (command == 98) {
                let subStringLength;
                if (beforeThree && variant == "beepbox") {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    const barCount = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    subStringLength = Math.ceil(barCount * 0.5);
                    const bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + subStringLength);
                    for (let i = 0; i < barCount; i++) {
                        this.channels[channel].bars[i] = bits.read(3) + 1;
                    }
                }
                else if (beforeFive && variant == "beepbox") {
                    let neededBits = 0;
                    while ((1 << neededBits) < this.patternsPerChannel)
                        neededBits++;
                    subStringLength = Math.ceil(this.getChannelCount() * this.barCount * neededBits / 6);
                    const bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + subStringLength);
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (let i = 0; i < this.barCount; i++) {
                            this.channels[channel].bars[i] = bits.read(neededBits) + 1;
                        }
                    }
                }
                else {
                    let neededBits = 0;
                    while ((1 << neededBits) < this.patternsPerChannel + 1)
                        neededBits++;
                    subStringLength = Math.ceil(this.getChannelCount() * this.barCount * neededBits / 6);
                    const bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + subStringLength);
                    for (channel = 0; channel < this.getChannelCount(); channel++) {
                        for (let i = 0; i < this.barCount; i++) {
                            this.channels[channel].bars[i] = bits.read(neededBits);
                        }
                    }
                }
                charIndex += subStringLength;
            }
            else if (command == 112) {
                let bitStringLength = 0;
                if (beforeThree && variant == "beepbox") {
                    channel = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    charIndex++;
                    bitStringLength = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    bitStringLength = bitStringLength << 6;
                    bitStringLength += base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                }
                else {
                    channel = 0;
                    let bitStringLengthLength = base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                    while (bitStringLengthLength > 0) {
                        bitStringLength = bitStringLength << 6;
                        bitStringLength += base64CharCodeToInt[compressed.charCodeAt(charIndex++)];
                        bitStringLengthLength--;
                    }
                }
                const bits = new BitFieldReader(base64CharCodeToInt, compressed, charIndex, charIndex + bitStringLength);
                charIndex += bitStringLength;
                let neededInstrumentBits = 0;
                while ((1 << neededInstrumentBits) < this.instrumentsPerChannel)
                    neededInstrumentBits++;
                while (true) {
                    const isNoiseChannel = this.getChannelIsNoise(channel);
                    const octaveOffset = isNoiseChannel ? 0 : this.channels[channel].octave * 12;
                    let note = null;
                    let pin = null;
                    let lastPitch = (isNoiseChannel ? 4 : 12) + octaveOffset;
                    const recentPitches = isNoiseChannel ? [4, 6, 7, 2, 3, 8, 0, 10] : [12, 19, 24, 31, 36, 7, 0];
                    const recentShapes = [];
                    for (let i = 0; i < recentPitches.length; i++) {
                        recentPitches[i] += octaveOffset;
                    }
                    for (let i = 0; i < this.patternsPerChannel; i++) {
                        const newPattern = this.channels[channel].patterns[i];
                        newPattern.reset();
                        newPattern.instrument = bits.read(neededInstrumentBits);
                        if (!(variant == "beepbox" && beforeThree) && bits.read(1) == 0)
                            continue;
                        let curPart = 0;
                        const newNotes = newPattern.notes;
                        while (curPart < this.beatsPerBar * beepbox.Config.partsPerBeat) {
                            const useOldShape = bits.read(1) == 1;
                            let newNote = false;
                            let shapeIndex = 0;
                            if (useOldShape) {
                                shapeIndex = bits.readLongTail(0, 0);
                            }
                            else {
                                newNote = bits.read(1) == 1;
                            }
                            if (!useOldShape && !newNote) {
                                const restLength = (beforeSeven && variant == "beepbox")
                                    ? bits.readLegacyPartDuration() * beepbox.Config.partsPerBeat / beepbox.Config.rhythms[this.rhythm].stepsPerBeat
                                    : bits.readPartDuration();
                                curPart += restLength;
                            }
                            else {
                                let shape;
                                let pinObj;
                                let pitch;
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
                                    if (variant == "beepbox") {
                                        shape.initialVolume = bits.read(2) * 2;
                                    }
                                    else {
                                        shape.initialVolume = bits.read(3);
                                    }
                                    shape.pins = [];
                                    shape.length = 0;
                                    shape.bendCount = 0;
                                    for (let j = 0; j < shape.pinCount; j++) {
                                        pinObj = {};
                                        pinObj.pitchBend = bits.read(1) == 1;
                                        if (pinObj.pitchBend)
                                            shape.bendCount++;
                                        shape.length += (beforeSeven && variant == "beepbox")
                                            ? bits.readLegacyPartDuration() * beepbox.Config.partsPerBeat / beepbox.Config.rhythms[this.rhythm].stepsPerBeat
                                            : bits.readPartDuration();
                                        pinObj.time = shape.length;
                                        if (variant == "beepbox") {
                                            pinObj.volume = bits.read(2) * 2;
                                        }
                                        else {
                                            pinObj.volume = bits.read(3);
                                        }
                                        shape.pins.push(pinObj);
                                    }
                                }
                                recentShapes.unshift(shape);
                                if (recentShapes.length > 10)
                                    recentShapes.pop();
                                note = new Note(0, curPart, curPart + shape.length, shape.initialVolume);
                                note.pitches = [];
                                note.pins.length = 1;
                                const pitchBends = [];
                                for (let j = 0; j < shape.pitchCount + shape.bendCount; j++) {
                                    const useOldPitch = bits.read(1) == 1;
                                    if (!useOldPitch) {
                                        const interval = bits.readPitchInterval();
                                        pitch = lastPitch;
                                        let intervalIter = interval;
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
                                        const pitchIndex = bits.read(3);
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
                                for (const pinObj of shape.pins) {
                                    if (pinObj.pitchBend)
                                        pitchBends.shift();
                                    pin = makeNotePin(pitchBends[0] - note.pitches[0], pinObj.time, pinObj.volume);
                                    note.pins.push(pin);
                                }
                                curPart = note.end;
                                newNotes.push(note);
                            }
                        }
                    }
                    if (beforeThree && variant == "beepbox") {
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
    }
    toJsonObject(enableIntro = true, loopCount = 1, enableOutro = true) {
        const channelArray = [];
        for (let channel = 0; channel < this.getChannelCount(); channel++) {
            const instrumentArray = [];
            const isNoiseChannel = this.getChannelIsNoise(channel);
            for (let i = 0; i < this.instrumentsPerChannel; i++) {
                instrumentArray.push(this.channels[channel].instruments[i].toJsonObject());
            }
            const patternArray = [];
            for (const pattern of this.channels[channel].patterns) {
                const noteArray = [];
                for (const note of pattern.notes) {
                    const pointArray = [];
                    for (const pin of note.pins) {
                        pointArray.push({
                            "tick": (pin.time + note.start) * beepbox.Config.rhythms[this.rhythm].stepsPerBeat / beepbox.Config.partsPerBeat,
                            "pitchBend": pin.interval,
                            "volume": Math.round(pin.volume * 100 / 6),
                        });
                    }
                    noteArray.push({
                        "pitches": note.pitches,
                        "points": pointArray,
                    });
                }
                patternArray.push({
                    "instrument": pattern.instrument + 1,
                    "notes": noteArray,
                });
            }
            const sequenceArray = [];
            if (enableIntro)
                for (let i = 0; i < this.loopStart; i++) {
                    sequenceArray.push(this.channels[channel].bars[i]);
                }
            for (let l = 0; l < loopCount; l++)
                for (let i = this.loopStart; i < this.loopStart + this.loopLength; i++) {
                    sequenceArray.push(this.channels[channel].bars[i]);
                }
            if (enableOutro)
                for (let i = this.loopStart + this.loopLength; i < this.barCount; i++) {
                    sequenceArray.push(this.channels[channel].bars[i]);
                }
            channelArray.push({
                "type": isNoiseChannel ? "drum" : "pitch",
                "octaveScrollBar": this.channels[channel].octave,
                "instruments": instrumentArray,
                "patterns": patternArray,
                "sequence": sequenceArray,
            });
        }
        return {
            "format": Song._format,
            "version": Song._latestJummBoxVersion,
            "scale": beepbox.Config.scales[this.scale].name,
            "key": beepbox.Config.keys[this.key].name,
            "introBars": this.loopStart,
            "loopBars": this.loopLength,
            "beatsPerBar": this.beatsPerBar,
            "ticksPerBeat": beepbox.Config.rhythms[this.rhythm].stepsPerBeat,
            "beatsPerMinute": this.tempo,
            "reverb": this.reverb,
            "channels": channelArray,
        };
    }
    fromJsonObject(jsonObject) {
        this.initToDefault(true);
        if (!jsonObject)
            return;
        const version = jsonObject["version"] | 0;
        this.scale = 0;
        if (jsonObject["scale"] != undefined) {
            const oldScaleNames = { "romani :)": 8, "romani :(": 9 };
            const scale = oldScaleNames[jsonObject["scale"]] != undefined ? oldScaleNames[jsonObject["scale"]] : beepbox.Config.scales.findIndex(scale => scale.name == jsonObject["scale"]);
            if (scale != -1)
                this.scale = scale;
        }
        if (jsonObject["key"] != undefined) {
            if (typeof (jsonObject["key"]) == "number") {
                this.key = ((jsonObject["key"] + 1200) >>> 0) % beepbox.Config.keys.length;
            }
            else if (typeof (jsonObject["key"]) == "string") {
                const key = jsonObject["key"];
                const letter = key.charAt(0).toUpperCase();
                const symbol = key.charAt(1).toLowerCase();
                const letterMap = { "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11 };
                const accidentalMap = { "#": 1, "♯": 1, "b": -1, "♭": -1 };
                let index = letterMap[letter];
                const offset = accidentalMap[symbol];
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
        if (jsonObject["beatsPerMinute"] != undefined) {
            this.tempo = clamp(beepbox.Config.tempoMin, beepbox.Config.tempoMax + 1, jsonObject["beatsPerMinute"] | 0);
        }
        if (jsonObject["reverb"] != undefined) {
            this.reverb = clamp(0, beepbox.Config.reverbRange, jsonObject["reverb"] | 0);
        }
        if (jsonObject["beatsPerBar"] != undefined) {
            this.beatsPerBar = Math.max(beepbox.Config.beatsPerBarMin, Math.min(beepbox.Config.beatsPerBarMax, jsonObject["beatsPerBar"] | 0));
        }
        let importedPartsPerBeat = 4;
        if (jsonObject["ticksPerBeat"] != undefined) {
            importedPartsPerBeat = (jsonObject["ticksPerBeat"] | 0) || 4;
            this.rhythm = beepbox.Config.rhythms.findIndex(rhythm => rhythm.stepsPerBeat == importedPartsPerBeat);
            if (this.rhythm == -1) {
                this.rhythm = 1;
            }
        }
        let maxInstruments = 1;
        let maxPatterns = 1;
        let maxBars = 1;
        if (jsonObject["channels"]) {
            for (const channelObject of jsonObject["channels"]) {
                if (channelObject["instruments"])
                    maxInstruments = Math.max(maxInstruments, channelObject["instruments"].length | 0);
                if (channelObject["patterns"])
                    maxPatterns = Math.max(maxPatterns, channelObject["patterns"].length | 0);
                if (channelObject["sequence"])
                    maxBars = Math.max(maxBars, channelObject["sequence"].length | 0);
            }
        }
        this.instrumentsPerChannel = maxInstruments;
        this.patternsPerChannel = maxPatterns;
        this.barCount = maxBars;
        if (jsonObject["introBars"] != undefined) {
            this.loopStart = clamp(0, this.barCount, jsonObject["introBars"] | 0);
        }
        if (jsonObject["loopBars"] != undefined) {
            this.loopLength = clamp(1, this.barCount - this.loopStart + 1, jsonObject["loopBars"] | 0);
        }
        let pitchChannelCount = 0;
        let noiseChannelCount = 0;
        if (jsonObject["channels"]) {
            for (let channel = 0; channel < jsonObject["channels"].length; channel++) {
                let channelObject = jsonObject["channels"][channel];
                if (this.channels.length <= channel)
                    this.channels[channel] = new Channel();
                let isNoiseChannel = false;
                if (channelObject["type"]) {
                    isNoiseChannel = (channelObject["type"] == "drum");
                }
                else {
                    isNoiseChannel = (channel >= 3);
                }
                if (isNoiseChannel)
                    noiseChannelCount++;
                else
                    pitchChannelCount++;
                if (channelObject["octaveScrollBar"] != undefined) {
                    this.channels[channel].octave = clamp(0, beepbox.Config.scrollableOctaves + 1, channelObject["octaveScrollBar"] | 0);
                }
                for (let i = this.channels[channel].instruments.length; i < this.instrumentsPerChannel; i++) {
                    this.channels[channel].instruments[i] = new Instrument(isNoiseChannel);
                }
                this.channels[channel].instruments.length = this.instrumentsPerChannel;
                for (let i = this.channels[channel].patterns.length; i < this.patternsPerChannel; i++) {
                    this.channels[channel].patterns[i] = new Pattern();
                }
                this.channels[channel].patterns.length = this.patternsPerChannel;
                for (let i = 0; i < this.barCount; i++) {
                    this.channels[channel].bars[i] = 1;
                }
                this.channels[channel].bars.length = this.barCount;
                for (let i = 0; i < this.instrumentsPerChannel; i++) {
                    const instrument = this.channels[channel].instruments[i];
                    instrument.fromJsonObject(channelObject["instruments"][i], isNoiseChannel);
                }
                for (let i = 0; i < this.patternsPerChannel; i++) {
                    const pattern = this.channels[channel].patterns[i];
                    let patternObject = undefined;
                    if (channelObject["patterns"])
                        patternObject = channelObject["patterns"][i];
                    if (patternObject == undefined)
                        continue;
                    pattern.instrument = clamp(0, this.instrumentsPerChannel, (patternObject["instrument"] | 0) - 1);
                    if (patternObject["notes"] && patternObject["notes"].length > 0) {
                        const maxNoteCount = Math.min(this.beatsPerBar * beepbox.Config.partsPerBeat, patternObject["notes"].length >>> 0);
                        let tickClock = 0;
                        for (let j = 0; j < patternObject["notes"].length; j++) {
                            if (j >= maxNoteCount)
                                break;
                            const noteObject = patternObject["notes"][j];
                            if (!noteObject || !noteObject["pitches"] || !(noteObject["pitches"].length >= 1) || !noteObject["points"] || !(noteObject["points"].length >= 2)) {
                                continue;
                            }
                            const note = new Note(0, 0, 0, 0);
                            note.pitches = [];
                            note.pins = [];
                            for (let k = 0; k < noteObject["pitches"].length; k++) {
                                const pitch = noteObject["pitches"][k] | 0;
                                if (note.pitches.indexOf(pitch) != -1)
                                    continue;
                                note.pitches.push(pitch);
                                if (note.pitches.length >= 4)
                                    break;
                            }
                            if (note.pitches.length < 1)
                                continue;
                            let noteClock = tickClock;
                            let startInterval = 0;
                            for (let k = 0; k < noteObject["points"].length; k++) {
                                const pointObject = noteObject["points"][k];
                                if (pointObject == undefined || pointObject["tick"] == undefined)
                                    continue;
                                const interval = (pointObject["pitchBend"] == undefined) ? 0 : (pointObject["pitchBend"] | 0);
                                const time = Math.round((+pointObject["tick"]) * beepbox.Config.partsPerBeat / importedPartsPerBeat);
                                const volume = (pointObject["volume"] == undefined) ? 6 : Math.max(0, Math.min(6, Math.round((pointObject["volume"] | 0) * 6 / 100)));
                                if (time > this.beatsPerBar * beepbox.Config.partsPerBeat)
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
                            const maxPitch = isNoiseChannel ? beepbox.Config.drumCount - 1 : beepbox.Config.maxPitch;
                            let lowestPitch = maxPitch;
                            let highestPitch = 0;
                            for (let k = 0; k < note.pitches.length; k++) {
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
                            for (let k = 0; k < note.pins.length; k++) {
                                const pin = note.pins[k];
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
                for (let i = 0; i < this.barCount; i++) {
                    this.channels[channel].bars[i] = channelObject["sequence"] ? Math.min(this.patternsPerChannel, channelObject["sequence"][i] >>> 0) : 0;
                }
            }
        }
        this.pitchChannelCount = pitchChannelCount;
        this.noiseChannelCount = noiseChannelCount;
        this.channels.length = this.getChannelCount();
    }
    getPattern(channel, bar) {
        const patternIndex = this.channels[channel].bars[bar];
        if (patternIndex == 0)
            return null;
        return this.channels[channel].patterns[patternIndex - 1];
    }
    getPatternInstrument(channel, bar) {
        const pattern = this.getPattern(channel, bar);
        return pattern == null ? 0 : pattern.instrument;
    }
    getBeatsPerMinute() {
        return this.tempo;
    }
}
Song._format = "BeepBox";
Song._oldestBeepboxVersion = 2;
Song._latestBeepboxVersion = 7;
Song._oldestJummBoxVersion = 1;
Song._latestJummBoxVersion = 1;
Song._variant = 0x6A;
Song._base64IntToCharCode = [48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 45, 95];
Song._base64CharCodeToInt = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 62, 62, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 0, 0, 0, 0, 0, 0, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 0, 0, 0, 0, 63, 0, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 0, 0, 0, 0, 0];
beepbox.Song = Song;
class Tone {
    constructor() {
        this.pitches = [0, 0, 0, 0];
        this.pitchCount = 0;
        this.chordSize = 0;
        this.drumsetPitch = 0;
        this.note = null;
        this.prevNote = null;
        this.nextNote = null;
        this.prevNotePitchIndex = 0;
        this.nextNotePitchIndex = 0;
        this.active = false;
        this.noteStart = 0;
        this.noteEnd = 0;
        this.noteLengthTicks = 0;
        this.ticksSinceReleased = 0;
        this.liveInputSamplesHeld = 0;
        this.lastInterval = 0;
        this.lastVolume = 0;
        this.sample = 0.0;
        this.phases = [];
        this.phaseDeltas = [];
        this.volumeStarts = [];
        this.volumeDeltas = [];
        this.volumeStart = 0.0;
        this.volumeDelta = 0.0;
        this.phaseDeltaScale = 0.0;
        this.pulseWidth = 0.0;
        this.pulseWidthDelta = 0.0;
        this.filter = 0.0;
        this.filterScale = 0.0;
        this.filterSample0 = 0.0;
        this.filterSample1 = 0.0;
        this.vibratoScale = 0.0;
        this.intervalMult = 0.0;
        this.intervalVolumeMult = 1.0;
        this.feedbackOutputs = [];
        this.feedbackMult = 0.0;
        this.feedbackDelta = 0.0;
        this.reset();
    }
    reset() {
        for (let i = 0; i < beepbox.Config.operatorCount; i++) {
            this.phases[i] = 0.0;
            this.feedbackOutputs[i] = 0.0;
        }
        this.sample = 0.0;
        this.filterSample0 = 0.0;
        this.filterSample1 = 0.0;
        this.liveInputSamplesHeld = 0.0;
    }
}
class Synth {
    constructor(song) {
        this.samplesPerSecond = 44100;
        this.song = new Song(song);
        this.liveInputPressed = false;
        this.liveInputPitches = [0];
        this.liveInputChannel = 0;
        this.enableIntro = true;
        this.enableOutro = false;
        this.loopCount = -1;
        this.volume = 1.0;
        this.playheadInternal = 0.0;
        this.bar = 0;
        this.beat = 0;
        this.part = 0;
        this.tick = 0;
        this.tickSampleCountdown = 0;
        this.paused = true;
        this.forceMono = false;
        this.tonePool = new beepbox.Deque();
        this.activeTones = [];
        this.releasedTones = [];
        this.liveInputTones = new beepbox.Deque();
        this.limitL = 0.0;
        this.limitR = 0.0;
        this.samplesForChorusLeft = null;
        this.samplesForChorusRight = null;
        this.samplesForChorusReverbLeft = null;
        this.samplesForChorusReverbRight = null;
        this.samplesForReverbLeft = null;
        this.samplesForReverbRight = null;
        this.chorusDelayLineLeft = new Float32Array(1024);
        this.chorusDelayLineRight = new Float32Array(1024);
        this.chorusDelayPos = 0;
        this.chorusPhase = 0;
        this.reverbDelayLineLeft = new Float32Array(16384);
        this.reverbDelayLineRight = new Float32Array(16384);
        this.reverbDelayPos = 0;
        this.reverbFeedback0L = 0.0;
        this.reverbFeedback1L = 0.0;
        this.reverbFeedback2L = 0.0;
        this.reverbFeedback3L = 0.0;
        this.reverbFeedback0R = 0.0;
        this.reverbFeedback1R = 0.0;
        this.reverbFeedback2R = 0.0;
        this.reverbFeedback3R = 0.0;
        this.audioCtx = null;
        this.scriptNode = null;
        this.splitter = null;
        this.pannerLeft = null;
        this.pannerRight = null;
        this.merger = null;
        this.compressor = null;
        this.audioProcessCallback = (audioProcessingEvent) => {
            const outputBuffer = audioProcessingEvent.outputBuffer;
            const outputDataL = outputBuffer.getChannelData(0);
            const outputDataR = outputBuffer.getChannelData(1);
            if (this.paused) {
                for (let i = 0; i < outputBuffer.length; i++) {
                    outputDataL[i] = 0.0;
                    outputDataR[i] = 0.0;
                }
            }
            else {
                this.synthesize(outputDataL, outputDataR, outputBuffer.length);
            }
        };
    }

    static operatorAmplitudeCurve(amplitude) {
        return (Math.pow(16.0, amplitude / 15.0) - 1.0) / 15.0;
    }

    get totalSamples() {
        if (this.song == null)
            return 0;
        const samplesPerBar = this.getSamplesPerTick() * beepbox.Config.ticksPerPart * beepbox.Config.partsPerBeat * this.song.beatsPerBar;
        let loopMinCount = this.loopCount;
        if (loopMinCount < 0)
            loopMinCount = 1;
        let bars = this.song.loopLength * loopMinCount;
        if (this.enableIntro)
            bars += this.song.loopStart;
        if (this.enableOutro)
            bars += this.song.barCount - (this.song.loopStart + this.song.loopLength);
        return bars * samplesPerBar;
    }

    get totalSeconds() {
        return this.totalSamples / this.samplesPerSecond;
    }
    
    pause() {
        if (this.paused)
            return;
        this.paused = true;
        this.scriptNode.disconnect(this.splitter);
        if (this.audioCtx.close) {
            this.audioCtx.close();
        }
        this.audioCtx = null;
        this.scriptNode = null;
    }
    synthesize(dataLeft, dataRight, bufferLength) {
        if (this.song == null) {
            for (let i = 0; i < bufferLength; i++) {
                dataLeft[i] = 0.0;
                dataRight[i] = 0.0;
            }
            return;
        }
        const channelCount = this.song.getChannelCount();
        for (let i = this.activeTones.length; i < channelCount; i++) {
            this.activeTones[i] = new beepbox.Deque();
            this.releasedTones[i] = new beepbox.Deque();
        }
        this.activeTones.length = channelCount;
        this.releasedTones.length = channelCount;
        const samplesPerTick = this.getSamplesPerTick();
        let bufferIndex = 0;
        let ended = false;
        if (this.tickSampleCountdown == 0 || this.tickSampleCountdown > samplesPerTick) {
            this.tickSampleCountdown = samplesPerTick;
        }
        if (this.beat >= this.song.beatsPerBar) {
            this.bar++;
            this.beat = 0;
            this.part = 0;
            this.tick = 0;
            this.tickSampleCountdown = samplesPerTick;
            if (this.loopCount == -1) {
                if (this.bar < this.song.loopStart && !this.enableIntro)
                    this.bar = this.song.loopStart;
                if (this.bar >= this.song.loopStart + this.song.loopLength && !this.enableOutro)
                    this.bar = this.song.loopStart;
            }
        }
        if (this.bar >= this.song.barCount) {
            if (this.enableOutro) {
                this.bar = 0;
                this.enableIntro = true;
                ended = true;
                this.pause();
            }
            else {
                this.bar = this.song.loopStart;
            }
        }
        if (this.bar >= this.song.loopStart) {
            this.enableIntro = false;
        }
        const synthStartTime = Date.now();
        if (this.samplesForChorusLeft == null || this.samplesForChorusLeft.length < bufferLength) {
            this.samplesForChorusLeft = new Float32Array(bufferLength);
        }
        if (this.samplesForChorusRight == null || this.samplesForChorusRight.length < bufferLength) {
            this.samplesForChorusRight = new Float32Array(bufferLength);
        }
        if (this.samplesForChorusReverbLeft == null || this.samplesForChorusReverbLeft.length < bufferLength) {
            this.samplesForChorusReverbLeft = new Float32Array(bufferLength);
        }
        if (this.samplesForChorusReverbRight == null || this.samplesForChorusReverbRight.length < bufferLength) {
            this.samplesForChorusReverbRight = new Float32Array(bufferLength);
        }
        if (this.samplesForReverbLeft == null || this.samplesForReverbLeft.length < bufferLength) {
            this.samplesForReverbLeft = new Float32Array(bufferLength);
        }
        if (this.samplesForReverbRight == null || this.samplesForReverbRight.length < bufferLength) {
            this.samplesForReverbRight = new Float32Array(bufferLength);
        }
        const samplesForChorusLeft = this.samplesForChorusLeft;
        const samplesForChorusRight = this.samplesForChorusRight;
        const samplesForChorusReverbLeft = this.samplesForChorusReverbLeft;
        const samplesForChorusReverbRight = this.samplesForChorusReverbRight;
        const samplesForReverbLeft = this.samplesForReverbLeft;
        const samplesForReverbRight = this.samplesForReverbRight;
        for (let i = 0; i < bufferLength;) {
            dataRight[i] = 0.0;
            dataLeft[i++] = 0.0;
            dataRight[i] = 0.0;
            dataLeft[i++] = 0.0;
            dataRight[i] = 0.0;
            dataLeft[i++] = 0.0;
            dataRight[i] = 0.0;
            dataLeft[i++] = 0.0;
            dataRight[i] = 0.0;
            dataLeft[i++] = 0.0;
            dataRight[i] = 0.0;
            dataLeft[i++] = 0.0;
            dataRight[i] = 0.0;
            dataLeft[i++] = 0.0;
            dataRight[i] = 0.0;
            dataLeft[i++] = 0.0;
        }
        const volume = +this.volume;
        const chorusDelayLineLeft = this.chorusDelayLineLeft;
        const chorusDelayLineRight = this.chorusDelayLineRight;
        const reverbDelayLineLeft = this.reverbDelayLineLeft;
        const reverbDelayLineRight = this.reverbDelayLineRight;
        const chorusDuration = 2.0;
        const chorusAngle = Math.PI * 2.0 / (chorusDuration * this.samplesPerSecond);
        const chorusRange = 150 * this.samplesPerSecond / 44100;
        const chorusOffset0 = 0x400 - 1.51 * chorusRange;
        const chorusOffset1 = 0x400 - 2.10 * chorusRange;
        const chorusOffset2 = 0x400 - 3.35 * chorusRange;
        let chorusPhase = this.chorusPhase % (Math.PI * 2.0);
        let chorusDelayPos = this.chorusDelayPos & 0x3FF;
        let reverbDelayPos = this.reverbDelayPos & 0x3FFF;
        let reverbFeedback0L = +this.reverbFeedback0L;
        let reverbFeedback1L = +this.reverbFeedback1L;
        let reverbFeedback2L = +this.reverbFeedback2L;
        let reverbFeedback3L = +this.reverbFeedback3L;
        let reverbFeedback0R = +this.reverbFeedback0R;
        let reverbFeedback1R = +this.reverbFeedback1R;
        let reverbFeedback2R = +this.reverbFeedback2R;
        let reverbFeedback3R = +this.reverbFeedback3R;
        const reverb = Math.pow(this.song.reverb / beepbox.Config.reverbRange, 0.667) * 0.425;
        const limitDecay = 1.0 - Math.pow(0.5, 4.0 / this.samplesPerSecond);
        const limitRise = 1.0 - Math.pow(0.5, 4000.0 / this.samplesPerSecond);
        let limitL = +this.limitL;
        let limitR = +this.limitR;
        const synthBufferByEffects = [dataLeft, dataRight, samplesForReverbLeft, samplesForReverbRight, samplesForChorusLeft, samplesForChorusRight, samplesForChorusReverbLeft, samplesForChorusReverbRight];
        while (bufferIndex < bufferLength && !ended) {
            while (bufferIndex < bufferLength) {
                const samplesLeftInBuffer = bufferLength - bufferIndex;
                const runLength = (this.tickSampleCountdown <= samplesLeftInBuffer)
                    ? this.tickSampleCountdown
                    : samplesLeftInBuffer;
                for (let channel = 0; channel < this.song.getChannelCount(); channel++) {
                    if (channel == this.liveInputChannel) {
                        this.determineLiveInputTones(this.song);
                        for (let i = 0; i < this.liveInputTones.count(); i++) {
                            const tone = this.liveInputTones.get(i);
                            this.playTone(this.song, bufferIndex, synthBufferByEffects, channel, samplesPerTick, runLength, tone, false, false);
                        }
                    }
                    this.determineCurrentActiveTones(this.song, channel);
                    for (let i = 0; i < this.activeTones[channel].count(); i++) {
                        const tone = this.activeTones[channel].get(i);
                        this.playTone(this.song, bufferIndex, synthBufferByEffects, channel, samplesPerTick, runLength, tone, false, false);
                    }
                    for (let i = 0; i < this.releasedTones[channel].count(); i++) {
                        const tone = this.releasedTones[channel].get(i);
                        if (tone.ticksSinceReleased >= tone.instrument.getTransition().releaseTicks) {
                            this.freeReleasedTone(channel, i);
                            i--;
                            continue;
                        }
                        const shouldFadeOutFast = (i + this.activeTones[channel].count() >= beepbox.Config.maximumTonesPerChannel);
                        this.playTone(this.song, bufferIndex, synthBufferByEffects, channel, samplesPerTick, runLength, tone, true, shouldFadeOutFast);
                    }
                }
                const chorusYMult = 2.0 * Math.cos(chorusAngle);
                let chorusTap0Index = chorusDelayPos + chorusOffset0 - chorusRange * Math.sin(chorusPhase + 0);
                let chorusTap1Index = chorusDelayPos + chorusOffset1 - chorusRange * Math.sin(chorusPhase + 2.1);
                let chorusTap2Index = chorusDelayPos + chorusOffset2 - chorusRange * Math.sin(chorusPhase + 4.2);
                chorusPhase += chorusAngle * runLength;
                const chorusTap0End = chorusDelayPos + runLength + chorusOffset0 - chorusRange * Math.sin(chorusPhase + 0);
                const chorusTap1End = chorusDelayPos + runLength + chorusOffset1 - chorusRange * Math.sin(chorusPhase + 2.1);
                const chorusTap2End = chorusDelayPos + runLength + chorusOffset2 - chorusRange * Math.sin(chorusPhase + 4.2);
                const chorusTap0Delta = (chorusTap0End - chorusTap0Index) / runLength;
                const chorusTap1Delta = (chorusTap1End - chorusTap1Index) / runLength;
                const chorusTap2Delta = (chorusTap2End - chorusTap2Index) / runLength;
                const runEnd = bufferIndex + runLength;
                for (let i = bufferIndex; i < runEnd; i++) {
                    const sampleForChorusL = samplesForChorusLeft[i];
                    const sampleForChorusR = samplesForChorusRight[i];
                    samplesForChorusLeft[i] = 0.0;
                    samplesForChorusRight[i] = 0.0;
                    const sampleForChorusReverbL = samplesForChorusReverbLeft[i];
                    const sampleForChorusReverbR = samplesForChorusReverbRight[i];
                    samplesForChorusReverbLeft[i] = 0.0;
                    samplesForChorusReverbRight[i] = 0.0;
                    const sampleForReverbL = samplesForReverbLeft[i];
                    const sampleForReverbR = samplesForReverbRight[i];
                    samplesForReverbLeft[i] = 0.0;
                    samplesForReverbRight[i] = 0.0;
                    const combinedChorusL = sampleForChorusL + sampleForChorusReverbL;
                    const combinedChorusR = sampleForChorusR + sampleForChorusReverbR;
                    const chorusTap0Ratio = chorusTap0Index % 1;
                    const chorusTap1Ratio = chorusTap1Index % 1;
                    const chorusTap2Ratio = chorusTap2Index % 1;
                    const chorusTap0AL = chorusDelayLineLeft[(chorusTap0Index) & 0x3FF];
                    const chorusTap0BL = chorusDelayLineLeft[(chorusTap0Index + 1) & 0x3FF];
                    const chorusTap1AL = chorusDelayLineLeft[(chorusTap1Index) & 0x3FF];
                    const chorusTap1BL = chorusDelayLineLeft[(chorusTap1Index + 1) & 0x3FF];
                    const chorusTap2AL = chorusDelayLineLeft[(chorusTap2Index) & 0x3FF];
                    const chorusTap2BL = chorusDelayLineLeft[(chorusTap2Index + 1) & 0x3FF];
                    const chorusTap0L = chorusTap0AL + (chorusTap0BL - chorusTap0AL) * chorusTap0Ratio;
                    const chorusTap1L = chorusTap1AL + (chorusTap1BL - chorusTap1AL) * chorusTap1Ratio;
                    const chorusTap2L = chorusTap2AL + (chorusTap2BL - chorusTap2AL) * chorusTap2Ratio;
                    const chorusTap0AR = chorusDelayLineRight[(chorusTap0Index) & 0x3FF];
                    const chorusTap0BR = chorusDelayLineRight[(chorusTap0Index + 1) & 0x3FF];
                    const chorusTap1AR = chorusDelayLineRight[(chorusTap1Index) & 0x3FF];
                    const chorusTap1BR = chorusDelayLineRight[(chorusTap1Index + 1) & 0x3FF];
                    const chorusTap2AR = chorusDelayLineRight[(chorusTap2Index) & 0x3FF];
                    const chorusTap2BR = chorusDelayLineRight[(chorusTap2Index + 1) & 0x3FF];
                    const chorusTap0R = chorusTap0AR + (chorusTap0BR - chorusTap0AR) * chorusTap0Ratio;
                    const chorusTap1R = chorusTap1AR + (chorusTap1BR - chorusTap1AR) * chorusTap1Ratio;
                    const chorusTap2R = chorusTap2AR + (chorusTap2BR - chorusTap2AR) * chorusTap2Ratio;
                    const chorusSampleLeft = 0.5 * (combinedChorusL - chorusTap0L + chorusTap1L - chorusTap2L);
                    const chorusSampleRight = 0.5 * (combinedChorusR - chorusTap0R + chorusTap1R - chorusTap2R);
                    chorusDelayLineLeft[chorusDelayPos] = combinedChorusL;
                    chorusDelayLineRight[chorusDelayPos] = combinedChorusR;
                    chorusDelayPos = (chorusDelayPos + 1) & 0x3FF;
                    chorusTap0Index += chorusTap0Delta;
                    chorusTap1Index += chorusTap1Delta;
                    chorusTap2Index += chorusTap2Delta;
                    const reverbDelayPos1 = (reverbDelayPos + 3041) & 0x3FFF;
                    const reverbDelayPos2 = (reverbDelayPos + 6426) & 0x3FFF;
                    const reverbDelayPos3 = (reverbDelayPos + 10907) & 0x3FFF;
                    const reverbSample0L = (reverbDelayLineLeft[reverbDelayPos] + sampleForReverbL);
                    const reverbSample1L = reverbDelayLineLeft[reverbDelayPos1];
                    const reverbSample2L = reverbDelayLineLeft[reverbDelayPos2];
                    const reverbSample3L = reverbDelayLineLeft[reverbDelayPos3];
                    const reverbSample0ChorusL = reverbSample0L + sampleForChorusReverbL;
                    const reverbTemp0L = -reverbSample0ChorusL + reverbSample1L;
                    const reverbTemp1L = -reverbSample0ChorusL - reverbSample1L;
                    const reverbTemp2L = -reverbSample2L + reverbSample3L;
                    const reverbTemp3L = -reverbSample2L - reverbSample3L;
                    reverbFeedback0L += ((reverbTemp0L + reverbTemp2L) * reverb - reverbFeedback0L) * 0.5;
                    reverbFeedback1L += ((reverbTemp1L + reverbTemp3L) * reverb - reverbFeedback1L) * 0.5;
                    reverbFeedback2L += ((reverbTemp0L - reverbTemp2L) * reverb - reverbFeedback2L) * 0.5;
                    reverbFeedback3L += ((reverbTemp1L - reverbTemp3L) * reverb - reverbFeedback3L) * 0.5;
                    reverbDelayLineLeft[reverbDelayPos1] = reverbFeedback0L;
                    reverbDelayLineLeft[reverbDelayPos2] = reverbFeedback1L;
                    reverbDelayLineLeft[reverbDelayPos3] = reverbFeedback2L;
                    reverbDelayLineLeft[reverbDelayPos] = reverbFeedback3L;
                    const reverbSample0R = (reverbDelayLineRight[reverbDelayPos] + sampleForReverbR);
                    const reverbSample1R = reverbDelayLineRight[reverbDelayPos1];
                    const reverbSample2R = reverbDelayLineRight[reverbDelayPos2];
                    const reverbSample3R = reverbDelayLineRight[reverbDelayPos3];
                    const reverbSample0ChorusR = reverbSample0R + sampleForChorusReverbR;
                    const reverbTemp0R = -reverbSample0ChorusR + reverbSample1R;
                    const reverbTemp1R = -reverbSample0ChorusR - reverbSample1R;
                    const reverbTemp2R = -reverbSample2R + reverbSample3R;
                    const reverbTemp3R = -reverbSample2R - reverbSample3R;
                    reverbFeedback0R += ((reverbTemp0R + reverbTemp2R) * reverb - reverbFeedback0R) * 0.5;
                    reverbFeedback1R += ((reverbTemp1R + reverbTemp3R) * reverb - reverbFeedback1R) * 0.5;
                    reverbFeedback2R += ((reverbTemp0R - reverbTemp2R) * reverb - reverbFeedback2R) * 0.5;
                    reverbFeedback3R += ((reverbTemp1R - reverbTemp3R) * reverb - reverbFeedback3R) * 0.5;
                    reverbDelayLineRight[reverbDelayPos1] = reverbFeedback0R;
                    reverbDelayLineRight[reverbDelayPos2] = reverbFeedback1R;
                    reverbDelayLineRight[reverbDelayPos3] = reverbFeedback2R;
                    reverbDelayLineRight[reverbDelayPos] = reverbFeedback3R;
                    reverbDelayPos = (reverbDelayPos + 1) & 0x3FFF;
                    const sampleLeft = dataLeft[i] + chorusSampleLeft + reverbSample0L + reverbSample1L + reverbSample2L + reverbSample3L;
                    const sampleRight = dataRight[i] + chorusSampleRight + reverbSample0R + reverbSample1R + reverbSample2R + reverbSample3R;
                    const absL = sampleLeft < 0.0 ? -sampleLeft : sampleLeft;
                    limitL += (absL - limitL) * (limitL < absL ? limitRise : limitDecay);
                    dataLeft[i] = (sampleLeft / (limitL >= 1 ? limitL * 1.05 : limitL * 0.8 + 0.25)) * volume;
                    const absR = sampleRight < 0.0 ? -sampleRight : sampleRight;
                    limitR += (absR - limitR) * (limitR < absR ? limitRise : limitDecay);
                    dataRight[i] = (sampleRight / (limitR >= 1 ? limitR * 1.05 : limitR * 0.8 + 0.25)) * volume;
                }
                bufferIndex += runLength;
                this.tickSampleCountdown -= runLength;
                if (this.tickSampleCountdown <= 0) {
                    for (let channel = 0; channel < this.song.getChannelCount(); channel++) {
                        for (let i = 0; i < this.releasedTones[channel].count(); i++) {
                            const tone = this.releasedTones[channel].get(i);
                            tone.ticksSinceReleased++;
                            const shouldFadeOutFast = (i + this.activeTones[channel].count() >= beepbox.Config.maximumTonesPerChannel);
                            if (shouldFadeOutFast) {
                                this.freeReleasedTone(channel, i);
                                i--;
                            }
                        }
                    }
                    this.tick++;
                    this.tickSampleCountdown = samplesPerTick;
                    if (this.tick == beepbox.Config.ticksPerPart) {
                        this.tick = 0;
                        this.part++;
                        for (let channel = 0; channel < this.song.getChannelCount(); channel++) {
                            for (let i = 0; i < this.activeTones[channel].count(); i++) {
                                const tone = this.activeTones[channel].get(i);
                                const transition = tone.instrument.getTransition();
                                if (!transition.isSeamless && tone.note != null && tone.note.end == this.part + this.beat * beepbox.Config.partsPerBeat) {
                                    if (transition.releases) {
                                        this.releaseTone(channel, tone);
                                    }
                                    else {
                                        this.freeTone(tone);
                                    }
                                    this.activeTones[channel].remove(i);
                                    i--;
                                }
                            }
                        }
                        if (this.part == beepbox.Config.partsPerBeat) {
                            this.part = 0;
                            this.beat++;
                            if (this.beat == this.song.beatsPerBar) {
                                this.beat = 0;
                                this.bar++;
                                if (this.bar < this.song.loopStart) {
                                    if (!this.enableIntro)
                                        this.bar = this.song.loopStart;
                                }
                                else {
                                    this.enableIntro = false;
                                }
                                if (this.bar >= this.song.loopStart + this.song.loopLength) {
                                    if (this.loopCount > 0)
                                        this.loopCount--;
                                    if (this.loopCount > 0 || !this.enableOutro) {
                                        this.bar = this.song.loopStart;
                                    }
                                }
                                if (this.bar >= this.song.barCount) {
                                    this.bar = 0;
                                    this.enableIntro = true;
                                    ended = true;
                                    this.pause();
                                }
                                break;
                            }
                        }
                    }
                }
            }
        }
        const epsilon = (1.0e-24);
        if (-epsilon < reverbFeedback0L && reverbFeedback0L < epsilon)
            reverbFeedback0L = 0.0;
        if (-epsilon < reverbFeedback1L && reverbFeedback1L < epsilon)
            reverbFeedback1L = 0.0;
        if (-epsilon < reverbFeedback2L && reverbFeedback2L < epsilon)
            reverbFeedback2L = 0.0;
        if (-epsilon < reverbFeedback3L && reverbFeedback3L < epsilon)
            reverbFeedback3L = 0.0;
        if (-epsilon < reverbFeedback0R && reverbFeedback0R < epsilon)
            reverbFeedback0R = 0.0;
        if (-epsilon < reverbFeedback1R && reverbFeedback1R < epsilon)
            reverbFeedback1R = 0.0;
        if (-epsilon < reverbFeedback2R && reverbFeedback2R < epsilon)
            reverbFeedback2R = 0.0;
        if (-epsilon < reverbFeedback3R && reverbFeedback3R < epsilon)
            reverbFeedback3R = 0.0;
        if (-epsilon < limitL && limitL < epsilon)
            limitL = 0.0;
        if (-epsilon < limitR && limitR < epsilon)
            limitR = 0.0;
        this.chorusPhase = chorusPhase;
        this.chorusDelayPos = chorusDelayPos;
        this.reverbDelayPos = reverbDelayPos;
        this.reverbFeedback0L = reverbFeedback0L;
        this.reverbFeedback1L = reverbFeedback1L;
        this.reverbFeedback2L = reverbFeedback2L;
        this.reverbFeedback3L = reverbFeedback3L;
        this.reverbFeedback0R = reverbFeedback0R;
        this.reverbFeedback1R = reverbFeedback1R;
        this.reverbFeedback2R = reverbFeedback2R;
        this.reverbFeedback3R = reverbFeedback3R;
        this.limitL = limitL;
        this.limitR = limitR;
        this.playheadInternal = (((this.tick + 1.0 - this.tickSampleCountdown / samplesPerTick) / 2.0 + this.part) / beepbox.Config.partsPerBeat + this.beat) / this.song.beatsPerBar + this.bar;
    }
    freeTone(tone) {
        this.tonePool.pushBack(tone);
    }
    newTone() {
        if (this.tonePool.count() > 0) {
            const tone = this.tonePool.popBack();
            tone.reset();
            tone.active = false;
            return tone;
        }
        return new Tone();
    }
    releaseTone(channel, tone) {
        this.releasedTones[channel].pushFront(tone);
    }
    freeReleasedTone(channel, toneIndex) {
        this.freeTone(this.releasedTones[channel].get(toneIndex));
        this.releasedTones[channel].remove(toneIndex);
    }
    freeAllTones() {
        while (this.liveInputTones.count() > 0) {
            this.freeTone(this.liveInputTones.popBack());
        }
        for (let i = 0; i < this.activeTones.length; i++) {
            while (this.activeTones[i].count() > 0) {
                this.freeTone(this.activeTones[i].popBack());
            }
        }
        for (let i = 0; i < this.releasedTones.length; i++) {
            while (this.releasedTones[i].count() > 0) {
                this.freeTone(this.releasedTones[i].popBack());
            }
        }
    }
    determineLiveInputTones(song) {
        if (this.liveInputPressed) {
            const instrument = song.channels[this.liveInputChannel].instruments[song.getPatternInstrument(this.liveInputChannel, this.bar)];
            let tone;
            if (this.liveInputTones.count() == 0) {
                tone = this.newTone();
                this.liveInputTones.pushBack(tone);
            }
            else if (!instrument.getTransition().isSeamless && this.liveInputTones.peakFront().pitches[0] != this.liveInputPitches[0]) {
                this.releaseTone(this.liveInputChannel, this.liveInputTones.popFront());
                tone = this.newTone();
                this.liveInputTones.pushBack(tone);
            }
            else {
                tone = this.liveInputTones.get(0);
            }
            for (let i = 0; i < this.liveInputPitches.length; i++) {
                tone.pitches[i] = this.liveInputPitches[i];
            }
            tone.pitchCount = this.liveInputPitches.length;
            tone.chordSize = 1;
            tone.instrument = instrument;
            tone.note = tone.prevNote = tone.nextNote = null;
        }
        else {
            while (this.liveInputTones.count() > 0) {
                this.releaseTone(this.liveInputChannel, this.liveInputTones.popBack());
            }
        }
    }
    determineCurrentActiveTones(song, channel) {
        const instrument = song.channels[channel].instruments[song.getPatternInstrument(channel, this.bar)];
        const pattern = song.getPattern(channel, this.bar);
        const time = this.part + this.beat * beepbox.Config.partsPerBeat;
        let note = null;
        let prevNote = null;
        let nextNote = null;
        if (pattern != null) {
            for (let i = 0; i < pattern.notes.length; i++) {
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
        const toneList = this.activeTones[channel];
        if (note != null) {
            if (prevNote != null && prevNote.end != note.start)
                prevNote = null;
            if (nextNote != null && nextNote.start != note.end)
                nextNote = null;
            this.syncTones(channel, toneList, instrument, note.pitches, note, prevNote, nextNote, time);
        }
        else {
            while (toneList.count() > 0) {
                if (toneList.peakBack().instrument.getTransition().releases) {
                    this.releaseTone(channel, toneList.popBack());
                }
                else {
                    this.freeTone(toneList.popBack());
                }
            }
        }
    }
    syncTones(channel, toneList, instrument, pitches, note, prevNote, nextNote, currentPart) {
        let toneCount = 0;
        if (instrument.getChord().arpeggiates) {
            let tone;
            if (toneList.count() == 0) {
                tone = this.newTone();
                toneList.pushBack(tone);
            }
            else {
                tone = toneList.get(0);
            }
            toneCount = 1;
            for (let i = 0; i < pitches.length; i++) {
                tone.pitches[i] = pitches[i];
            }
            tone.pitchCount = pitches.length;
            tone.chordSize = 1;
            tone.instrument = instrument;
            tone.note = note;
            tone.noteStart = note.start;
            tone.noteEnd = note.end;
            tone.prevNote = prevNote;
            tone.nextNote = nextNote;
            tone.prevNotePitchIndex = 0;
            tone.nextNotePitchIndex = 0;
        }
        else {
            const transition = instrument.getTransition();
            for (let i = 0; i < pitches.length; i++) {
                const strumOffsetParts = i * instrument.getChord().strumParts;
                let prevNoteForThisTone = (prevNote && prevNote.pitches.length > i) ? prevNote : null;
                let noteForThisTone = note;
                let nextNoteForThisTone = (nextNote && nextNote.pitches.length > i) ? nextNote : null;
                let noteStart = noteForThisTone.start + strumOffsetParts;
                if (noteStart > currentPart) {
                    if (toneList.count() > i && transition.isSeamless && prevNoteForThisTone != null) {
                        nextNoteForThisTone = noteForThisTone;
                        noteForThisTone = prevNoteForThisTone;
                        prevNoteForThisTone = null;
                        noteStart = noteForThisTone.start + strumOffsetParts;
                    }
                    else {
                        break;
                    }
                }
                let noteEnd = noteForThisTone.end;
                if (transition.isSeamless && nextNoteForThisTone != null) {
                    noteEnd = Math.min(beepbox.Config.partsPerBeat * this.song.beatsPerBar, noteEnd + strumOffsetParts);
                }
                let tone;
                if (toneList.count() > i) {
                    tone = toneList.get(i);
                }
                else {
                    tone = this.newTone();
                    toneList.pushBack(tone);
                }
                toneCount++;
                tone.pitches[0] = noteForThisTone.pitches[i];
                tone.pitchCount = 1;
                tone.chordSize = noteForThisTone.pitches.length;
                tone.instrument = instrument;
                tone.note = noteForThisTone;
                tone.noteStart = noteStart;
                tone.noteEnd = noteEnd;
                tone.prevNote = prevNoteForThisTone;
                tone.nextNote = nextNoteForThisTone;
                tone.prevNotePitchIndex = i;
                tone.nextNotePitchIndex = i;
            }
        }
        while (toneList.count() > toneCount) {
            if (toneList.peakBack().instrument.getTransition().releases) {
                this.releaseTone(channel, toneList.popBack());
            }
            else {
                this.freeTone(toneList.popBack());
            }
        }
    }
    playTone(song, bufferIndex, synthBufferByEffects, channel, samplesPerTick, runLength, tone, released, shouldFadeOutFast) {
        Synth.computeTone(this, song, channel, samplesPerTick, runLength, tone, released, shouldFadeOutFast);
        const synthBufferL = synthBufferByEffects[tone.instrument.effects * 2];
        const synthBufferR = synthBufferByEffects[tone.instrument.effects * 2 + 1];
        const synthesizer = Synth.getInstrumentSynthFunction(tone.instrument);
        if (song.channels[channel].muted == false){

            synthesizer(this, synthBufferL, synthBufferR, bufferIndex, runLength, tone, tone.instrument);
        }
    }
    static computeEnvelope(envelope, time, beats, customVolume) {
        switch (envelope.type) {
            case 0: return customVolume;
            case 1: return 1.0;
            case 4:
                return 1.0 / (1.0 + time * envelope.speed);
            case 5:
                return 1.0 - 1.0 / (1.0 + time * envelope.speed);
            case 6:
                return 0.5 - Math.cos(beats * 2.0 * Math.PI * envelope.speed) * 0.5;
            case 7:
                return 0.75 - Math.cos(beats * 2.0 * Math.PI * envelope.speed) * 0.25;
            case 2:
                return Math.max(1.0, 2.0 - time * 10.0);
            case 3:
                const speed = envelope.speed;
                const attack = 0.25 / Math.sqrt(speed);
                return time < attack ? time / attack : 1.0 / (1.0 + (time - attack) * speed);
            case 8:
                return Math.pow(2, -envelope.speed * time);
            default: throw new Error("Unrecognized operator envelope type.");
        }
    }
    static computeChordVolume(chordSize) {
        return 1.0 / ((chordSize - 1) * 0.25 + 1.0);
    }
    static computeTone(synth, song, channel, samplesPerTick, runLength, tone, released, shouldFadeOutFast) {
        const instrument = tone.instrument;
        const transition = instrument.getTransition();
        const chord = instrument.getChord();
        const chordVolume = chord.arpeggiates ? 1 : Synth.computeChordVolume(tone.chordSize);
        const isNoiseChannel = song.getChannelIsNoise(channel);
        const intervalScale = isNoiseChannel ? beepbox.Config.noiseInterval : 1;
        const secondsPerPart = beepbox.Config.ticksPerPart * samplesPerTick / synth.samplesPerSecond;
        const beatsPerPart = 1.0 / beepbox.Config.partsPerBeat;
        const toneWasActive = tone.active;
        const tickSampleCountdown = synth.tickSampleCountdown;
        const startRatio = 1.0 - (tickSampleCountdown) / samplesPerTick;
        const endRatio = 1.0 - (tickSampleCountdown - runLength) / samplesPerTick;
        const ticksIntoBar = (synth.beat * beepbox.Config.partsPerBeat + synth.part) * beepbox.Config.ticksPerPart + synth.tick;
        const partTimeTickStart = (ticksIntoBar) / beepbox.Config.ticksPerPart;
        const partTimeTickEnd = (ticksIntoBar + 1) / beepbox.Config.ticksPerPart;
        const partTimeStart = partTimeTickStart + (partTimeTickEnd - partTimeTickStart) * startRatio;
        const partTimeEnd = partTimeTickStart + (partTimeTickEnd - partTimeTickStart) * endRatio;
        tone.phaseDeltaScale = 0.0;
        tone.filter = 1.0;
        tone.filterScale = 1.0;
        tone.vibratoScale = 0.0;
        tone.intervalMult = 1.0;
        tone.intervalVolumeMult = 1.0;
        tone.active = false;
        let resetPhases = true;
        let partsSinceStart = 0.0;
        let intervalStart = 0.0;
        let intervalEnd = 0.0;
        let transitionVolumeStart = 1.0;
        let transitionVolumeEnd = 1.0;
        let chordVolumeStart = chordVolume;
        let chordVolumeEnd = chordVolume;
        let customVolumeStart = 0.0;
        let customVolumeEnd = 0.0;
        let decayTimeStart = 0.0;
        let decayTimeEnd = 0.0;
        let volumeReferencePitch;
        let basePitch;
        let baseVolume;
        let pitchDamping;
        if (instrument.type == 3) {
            if (isNoiseChannel) {
                basePitch = beepbox.Config.spectrumBasePitch;
                baseVolume = 0.6;
            }
            else {
                basePitch = beepbox.Config.keys[song.key].basePitch;
                baseVolume = 0.3;
            }
            volumeReferencePitch = beepbox.Config.spectrumBasePitch;
            pitchDamping = 28;
        }
        else if (instrument.type == 4) {
            basePitch = beepbox.Config.spectrumBasePitch;
            baseVolume = 0.45;
            volumeReferencePitch = basePitch;
            pitchDamping = 48;
        }
        else if (instrument.type == 2) {
            basePitch = beepbox.Config.chipNoises[instrument.chipNoise].basePitch;
            baseVolume = 0.19;
            volumeReferencePitch = basePitch;
            pitchDamping = beepbox.Config.chipNoises[instrument.chipNoise].isSoft ? 24.0 : 60.0;
        }
        else if (instrument.type == 1) {
            basePitch = beepbox.Config.keys[song.key].basePitch;
            baseVolume = 0.03;
            volumeReferencePitch = 16;
            pitchDamping = 48;
        }
        else if (instrument.type == 0 || instrument.type == 7) {
            basePitch = beepbox.Config.keys[song.key].basePitch;
            baseVolume = 0.03375;
            volumeReferencePitch = 16;
            pitchDamping = 48;
        }
        else if (instrument.type == 5) {
            basePitch = beepbox.Config.keys[song.key].basePitch;
            baseVolume = 0.025;
            volumeReferencePitch = 16;
            pitchDamping = 48;
        }
        else if (instrument.type == 6) {
            basePitch = beepbox.Config.keys[song.key].basePitch;
            baseVolume = 0.04725;
            volumeReferencePitch = 16;
            pitchDamping = 48;
        }
        else {
            throw new Error("Unknown instrument type in computeTone.");
        }
        for (let i = 0; i < beepbox.Config.operatorCount; i++) {
            tone.phaseDeltas[i] = 0.0;
            tone.volumeStarts[i] = 0.0;
            tone.volumeDeltas[i] = 0.0;
        }
        if (released) {
            const ticksSoFar = tone.noteLengthTicks + tone.ticksSinceReleased;
            const startTicksSinceReleased = tone.ticksSinceReleased + startRatio;
            const endTicksSinceReleased = tone.ticksSinceReleased + endRatio;
            const startTick = tone.noteLengthTicks + startTicksSinceReleased;
            const endTick = tone.noteLengthTicks + endTicksSinceReleased;
            const toneTransition = tone.instrument.getTransition();
            resetPhases = false;
            partsSinceStart = Math.floor(ticksSoFar / beepbox.Config.ticksPerPart);
            intervalStart = intervalEnd = tone.lastInterval;
            customVolumeStart = customVolumeEnd = Synth.expressionToVolumeMult(tone.lastVolume);
            transitionVolumeStart = Synth.expressionToVolumeMult((1.0 - startTicksSinceReleased / toneTransition.releaseTicks) * 6.0);
            transitionVolumeEnd = Synth.expressionToVolumeMult((1.0 - endTicksSinceReleased / toneTransition.releaseTicks) * 6.0);
            decayTimeStart = startTick / beepbox.Config.ticksPerPart;
            decayTimeEnd = endTick / beepbox.Config.ticksPerPart;
            if (shouldFadeOutFast) {
                transitionVolumeStart *= 1.0 - startRatio;
                transitionVolumeEnd *= 1.0 - endRatio;
            }
        }
        else if (tone.note == null) {
            transitionVolumeStart = transitionVolumeEnd = 1;
            customVolumeStart = customVolumeEnd = 1;
            tone.lastInterval = 0;
            tone.lastVolume = 3;
            tone.ticksSinceReleased = 0;
            resetPhases = false;
            const heldTicksStart = tone.liveInputSamplesHeld / samplesPerTick;
            tone.liveInputSamplesHeld += runLength;
            const heldTicksEnd = tone.liveInputSamplesHeld / samplesPerTick;
            tone.noteLengthTicks = heldTicksEnd;
            const heldPartsStart = heldTicksStart / beepbox.Config.ticksPerPart;
            const heldPartsEnd = heldTicksEnd / beepbox.Config.ticksPerPart;
            partsSinceStart = Math.floor(heldPartsStart);
            decayTimeStart = heldPartsStart;
            decayTimeEnd = heldPartsEnd;
        }
        else {
            const note = tone.note;
            const prevNote = tone.prevNote;
            const nextNote = tone.nextNote;
            const time = synth.part + synth.beat * beepbox.Config.partsPerBeat;
            const partsPerBar = beepbox.Config.partsPerBeat * song.beatsPerBar;
            const noteStart = tone.noteStart;
            const noteEnd = tone.noteEnd;
            partsSinceStart = time - noteStart;
            let endPinIndex;
            for (endPinIndex = 1; endPinIndex < note.pins.length - 1; endPinIndex++) {
                if (note.pins[endPinIndex].time + note.start > time)
                    break;
            }
            const startPin = note.pins[endPinIndex - 1];
            const endPin = note.pins[endPinIndex];
            const noteStartTick = noteStart * beepbox.Config.ticksPerPart;
            const noteEndTick = noteEnd * beepbox.Config.ticksPerPart;
            const noteLengthTicks = noteEndTick - noteStartTick;
            const pinStart = (note.start + startPin.time) * beepbox.Config.ticksPerPart;
            const pinEnd = (note.start + endPin.time) * beepbox.Config.ticksPerPart;
            tone.lastInterval = note.pins[note.pins.length - 1].interval;
            tone.lastVolume = note.pins[note.pins.length - 1].volume;
            tone.ticksSinceReleased = 0;
            tone.noteLengthTicks = noteLengthTicks;
            const tickTimeStart = time * beepbox.Config.ticksPerPart + synth.tick;
            const tickTimeEnd = time * beepbox.Config.ticksPerPart + synth.tick + 1;
            const noteTicksPassedTickStart = tickTimeStart - noteStartTick;
            const noteTicksPassedTickEnd = tickTimeEnd - noteStartTick;
            const pinRatioStart = Math.min(1.0, (tickTimeStart - pinStart) / (pinEnd - pinStart));
            const pinRatioEnd = Math.min(1.0, (tickTimeEnd - pinStart) / (pinEnd - pinStart));
            let customVolumeTickStart = startPin.volume + (endPin.volume - startPin.volume) * pinRatioStart;
            let customVolumeTickEnd = startPin.volume + (endPin.volume - startPin.volume) * pinRatioEnd;
            let transitionVolumeTickStart = 1.0;
            let transitionVolumeTickEnd = 1.0;
            let chordVolumeTickStart = chordVolume;
            let chordVolumeTickEnd = chordVolume;
            let intervalTickStart = startPin.interval + (endPin.interval - startPin.interval) * pinRatioStart;
            let intervalTickEnd = startPin.interval + (endPin.interval - startPin.interval) * pinRatioEnd;
            let decayTimeTickStart = partTimeTickStart - noteStart;
            let decayTimeTickEnd = partTimeTickEnd - noteStart;
            resetPhases = (tickTimeStart + startRatio - noteStartTick == 0.0) || !toneWasActive;
            const maximumSlideTicks = noteLengthTicks * 0.5;
            if (transition.isSeamless && !transition.slides && note.start == 0) {
                resetPhases = !toneWasActive;
            }
            else if (transition.isSeamless && prevNote != null) {
                resetPhases = !toneWasActive;
                if (transition.slides) {
                    const slideTicks = Math.min(maximumSlideTicks, transition.slideTicks);
                    const slideRatioStartTick = Math.max(0.0, 1.0 - noteTicksPassedTickStart / slideTicks);
                    const slideRatioEndTick = Math.max(0.0, 1.0 - noteTicksPassedTickEnd / slideTicks);
                    const intervalDiff = ((prevNote.pitches[tone.prevNotePitchIndex] + prevNote.pins[prevNote.pins.length - 1].interval) - tone.pitches[0]) * 0.5;
                    const volumeDiff = (prevNote.pins[prevNote.pins.length - 1].volume - note.pins[0].volume) * 0.5;
                    const decayTimeDiff = (prevNote.end - prevNote.start) * 0.5;
                    intervalTickStart += slideRatioStartTick * intervalDiff;
                    intervalTickEnd += slideRatioEndTick * intervalDiff;
                    customVolumeTickStart += slideRatioStartTick * volumeDiff;
                    customVolumeTickEnd += slideRatioEndTick * volumeDiff;
                    decayTimeTickStart += slideRatioStartTick * decayTimeDiff;
                    decayTimeTickEnd += slideRatioEndTick * decayTimeDiff;
                    if (!chord.arpeggiates) {
                        const chordSizeDiff = (prevNote.pitches.length - tone.chordSize) * 0.5;
                        chordVolumeTickStart = Synth.computeChordVolume(tone.chordSize + slideRatioStartTick * chordSizeDiff);
                        chordVolumeTickEnd = Synth.computeChordVolume(tone.chordSize + slideRatioEndTick * chordSizeDiff);
                    }
                }
            }
            if (transition.isSeamless && !transition.slides && note.end == partsPerBar) {
            }
            else if (transition.isSeamless && nextNote != null) {
                if (transition.slides) {
                    const slideTicks = Math.min(maximumSlideTicks, transition.slideTicks);
                    const slideRatioStartTick = Math.max(0.0, 1.0 - (noteLengthTicks - noteTicksPassedTickStart) / slideTicks);
                    const slideRatioEndTick = Math.max(0.0, 1.0 - (noteLengthTicks - noteTicksPassedTickEnd) / slideTicks);
                    const intervalDiff = (nextNote.pitches[tone.nextNotePitchIndex] - (tone.pitches[0] + note.pins[note.pins.length - 1].interval)) * 0.5;
                    const volumeDiff = (nextNote.pins[0].volume - note.pins[note.pins.length - 1].volume) * 0.5;
                    const decayTimeDiff = -(noteEnd - noteStart) * 0.5;
                    intervalTickStart += slideRatioStartTick * intervalDiff;
                    intervalTickEnd += slideRatioEndTick * intervalDiff;
                    customVolumeTickStart += slideRatioStartTick * volumeDiff;
                    customVolumeTickEnd += slideRatioEndTick * volumeDiff;
                    decayTimeTickStart += slideRatioStartTick * decayTimeDiff;
                    decayTimeTickEnd += slideRatioEndTick * decayTimeDiff;
                    if (!chord.arpeggiates) {
                        const chordSizeDiff = (nextNote.pitches.length - tone.chordSize) * 0.5;
                        chordVolumeTickStart = Synth.computeChordVolume(tone.chordSize + slideRatioStartTick * chordSizeDiff);
                        chordVolumeTickEnd = Synth.computeChordVolume(tone.chordSize + slideRatioEndTick * chordSizeDiff);
                    }
                }
            }
            else if (!transition.releases) {
                const releaseTicks = transition.releaseTicks;
                if (releaseTicks > 0.0) {
                    transitionVolumeTickStart *= Math.min(1.0, (noteLengthTicks - noteTicksPassedTickStart) / releaseTicks);
                    transitionVolumeTickEnd *= Math.min(1.0, (noteLengthTicks - noteTicksPassedTickEnd) / releaseTicks);
                }
            }
            intervalStart = intervalTickStart + (intervalTickEnd - intervalTickStart) * startRatio;
            intervalEnd = intervalTickStart + (intervalTickEnd - intervalTickStart) * endRatio;
            customVolumeStart = Synth.expressionToVolumeMult(customVolumeTickStart + (customVolumeTickEnd - customVolumeTickStart) * startRatio);
            customVolumeEnd = Synth.expressionToVolumeMult(customVolumeTickStart + (customVolumeTickEnd - customVolumeTickStart) * endRatio);
            transitionVolumeStart = transitionVolumeTickStart + (transitionVolumeTickEnd - transitionVolumeTickStart) * startRatio;
            transitionVolumeEnd = transitionVolumeTickStart + (transitionVolumeTickEnd - transitionVolumeTickStart) * endRatio;
            chordVolumeStart = chordVolumeTickStart + (chordVolumeTickEnd - chordVolumeTickStart) * startRatio;
            chordVolumeEnd = chordVolumeTickStart + (chordVolumeTickEnd - chordVolumeTickStart) * endRatio;
            decayTimeStart = decayTimeTickStart + (decayTimeTickEnd - decayTimeTickStart) * startRatio;
            decayTimeEnd = decayTimeTickStart + (decayTimeTickEnd - decayTimeTickStart) * endRatio;
        }
        const sampleTime = 1.0 / synth.samplesPerSecond;
        tone.active = true;
        if (instrument.type == 0 || instrument.type == 1 || instrument.type == 5 || instrument.type == 6 || instrument.type == 7) {
            const lfoEffectStart = Synth.getLFOAmplitude(instrument, secondsPerPart * partTimeStart);
            const lfoEffectEnd = Synth.getLFOAmplitude(instrument, secondsPerPart * partTimeEnd);
            const vibratoScale = (partsSinceStart < beepbox.Config.vibratos[instrument.vibrato].delayParts) ? 0.0 : beepbox.Config.vibratos[instrument.vibrato].amplitude;
            const vibratoStart = vibratoScale * lfoEffectStart;
            const vibratoEnd = vibratoScale * lfoEffectEnd;
            intervalStart += vibratoStart;
            intervalEnd += vibratoEnd;
        }
        if (!transition.isSeamless || (!(!transition.slides && tone.note != null && tone.note.start == 0) && !(tone.prevNote != null))) {
            const attackSeconds = transition.attackSeconds;
            if (attackSeconds > 0.0) {
                transitionVolumeStart *= Math.min(1.0, secondsPerPart * decayTimeStart / attackSeconds);
                transitionVolumeEnd *= Math.min(1.0, secondsPerPart * decayTimeEnd / attackSeconds);
            }
        }
        const instrumentVolumeMult = Synth.instrumentVolumeToVolumeMult(instrument.volume);
        if (instrument.type == 4) {
            tone.drumsetPitch = tone.pitches[0];
            if (tone.note != null)
                tone.drumsetPitch += tone.note.pickMainInterval();
            tone.drumsetPitch = Math.max(0, Math.min(beepbox.Config.drumCount - 1, tone.drumsetPitch));
        }
        const cutoffOctaves = instrument.getFilterCutoffOctaves();
        const filterEnvelope = (instrument.type == 4) ? instrument.getDrumsetEnvelope(tone.drumsetPitch) : instrument.getFilterEnvelope();
        const filterCutoffHz = beepbox.Config.filterCutoffMaxHz * Math.pow(2.0, cutoffOctaves);
        const filterBase = 2.0 * Math.sin(Math.PI * filterCutoffHz / synth.samplesPerSecond);
        const filterMin = 2.0 * Math.sin(Math.PI * beepbox.Config.filterCutoffMinHz / synth.samplesPerSecond);
        tone.filter = filterBase * Synth.computeEnvelope(filterEnvelope, secondsPerPart * decayTimeStart, beatsPerPart * partTimeStart, customVolumeStart);
        let endFilter = filterBase * Synth.computeEnvelope(filterEnvelope, secondsPerPart * decayTimeEnd, beatsPerPart * partTimeEnd, customVolumeEnd);
        tone.filter = Math.min(beepbox.Config.filterMax, Math.max(filterMin, tone.filter));
        endFilter = Math.min(beepbox.Config.filterMax, Math.max(filterMin, endFilter));
        tone.filterScale = Math.pow(endFilter / tone.filter, 1.0 / runLength);
        let filterVolume = Math.pow(0.5, cutoffOctaves * 0.35);
        if (instrument.filterResonance > 0) {
            filterVolume = Math.pow(filterVolume, 1.7) * Math.pow(0.5, 0.125 * (instrument.filterResonance - 1));
        }
        if (filterEnvelope.type == 8) {
            filterVolume *= (1.25 + .025 * filterEnvelope.speed);
        }
        else if (filterEnvelope.type == 4) {
            filterVolume *= (1 + .02 * filterEnvelope.speed);
        }
        if (resetPhases) {
            tone.reset();
        }
        if (instrument.type == 1) {
            let sineVolumeBoost = 1.0;
            let totalCarrierVolume = 0.0;
            let arpeggioInterval = 0;
            if (tone.pitchCount > 1 && !chord.harmonizes) {
                const arpeggio = Math.floor((synth.tick + synth.part * beepbox.Config.ticksPerPart) / beepbox.Config.rhythms[song.rhythm].ticksPerArpeggio);
                const arpeggioPattern = beepbox.Config.rhythms[song.rhythm].arpeggioPatterns[tone.pitchCount - 1];
                arpeggioInterval = tone.pitches[arpeggioPattern[arpeggio % arpeggioPattern.length]] - tone.pitches[0];
            }
            const carrierCount = beepbox.Config.algorithms[instrument.algorithm].carrierCount;
            for (let i = 0; i < beepbox.Config.operatorCount; i++) {
                const associatedCarrierIndex = beepbox.Config.algorithms[instrument.algorithm].associatedCarrier[i] - 1;
                const pitch = tone.pitches[!chord.harmonizes ? 0 : ((i < tone.pitchCount) ? i : ((associatedCarrierIndex < tone.pitchCount) ? associatedCarrierIndex : 0))];
                const freqMult = beepbox.Config.operatorFrequencies[instrument.operators[i].frequency].mult;
                const interval = beepbox.Config.operatorCarrierInterval[associatedCarrierIndex] + arpeggioInterval;
                const startPitch = basePitch + (pitch + intervalStart) * intervalScale + interval;
                const startFreq = freqMult * (Instrument.frequencyFromPitch(startPitch)) + beepbox.Config.operatorFrequencies[instrument.operators[i].frequency].hzOffset;
                tone.phaseDeltas[i] = startFreq * sampleTime * beepbox.Config.sineWaveLength;
                const amplitudeCurve = Synth.operatorAmplitudeCurve(instrument.operators[i].amplitude);
                const amplitudeMult = amplitudeCurve * beepbox.Config.operatorFrequencies[instrument.operators[i].frequency].amplitudeSign;
                let volumeStart = amplitudeMult;
                let volumeEnd = amplitudeMult;
                if (i < carrierCount) {
                    const endPitch = basePitch + (pitch + intervalEnd) * intervalScale + interval;
                    const pitchVolumeStart = Math.pow(2.0, -(startPitch - volumeReferencePitch) / pitchDamping);
                    const pitchVolumeEnd = Math.pow(2.0, -(endPitch - volumeReferencePitch) / pitchDamping);
                    volumeStart *= pitchVolumeStart;
                    volumeEnd *= pitchVolumeEnd;
                    totalCarrierVolume += amplitudeCurve;
                }
                else {
                    volumeStart *= beepbox.Config.sineWaveLength * 1.5;
                    volumeEnd *= beepbox.Config.sineWaveLength * 1.5;
                    sineVolumeBoost *= 1.0 - Math.min(1.0, instrument.operators[i].amplitude / 15);
                }
                const operatorEnvelope = beepbox.Config.envelopes[instrument.operators[i].envelope];
                volumeStart *= Synth.computeEnvelope(operatorEnvelope, secondsPerPart * decayTimeStart, beatsPerPart * partTimeStart, customVolumeStart);
                volumeEnd *= Synth.computeEnvelope(operatorEnvelope, secondsPerPart * decayTimeEnd, beatsPerPart * partTimeEnd, customVolumeEnd);
                tone.volumeStarts[i] = volumeStart;
                tone.volumeDeltas[i] = (volumeEnd - volumeStart) / runLength;
            }
            const feedbackAmplitude = beepbox.Config.sineWaveLength * 0.3 * instrument.feedbackAmplitude / 15.0;
            const feedbackEnvelope = beepbox.Config.envelopes[instrument.feedbackEnvelope];
            let feedbackStart = feedbackAmplitude * Synth.computeEnvelope(feedbackEnvelope, secondsPerPart * decayTimeStart, beatsPerPart * partTimeStart, customVolumeStart);
            let feedbackEnd = feedbackAmplitude * Synth.computeEnvelope(feedbackEnvelope, secondsPerPart * decayTimeEnd, beatsPerPart * partTimeEnd, customVolumeEnd);
            tone.feedbackMult = feedbackStart;
            tone.feedbackDelta = (feedbackEnd - tone.feedbackMult) / runLength;
            const volumeMult = baseVolume * instrumentVolumeMult;
            tone.volumeStart = filterVolume * volumeMult * transitionVolumeStart * chordVolumeStart;
            const volumeEnd = filterVolume * volumeMult * transitionVolumeEnd * chordVolumeEnd;
            tone.volumeDelta = (volumeEnd - tone.volumeStart) / runLength;
            sineVolumeBoost *= (Math.pow(2.0, (2.0 - 1.4 * instrument.feedbackAmplitude / 15.0)) - 1.0) / 3.0;
            sineVolumeBoost *= 1.0 - Math.min(1.0, Math.max(0.0, totalCarrierVolume - 1) / 2.0);
            tone.volumeStart *= 1.0 + sineVolumeBoost * 3.0;
            tone.volumeDelta *= 1.0 + sineVolumeBoost * 3.0;
        }
        else {
            let pitch = tone.pitches[0];
            if (tone.pitchCount > 1) {
                const arpeggio = Math.floor((synth.tick + synth.part * beepbox.Config.ticksPerPart) / beepbox.Config.rhythms[song.rhythm].ticksPerArpeggio);
                if (chord.harmonizes) {
                    const arpeggioPattern = beepbox.Config.rhythms[song.rhythm].arpeggioPatterns[tone.pitchCount - 2];
                    const intervalOffset = tone.pitches[1 + arpeggioPattern[arpeggio % arpeggioPattern.length]] - tone.pitches[0];
                    tone.intervalMult = Math.pow(2.0, intervalOffset / 12.0);
                    tone.intervalVolumeMult = Math.pow(2.0, -intervalOffset / pitchDamping);
                }
                else {
                    const arpeggioPattern = beepbox.Config.rhythms[song.rhythm].arpeggioPatterns[tone.pitchCount - 1];
                    pitch = tone.pitches[arpeggioPattern[arpeggio % arpeggioPattern.length]];
                }
            }
            const startPitch = basePitch + (pitch + intervalStart) * intervalScale;
            const endPitch = basePitch + (pitch + intervalEnd) * intervalScale;
            const startFreq = Instrument.frequencyFromPitch(startPitch);
            const pitchVolumeStart = Math.pow(2.0, -(startPitch - volumeReferencePitch) / pitchDamping);
            const pitchVolumeEnd = Math.pow(2.0, -(endPitch - volumeReferencePitch) / pitchDamping);
            let settingsVolumeMult = baseVolume * filterVolume;
            if (instrument.type == 2) {
                settingsVolumeMult *= beepbox.Config.chipNoises[instrument.chipNoise].volume;
            }
            if (instrument.type == 0 || instrument.type == 7) {
                settingsVolumeMult *= beepbox.Config.chipWaves[instrument.chipWave].volume;
            }
            if (instrument.type == 0 || instrument.type == 5 || instrument.type == 7) {
                settingsVolumeMult *= beepbox.Config.intervals[instrument.interval].volume;
            }
            if (instrument.type == 6) {
                const pulseEnvelope = beepbox.Config.envelopes[instrument.pulseEnvelope];
                const basePulseWidth = instrument.pulseWidth / 100;
                const pulseWidthStart = basePulseWidth * Synth.computeEnvelope(pulseEnvelope, secondsPerPart * decayTimeStart, beatsPerPart * partTimeStart, customVolumeStart);
                const pulseWidthEnd = basePulseWidth * Synth.computeEnvelope(pulseEnvelope, secondsPerPart * decayTimeEnd, beatsPerPart * partTimeEnd, customVolumeEnd);
                tone.pulseWidth = pulseWidthStart;
                tone.pulseWidthDelta = (pulseWidthEnd - pulseWidthStart) / runLength;
            }
            tone.phaseDeltas[0] = startFreq * sampleTime;
            tone.volumeStart = transitionVolumeStart * chordVolumeStart * pitchVolumeStart * settingsVolumeMult * instrumentVolumeMult;
            let volumeEnd = transitionVolumeEnd * chordVolumeEnd * pitchVolumeEnd * settingsVolumeMult * instrumentVolumeMult;
            if (filterEnvelope.type != 0 && (instrument.type != 6 || beepbox.Config.envelopes[instrument.pulseEnvelope].type != 0)) {
                tone.volumeStart *= customVolumeStart;
                volumeEnd *= customVolumeEnd;
            }
            tone.volumeDelta = (volumeEnd - tone.volumeStart) / runLength;
        }
        tone.phaseDeltaScale = Math.pow(2.0, ((intervalEnd - intervalStart) * intervalScale / 12.0) / runLength);
    }
    static getLFOAmplitude(instrument, secondsIntoBar) {
        let effect = 0.0;
        for (const vibratoPeriodSeconds of beepbox.Config.vibratos[instrument.vibrato].periodsSeconds) {
            effect += Math.sin(Math.PI * 2.0 * secondsIntoBar / vibratoPeriodSeconds);
        }
        return effect;
    }
    static getInstrumentSynthFunction(instrument) {
        if (instrument.type == 1) {
            const fingerprint = instrument.algorithm + "_" + instrument.feedbackType;
            if (Synth.fmSynthFunctionCache[fingerprint] == undefined) {
                const synthSource = [];
                for (const line of Synth.fmSourceTemplate) {
                    if (line.indexOf("// CARRIER OUTPUTS") != -1) {
                        const outputs = [];
                        for (let j = 0; j < beepbox.Config.algorithms[instrument.algorithm].carrierCount; j++) {
                            outputs.push("operator" + j + "Scaled");
                        }
                        synthSource.push(line.replace("/*operator#Scaled*/", outputs.join(" + ")));
                    }
                    else if (line.indexOf("// INSERT OPERATOR COMPUTATION HERE") != -1) {
                        for (let j = beepbox.Config.operatorCount - 1; j >= 0; j--) {
                            for (const operatorLine of Synth.operatorSourceTemplate) {
                                if (operatorLine.indexOf("/* + operator@Scaled*/") != -1) {
                                    let modulators = "";
                                    for (const modulatorNumber of beepbox.Config.algorithms[instrument.algorithm].modulatedBy[j]) {
                                        modulators += " + operator" + (modulatorNumber - 1) + "Scaled";
                                    }
                                    const feedbackIndices = beepbox.Config.feedbacks[instrument.feedbackType].indices[j];
                                    if (feedbackIndices.length > 0) {
                                        modulators += " + feedbackMult * (";
                                        const feedbacks = [];
                                        for (const modulatorNumber of feedbackIndices) {
                                            feedbacks.push("operator" + (modulatorNumber - 1) + "Output");
                                        }
                                        modulators += feedbacks.join(" + ") + ")";
                                    }
                                    synthSource.push(operatorLine.replace(/\#/g, j + "").replace("/* + operator@Scaled*/", modulators));
                                }
                                else {
                                    synthSource.push(operatorLine.replace(/\#/g, j + ""));
                                }
                            }
                        }
                    }
                    else if (line.indexOf("#") != -1) {
                        for (let j = 0; j < beepbox.Config.operatorCount; j++) {
                            synthSource.push(line.replace(/\#/g, j + ""));
                        }
                    }
                    else {
                        synthSource.push(line);
                    }
                }
                global.beepbox = beepbox
                Synth.fmSynthFunctionCache[fingerprint] = new Function("synth", "dataLeft", "dataRight", "bufferIndex", "runLength", "tone", "instrument", synthSource.join("\n"));
            }
            return Synth.fmSynthFunctionCache[fingerprint];
        }
        else if (instrument.type == 0) {
            return Synth.chipSynth;
        }
        else if (instrument.type == 7) {
            return Synth.chipSynth;
        }
        else if (instrument.type == 5) {
            return Synth.harmonicsSynth;
        }
        else if (instrument.type == 6) {
            return Synth.pulseWidthSynth;
        }
        else if (instrument.type == 2) {
            return Synth.noiseSynth;
        }
        else if (instrument.type == 3) {
            return Synth.spectrumSynth;
        }
        else if (instrument.type == 4) {
            return Synth.drumsetSynth;
        }
        else {
            throw new Error("Unrecognized instrument type: " + instrument.type);
        }
    }
    static chipSynth(synth, dataLeft, dataRight, bufferIndex, runLength, tone, instrument) {
        var wave;
        var volumeScale;
        const isCustomWave = (instrument.type == 7);
        if (!isCustomWave) {
            wave = beepbox.Config.chipWaves[instrument.chipWave].samples;
            volumeScale = 1.0;
        }
        else {
            wave = instrument.customChipWaveIntegral;
            volumeScale = 0.1;
        }
        const waveLength = +wave.length - 1;
        const intervalA = +Math.pow(2.0, (beepbox.Config.intervals[instrument.interval].offset + beepbox.Config.intervals[instrument.interval].spread) / 12.0);
        const intervalB = Math.pow(2.0, (beepbox.Config.intervals[instrument.interval].offset - beepbox.Config.intervals[instrument.interval].spread) / 12.0) * tone.intervalMult;
        const intervalSign = tone.intervalVolumeMult * beepbox.Config.intervals[instrument.interval].sign;
        if (instrument.interval == 0 && !instrument.getChord().customInterval)
            tone.phases[1] = tone.phases[0];
        const deltaRatio = intervalB / intervalA;
        let phaseDeltaA = tone.phaseDeltas[0] * intervalA * waveLength;
        let phaseDeltaB = phaseDeltaA * deltaRatio;
        const phaseDeltaScale = +tone.phaseDeltaScale;
        let volume = +tone.volumeStart;
        const volumeDelta = +tone.volumeDelta;
        let phaseA = (tone.phases[0] % 1) * waveLength;
        let phaseB = (tone.phases[1] % 1) * waveLength;
        let filter1 = +tone.filter;
        let filter2 = instrument.getFilterIsFirstOrder() ? 1.0 : filter1;
        const filterScale1 = +tone.filterScale;
        const filterScale2 = instrument.getFilterIsFirstOrder() ? 1.0 : filterScale1;
        const filterResonance = beepbox.Config.filterMaxResonance * Math.pow(Math.max(0, instrument.getFilterResonance() - 1) / (beepbox.Config.filterResonanceRange - 2), 0.5);
        let filterSample0 = +tone.filterSample0;
        let filterSample1 = +tone.filterSample1;
        const phaseAInt = phaseA | 0;
        const phaseBInt = phaseB | 0;
        const indexA = phaseAInt % waveLength;
        const indexB = phaseBInt % waveLength;
        const phaseRatioA = phaseA - phaseAInt;
        const phaseRatioB = phaseB - phaseBInt;
        let prevWaveIntegralA = wave[indexA];
        let prevWaveIntegralB = wave[indexB];
        prevWaveIntegralA += (wave[indexA + 1] - prevWaveIntegralA) * phaseRatioA;
        prevWaveIntegralB += (wave[indexB + 1] - prevWaveIntegralB) * phaseRatioB;
        const stopIndex = bufferIndex + runLength;
        while (bufferIndex < stopIndex) {
            phaseA += phaseDeltaA;
            phaseB += phaseDeltaB;
            const phaseAInt = phaseA | 0;
            const phaseBInt = phaseB | 0;
            const indexA = phaseAInt % waveLength;
            const indexB = phaseBInt % waveLength;
            let nextWaveIntegralA = wave[indexA];
            let nextWaveIntegralB = wave[indexB];
            const phaseRatioA = phaseA - phaseAInt;
            const phaseRatioB = phaseB - phaseBInt;
            nextWaveIntegralA += (wave[indexA + 1] - nextWaveIntegralA) * phaseRatioA;
            nextWaveIntegralB += (wave[indexB + 1] - nextWaveIntegralB) * phaseRatioB;
            let waveA = (nextWaveIntegralA - prevWaveIntegralA) / phaseDeltaA;
            let waveB = (nextWaveIntegralB - prevWaveIntegralB) / phaseDeltaB;
            prevWaveIntegralA = nextWaveIntegralA;
            prevWaveIntegralB = nextWaveIntegralB;
            const combinedWave = (waveA + waveB * intervalSign);
            const feedback = filterResonance + filterResonance / (1.0 - filter1);
            filterSample0 += filter1 * (combinedWave - filterSample0 + feedback * (filterSample0 - filterSample1));
            filterSample1 += filter2 * (filterSample0 - filterSample1);
            filter1 *= filterScale1;
            filter2 *= filterScale2;
            phaseDeltaA *= phaseDeltaScale;
            phaseDeltaB *= phaseDeltaScale;
            if (!synth.forceMono) {
                dataLeft[bufferIndex] += filterSample1 * volume * volumeScale * Math.cos(((instrument.pan) / 100.0) * Math.PI / 2);
                dataRight[bufferIndex] += filterSample1 * volume * volumeScale * Math.sin(((instrument.pan) / 100.0) * Math.PI / 2);
            }
            else {
                dataLeft[bufferIndex] += filterSample1 * volume * volumeScale;
                dataRight[bufferIndex] += filterSample1 * volume * volumeScale;
            }
            volume += volumeDelta;
            bufferIndex++;
        }
        tone.phases[0] = phaseA / waveLength;
        tone.phases[1] = phaseB / waveLength;
        const epsilon = (1.0e-24);
        if (-epsilon < filterSample0 && filterSample0 < epsilon)
            filterSample0 = 0.0;
        if (-epsilon < filterSample1 && filterSample1 < epsilon)
            filterSample1 = 0.0;
        tone.filterSample0 = filterSample0;
        tone.filterSample1 = filterSample1;
    }
    static harmonicsSynth(synth, dataLeft, dataRight, bufferIndex, runLength, tone, instrument) {
        const wave = instrument.harmonicsWave.getCustomWave();
        const waveLength = +wave.length - 1;
        const intervalA = +Math.pow(2.0, (beepbox.Config.intervals[instrument.interval].offset + beepbox.Config.intervals[instrument.interval].spread) / 12.0);
        const intervalB = Math.pow(2.0, (beepbox.Config.intervals[instrument.interval].offset - beepbox.Config.intervals[instrument.interval].spread) / 12.0) * tone.intervalMult;
        const intervalSign = tone.intervalVolumeMult * beepbox.Config.intervals[instrument.interval].sign;
        if (instrument.interval == 0 && !instrument.getChord().customInterval)
            tone.phases[1] = tone.phases[0];
        const deltaRatio = intervalB / intervalA;
        let phaseDeltaA = tone.phaseDeltas[0] * intervalA * waveLength;
        let phaseDeltaB = phaseDeltaA * deltaRatio;
        const phaseDeltaScale = +tone.phaseDeltaScale;
        let volume = +tone.volumeStart;
        const volumeDelta = +tone.volumeDelta;
        let phaseA = (tone.phases[0] % 1) * waveLength;
        let phaseB = (tone.phases[1] % 1) * waveLength;
        let filter1 = +tone.filter;
        let filter2 = instrument.getFilterIsFirstOrder() ? 1.0 : filter1;
        const filterScale1 = +tone.filterScale;
        const filterScale2 = instrument.getFilterIsFirstOrder() ? 1.0 : filterScale1;
        const filterResonance = beepbox.Config.filterMaxResonance * Math.pow(Math.max(0, instrument.getFilterResonance() - 1) / (beepbox.Config.filterResonanceRange - 2), 0.5);
        let filterSample0 = +tone.filterSample0;
        let filterSample1 = +tone.filterSample1;
        const phaseAInt = phaseA | 0;
        const phaseBInt = phaseB | 0;
        const indexA = phaseAInt % waveLength;
        const indexB = phaseBInt % waveLength;
        const phaseRatioA = phaseA - phaseAInt;
        const phaseRatioB = phaseB - phaseBInt;
        let prevWaveIntegralA = wave[indexA];
        let prevWaveIntegralB = wave[indexB];
        prevWaveIntegralA += (wave[indexA + 1] - prevWaveIntegralA) * phaseRatioA;
        prevWaveIntegralB += (wave[indexB + 1] - prevWaveIntegralB) * phaseRatioB;
        const stopIndex = bufferIndex + runLength;
        while (bufferIndex < stopIndex) {
            phaseA += phaseDeltaA;
            phaseB += phaseDeltaB;
            const phaseAInt = phaseA | 0;
            const phaseBInt = phaseB | 0;
            const indexA = phaseAInt % waveLength;
            const indexB = phaseBInt % waveLength;
            let nextWaveIntegralA = wave[indexA];
            let nextWaveIntegralB = wave[indexB];
            const phaseRatioA = phaseA - phaseAInt;
            const phaseRatioB = phaseB - phaseBInt;
            nextWaveIntegralA += (wave[indexA + 1] - nextWaveIntegralA) * phaseRatioA;
            nextWaveIntegralB += (wave[indexB + 1] - nextWaveIntegralB) * phaseRatioB;
            let waveA = (nextWaveIntegralA - prevWaveIntegralA) / phaseDeltaA;
            let waveB = (nextWaveIntegralB - prevWaveIntegralB) / phaseDeltaB;
            prevWaveIntegralA = nextWaveIntegralA;
            prevWaveIntegralB = nextWaveIntegralB;
            const combinedWave = (waveA + waveB * intervalSign);
            const feedback = filterResonance + filterResonance / (1.0 - filter1);
            filterSample0 += filter1 * (combinedWave - filterSample0 + feedback * (filterSample0 - filterSample1));
            filterSample1 += filter2 * (filterSample0 - filterSample1);
            filter1 *= filterScale1;
            filter2 *= filterScale2;
            phaseDeltaA *= phaseDeltaScale;
            phaseDeltaB *= phaseDeltaScale;
            if (!synth.forceMono) {
                dataLeft[bufferIndex] += filterSample1 * volume * Math.cos(((instrument.pan) / 100.0) * Math.PI / 2);
                dataRight[bufferIndex] += filterSample1 * volume * Math.sin(((instrument.pan) / 100.0) * Math.PI / 2);
            }
            else {
                dataLeft[bufferIndex] += filterSample1 * volume;
                dataRight[bufferIndex] += dataLeft[bufferIndex];
            }
            volume += volumeDelta;
            bufferIndex++;
        }
        tone.phases[0] = phaseA / waveLength;
        tone.phases[1] = phaseB / waveLength;
        const epsilon = (1.0e-24);
        if (-epsilon < filterSample0 && filterSample0 < epsilon)
            filterSample0 = 0.0;
        if (-epsilon < filterSample1 && filterSample1 < epsilon)
            filterSample1 = 0.0;
        tone.filterSample0 = filterSample0;
        tone.filterSample1 = filterSample1;
    }
    static pulseWidthSynth(synth, dataLeft, dataRight, bufferIndex, runLength, tone, instrument) {
        let phaseDelta = tone.phaseDeltas[0];
        const phaseDeltaScale = +tone.phaseDeltaScale;
        let volume = +tone.volumeStart;
        const volumeDelta = +tone.volumeDelta;
        let phase = (tone.phases[0] % 1);
        let pulseWidth = tone.pulseWidth;
        const pulseWidthDelta = tone.pulseWidthDelta;
        let filter1 = +tone.filter;
        let filter2 = instrument.getFilterIsFirstOrder() ? 1.0 : filter1;
        const filterScale1 = +tone.filterScale;
        const filterScale2 = instrument.getFilterIsFirstOrder() ? 1.0 : filterScale1;
        const filterResonance = beepbox.Config.filterMaxResonance * Math.pow(Math.max(0, instrument.getFilterResonance() - 1) / (beepbox.Config.filterResonanceRange - 2), 0.5);
        let filterSample0 = +tone.filterSample0;
        let filterSample1 = +tone.filterSample1;
        const stopIndex = bufferIndex + runLength;
        while (bufferIndex < stopIndex) {
            const sawPhaseA = phase % 1;
            const sawPhaseB = (phase + pulseWidth) % 1;
            let pulseWave = sawPhaseB - sawPhaseA;
            if (sawPhaseA < phaseDelta) {
                var t = sawPhaseA / phaseDelta;
                pulseWave += (t + t - t * t - 1) * 0.5;
            }
            else if (sawPhaseA > 1.0 - phaseDelta) {
                var t = (sawPhaseA - 1.0) / phaseDelta;
                pulseWave += (t + t + t * t + 1) * 0.5;
            }
            if (sawPhaseB < phaseDelta) {
                var t = sawPhaseB / phaseDelta;
                pulseWave -= (t + t - t * t - 1) * 0.5;
            }
            else if (sawPhaseB > 1.0 - phaseDelta) {
                var t = (sawPhaseB - 1.0) / phaseDelta;
                pulseWave -= (t + t + t * t + 1) * 0.5;
            }
            const feedback = filterResonance + filterResonance / (1.0 - filter1);
            filterSample0 += filter1 * (pulseWave - filterSample0 + feedback * (filterSample0 - filterSample1));
            filterSample1 += filter2 * (filterSample0 - filterSample1);
            filter1 *= filterScale1;
            filter2 *= filterScale2;
            phase += phaseDelta;
            phaseDelta *= phaseDeltaScale;
            pulseWidth += pulseWidthDelta;
            if (!synth.forceMono) {
                dataLeft[bufferIndex] += filterSample1 * volume * Math.cos(((instrument.pan) / 100.0) * Math.PI / 2);
                dataRight[bufferIndex] += filterSample1 * volume * Math.sin(((instrument.pan) / 100.0) * Math.PI / 2);
            }
            else {
                dataLeft[bufferIndex] += filterSample1 * volume;
                dataRight[bufferIndex] += dataLeft[bufferIndex];
            }
            volume += volumeDelta;
            bufferIndex++;
        }
        tone.phases[0] = phase;
        const epsilon = (1.0e-24);
        if (-epsilon < filterSample0 && filterSample0 < epsilon)
            filterSample0 = 0.0;
        if (-epsilon < filterSample1 && filterSample1 < epsilon)
            filterSample1 = 0.0;
        tone.filterSample0 = filterSample0;
        tone.filterSample1 = filterSample1;
    }
    static noiseSynth(synth, dataLeft, dataRight, bufferIndex, runLength, tone, instrument) {
        let wave = instrument.getDrumWave();
        let phaseDelta = +tone.phaseDeltas[0];
        const phaseDeltaScale = +tone.phaseDeltaScale;
        let volume = +tone.volumeStart;
        const volumeDelta = +tone.volumeDelta;
        let phase = (tone.phases[0] % 1) * beepbox.Config.chipNoiseLength;
        if (tone.phases[0] == 0) {
            phase = Math.random() * beepbox.Config.chipNoiseLength;
        }
        let sample = +tone.sample;
        let filter1 = +tone.filter;
        let filter2 = instrument.getFilterIsFirstOrder() ? 1.0 : filter1;
        const filterScale1 = +tone.filterScale;
        const filterScale2 = instrument.getFilterIsFirstOrder() ? 1.0 : filterScale1;
        const filterResonance = beepbox.Config.filterMaxResonance * Math.pow(Math.max(0, instrument.getFilterResonance() - 1) / (beepbox.Config.filterResonanceRange - 2), 0.5);
        let filterSample0 = +tone.filterSample0;
        let filterSample1 = +tone.filterSample1;
        const pitchRelativefilter = Math.min(1.0, tone.phaseDeltas[0] * beepbox.Config.chipNoises[instrument.chipNoise].pitchFilterMult);
        const stopIndex = bufferIndex + runLength;
        while (bufferIndex < stopIndex) {
            const waveSample = wave[phase & 0x7fff];
            sample += (waveSample - sample) * pitchRelativefilter;
            const feedback = filterResonance + filterResonance / (1.0 - filter1);
            filterSample0 += filter1 * (sample - filterSample0 + feedback * (filterSample0 - filterSample1));
            filterSample1 += filter2 * (filterSample0 - filterSample1);
            phase += phaseDelta;
            filter1 *= filterScale1;
            filter2 *= filterScale2;
            phaseDelta *= phaseDeltaScale;
            if (!synth.forceMono) {
                dataLeft[bufferIndex] += filterSample1 * volume * Math.cos(((instrument.pan) / 100.0) * Math.PI / 2);
                dataRight[bufferIndex] += filterSample1 * volume * Math.sin(((instrument.pan) / 100.0) * Math.PI / 2);
            }
            else {
                dataLeft[bufferIndex] += filterSample1 * volume;
                dataRight[bufferIndex] += dataLeft[bufferIndex];
            }
            volume += volumeDelta;
            bufferIndex++;
        }
        tone.phases[0] = phase / beepbox.Config.chipNoiseLength;
        tone.sample = sample;
        const epsilon = (1.0e-24);
        if (-epsilon < filterSample0 && filterSample0 < epsilon)
            filterSample0 = 0.0;
        if (-epsilon < filterSample1 && filterSample1 < epsilon)
            filterSample1 = 0.0;
        tone.filterSample0 = filterSample0;
        tone.filterSample1 = filterSample1;
    }
    static spectrumSynth(synth, dataLeft, dataRight, bufferIndex, runLength, tone, instrument) {
        let wave = instrument.getDrumWave();
        let phaseDelta = tone.phaseDeltas[0] * (1 << 7);
        const phaseDeltaScale = +tone.phaseDeltaScale;
        let volume = +tone.volumeStart;
        const volumeDelta = +tone.volumeDelta;
        let sample = +tone.sample;
        let filter1 = +tone.filter;
        let filter2 = instrument.getFilterIsFirstOrder() ? 1.0 : filter1;
        const filterScale1 = +tone.filterScale;
        const filterScale2 = instrument.getFilterIsFirstOrder() ? 1.0 : filterScale1;
        const filterResonance = beepbox.Config.filterMaxResonance * Math.pow(Math.max(0, instrument.getFilterResonance() - 1) / (beepbox.Config.filterResonanceRange - 2), 0.5);
        let filterSample0 = +tone.filterSample0;
        let filterSample1 = +tone.filterSample1;
        let phase = (tone.phases[0] % 1) * beepbox.Config.chipNoiseLength;
        if (tone.phases[0] == 0)
            phase = Synth.findRandomZeroCrossing(wave) + phaseDelta;
        const pitchRelativefilter = Math.min(1.0, phaseDelta);
        const stopIndex = bufferIndex + runLength;
        while (bufferIndex < stopIndex) {
            const phaseInt = phase | 0;
            const index = phaseInt & 0x7fff;
            let waveSample = wave[index];
            const phaseRatio = phase - phaseInt;
            waveSample += (wave[index + 1] - waveSample) * phaseRatio;
            sample += (waveSample - sample) * pitchRelativefilter;
            const feedback = filterResonance + filterResonance / (1.0 - filter1);
            filterSample0 += filter1 * (sample - filterSample0 + feedback * (filterSample0 - filterSample1));
            filterSample1 += filter2 * (filterSample0 - filterSample1);
            phase += phaseDelta;
            filter1 *= filterScale1;
            filter2 *= filterScale2;
            phaseDelta *= phaseDeltaScale;
            if (!synth.forceMono) {
                dataLeft[bufferIndex] += filterSample1 * volume * Math.cos(((instrument.pan) / 100.0) * Math.PI / 2);
                dataRight[bufferIndex] += filterSample1 * volume * Math.sin(((instrument.pan) / 100.0) * Math.PI / 2);
            }
            else {
                dataLeft[bufferIndex] += filterSample1 * volume;
                dataRight[bufferIndex] += dataLeft[bufferIndex];
            }
            volume += volumeDelta;
            bufferIndex++;
        }
        tone.phases[0] = phase / beepbox.Config.chipNoiseLength;
        tone.sample = sample;
        const epsilon = (1.0e-24);
        if (-epsilon < filterSample0 && filterSample0 < epsilon)
            filterSample0 = 0.0;
        if (-epsilon < filterSample1 && filterSample1 < epsilon)
            filterSample1 = 0.0;
        tone.filterSample0 = filterSample0;
        tone.filterSample1 = filterSample1;
    }
    static drumsetSynth(synth, dataLeft, dataRight, bufferIndex, runLength, tone, instrument) {
        let wave = instrument.getDrumsetWave(tone.drumsetPitch);
        let phaseDelta = tone.phaseDeltas[0] / Instrument.drumsetIndexReferenceDelta(tone.drumsetPitch);
        ;
        const phaseDeltaScale = +tone.phaseDeltaScale;
        let volume = +tone.volumeStart;
        const volumeDelta = +tone.volumeDelta;
        let sample = +tone.sample;
        let filter1 = +tone.filter;
        let filter2 = instrument.getFilterIsFirstOrder() ? 1.0 : filter1;
        const filterScale1 = +tone.filterScale;
        const filterScale2 = instrument.getFilterIsFirstOrder() ? 1.0 : filterScale1;
        const filterResonance = beepbox.Config.filterMaxResonance * Math.pow(Math.max(0, instrument.getFilterResonance() - 1) / (beepbox.Config.filterResonanceRange - 2), 0.5);
        let filterSample0 = +tone.filterSample0;
        let filterSample1 = +tone.filterSample1;
        let phase = (tone.phases[0] % 1) * beepbox.Config.chipNoiseLength;
        if (tone.phases[0] == 0)
            phase = Synth.findRandomZeroCrossing(wave) + phaseDelta;
        const stopIndex = bufferIndex + runLength;
        while (bufferIndex < stopIndex) {
            const phaseInt = phase | 0;
            const index = phaseInt & 0x7fff;
            sample = wave[index];
            const phaseRatio = phase - phaseInt;
            sample += (wave[index + 1] - sample) * phaseRatio;
            const feedback = filterResonance + filterResonance / (1.0 - filter1);
            filterSample0 += filter1 * (sample - filterSample0 + feedback * (filterSample0 - filterSample1));
            filterSample1 += filter2 * (filterSample0 - filterSample1);
            phase += phaseDelta;
            filter1 *= filterScale1;
            filter2 *= filterScale2;
            phaseDelta *= phaseDeltaScale;
            if (!synth.forceMono) {
                dataLeft[bufferIndex] += filterSample1 * volume * Math.cos(((instrument.pan) / 100.0) * Math.PI / 2);
                dataRight[bufferIndex] += filterSample1 * volume * Math.sin(((instrument.pan) / 100.0) * Math.PI / 2);
            }
            else {
                dataLeft[bufferIndex] += filterSample1 * volume;
                dataRight[bufferIndex] += dataLeft[bufferIndex];
            }
            volume += volumeDelta;
            bufferIndex++;
        }
        tone.phases[0] = phase / beepbox.Config.chipNoiseLength;
        tone.sample = sample;
        const epsilon = (1.0e-24);
        if (-epsilon < filterSample0 && filterSample0 < epsilon)
            filterSample0 = 0.0;
        if (-epsilon < filterSample1 && filterSample1 < epsilon)
            filterSample1 = 0.0;
        tone.filterSample0 = filterSample0;
        tone.filterSample1 = filterSample1;
    }
    static findRandomZeroCrossing(wave) {
        let phase = Math.random() * beepbox.Config.chipNoiseLength;
        let indexPrev = phase & 0x7fff;
        let wavePrev = wave[indexPrev];
        const stride = 16;
        for (let attemptsRemaining = 128; attemptsRemaining > 0; attemptsRemaining--) {
            const indexNext = (indexPrev + stride) & 0x7fff;
            const waveNext = wave[indexNext];
            if (wavePrev * waveNext <= 0.0) {
                for (let i = 0; i < 16; i++) {
                    const innerIndexNext = (indexPrev + 1) & 0x7fff;
                    const innerWaveNext = wave[innerIndexNext];
                    if (wavePrev * innerWaveNext <= 0.0) {
                        const slope = innerWaveNext - wavePrev;
                        phase = indexPrev;
                        if (Math.abs(slope) > 0.00000001) {
                            phase += -wavePrev / slope;
                        }
                        phase = Math.max(0, phase) % beepbox.Config.chipNoiseLength;
                        break;
                    }
                    else {
                        indexPrev = innerIndexNext;
                        wavePrev = innerWaveNext;
                    }
                }
                break;
            }
            else {
                indexPrev = indexNext;
                wavePrev = waveNext;
            }
        }
        return phase;
    }
    static instrumentVolumeToVolumeMult(instrumentVolume) {
        return (instrumentVolume == -beepbox.Config.volumeRange / 2.0) ? 0.0 : Math.pow(2, beepbox.Config.volumeLogScale * instrumentVolume);
    }
    static volumeMultToInstrumentVolume(volumeMult) {
        return (volumeMult <= 0.0) ? -beepbox.Config.volumeRange / 2 : Math.min(beepbox.Config.volumeRange, (Math.log(volumeMult) / Math.LN2) / beepbox.Config.volumeLogScale);
    }
    static expressionToVolumeMult(expression) {
        return Math.pow(Math.max(0.0, expression) / 6.0, 1.5);
    }
    static volumeMultToExpression(volumeMult) {
        return Math.pow(Math.max(0.0, volumeMult), 1 / 1.5) * 6.0;
    }
    getSamplesPerTick() {
        if (this.song == null)
            return 0;
        const beatsPerMinute = this.song.getBeatsPerMinute();
        const beatsPerSecond = beatsPerMinute / 60.0;
        const partsPerSecond = beatsPerSecond * beepbox.Config.partsPerBeat;
        const tickPerSecond = partsPerSecond * beepbox.Config.ticksPerPart;
        return Math.floor(this.samplesPerSecond / tickPerSecond);
    }
}
Synth.negativePhaseGuard = 1000;
Synth.fmSynthFunctionCache = {};
Synth.fmSourceTemplate = (`
        var sineWave = beepbox.Config.sineWave;
        
        var phaseDeltaScale = +tone.phaseDeltaScale;
        var operator#Phase       = +((tone.phases[#] % 1) + beepbox.Synth.negativePhaseGuard) * beepbox.Config.sineWaveLength;
        var operator#PhaseDelta  = +tone.phaseDeltas[#];
        var operator#OutputMult  = +tone.volumeStarts[#];
        var operator#OutputDelta = +tone.volumeDeltas[#];
        var operator#Output      = +tone.feedbackOutputs[#];
        var feedbackMult         = +tone.feedbackMult;
        var feedbackDelta        = +tone.feedbackDelta;
        var volume = +tone.volumeStart;
        var volumeDelta = +tone.volumeDelta;
        
        var filter1 = +tone.filter;
        var filter2 = instrument.getFilterIsFirstOrder() ? 1.0 : filter1;
        var filterScale1 = +tone.filterScale;
        var filterScale2 = instrument.getFilterIsFirstOrder() ? 1.0 : filterScale1;
        var filterResonance = beepbox.Config.filterMaxResonance * Math.pow(Math.max(0, instrument.getFilterResonance() - 1) / (beepbox.Config.filterResonanceRange - 2), 0.5);
        var filterSample0 = +tone.filterSample0;
        var filterSample1 = +tone.filterSample1;
        
        var stopIndex = bufferIndex + runLength;
        while (bufferIndex < stopIndex) {
            // INSERT OPERATOR COMPUTATION HERE
            var fmOutput = (/*operator#Scaled*/); // CARRIER OUTPUTS
            
            var feedback = filterResonance + filterResonance / (1.0 - filter1);
            filterSample0 += filter1 * (fmOutput - filterSample0 + feedback * (filterSample0 - filterSample1));
            filterSample1 += filter2 * (filterSample0 - filterSample1);
            
            feedbackMult += feedbackDelta;
            operator#OutputMult += operator#OutputDelta;
            operator#Phase += operator#PhaseDelta;
            operator#PhaseDelta *= phaseDeltaScale;
            filter1 *= filterScale1;
            filter2 *= filterScale2;
            
            // Check if panning should be used - otherwise just use mono and both channels will be the same power.
    if ( !synth.forceMono ) {

      // "Constant Power" panning - left audio is cos(angle), right audio is sin(angle)
      // "angle" in this context is in radians from 0 (left) to pi/2 (right)
      dataLeft[bufferIndex] += filterSample1 * volume * Math.cos(((instrument.pan) / 100.0) * Math.PI / 2);
      dataRight[bufferIndex] += filterSample1 * volume * Math.sin(((instrument.pan) / 100.0) * Math.PI / 2);

    } else {

      dataLeft[bufferIndex] += filterSample1 * volume;
      dataRight[bufferIndex] += dataLeft[bufferIndex];

    }


            volume += volumeDelta;
            bufferIndex++;
        }
        
        tone.phases[#] = operator#Phase / beepbox.Config.sineWaveLength;
        tone.feedbackOutputs[#] = operator#Output;
        
        var epsilon = (1.0e-24);
        if (-epsilon < filterSample0 && filterSample0 < epsilon) filterSample0 = 0.0;
        if (-epsilon < filterSample1 && filterSample1 < epsilon) filterSample1 = 0.0;
        tone.filterSample0 = filterSample0;
        tone.filterSample1 = filterSample1;
    `).split("\n");
Synth.operatorSourceTemplate = (`
            var operator#PhaseMix = operator#Phase/* + operator@Scaled*/;
            var operator#PhaseInt = operator#PhaseMix|0;
            var operator#Index    = operator#PhaseInt & beepbox.Config.sineWaveMask;
            var operator#Sample   = sineWave[operator#Index];
            operator#Output       = operator#Sample + (sineWave[operator#Index + 1] - operator#Sample) * (operator#PhaseMix - operator#PhaseInt);
            var operator#Scaled   = operator#OutputMult * operator#Output;
    `).split("\n");

class Config {
}
Config.thresholdVal = -10;
Config.kneeVal = 40;
Config.ratioVal = 12;
Config.attackVal = 0;
Config.releaseVal = 0.25;
Config.versionDisplayName = "JummBox 1.1";
Config.scales = toNameMap([
    { name: "Free", flags: [true, true, true, true, true, true, true, true, true, true, true, true] },
    { name: "Major", flags: [true, false, true, false, true, true, false, true, false, true, false, true] },
    { name: "Minor", flags: [true, false, true, true, false, true, false, true, true, false, true, false] },
    { name: "Mixolydian", flags: [true, false, true, false, true, true, false, true, false, true, true, false] },
    { name: "Lydian", flags: [true, false, true, false, true, false, true, true, false, true, false, true] },
    { name: "Dorian", flags: [true, false, true, true, false, true, false, true, false, true, true, false] },
    { name: "Phrygian", flags: [true, true, false, true, false, true, false, true, true, false, true, false] },
    { name: "Locrian", flags: [true, true, false, true, false, true, true, false, true, false, true, false] },
    { name: "Lydian Dominant", flags: [true, false, true, false, true, false, true, true, false, true, true, false] },
    { name: "Phrygian Dominant", flags: [true, true, false, false, true, true, false, true, true, false, true, false] },
    { name: "Harmonic Major", flags: [true, false, true, false, true, true, false, true, true, false, false, true] },
    { name: "Harmonic Minor", flags: [true, false, true, true, false, true, false, true, true, false, false, true] },
    { name: "Melodic Minor", flags: [true, false, true, true, false, true, false, true, false, true, false, true] },
    { name: "Blues", flags: [true, false, false, true, false, true, true, true, false, false, true, false] },
    { name: "Altered", flags: [true, true, false, true, true, false, true, false, true, false, true, false] },
    { name: "Major Pentatonic", flags: [true, false, true, false, true, false, false, true, false, true, false, false] },
    { name: "Minor Pentatonic", flags: [true, false, false, true, false, true, false, true, false, false, true, false] },
    { name: "Whole Tone", flags: [true, false, true, false, true, false, true, false, true, false, true, false] },
    { name: "Octatonic", flags: [true, false, true, true, false, true, true, false, true, true, false, true] },
    { name: "Hexatonic", flags: [true, false, false, true, true, false, false, true, true, false, false, true] },
]);
Config.keys = toNameMap([
    { name: "C", isWhiteKey: true, basePitch: 12 },
    { name: "C♯", isWhiteKey: false, basePitch: 13 },
    { name: "D", isWhiteKey: true, basePitch: 14 },
    { name: "D♯", isWhiteKey: false, basePitch: 15 },
    { name: "E", isWhiteKey: true, basePitch: 16 },
    { name: "F", isWhiteKey: true, basePitch: 17 },
    { name: "F♯", isWhiteKey: false, basePitch: 18 },
    { name: "G", isWhiteKey: true, basePitch: 19 },
    { name: "G♯", isWhiteKey: false, basePitch: 20 },
    { name: "A", isWhiteKey: true, basePitch: 21 },
    { name: "A♯", isWhiteKey: false, basePitch: 22 },
    { name: "B", isWhiteKey: true, basePitch: 23 },
]);
Config.blackKeyNameParents = [-1, 1, -1, 1, -1, 1, -1, -1, 1, -1, 1, -1];
Config.tempoMin = 30;
Config.tempoMax = 320;
Config.reverbRange = 32;
Config.beatsPerBarMin = 3;
Config.beatsPerBarMax = 16;
Config.barCountMin = 1;
Config.barCountMax = 256;
Config.patternsPerChannelMin = 1;
Config.patternsPerChannelMax = 128;
Config.instrumentsPerChannelMin = 1;
Config.instrumentsPerChannelMax = 10;
Config.partsPerBeat = 24;
Config.ticksPerPart = 2;
Config.rhythms = toNameMap([
    { name: "÷3 (triplets)", stepsPerBeat: 3, ticksPerArpeggio: 4, arpeggioPatterns: [[0], [0, 0, 1, 1], [0, 1, 2, 1], [0, 1, 2, 3]], roundUpThresholds: [5, 12, 18] },
    { name: "÷4 (standard)", stepsPerBeat: 4, ticksPerArpeggio: 3, arpeggioPatterns: [[0], [0, 0, 1, 1], [0, 1, 2, 1], [0, 1, 2, 3]], roundUpThresholds: [3, 9, 17, 21] },
    { name: "÷6", stepsPerBeat: 6, ticksPerArpeggio: 4, arpeggioPatterns: [[0], [0, 1], [0, 1, 2, 1], [0, 1, 2, 3]], roundUpThresholds: null },
    { name: "÷8", stepsPerBeat: 8, ticksPerArpeggio: 3, arpeggioPatterns: [[0], [0, 1], [0, 1, 2, 1], [0, 1, 2, 3]], roundUpThresholds: null },
    { name: "freehand", stepsPerBeat: 24, ticksPerArpeggio: 3, arpeggioPatterns: [[0], [0, 1], [0, 1, 2, 1], [0, 1, 2, 3]], roundUpThresholds: null },
]);
Config.instrumentTypeNames = ["chip", "FM", "noise", "spectrum", "drumset", "harmonics", "PWM", "custom chip"];
Config.instrumentTypeHasSpecialInterval = [true, true, false, false, false, true, false, true];
Config.instrumentTypeHasChorus = [true, true, true, false, false, true, true, true];
Config.chipWaves = toNameMap([
    { name: "rounded", volume: 0.94, samples: centerWave([0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.95, 0.9, 0.85, 0.8, 0.7, 0.6, 0.5, 0.4, 0.2, 0.0, -0.2, -0.4, -0.5, -0.6, -0.7, -0.8, -0.85, -0.9, -0.95, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -0.95, -0.9, -0.85, -0.8, -0.7, -0.6, -0.5, -0.4, -0.2]) },
    { name: "triangle", volume: 1.0, samples: centerWave([1.0 / 15.0, 3.0 / 15.0, 5.0 / 15.0, 7.0 / 15.0, 9.0 / 15.0, 11.0 / 15.0, 13.0 / 15.0, 15.0 / 15.0, 15.0 / 15.0, 13.0 / 15.0, 11.0 / 15.0, 9.0 / 15.0, 7.0 / 15.0, 5.0 / 15.0, 3.0 / 15.0, 1.0 / 15.0, -1.0 / 15.0, -3.0 / 15.0, -5.0 / 15.0, -7.0 / 15.0, -9.0 / 15.0, -11.0 / 15.0, -13.0 / 15.0, -15.0 / 15.0, -15.0 / 15.0, -13.0 / 15.0, -11.0 / 15.0, -9.0 / 15.0, -7.0 / 15.0, -5.0 / 15.0, -3.0 / 15.0, -1.0 / 15.0]) },
    { name: "square", volume: 0.5, samples: centerWave([1.0, -1.0]) },
    { name: "1/4 pulse", volume: 0.5, samples: centerWave([1.0, -1.0, -1.0, -1.0]) },
    { name: "1/8 pulse", volume: 0.5, samples: centerWave([1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0]) },
    { name: "sawtooth", volume: 0.65, samples: centerWave([1.0 / 31.0, 3.0 / 31.0, 5.0 / 31.0, 7.0 / 31.0, 9.0 / 31.0, 11.0 / 31.0, 13.0 / 31.0, 15.0 / 31.0, 17.0 / 31.0, 19.0 / 31.0, 21.0 / 31.0, 23.0 / 31.0, 25.0 / 31.0, 27.0 / 31.0, 29.0 / 31.0, 31.0 / 31.0, -31.0 / 31.0, -29.0 / 31.0, -27.0 / 31.0, -25.0 / 31.0, -23.0 / 31.0, -21.0 / 31.0, -19.0 / 31.0, -17.0 / 31.0, -15.0 / 31.0, -13.0 / 31.0, -11.0 / 31.0, -9.0 / 31.0, -7.0 / 31.0, -5.0 / 31.0, -3.0 / 31.0, -1.0 / 31.0]) },
    { name: "double saw", volume: 0.5, samples: centerWave([0.0, -0.2, -0.4, -0.6, -0.8, -1.0, 1.0, -0.8, -0.6, -0.4, -0.2, 1.0, 0.8, 0.6, 0.4, 0.2]) },
    { name: "double pulse", volume: 0.4, samples: centerWave([1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0]) },
    { name: "spiky", volume: 0.4, samples: centerWave([1.0, -1.0, 1.0, -1.0, 1.0, 0.0]) },
    { name: "sine", volume: 0.88, samples: centerAndNormalizeWave([8.0, 9.0, 11.0, 12.0, 13.0, 14.0, 15.0, 15.0, 15.0, 15.0, 14.0, 14.0, 13.0, 11.0, 10.0, 9.0, 7.0, 6.0, 4.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 2.0, 4.0, 5.0, 6.0]) },
    { name: "flute", volume: 0.8, samples: centerAndNormalizeWave([3.0, 4.0, 6.0, 8.0, 10.0, 11.0, 13.0, 14.0, 15.0, 15.0, 14.0, 13.0, 11.0, 8.0, 5.0, 3.0]) },
    { name: "harp", volume: 0.8, samples: centerAndNormalizeWave([0.0, 3.0, 3.0, 3.0, 4.0, 5.0, 5.0, 6.0, 7.0, 8.0, 9.0, 11.0, 11.0, 13.0, 13.0, 15.0, 15.0, 14.0, 12.0, 11.0, 10.0, 9.0, 8.0, 7.0, 7.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.0, 0.0]) },
    { name: "sharp clarinet", volume: 0.38, samples: centerAndNormalizeWave([0.0, 0.0, 0.0, 1.0, 1.0, 8.0, 8.0, 9.0, 9.0, 9.0, 8.0, 8.0, 8.0, 8.0, 8.0, 9.0, 9.0, 7.0, 9.0, 9.0, 10.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]) },
    { name: "soft clarinet", volume: 0.45, samples: centerAndNormalizeWave([0.0, 1.0, 5.0, 8.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 11.0, 11.0, 12.0, 13.0, 12.0, 10.0, 9.0, 7.0, 6.0, 4.0, 3.0, 3.0, 3.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]) },
    { name: "alto sax", volume: 0.3, samples: centerAndNormalizeWave([5.0, 5.0, 6.0, 4.0, 3.0, 6.0, 8.0, 7.0, 2.0, 1.0, 5.0, 6.0, 5.0, 4.0, 5.0, 7.0, 9.0, 11.0, 13.0, 14.0, 14.0, 14.0, 14.0, 13.0, 10.0, 8.0, 7.0, 7.0, 4.0, 3.0, 4.0, 2.0]) },
    { name: "bassoon", volume: 0.35, samples: centerAndNormalizeWave([9.0, 9.0, 7.0, 6.0, 5.0, 4.0, 4.0, 4.0, 4.0, 5.0, 7.0, 8.0, 9.0, 10.0, 11.0, 13.0, 13.0, 11.0, 10.0, 9.0, 7.0, 6.0, 4.0, 2.0, 1.0, 1.0, 1.0, 2.0, 2.0, 5.0, 11.0, 14.0]) },
    { name: "trumpet", volume: 0.22, samples: centerAndNormalizeWave([10.0, 11.0, 8.0, 6.0, 5.0, 5.0, 5.0, 6.0, 7.0, 7.0, 7.0, 7.0, 6.0, 6.0, 7.0, 7.0, 7.0, 7.0, 7.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 7.0, 8.0, 9.0, 11.0, 14.0]) },
    { name: "electric guitar", volume: 0.2, samples: centerAndNormalizeWave([11.0, 12.0, 12.0, 10.0, 6.0, 6.0, 8.0, 0.0, 2.0, 4.0, 8.0, 10.0, 9.0, 10.0, 1.0, 7.0, 11.0, 3.0, 6.0, 6.0, 8.0, 13.0, 14.0, 2.0, 0.0, 12.0, 8.0, 4.0, 13.0, 11.0, 10.0, 13.0]) },
    { name: "organ", volume: 0.2, samples: centerAndNormalizeWave([11.0, 10.0, 12.0, 11.0, 14.0, 7.0, 5.0, 5.0, 12.0, 10.0, 10.0, 9.0, 12.0, 6.0, 4.0, 5.0, 13.0, 12.0, 12.0, 10.0, 12.0, 5.0, 2.0, 2.0, 8.0, 6.0, 6.0, 5.0, 8.0, 3.0, 2.0, 1.0]) },
    { name: "pan flute", volume: 0.35, samples: centerAndNormalizeWave([1.0, 4.0, 7.0, 6.0, 7.0, 9.0, 7.0, 7.0, 11.0, 12.0, 13.0, 15.0, 13.0, 11.0, 11.0, 12.0, 13.0, 10.0, 7.0, 5.0, 3.0, 6.0, 10.0, 7.0, 3.0, 3.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]) },
]);
Config.chipNoises = toNameMap([
    { name: "retro", volume: 0.25, basePitch: 69, pitchFilterMult: 1024.0, isSoft: false, samples: null },
    { name: "white", volume: 1.0, basePitch: 69, pitchFilterMult: 8.0, isSoft: true, samples: null },
    { name: "clang", volume: 0.4, basePitch: 69, pitchFilterMult: 1024.0, isSoft: false, samples: null },
    { name: "buzz", volume: 0.3, basePitch: 69, pitchFilterMult: 1024.0, isSoft: false, samples: null },
    { name: "hollow", volume: 1.5, basePitch: 96, pitchFilterMult: 1.0, isSoft: true, samples: null },
    { name: "shine", volume: 1.0, basePitch: 69, pitchFilterMult: 1024.0, isSoft: false, samples: null },
    { name: "deep", volume: 1.5, basePitch: 120, pitchFilterMult: 1024.0, isSoft: true, samples: null },
    { name: "cutter", volume: 0.005, basePitch: 96, pitchFilterMult: 1024.0, isSoft: false, samples: null },
    { name: "metallic", volume: 1.0, basePitch: 96, pitchFilterMult: 1024.0, isSoft: false, samples: null },
]);
Config.filterCutoffMaxHz = 8000;
Config.filterCutoffMinHz = 1;
Config.filterMax = 0.95;
Config.filterMaxResonance = 0.95;
Config.filterCutoffRange = 11;
Config.filterResonanceRange = 8;
Config.transitions = toNameMap([
    { name: "seamless", isSeamless: true, attackSeconds: 0.0, releases: false, releaseTicks: 1, slides: false, slideTicks: 3 },
    { name: "hard", isSeamless: false, attackSeconds: 0.0, releases: false, releaseTicks: 3, slides: false, slideTicks: 3 },
    { name: "soft", isSeamless: false, attackSeconds: 0.025, releases: false, releaseTicks: 3, slides: false, slideTicks: 3 },
    { name: "slide", isSeamless: true, attackSeconds: 0.025, releases: false, releaseTicks: 3, slides: true, slideTicks: 3 },
    { name: "cross fade", isSeamless: false, attackSeconds: 0.04, releases: true, releaseTicks: 6, slides: false, slideTicks: 3 },
    { name: "hard fade", isSeamless: false, attackSeconds: 0.0, releases: true, releaseTicks: 48, slides: false, slideTicks: 3 },
    { name: "medium fade", isSeamless: false, attackSeconds: 0.0125, releases: true, releaseTicks: 72, slides: false, slideTicks: 3 },
    { name: "soft fade", isSeamless: false, attackSeconds: 0.06, releases: true, releaseTicks: 96, slides: false, slideTicks: 6 },
]);
Config.vibratos = toNameMap([
    { name: "none", amplitude: 0.0, periodsSeconds: [0.14], delayParts: 0 },
    { name: "light", amplitude: 0.15, periodsSeconds: [0.14], delayParts: 0 },
    { name: "delayed", amplitude: 0.3, periodsSeconds: [0.14], delayParts: 18 },
    { name: "heavy", amplitude: 0.45, periodsSeconds: [0.14], delayParts: 0 },
    { name: "shaky", amplitude: 0.1, periodsSeconds: [0.11, 1.618 * 0.11, 3 * 0.11], delayParts: 0 },
]);
Config.intervals = toNameMap([
    { name: "union", spread: 0.0, offset: 0.0, volume: 0.7, sign: 1.0 },
    { name: "shimmer", spread: 0.016, offset: 0.0, volume: 0.8, sign: 1.0 },
    { name: "hum", spread: 0.045, offset: 0.0, volume: 1.0, sign: 1.0 },
    { name: "honky tonk", spread: 0.09, offset: 0.0, volume: 1.0, sign: 1.0 },
    { name: "dissonant", spread: 0.25, offset: 0.0, volume: 0.9, sign: 1.0 },
    { name: "fifth", spread: 3.5, offset: 3.5, volume: 0.9, sign: 1.0 },
    { name: "octave", spread: 6.0, offset: 6.0, volume: 0.8, sign: 1.0 },
    { name: "bowed", spread: 0.02, offset: 0.0, volume: 1.0, sign: -1.0 },
]);
Config.effectsNames = ["none", "reverb", "chorus", "chorus & reverb"];
Config.volumeRange = 50;
Config.volumeLogScale = 0.1428;
Config.chords = toNameMap([
    { name: "harmony", harmonizes: true, customInterval: false, arpeggiates: false, isCustomInterval: false, strumParts: 0 },
    { name: "strum", harmonizes: true, customInterval: false, arpeggiates: false, isCustomInterval: false, strumParts: 1 },
    { name: "arpeggio", harmonizes: false, customInterval: false, arpeggiates: true, isCustomInterval: false, strumParts: 0 },
    { name: "custom interval", harmonizes: true, customInterval: true, arpeggiates: true, isCustomInterval: true, strumParts: 0 },
]);
Config.operatorCount = 4;
Config.algorithms = toNameMap([
    { name: "1←(2 3 4)", carrierCount: 1, associatedCarrier: [1, 1, 1, 1], modulatedBy: [[2, 3, 4], [], [], []] },
    { name: "1←(2 3←4)", carrierCount: 1, associatedCarrier: [1, 1, 1, 1], modulatedBy: [[2, 3], [], [4], []] },
    { name: "1←2←(3 4)", carrierCount: 1, associatedCarrier: [1, 1, 1, 1], modulatedBy: [[2], [3, 4], [], []] },
    { name: "1←(2 3)←4", carrierCount: 1, associatedCarrier: [1, 1, 1, 1], modulatedBy: [[2, 3], [4], [4], []] },
    { name: "1←2←3←4", carrierCount: 1, associatedCarrier: [1, 1, 1, 1], modulatedBy: [[2], [3], [4], []] },
    { name: "1←3 2←4", carrierCount: 2, associatedCarrier: [1, 2, 1, 2], modulatedBy: [[3], [4], [], []] },
    { name: "1 2←(3 4)", carrierCount: 2, associatedCarrier: [1, 2, 2, 2], modulatedBy: [[], [3, 4], [], []] },
    { name: "1 2←3←4", carrierCount: 2, associatedCarrier: [1, 2, 2, 2], modulatedBy: [[], [3], [4], []] },
    { name: "(1 2)←3←4", carrierCount: 2, associatedCarrier: [1, 2, 2, 2], modulatedBy: [[3], [3], [4], []] },
    { name: "(1 2)←(3 4)", carrierCount: 2, associatedCarrier: [1, 2, 2, 2], modulatedBy: [[3, 4], [3, 4], [], []] },
    { name: "1 2 3←4", carrierCount: 3, associatedCarrier: [1, 2, 3, 3], modulatedBy: [[], [], [4], []] },
    { name: "(1 2 3)←4", carrierCount: 3, associatedCarrier: [1, 2, 3, 3], modulatedBy: [[4], [4], [4], []] },
    { name: "1 2 3 4", carrierCount: 4, associatedCarrier: [1, 2, 3, 4], modulatedBy: [[], [], [], []] },
]);
Config.operatorCarrierInterval = [0.0, 0.04, -0.073, 0.091];
Config.operatorAmplitudeMax = 15;
Config.operatorFrequencies = toNameMap([
    { name: "1×", mult: 1.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "~1×", mult: 1.0, hzOffset: 1.5, amplitudeSign: -1.0 },
    { name: "2×", mult: 2.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "~2×", mult: 2.0, hzOffset: -1.3, amplitudeSign: -1.0 },
    { name: "3×", mult: 3.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "4×", mult: 4.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "5×", mult: 5.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "6×", mult: 6.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "7×", mult: 7.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "8×", mult: 8.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "9×", mult: 9.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "11×", mult: 11.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "13×", mult: 13.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "16×", mult: 16.0, hzOffset: 0.0, amplitudeSign: 1.0 },
    { name: "20×", mult: 20.0, hzOffset: 0.0, amplitudeSign: 1.0 },
]);
Config.envelopes = toNameMap([
    { name: "custom", type: 0, speed: 0.0 },
    { name: "steady", type: 1, speed: 0.0 },
    { name: "punch", type: 2, speed: 0.0 },
    { name: "flare 1", type: 3, speed: 32.0 },
    { name: "flare 2", type: 3, speed: 8.0 },
    { name: "flare 3", type: 3, speed: 2.0 },
    { name: "twang 1", type: 4, speed: 32.0 },
    { name: "twang 2", type: 4, speed: 8.0 },
    { name: "twang 3", type: 4, speed: 2.0 },
    { name: "swell 1", type: 5, speed: 32.0 },
    { name: "swell 2", type: 5, speed: 8.0 },
    { name: "swell 3", type: 5, speed: 2.0 },
    { name: "tremolo1", type: 6, speed: 4.0 },
    { name: "tremolo2", type: 6, speed: 2.0 },
    { name: "tremolo3", type: 6, speed: 1.0 },
    { name: "tremolo4", type: 7, speed: 4.0 },
    { name: "tremolo5", type: 7, speed: 2.0 },
    { name: "tremolo6", type: 7, speed: 1.0 },
    { name: "decay 1", type: 8, speed: 10.0 },
    { name: "decay 2", type: 8, speed: 7.0 },
    { name: "decay 3", type: 8, speed: 4.0 },
]);
Config.feedbacks = toNameMap([
    { name: "1⟲", indices: [[1], [], [], []] },
    { name: "2⟲", indices: [[], [2], [], []] },
    { name: "3⟲", indices: [[], [], [3], []] },
    { name: "4⟲", indices: [[], [], [], [4]] },
    { name: "1⟲ 2⟲", indices: [[1], [2], [], []] },
    { name: "3⟲ 4⟲", indices: [[], [], [3], [4]] },
    { name: "1⟲ 2⟲ 3⟲", indices: [[1], [2], [3], []] },
    { name: "2⟲ 3⟲ 4⟲", indices: [[], [2], [3], [4]] },
    { name: "1⟲ 2⟲ 3⟲ 4⟲", indices: [[1], [2], [3], [4]] },
    { name: "1→2", indices: [[], [1], [], []] },
    { name: "1→3", indices: [[], [], [1], []] },
    { name: "1→4", indices: [[], [], [], [1]] },
    { name: "2→3", indices: [[], [], [2], []] },
    { name: "2→4", indices: [[], [], [], [2]] },
    { name: "3→4", indices: [[], [], [], [3]] },
    { name: "1→3 2→4", indices: [[], [], [1], [2]] },
    { name: "1→4 2→3", indices: [[], [], [2], [1]] },
    { name: "1→2→3→4", indices: [[], [1], [2], [3]] },
]);
Config.chipNoiseLength = 1 << 15;
Config.spectrumBasePitch = 24;
Config.spectrumControlPoints = 30;
Config.spectrumControlPointsPerOctave = 7;
Config.spectrumControlPointBits = 3;
Config.spectrumMax = (1 << Config.spectrumControlPointBits) - 1;
Config.harmonicsControlPoints = 28;
Config.harmonicsRendered = 64;
Config.harmonicsControlPointBits = 3;
Config.harmonicsMax = (1 << Config.harmonicsControlPointBits) - 1;
Config.harmonicsWavelength = 1 << 11;
Config.pulseWidthRange = 50;
Config.pitchChannelCountMin = 1;
Config.pitchChannelCountMax = 20;
Config.noiseChannelCountMin = 0;
Config.noiseChannelCountMax = 4;
Config.noiseInterval = 6;
Config.drumCount = 12;
Config.pitchOctaves = 7;
Config.windowOctaves = 3;
Config.scrollableOctaves = Config.pitchOctaves - Config.windowOctaves;
Config.windowPitchCount = Config.windowOctaves * 12 + 1;
Config.maxPitch = Config.pitchOctaves * 12;
Config.maximumTonesPerChannel = 8;
Config.sineWaveLength = 1 << 8;
Config.sineWaveMask = Config.sineWaveLength - 1;
Config.sineWave = generateSineWave();
Config.barEditorHeight = 10;
beepbox.Config = Config;
function centerWave(wave) {
    let sum = 0.0;
    for (let i = 0; i < wave.length; i++) {
        sum += wave[i];
    }
    const average = sum / wave.length;
    let cumulative = 0;
    let wavePrev = 0;
    for (let i = 0; i < wave.length; i++) {
        cumulative += wavePrev;
        wavePrev = wave[i] - average;
        wave[i] = cumulative;
    }
    wave.push(0);
    return new Float64Array(wave);
}
function centerAndNormalizeWave(wave) {
    let sum = 0.0;
    let magn = 0.0;
    for (let i = 0; i < wave.length; i++) {
        sum += wave[i];
        magn += Math.abs(wave[i]);
    }
    const average = sum / wave.length;
    const magnAvg = magn / wave.length;
    let cumulative = 0;
    let wavePrev = 0;
    for (let i = 0; i < wave.length; i++) {
        cumulative += wavePrev;
        wavePrev = (wave[i] - average) / (magnAvg);
        wave[i] = cumulative;
    }
    wave.push(0);
    return new Float64Array(wave);
}
function getDrumWave(index) {
    let wave = Config.chipNoises[index].samples;
    if (wave == null) {
        wave = new Float32Array(Config.chipNoiseLength + 1);
        Config.chipNoises[index].samples = wave;
        if (index == 0) {
            let drumBuffer = 1;
            for (let i = 0; i < Config.chipNoiseLength; i++) {
                wave[i] = (drumBuffer & 1) * 2.0 - 1.0;
                let newBuffer = drumBuffer >> 1;
                if (((drumBuffer + newBuffer) & 1) == 1) {
                    newBuffer += 1 << 14;
                }
                drumBuffer = newBuffer;
            }
        }
        else if (index == 1) {
            for (let i = 0; i < Config.chipNoiseLength; i++) {
                wave[i] = Math.random() * 2.0 - 1.0;
            }
        }
        else if (index == 2) {
            let drumBuffer = 1;
            for (let i = 0; i < Config.chipNoiseLength; i++) {
                wave[i] = (drumBuffer & 1) * 2.0 - 1.0;
                let newBuffer = drumBuffer >> 1;
                if (((drumBuffer + newBuffer) & 1) == 1) {
                    newBuffer += 2 << 14;
                }
                drumBuffer = newBuffer;
            }
        }
        else if (index == 3) {
            let drumBuffer = 1;
            for (let i = 0; i < Config.chipNoiseLength; i++) {
                wave[i] = (drumBuffer & 1) * 2.0 - 1.0;
                let newBuffer = drumBuffer >> 1;
                if (((drumBuffer + newBuffer) & 1) == 1) {
                    newBuffer += 10 << 2;
                }
                drumBuffer = newBuffer;
            }
        }
        else if (index == 4) {
            drawNoiseSpectrum(wave, 10, 11, 1, 1, 0);
            drawNoiseSpectrum(wave, 11, 14, .6578, .6578, 0);
            beepbox.inverseRealFourierTransform(wave, Config.chipNoiseLength);
            beepbox.scaleElementsByFactor(wave, 1.0 / Math.sqrt(Config.chipNoiseLength));
        }
        else if (index == 5) {
            var drumBuffer = 1;
            for (var i = 0; i < Config.chipNoiseLength; i++) {
                wave[i] = (drumBuffer & 1) * 2.0 - 1.0;
                var newBuffer = drumBuffer >> 1;
                if (((drumBuffer + newBuffer) & 1) == 1) {
                    newBuffer += 10 << 2;
                }
                drumBuffer = newBuffer;
            }
        }
        else if (index == 6) {
            drawNoiseSpectrum(wave, 1, 10, 1, 1, 0);
            drawNoiseSpectrum(wave, 20, 14, -2, -2, 0);
            beepbox.inverseRealFourierTransform(wave, Config.chipNoiseLength);
            beepbox.scaleElementsByFactor(wave, 1.0 / Math.sqrt(Config.chipNoiseLength));
        }
        else if (index == 7) {
            var drumBuffer = 1;
            for (var i = 0; i < Config.chipNoiseLength; i++) {
                wave[i] = (drumBuffer & 1) * 4.0 * (Math.random() * 14 + 1);
                var newBuffer = drumBuffer >> 1;
                if (((drumBuffer + newBuffer) & 1) == 1) {
                    newBuffer += 15 << 2;
                }
                drumBuffer = newBuffer;
            }
        }
        else if (index == 8) {
            var drumBuffer = 1;
            for (var i = 0; i < 32768; i++) {
                wave[i] = (drumBuffer & 1) / 2.0 + 0.5;
                var newBuffer = drumBuffer >> 1;
                if (((drumBuffer + newBuffer) & 1) == 1) {
                    newBuffer -= 10 << 2;
                }
                drumBuffer = newBuffer;
            }
        }
        else {
            throw new Error("Unrecognized drum index: " + index);
        }
        wave[Config.chipNoiseLength] = wave[0];
    }
    return wave;
}
beepbox.getDrumWave = getDrumWave;
function drawNoiseSpectrum(wave, lowOctave, highOctave, lowPower, highPower, overallSlope) {
    const referenceOctave = 11;
    const referenceIndex = 1 << referenceOctave;
    const lowIndex = Math.pow(2, lowOctave) | 0;
    const highIndex = Math.min(Config.chipNoiseLength >> 1, Math.pow(2, highOctave) | 0);
    const retroWave = getDrumWave(0);
    let combinedAmplitude = 0.0;
    for (let i = lowIndex; i < highIndex; i++) {
        let lerped = lowPower + (highPower - lowPower) * (Math.log(i) / Math.LN2 - lowOctave) / (highOctave - lowOctave);
        let amplitude = Math.pow(2, (lerped - 1) * Config.spectrumMax + 1) * lerped;
        amplitude *= Math.pow(i / referenceIndex, overallSlope);
        combinedAmplitude += amplitude;
        amplitude *= retroWave[i];
        const radians = 0.61803398875 * i * i * Math.PI * 2.0;
        wave[i] = Math.cos(radians) * amplitude;
        wave[Config.chipNoiseLength - i] = Math.sin(radians) * amplitude;
    }
    return combinedAmplitude;
}
beepbox.drawNoiseSpectrum = drawNoiseSpectrum;
function generateSineWave() {
    const wave = new Float64Array(Config.sineWaveLength + 1);
    for (let i = 0; i < Config.sineWaveLength + 1; i++) {
        wave[i] = Math.sin(i * Math.PI * 2.0 / Config.sineWaveLength);
    }
    return wave;
}
function toNameMap(array) {
    const dictionary = {};
    for (let i = 0; i < array.length; i++) {
        const value = array[i];
        value.index = i;
        dictionary[value.name] = value;
    }
    const result = array;
    result.dictionary = dictionary;
    return result;
}
beepbox.toNameMap = toNameMap;


beepbox.Synth = Synth;

module.exports = {
    getBuffer: exportToWav,
    "classes": beepbox.Synth
}