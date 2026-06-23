// Source: typeless_src/dist/renderer/static/js/C_80p6cs.js (99 lines)
// Typeless AudioWorklet processor - UNOBFUSCATED original source
// Processing: Float32Array, 1024 samples/batch, port.postMessage
// ================================================================

1|/* global AudioWorkletProcessor, registerProcessor */
2|
3|const PROCESSOR_NAME = 'typeless-audio-capture'
4|const SAMPLES_PER_MESSAGE = 1024
5|
6|class TypelessAudioCaptureProcessor extends AudioWorkletProcessor {
7|  constructor() {
8|    super()
9|
10|    this.recording = false
11|    this.pendingSamples = new Float32Array(SAMPLES_PER_MESSAGE)
12|    this.pendingSampleCount = 0
13|
14|    this.dataMessage = {
15|      type: 'recording:data',
16|      samples: null,
17|    }
18|    this.port.onmessage = (event) => {
19|      const message = event.data
20|
21|      if (message?.type === 'recording:start') {
22|        this.startRecording()
23|        return
24|      }
25|
26|      if (message?.type === 'recording:stop') {
27|        this.recording = false
28|        this.flushPendingSamples()
29|        this.port.postMessage({
30|          type: 'recording:stopped',
31|        })
32|        this.pendingSampleCount = 0
33|      }
34|    }
35|  }
36|
37|  startRecording() {
38|    this.pendingSampleCount = 0
39|    this.recording = true
40|  }
41|
42|  flushPendingSamples() {
43|    if (this.pendingSampleCount === 0) {
44|      return
45|    }
46|
47|    const samples = new Float32Array(this.pendingSampleCount)
48|    for (let i = 0; i < this.pendingSampleCount; i += 1) {
49|      samples[i] = this.pendingSamples[i]
50|    }
51|    this.pendingSampleCount = 0
52|
53|    this.dataMessage.samples = samples
54|    this.port.postMessage(this.dataMessage, [samples.buffer])
55|    this.dataMessage.samples = null
56|  }
57|
58|  appendSamples(channel) {
59|    let readOffset = 0
60|
61|    while (readOffset < channel.length) {
62|      const availableSpace = SAMPLES_PER_MESSAGE - this.pendingSampleCount
63|      const samplesToCopy = Math.min(
64|        availableSpace,
65|        channel.length - readOffset,
66|      )
67|
68|      for (let i = 0; i < samplesToCopy; i += 1) {
69|        this.pendingSamples[this.pendingSampleCount + i] =
70|          channel[readOffset + i]
71|      }
72|
73|      this.pendingSampleCount += samplesToCopy
74|      readOffset += samplesToCopy
75|
76|      if (this.pendingSampleCount === SAMPLES_PER_MESSAGE) {
77|        this.flushPendingSamples()
78|      }
79|    }
80|  }
81|
82|  process(inputs) {
83|    if (!this.recording) {
84|      return true
85|    }
86|
87|    const input = inputs[0]
88|    const channel = input && input[0]
89|    if (!channel || channel.length === 0) {
90|      return true
91|    }
92|
93|    this.appendSamples(channel)
94|
95|    return true
96|  }
97|}
98|
99|registerProcessor(PROCESSOR_NAME, TypelessAudioCaptureProcessor)
100|