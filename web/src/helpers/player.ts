import type EventEmitter from 'eventemitter3'
import { nanoid } from 'nanoid'

import { PlayerEventTypes } from '../interface/eventType'
import { getAudioContext } from './audioContext'
interface IOption {
  channels: number
  // analyserNode fftSize
  fftSize: number
  // Sample encoding of the input data
  inputCodec: 'Int8' | 'Int16' | 'Int32' | 'Float32'
  onended: (extParams?: IExtInfo) => void
  // Hz
  sampleRate: number
  isMute: boolean
}
interface ITypedArrays {
  Float32: typeof Float32Array
  Int16: typeof Int16Array
  Int32: typeof Int32Array
  Int8: typeof Int8Array
}
type IExtInfo = Record<string, unknown>
interface ISamples {
  data: Float32Array
  end_of_batch: boolean
  startTime?: number
}
export class Player {
  static isTypedArray(data: Int8Array | Int16Array | Int32Array | Float32Array) {
    // Is the input a TypedArray or an ArrayBuffer?
    return (
      (data.byteLength && data.buffer && data.buffer.constructor === ArrayBuffer) ||
      data.constructor === ArrayBuffer
    )
  }
  id = nanoid()
  analyserNode?: AnalyserNode
  audioCtx?: AudioContext
  // Autoplay
  autoPlay = true
  bufferSource?: AudioBufferSourceNode
  convertValue = 32768
  ee: EventEmitter
  gainNode?: GainNode
  option: IOption = {
    inputCodec: 'Int16', // Sample encoding of the input data (default 16-bit)
    channels: 1, // Channel count
    sampleRate: 8000, // Sample rate in Hz
    fftSize: 2048, // analyserNode fftSize
    onended: () => {},
    isMute: false,
  }
  samplesList: ISamples[] = []
  sources: AudioBufferSourceNode[] = []

  startTime?: number
  typedArray?: typeof Int8Array | typeof Int16Array | typeof Int32Array | typeof Float32Array

  _firstStartRelativeTime?: number
  _firstStartAbsoluteTime?: number

  constructor(option: IOption, ee: EventEmitter) {
    this.ee = ee
    this.init(option)
  }

  async continue() {
    await this.audioCtx!.resume()
  }
  destroy() {
    // BwithU: the AudioContext is shared, so silence this player instead of closing the context.
    this.samplesList = []
    this.sources.forEach((src) => {
      try {
        src.onended = null
        src.stop()
      } catch {
        // already stopped
      }
    })
    this.sources = []
    this.gainNode?.disconnect()
    this.audioCtx = undefined
  }
  feed(audioOptions: {
    audio: Int8Array | Int16Array | Int32Array | Float32Array
    end_of_batch: boolean
  }) {
    let { audio } = audioOptions
    const { end_of_batch } = audioOptions
    if (!audio) {
      return
    }
    this._isSupported(audio)
    // Format the incoming buffer
    audio = this._getFormattedValue(audio)
    // Copy the buffer data
    // into a new Float32Array
    const data = new Float32Array(audio.length)
    // copy the new data in
    // after the existing samples
    data.set(audio, 0)
    // and store the combined buffer as samples
    const samples = {
      data,
      end_of_batch,
    }
    this.samplesList.push(samples)
    this.flush(samples, this.samplesList.length - 1)
  }
  flush(samples: ISamples, index: number) {
    if (!(samples && this.autoPlay && this.audioCtx)) return
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume()
    }
    const { data, end_of_batch } = samples
    if (this.bufferSource) {
      this.bufferSource.onended = () => {}
    }
    this.bufferSource = this.audioCtx!.createBufferSource()
    if (typeof this.option.onended === 'function') {
      this.bufferSource.onended = () => {
        if (!end_of_batch && index === this.samplesList.length - 1) {
          this.ee.emit(PlayerEventTypes.Player_WaitNextAudioClip)
        }
        this.option.onended()
      }
    }
    const length = data.length / this.option.channels
    const audioBuffer = this.audioCtx!.createBuffer(
      this.option.channels,
      length,
      this.option.sampleRate
    )

    for (let channel = 0; channel < this.option.channels; channel++) {
      const audioData = audioBuffer.getChannelData(channel)
      let offset = channel
      let decrement = 50
      for (let i = 0; i < length; i++) {
        audioData[i] = data[offset]
        /* fadein */
        if (i < 50) {
          audioData[i] = (audioData[i] * i) / 50
        }
        /* fadeout */
        if (i >= length - 51) {
          audioData[i] = (audioData[i] * decrement--) / 50
        }
        offset += this.option.channels
      }
    }

    if (this.startTime! < this.audioCtx!.currentTime) {
      this.startTime = this.audioCtx!.currentTime
    }
    this.bufferSource.buffer = audioBuffer
    this.bufferSource.connect(this.gainNode!)
    this.bufferSource.connect(this.analyserNode!)
    this.bufferSource.start(this.startTime)
    this.sources.push(this.bufferSource)
    samples.startTime = this.startTime
    if (this._firstStartAbsoluteTime === undefined) {
      this._firstStartAbsoluteTime = Date.now()
    }
    if (this._firstStartRelativeTime === undefined) {
      this._firstStartRelativeTime = this.startTime
      this.ee.emit(PlayerEventTypes.Player_StartSpeaking, this)
    }
    this.startTime! += audioBuffer.duration
  }
  init(option: IOption) {
    this.option = Object.assign(this.option, option) // Final options for this instance
    this.convertValue = this._getConvertValue()
    this.typedArray = this._getTypedArray()
    this.initAudioContext()
  }
  initAudioContext() {
    // Set up the audio context
    this.audioCtx = getAudioContext()
    // GainNode for volume
    // https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/createGain
    this.gainNode = this.audioCtx.createGain()
    this.gainNode.gain.value = this.option.isMute ? 0 : 1
    this.gainNode.connect(this.audioCtx.destination)
    this.startTime = this.audioCtx.currentTime
    this.analyserNode = this.audioCtx.createAnalyser()
    this.analyserNode.fftSize = this.option.fftSize
  }
  setMute(isMute: boolean) {
    this.gainNode!.gain.value = isMute ? 0 : 1
  }
  async pause() {
    await this.audioCtx!.suspend()
  }
  async updateAutoPlay(value: boolean) {
    if (this.autoPlay !== value && value) {
      this.autoPlay = value
      this.samplesList.forEach((sample, index) => {
        this.flush(sample, index)
      })
    } else {
      this.autoPlay = value
    }
  }

  volume(volume: number) {
    this.gainNode!.gain.value = volume
  }
  _getFormattedValue(data: Int8Array | Int16Array | Int32Array | Float32Array) {
    const TargetArray = this.typedArray!
    if (data.constructor === ArrayBuffer) {
      data = new TargetArray(data)
    } else {
      data = new TargetArray(data.buffer as ArrayBuffer)
    }

    const float32 = new Float32Array(data.length)

    for (let i = 0; i < data.length; i++) {
      // AudioBuffer data must be 32-bit linear PCM (IEEE 754) in -1..+1,
      // so divide each sample
      // by the range of its bit depth.
      // float32[i] = data[i] / 0x8000;
      float32[i] = data[i] / this.convertValue
    }
    return float32
  }

  private _isSupported(data: Int8Array | Int16Array | Int32Array | Float32Array) {
    // Only ArrayBuffer or a TypedArray is supported
    if (!Player.isTypedArray(data)) throw new Error('Expected an ArrayBuffer or a TypedArray')
    return true
  }

  private _getConvertValue() {
    // Pick the base value for the conversion
    // from the input bit depth
    const inputCodecs = {
      Int8: 128,
      Int16: 32768,
      Int32: 2147483648,
      Float32: 1,
    }
    if (!inputCodecs[this.option.inputCodec])
      throw new Error('wrong codec.please input one of these codecs:Int8,Int16,Int32,Float32')
    return inputCodecs[this.option.inputCodec]
  }

  private _getTypedArray() {
    // Pick the TypedArray that matches
    // the input bit depth
    // https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/TypedArray
    const typedArrays: ITypedArrays = {
      Int8: Int8Array,
      Int16: Int16Array,
      Int32: Int32Array,
      Float32: Float32Array,
    }
    if (!typedArrays[this.option.inputCodec])
      throw new Error('wrong codec.please input one of these codecs:Int8,Int16,Int32,Float32')
    return typedArrays[this.option.inputCodec]
  }
}
