// Source: typeless_src/cracked_float/deobfuscated.js, lines 5861-7500
// Typeless float bar XState state machine COMPLETE DEFINITION
// States: idle → starting-microphone → recording_active (sub: pushToTalk/handsFree/translationModeHandsFree)
//         → stopping → done → error (FATAL/RECOVERABLE)
// Events: RECORD.START, RECORD.STOP, RECORD.STOP_COMPLETE, RECORD.RETRY_HISTORY,
//         CLICK.CANCEL_BUTTON, WEBSOCKET.SEND_AUDIO_CHUNK, etc.
// Actions: assignEscapeRecording, hideFloatingBarAlert, clearError, startRecording,
//          clearAudioId, updateTimer, etc.
// Guards: isAuthorized, hasRecordingResult, etc.
// This is the COMPLETE machine — every state, transition, guard, and action.
5861|    hideFloatingBarAlert: () => {
5862|      _0x4037c7();
5863|    },
5864|    hideTranslationModeAlert: () => {
5865|      _0x4037c7("showTranslationModeAlert");
5866|    },
5867|    showDictateBrandAlertAction: ({
5868|      context: _0x27441e
5869|    }) => {
5870|      _0x27441e.mode;
5871|      _0xa42a3b.VOICE_TRANSCRIPT;
5872|    },
5873|    hideDictateBrandAlertAction: () => {
5874|      _0x4037c7("showDictateBrandAlert");
5875|    },
5876|    showAskAnythingAlertAction: async ({
5877|      context: _0x13f2cc
5878|    }) => {
5879|      if (_0x13f2cc.mode === _0xa42a3b.VOICE_COMMAND) {
5880|        _0x47d2b2();
5881|      }
5882|    },
5883|    hideAskAnythingAlertAction: () => {
5884|      _0x4037c7("showAskAnythingAlert");
5885|    },
5886|    showPressToStopDictationOnboardingAction: ve(({
5887|      context: _0x5c73ad,
5888|      self: _0x17e636
5889|    }) => {
5890|      const _0x1fa3a9 = _0x17e636.getSnapshot().matches("recording_active.pushToTalk");
5891|      const _0x5acd6c = new BroadcastChannel("recording-machine");
5892|      _0x5acd6c.postMessage({
5893|        type: "showPressToStopOnboarding",
5894|        mode: _0x5c73ad.mode,
5895|        isPushToTalkMode: _0x1fa3a9
5896|      });
5897|      _0x5acd6c.close();
5898|    }),
5899|    hidePressToStopDictationOnboardingAction: () => {
5900|      _0x4037c7("showPressToStopDictationOnboardingAlert");
5901|    },
5902|    showDoNotHoldJustPressAlertAction: ve(() => {
5903|      _0x969c94("showDoNotHoldJustPressAlert");
5904|    }),
5905|    hideDoNotHoldJustPressAlertAction: () => {
5906|      _0x1e311f("showDoNotHoldJustPressAlert");
5907|    },
5908|    checkTranslationModeAvailable: ve(({
5909|      context: _0x2ef352,
5910|      self: _0x152a3a
5911|    }) => {
5912|      _0x3f4957("app-settings", "translationModeTargetLanguageCode").then(_0x2de830 => {
5913|        if (!_0x2de830) {
5914|          _0x152a3a.send({
5915|            type: "ERROR.FATAL",
5916|            data: "FATAL_NOT_SET_TARGET_TRANSLATION_LANGUAGE"
5917|          });
5918|        }
5919|      }).catch(() => {
5920|        _0x152a3a.send({
5921|          type: "ERROR.FATAL",
5922|          data: "FATAL_NOT_SET_TARGET_TRANSLATION_LANGUAGE"
5923|        });
5924|      });
5925|    }),
5926|    showTranslationModeAlert: _0x5ae6cf,
5927|    checkTranslationModeOnboardingAlert: ({
5928|      context: _0x16c93e
5929|    }) => {
5930|      _0x4ee659().then(_0x5b3ab4 => {
5931|        if (_0x5b3ab4 && _0x16c93e.mode !== _0xa42a3b.VOICE_TRANSLATION) {
5932|          _0xb0f524();
5933|        }
5934|      });
5935|      _0x40aba3();
5936|    },
5937|    resetDictationModeToVoiceTranscription: O({
5938|      mode: () => _0xa42a3b.VOICE_TRANSCRIPT
5939|    }),
5940|    assignDictationMode: O({
5941|      mode: ({
5942|        event: _0x5ca29f,
5943|        context: _0x59b14b
5944|      }) => _0x5ca29f.type === "DICTATION_MODE_TYPES.SET_MODE" ? _0x5ca29f.mode : _0x5ca29f.type === "DICTATION_MODE_TYPES.RESET_TO_VOICE_TRANSCRIPT" ? _0xa42a3b.VOICE_TRANSCRIPT : _0x59b14b.mode
5945|    }),
5946|    socketSendStartAudioMessage: Z("webSocket", ({
5947|      context: _0x2389ac
5948|    }) => {
5949|      var _0x1517f0;
5950|      var _0x150071;
5951|      var _0x18dc44;
5952|      var _0x156df4;
5953|      var _0x253efe;
5954|      var _0x43c979;
5955|      const _0x583162 = {
5956|        audio_duration: _t() / 1000,
5957|        audio_format: "wav",
5958|        audio_bitrate: ((_0x1517f0 = _0x2389ac.recorderState) == null ? undefined : _0x1517f0.audioRecorderOptions.encoderBitRate) || 64000,
5959|        audio_channels: ((_0x150071 = _0x2389ac.recorderState) == null ? undefined : _0x150071.audioRecorderOptions.numberOfChannels) || 1,
5960|        audio_sample_rate: ((_0x156df4 = (_0x18dc44 = _0x2389ac.recorderState) == null ? undefined : _0x18dc44.audioContext) == null ? undefined : _0x156df4.sampleRate) || _0x2adabe,
5961|        audio_codec: "pcm",
5962|        audio_variable_bitrate: false,
5963|        audio_bit_depth: ((_0x253efe = _0x2389ac.recorderState) == null ? undefined : _0x253efe.audioRecorderOptions.wavBitDepth) || 16,
5964|        need_merge: true
5965|      };
5966|      return {
5967|        type: "WEBSOCKET.SEND_VOICE_MESSAGE",
5968|        message: {
5969|          type: _0x110eca.START_AUDIO,
5970|          audio_chunk_time: _0x583162.audio_duration,
5971|          audio_sample_rate: _0x583162.audio_sample_rate,
5972|          audio_metadata: _0x583162,
5973|          device_id: (_0x43c979 = _0x2389ac.recorderState) == null ? undefined : _0x43c979.deviceId,
5974|          mode: _0x2389ac.mode
5975|        }
5976|      };
5977|    }),
5978|    socketSendEndAudioMessage: Z("webSocket", ({
5979|      event: _0x4be03a,
5980|      context: _0x2878ed
5981|    }) => {
5982|      if (_0x4be03a.type === "RECORD.STOP_COMPLETE" && _0x4be03a.result) {
5983|        const {
5984|          allRecordingTime: _0x541eb7,
5985|          startRecordingTime: _0x7853d8,
5986|          stopRecordingTime: _0x472f16,
5987|          currentStartTime: _0x218af5,
5988|          userOverTime: _0x1036f1
5989|        } = _0x4be03a.result;
5990|        return {
5991|          type: "WEBSOCKET.SEND_VOICE_MESSAGE",
5992|          message: {
5993|            type: _0x110eca.END_AUDIO,
5994|            user_over_time: _0x1036f1,
5995|            send_time: Date.now(),
5996|            audio_time: _0x541eb7 + "s",
5997|            total_duration: _0x541eb7,
5998|            start_recording_time: _0x7853d8,
5999|            stop_recording_time: _0x472f16,
6000|            diff: Date.now() - _0x218af5 + "ms",
6001|            mode: _0x2878ed.mode
6002|          }
6003|        };
6004|      }
6005|      return {
6006|        type: "WEBSOCKET.SEND_VOICE_MESSAGE",
6007|        message: {
6008|          type: _0x110eca.END_AUDIO
6009|        }
6010|      };
6011|    }),
6012|    socketSendAudioChunk: ve(({
6013|      event: _0x205825,
6014|      context: _0x42b418,
6015|      enqueue: _0x2489ee
6016|    }) => {
6017|      if (_0x42b418.recorderState) {
6018|        if (_0x205825.type === "RECORD.STOP_COMPLETE" && _0x205825.result) {
6019|          _0x2489ee(Z("webSocket", {
6020|            type: "WEBSOCKET.SEND_AUDIO_CHUNK",
6021|            blob: _0x205825.result.currentAudioBlob
6022|          }));
6023|        } else {
6024|          let _0x3d8ab0 = 20;
6025|          const _0x392880 = _t();
6026|          while (_0x3d8ab0 > 0) {
6027|            _0x3d8ab0 -= 1;
6028|            try {
6029|              const _0x305930 = _0x42b418.recorderState.getCurrentAudioBlob({
6030|                durationTime: _0x392880
6031|              });
6032|              if (_0x305930) {
6033|                _0x2489ee(Z("webSocket", {
6034|                  type: "WEBSOCKET.SEND_AUDIO_CHUNK",
6035|                  blob: _0x305930
6036|                }));
6037|              } else {
6038|                break;
6039|              }
6040|            } catch {
6041|              break;
6042|            }
6043|          }
6044|          const _0x453443 = 20 - _0x3d8ab0;
6045|          if (_0x453443 > 3) {
6046|            window.ipcRenderer.invoke("mixpanel:track-event", {
6047|              eventKey: "error_monitoring_audio_chunk_backlog",
6048|              data: {
6049|                trigger_event_type: _0x205825.type,
6050|                backlog_count: _0x453443,
6051|                backlog_duration_ms: _0x453443 * _0x392880
6052|              }
6053|            });
6054|          }
6055|        }
6056|      }
6057|    }),
6058|    reconnectSocket: Z("webSocket", ({
6059|      context: _0x3c311a
6060|    }) => {
6061|      var _0x676cb3;
6062|      var _0x46c1e0;
6063|      return {
6064|        type: "WEBSOCKET.RECONNECT",
6065|        userToken: ((_0x46c1e0 = (_0x676cb3 = _0x3c311a.stateInput) == null ? undefined : _0x676cb3.authChecker) == null ? undefined : _0x46c1e0.userToken) || ""
6066|      };
6067|    }),
6068|    disconnectSocket: Z("webSocket", () => ({
6069|      type: "WEBSOCKET.DISCONNECT"
6070|    })),
6071|    assignFatalError: O({
6072|      error: ({
6073|        event: _0x349b92
6074|      }) => {
6075|        var _0x13943a;
6076|        if (_0x349b92.type === "ERROR.FATAL" && "data" in _0x349b92) {
6077|          return _0x349b92.data;
6078|        } else {
6079|          return ((_0x13943a = _0x349b92 == null ? undefined : _0x349b92.error) == null ? undefined : _0x13943a.message) || "unknown fatal error";
6080|        }
6081|      },
6082|      errorType: () => "fatal",
6083|      onStopTarget: "failure"
6084|    }),
6085|    assignRecoverableError: O({
6086|      onStopTarget: "error",
6087|      error: ({
6088|        event: _0x49ea00
6089|      }) => {
6090|        var _0x130b26;
6091|        if (_0x49ea00.type === "ERROR.RECOVERABLE" && "data" in _0x49ea00) {
6092|          return _0x49ea00.data;
6093|        } else {
6094|          return ((_0x130b26 = _0x49ea00 == null ? undefined : _0x49ea00.error) == null ? undefined : _0x130b26.message) || "unknown recoverable error";
6095|        }
6096|      },
6097|      errorType: () => "recoverable"
6098|    }),
6099|    assignInitializationResult: O(({
6100|      event: _0x587de3
6101|    }) => ({
6102|      isLoggedIn: _0x587de3.output.isLoggedIn,
6103|      error: null,
6104|      errorType: null
6105|    })),
6106|    clearError: O({
6107|      error: () => null,
6108|      errorType: () => null
6109|    }),
6110|    clearOnStopTarget: O({
6111|      onStopTarget: () => null
6112|    }),
6113|    handleFatalError: ({
6114|      context: _0x4edb6e
6115|    }) => {
6116|      if (_0x4edb6e.errorType === "fatal") {
6117|        if (_0x4edb6e.error === "FATAL_MICROPHONE_PERMISSION_REQUIRED") {
6118|          _0x1d4c74();
6119|        } else if (_0x4edb6e.error === "FATAL_ACCESSIBILITY_PERMISSION_REQUIRED") {
6120|          _0x27c50d();
6121|        } else if (_0x4edb6e.error === "FATAL_NOT_INTERNET_CONNECTED") {
6122|          _0x346438();
6123|        } else if (_0x4edb6e.error === "FATAL_POOR_INTERNET_CONNECTED") {
6124|          _0x1a8560();
6125|        } else if (_0x4edb6e.error === "FATAL_TRANSCRIPTION_TIMEOUT") {
6126|          _0x4b7c8d();
6127|        } else if (_0x4edb6e.error === "FATAL_NOT_SET_TARGET_TRANSLATION_LANGUAGE") {
6128|          _0x4f53e7();
6129|        } else {
6130|          _0x5d884e(async () => {}, _0x4edb6e.error || "");
6131|        }
6132|      }
6133|    },
6134|    handleRecoverableError: ({
6135|      context: _0x5f3057
6136|    }) => {
6137|      if (_0x5f3057.errorType === "recoverable") {
6138|        if (_0x5f3057.error === "RECOVERABLE_NOT_LOGGED_IN") {
6139|          _0x4cd956();
6140|        } else if (_0x5f3057.error === "RECOVERABLE_NO_SPEECH_DETECTED") {
6141|          _0xe9c01c();
6142|        }
6143|      }
6144|    },
6145|    assignSocketIdleTimer: O(({
6146|      event: _0xc948ca
6147|    }) => _0xc948ca.type === "RECORD.COUNTDOWN_UPDATE" ? {
6148|      recorderTimeoutState: {
6149|        timeUntilCountdown: _0xc948ca.data.timeUntilCountdown || 0,
6150|        remainingTime: _0xc948ca.data.remainingTime || 0
6151|      }
6152|    } : {
6153|      recorderTimeoutState: {
6154|        timeUntilCountdown: 0,
6155|        remainingTime: 0
6156|      }
6157|    }),
6158|    showFinishingAlert: ({
6159|      event: _0x27b8da,
6160|      self: _0x31bd2b
6161|    }) => {
6162|      _0x1eb623(async () => {
6163|        _0x31bd2b.send({
6164|          type: "ESC"
6165|        });
6166|      });
6167|    },
6168|    showHandsFreeModeAlert: () => {
6169|      _0x451a79();
6170|    },
6171|    assignAudioId: O(({
6172|      event: _0x160b6c,
6173|      context: _0x189964
6174|    }) => _0x160b6c.type === "WEBSOCKET.UPDATE_AUDIO_ID" ? {
6175|      audioId: _0x160b6c.audioId || _0x189964.audioId
6176|    } : {
6177|      audioId: _0x189964.audioId
6178|    }),
6179|    clearAudioId: O({
6180|      audioId: undefined
6181|    }),
6182|    assignIsFinishing: O({
6183|      isFinishing: true
6184|    }),
6185|    clearIsFinishing: O({
6186|      isFinishing: false
6187|    }),
6188|    assignEscapeRecording: O({
6189|      isEscapeRecording: true
6190|    }),
6191|    clearEscapeRecording: O({
6192|      isEscapeRecording: false
6193|    })
6194|  },
6195|  guards: {
6196|    isRecording: ({
6197|      context: _0xa3b2e7
6198|    }) => {
6199|      var _0x200208;
6200|      return ((_0x200208 = _0xa3b2e7.recorderState) == null ? undefined : _0x200208.isRecording) === true;
6201|    },
6202|    hasDetectedSilence: ({
6203|      event: _0x53940f
6204|    }) => _0x53940f.type === "VOLUME.DETECTION_COMPLETE" && !_0x53940f.result.detected,
6205|    isRecoverableError: ({
6206|      event: _0x471019
6207|    }) => {
6208|      const _0x8d9686 = _0x471019.error;
6209|      return _0x8d9686 && _0x8d9686.message && _0x8d9686.message.includes("RECOVERABLE");
6210|    }
6211|  }
6212|}).createMachine({
6213|  id: "recording",
6214|  initial: "idle",
6215|  context: _0x298e05 => ({
6216|    isFinishing: false,
6217|    isEscapeRecording: false,
6218|    error: null,
6219|    errorType: null,
6220|    recorderState: null,
6221|    socketIdleTimer: null,
6222|    recorderTimeoutState: null,
6223|    timeUntilCountdown: 0,
6224|    isLoggedIn: false,
6225|    stateInput: _0x298e05.input,
6226|    onStopTarget: null,
6227|    mode: _0xa42a3b.VOICE_TRANSCRIPT
6228|  }),
6229|  invoke: [{
6230|    id: "audioRecorder",
6231|    src: "audioRecorderActor",
6232|    input: () => ({})
6233|  }, {
6234|    id: "webSocket",
6235|    src: "webSocketActor",
6236|    input: ({
6237|      context: _0x29725c
6238|    }) => {
6239|      var _0x16500c;
6240|      var _0x1d61b0;
6241|      return {
6242|        userToken: ((_0x1d61b0 = (_0x16500c = _0x29725c.stateInput) == null ? undefined : _0x16500c.authChecker) == null ? undefined : _0x1d61b0.userToken) || ""
6243|      };
6244|    }
6245|  }, {
6246|    id: "volumeDetector",
6247|    src: "volumeDetectorActor",
6248|    input: () => ({})
6249|  }],
6250|  on: {
6251|    "SESSION.INTERRUPT_AND_RESET": {
6252|      target: ".stopping",
6253|      actions: [O({
6254|        onStopTarget: "idle"
6255|      }), "clearError", "clearIsFinishing", Z("webSocket", {
6256|        type: "WEBSOCKET.CLEAR_AUDIO_ID"
6257|      })]
6258|    },
6259|    "DICTATION_MODE_TYPES.SET_MODE": {
6260|      actions: "assignDictationMode"
6261|    },
6262|    "DICTATION_MODE_TYPES.RESET_TO_VOICE_TRANSCRIPT": {
6263|      actions: "assignDictationMode"
6264|    },
6265|    ESC: {
6266|      target: ".stopping",
6267|      actions: ["assignEscapeRecording", "hideFloatingBarAlert", "clearError", O({
6268|        onStopTarget: "idle"
6269|      })]
6270|    },
6271|    "ERROR.FATAL": {
6272|      target: ".stopping",
6273|      actions: "assignFatalError"
6274|    },
6275|    "ERROR.RECOVERABLE": {
6276|      target: ".stopping",
6277|      actions: "assignRecoverableError"
6278|    },
6279|    "RECORD.STATE_UPDATE": {
6280|      actions: "setRecordingState"
6281|    },
6282|    "RECORD.TIMEOUT_STATE_UPDATE": {
6283|      actions: "setRecordingTimeoutState"
6284|    },
6285|    "WEBSOCKET.UPDATE_AUDIO_ID": {
6286|      actions: "assignAudioId"
6287|    },
6288|    "WEBSOCKET.CLEAR_AUDIO_ID": {
6289|      actions: Z("webSocket", {
6290|        type: "WEBSOCKET.CLEAR_AUDIO_ID"
6291|      })
6292|    },
6293|    FORWARD_TO_RECORDER: {
6294|      actions: Z("audioRecorder", ({
6295|        event: _0x568eb6
6296|      }) => {
6297|        if (_0x568eb6.type === "FORWARD_TO_RECORDER") {
6298|          return _0x568eb6.actor_data;
6299|        }
6300|      })
6301|    },
6302|    RETRY_AUDIO: {
6303|      target: ".retrying"
6304|    },
6305|    UPDATE_STATE_INPUT: {
6306|      actions: [O({
6307|        stateInput: ({
6308|          event: _0x193b00
6309|        }) => _0x193b00.stateInput
6310|      }), "reconnectSocket"]
6311|    },
6312|    "INITIALIZATION.AUTH_REQUIRED": {
6313|      target: ".stopping",
6314|      actions: ["clearAudioId", "clearError", O({
6315|        onStopTarget: "idle"
6316|      })]
6317|    }
6318|  },
6319|  states: {
6320|    idle: {
6321|      entry: [({
6322|        event: _0x10df68
6323|      }) => {}, Z("webSocket", {
6324|        type: "WEBSOCKET.CLEAR_AUDIO_ID"
6325|      })],
6326|      invoke: [{
6327|        id: "socketIdleTimer",
6328|        src: "socketIdleTimer"
6329|      }],
6330|      on: {
6331|        "PRIMARY_KEY.DOWN": {
6332|          target: "initializingForTapOrHold",
6333|          actions: O({
6334|            mode: _0xa42a3b.VOICE_TRANSCRIPT
6335|          })
6336|        },
6337|        "HANDSFREE_KEY.DOWN": {
6338|          target: "initializingForHandsFree",
6339|          actions: O({
6340|            mode: _0xa42a3b.VOICE_COMMAND
6341|          })
6342|        },
6343|        "TRANSLATION_KEY.DOWN": {
6344|          target: "initializingForTranslation",
6345|          actions: O({
6346|            mode: _0xa42a3b.VOICE_TRANSLATION
6347|          })
6348|        },
6349|        "CLICK.HANDSFREE_BUTTON": {
6350|          target: "initializingForHandsFree"
6351|        },
6352|        SOCKET_IDLE_TIMEOUT: {
6353|          actions: "disconnectSocket"
6354|        }
6355|      }
6356|    },
6357|    initializingForTapOrHold: {
6358|      entry: ["clearAudioId", "startRecording", "hideFloatingBarAlert"],
6359|      invoke: {
6360|        id: "initialize",
6361|        src: "initializeRecording",
6362|        input: ({
6363|          context: _0xcc95c
6364|        }) => _0xcc95c.stateInput,
6365|        onDone: {
6366|          target: "awaiting_long_press_or_tap",
6367|          actions: "assignInitializationResult"
6368|        },
6369|        onError: [{
6370|          target: "stopping",
6371|          guard: "isRecoverableError",
6372|          actions: "assignRecoverableError"
6373|        }, {
6374|          target: "stopping",
6375|          actions: "assignFatalError"
6376|        }]
6377|      },
6378|      on: {
6379|        "WRONG_KEY.DOWN": {
6380|          target: "stopping",
6381|          actions: ["assignEscapeRecording", O({
6382|            onStopTarget: "idle"
6383|          })]
6384|        },
6385|        "HANDSFREE_KEY.DOWN": {
6386|          target: "initializingForHandsFree"
6387|        },
6388|        "TRANSLATION_KEY.DOWN": {
6389|          target: "initializingForTranslation",
6390|          actions: O({
6391|            mode: _0xa42a3b.VOICE_TRANSLATION
6392|          })
6393|        }
6394|      }
6395|    },
6396|    initializingForHandsFree: {
6397|      entry: ["clearAudioId", "startRecording", "hideFloatingBarAlert", O({
6398|        mode: _0xa42a3b.VOICE_COMMAND
6399|      })],
6400|      invoke: {
6401|        id: "initialize",
6402|        src: "initializeRecording",
6403|        input: ({
6404|          context: _0x9d9b67
6405|        }) => _0x9d9b67.stateInput,
6406|        onDone: {
6407|          target: "awaiting_long_press_or_tap",
6408|          actions: "assignInitializationResult"
6409|        },
6410|        onError: [{
6411|          target: "stopping",
6412|          guard: "isRecoverableError",
6413|          actions: "assignRecoverableError"
6414|        }, {
6415|          target: "stopping",
6416|          actions: "assignFatalError"
6417|        }]
6418|      }
6419|    },
6420|    initializingForTranslation: {
6421|      entry: ["clearAudioId", "startRecording", "hideFloatingBarAlert"],
6422|      invoke: {
6423|        id: "initialize",
6424|        src: "initializeRecording",
6425|        input: ({
6426|          context: _0x5a49cc
6427|        }) => _0x5a49cc.stateInput,
6428|        onDone: {
6429|          target: "awaiting_long_press_or_tap",
6430|          actions: "assignInitializationResult"
6431|        },
6432|        onError: [{
6433|          target: "stopping",
6434|          guard: "isRecoverableError",
6435|          actions: "assignRecoverableError"
6436|        }, {
6437|          target: "stopping",
6438|          actions: "assignFatalError"
6439|        }]
6440|      }
6441|    },
6442|    awaiting_long_press_or_tap: {
6443|      on: {
6444|        LONG_HOLD: {
6445|          target: "long_pressing"
6446|        },
6447|        "PRIMARY_KEY.DOWN": {
6448|          actions: O({
6449|            mode: _0xa42a3b.VOICE_TRANSCRIPT
6450|          })
6451|        },
6452|        "HANDSFREE_KEY.DOWN": {
6453|          actions: O({
6454|            mode: _0xa42a3b.VOICE_COMMAND
6455|          })
6456|        },
6457|        "TRANSLATION_KEY.DOWN": {
6458|          actions: O({
6459|            mode: _0xa42a3b.VOICE_TRANSLATION
6460|          })
6461|        },
6462|        "TRANSLATION_KEY.UP": [{
6463|          actions: O({
6464|            mode: _0xa42a3b.VOICE_TRANSLATION
6465|          }),
6466|          target: "recording_active.translationModeHandsFree"
6467|        }],
6468|        "PRIMARY_KEY.UP": [{
6469|          actions: O({
6470|            mode: _0xa42a3b.VOICE_TRANSCRIPT
6471|          }),
6472|          target: "recording_active.handsFree"
6473|        }],
6474|        "HANDSFREE_KEY.UP": [{
6475|          actions: O({
6476|            mode: _0xa42a3b.VOICE_COMMAND
6477|          }),
6478|          target: "recording_active.handsFree"
6479|        }],
6480|        "WRONG_KEY.DOWN": {
6481|          target: "stopping",
6482|          actions: ["assignEscapeRecording", O({
6483|            onStopTarget: "idle"
6484|          })]
6485|        }
6486|      }
6487|    },
6488|    long_pressing: {
6489|      entry: ["showDoNotHoldJustPressAlertAction", "stopRecording", Z("webSocket", {
6490|        type: "WEBSOCKET.CLEAR_AUDIO_ID"
6491|      })],
6492|      exit: ["hideDoNotHoldJustPressAlertAction"],
6493|      on: {
6494|        "PRIMARY_KEY.UP": {
6495|          target: "idle"
6496|        },
6497|        "HANDSFREE_KEY.UP": {
6498|          target: "idle"
6499|        },
6500|        "TRANSLATION_KEY.UP": {
6501|          target: "idle"
6502|        },
6503|        ESC: {
6504|          target: "idle"
6505|        }
6506|      }
6507|    },
6508|    recording_active: {
6509|      initial: "pushToTalk",
6510|      invoke: [{
6511|        id: "socketTickTimer",
6512|        src: "socketTickTimer"
6513|      }, {
6514|        id: "audioRecorderTimeoutActor",
6515|        src: "audioRecorderTimeoutActor"
6516|      }],
6517|      entry: ["socketSendStartAudioMessage"],
6518|      after: {
6519|        1000: {
6520|          actions: "startVolumeDetection"
6521|        }
6522|      },
6523|      on: {
6524|        "VOLUME.DETECTION_COMPLETE": {
6525|          guard: "hasDetectedSilence",
6526|          target: "stopping",
6527|          actions: O({
6528|            onStopTarget: "error",
6529|            errorType: "recoverable",
6530|            error: "RECOVERABLE_NO_SPEECH_DETECTED"
6531|          })
6532|        },
6533|        "VOLUME.DETECTION_ERROR": {
6534|          actions: ({
6535|            context: _0x5a431f,
6536|            event: _0x5d20e4
6537|          }) => {}
6538|        },
6539|        SOCKET_TICK: {
6540|          actions: "socketSendAudioChunk"
6541|        },
6542|        "RECORD.TIMEOUT": {
6543|          target: "stopping",
6544|          actions: O({
6545|            onStopTarget: "finishing"
6546|          })
6547|        }
6548|      },
6549|      states: {
6550|        pushToTalk: {
6551|          entry: [O({
6552|            mode: _0xa42a3b.VOICE_TRANSCRIPT
6553|          }), "checkTranslationModeOnboardingAlert", "showDoNotHoldJustPressAlertAction", "showDictateBrandAlertAction"],
6554|          after: {
6555|            [zs]: {
6556|              actions: "showPressToStopDictationOnboardingAction"
6557|            }
6558|          },
6559|          on: {
6560|            "PRIMARY_KEY.UP": {
6561|              target: "#recording.stopping",
6562|              actions: O({
6563|                onStopTarget: "finishing"
6564|              })
6565|            },
6566|            "HANDSFREE_KEY.DOWN": {
6567|              target: "#recording.stopping",
6568|              actions: O({
6569|                onStopTarget: "finishing"
6570|              })
6571|            },
6572|            "TRANSLATION_KEY.DOWN": {
6573|              target: "#recording.stopping",
6574|              actions: O({
6575|                onStopTarget: "finishing"
6576|              })
6577|            }
6578|          }
6579|        },
6580|        handsFree: {
6581|          entry: ["showAskAnythingAlertAction", "showDictateBrandAlertAction"],
6582|          after: {
6583|            [Xs]: {
6584|              actions: "showPressToStopDictationOnboardingAction"
6585|            }
6586|          },
6587|          on: {
6588|            "PRIMARY_KEY.DOWN": {
6589|              target: "#recording.stopping",
6590|              actions: O({
6591|                onStopTarget: "finishing"
6592|              })
6593|            },
6594|            "HANDSFREE_KEY.DOWN": {
6595|              target: "#recording.stopping",
6596|              actions: O({
6597|                onStopTarget: "finishing"
6598|              })
6599|            },
6600|            "TRANSLATION_KEY.DOWN": {
6601|              target: "#recording.stopping",
6602|              actions: O({
6603|                onStopTarget: "finishing"
6604|              })
6605|            },
6606|            "CLICK.FINISH_BUTTON": {
6607|              target: "#recording.stopping",
6608|              actions: O({
6609|                onStopTarget: "finishing"
6610|              })
6611|            },
6612|            "CLICK.CANCEL_BUTTON": {
6613|              target: "#recording.stopping",
6614|              actions: O({
6615|                onStopTarget: "idle"
6616|              })
6617|            }
6618|          }
6619|        },
6620|        translationModeHandsFree: {
6621|          entry: [O({
6622|            mode: _0xa42a3b.VOICE_TRANSLATION
6623|          }), "checkTranslationModeAvailable", "showTranslationModeAlert"],
6624|          after: {
6625|            [Js]: {
6626|              actions: "showPressToStopDictationOnboardingAction"
6627|            }
6628|          },
6629|          exit: [O({
6630|            mode: _0xa42a3b.VOICE_TRANSLATION
6631|          })],
6632|          on: {
6633|            "PRIMARY_KEY.DOWN": {
6634|              target: "#recording.stopping",
6635|              actions: O({
6636|                onStopTarget: "finishing"
6637|              })
6638|            },
6639|            "HANDSFREE_KEY.DOWN": {
6640|              target: "#recording.stopping",
6641|              actions: O({
6642|                onStopTarget: "finishing"
6643|              })
6644|            },
6645|            "TRANSLATION_KEY.DOWN": {
6646|              target: "#recording.stopping",
6647|              actions: O({
6648|                onStopTarget: "finishing"
6649|              })
6650|            },
6651|            "CLICK.FINISH_BUTTON": {
6652|              target: "#recording.stopping",
6653|              actions: O({
6654|                onStopTarget: "finishing"
6655|              })
6656|            },
6657|            "CLICK.CANCEL_BUTTON": {
6658|              target: "#recording.stopping",
6659|              actions: O({
6660|                onStopTarget: "idle"
6661|              })
6662|            }
6663|          }
6664|        }
6665|      }
6666|    },
6667|    stopping: {
6668|      id: "stopping",
6669|      entry: [({
6670|        event: _0x5eb9ca,
6671|        context: _0x381060
6672|      }) => {}, "stopRecording", "cancelVolumeDetection", "hideTranslationModeAlert", "hideDictateBrandAlertAction", "hideAskAnythingAlertAction", "hidePressToStopDictationOnboardingAction", "hideDoNotHoldJustPressAlertAction", ({
6673|        context: _0x2c8ded
6674|      }) => {
6675|        const _0x4efc53 = _0x2c8ded.audioId;
6676|        const _0x75cc0e = _0x2c8ded.mode;
6677|        if (_0x4efc53 && _0x75cc0e === _0xa42a3b.VOICE_TRANSLATION) {
6678|          _0x3f4957("app-settings", "translationModeTargetLanguageCode").then(_0x4bfb76 => {
6679|            _0x213cf9(_0x4efc53, {
6680|              mode: _0x75cc0e
6681|            });
6682|            _0x13fe24(_0x4efc53, {
6683|              output_language: _0x4bfb76 || ""
6684|            });
6685|          }).catch();
6686|        }
6687|      }],
6688|      exit: ["clearIsFinishing", "clearEscapeRecording"],
6689|      on: {
6690|        "RECORD.STOP_COMPLETE": [{
6691|          guard: ({
6692|            context: _0x4e4b94
6693|          }) => _0x4e4b94.onStopTarget === "finishing",
6694|          target: "finishing",
6695|          actions: ve(({
6696|            event: _0x529b49,
6697|            enqueue: _0x5edbf2
6698|          }) => {
6699|            var _0x2949ec;
6700|            _0x5edbf2("clearOnStopTarget");
6701|            if (_0x529b49.type === "RECORD.STOP_COMPLETE" && (_0x2949ec = _0x529b49.result) != null && _0x2949ec.allRecordingTime && _0x529b49.result.allRecordingTime > 0.5) {
6702|              _0x5edbf2("socketSendAudioChunk");
6703|            }
6704|            _0x5edbf2("socketSendEndAudioMessage");
6705|          })
6706|        }, {
6707|          guard: ({
6708|            context: _0x291ef7
6709|          }) => _0x291ef7.onStopTarget === "error",
6710|          target: "error",
6711|          actions: "clearOnStopTarget"
6712|        }, {
6713|          guard: ({
6714|            context: _0x43f7e4
6715|          }) => _0x43f7e4.onStopTarget === "failure",
6716|          target: "failure",
6717|          actions: "clearOnStopTarget"
6718|        }, {
6719|          target: "idle",
6720|          actions: "clearOnStopTarget"
6721|        }]
6722|      }
6723|    },
6724|    finishing: {
6725|      id: "finishing",
6726|      invoke: [{
6727|        id: "socketRefiningTimeoutTimer",
6728|        src: "socketRefiningTimeoutTimer",
6729|        input: ({
6730|          event: _0x432793,
6731|          context: _0x6c3e4c
6732|        }) => {
6733|          var _0x2e8b24;
6734|          var _0x2e0672;
6735|          if (_0x432793.type === "RECORD.RETRY_HISTORY" && (_0x2e8b24 = _0x432793 == null ? undefined : _0x432793.history) != null && _0x2e8b24.duration) {
6736|            return {
6737|              timeout: ((_0x2e0672 = _0x432793 == null ? undefined : _0x432793.history) == null ? undefined : _0x2e0672.duration) * 1000,
6738|              audioId: _0x432793.audioId
6739|            };
6740|          } else {
6741|            return {
6742|              audioId: _0x6c3e4c.audioId
6743|            };
6744|          }
6745|        }
6746|      }],
6747|      entry: ["assignIsFinishing", "resetDictationModeToVoiceTranscription"],
6748|      exit: ["sentToHubRecordingState"],
6749|      on: {
6750|        "WEBSOCKET.REFINE_COMPLETED": {
6751|          target: "idle",
6752|          actions: ["clearError", "clearIsFinishing"]
6753|        },
6754|        "PRIMARY_KEY.DOWN": {
6755|          actions: "showFinishingAlert"
6756|        },
6757|        ESC: {
6758|          target: "idle",
6759|          actions: ["clearError", "clearIsFinishing", ({
6760|            context: _0x5d02ac
6761|          }) => {
6762|            if (_0x5d02ac.audioId) {
6763|              _0x1e21b8();
6764|              _0x213cf9(_0x5d02ac.audioId, {
6765|                status: "dismissed"
6766|              });
6767|            }
6768|          }]
6769|        }
6770|      }
6771|    },
6772|    retrying: {
6773|      id: "retrying",
6774|      invoke: [{
6775|        id: "audioRetryActor",
6776|        src: "audioRetryActor",
6777|        input: ({
6778|          event: _0x2bfe77
6779|        }) => _0x2bfe77.type === "RETRY_AUDIO" ? {
6780|          audioId: _0x2bfe77.audioId
6781|        } : {
6782|          audioId: ""
6783|        }
6784|      }],
6785|      on: {
6786|        "RECORD.RETRY_HISTORY": [{
6787|          guard: ({
6788|            event: _0x454b8f
6789|          }) => _0x454b8f.audioId.length > 0 && _0x454b8f.history.audio !== undefined,
6790|          target: "finishing",
6791|          actions: Z("webSocket", ({
6792|            event: _0x1e8e88
6793|          }) => ({
6794|            type: "WEBSOCKET.SEND_RETRY_DATA",
6795|            audioId: _0x1e8e88.audioId,
6796|            history: _0x1e8e88.history
6797|          }))
6798|        }, {
6799|          target: "failure",
6800|          actions: O({
6801|            error: "RETRY_AUDIO_FAILED",
6802|            errorType: "fatal"
6803|          })
6804|        }]
6805|      }
6806|    },
6807|    error: {
6808|      entry: "handleRecoverableError",
6809|      exit: ["resetDictationModeToVoiceTranscription"],
6810|      on: {
6811|        "PRIMARY_KEY.DOWN": {
6812|          target: "initializingForTapOrHold"
6813|        },
6814|        "HANDSFREE_KEY.DOWN": {
6815|          target: "initializingForHandsFree"
6816|        },
6817|        "TRANSLATION_KEY.DOWN": {
6818|          target: "initializingForTranslation"
6819|        },
6820|        "CLICK.HANDSFREE_BUTTON": {
6821|          target: "initializingForHandsFree"
6822|        },
6823|        "CLICK.RETRY_BUTTON": {
6824|          target: "idle",
6825|          actions: "clearError"
6826|        }
6827|      }
6828|    },
6829|    failure: {
6830|      entry: "handleFatalError",
6831|      exit: ["resetDictationModeToVoiceTranscription", "clearError"],
6832|      on: {
6833|        "PRIMARY_KEY.DOWN": {
6834|          target: "initializingForTapOrHold"
6835|        },
6836|        "HANDSFREE_KEY.DOWN": {
6837|          target: "initializingForHandsFree"
6838|        },
6839|        "TRANSLATION_KEY.DOWN": {
6840|          target: "initializingForTranslation"
6841|        },
6842|        "CLICK.HANDSFREE_BUTTON": {
6843|          target: "initializingForHandsFree"
6844|        }
6845|      }
6846|    }
6847|  }
6848|});
6849|const re = ({
6850|  activeSession: _0x433400 = null,
6851|  shortcutSessionFact: _0x56d998 = null
6852|}) => ({
6853|  activeSession: _0x433400,
6854|  shortcutSessionFact: _0x56d998
6855|});
6856|const qs = (_0x1b0d19, _0x55dbd2, _0x3e1405) => {
6857|  switch (_0x55dbd2.type) {
6858|    case "SHORTCUT_HIT":
6859|      if (_0x1b0d19.activeSession === null) {
6860|        return re({
6861|          activeSession: {
6862|            feature: _0x55dbd2.feature,
6863|            shortcut: _0x55dbd2.shortcut,
6864|            hitCount: 1,
6865|            runId: 1,
6866|            awaitingReleaseAfterLongHold: false
6867|          },
6868|          shortcutSessionFact: {
6869|            type: "shortcutKeyDown",
6870|            feature: _0x55dbd2.feature
6871|          }
6872|        });
6873|      } else if (_0x1b0d19.activeSession.awaitingReleaseAfterLongHold) {
6874|        return re({
6875|          activeSession: _0x1b0d19.activeSession
6876|        });
6877|      } else if (_0x1b0d19.activeSession.hitCount >= 2) {
6878|        return re({
6879|          activeSession: _0x1b0d19.activeSession
6880|        });
6881|      } else {
6882|        return re({
6883|          activeSession: {
6884|            feature: _0x55dbd2.feature,
6885|            shortcut: _0x55dbd2.shortcut,
6886|            hitCount: 2,
6887|            runId: _0x1b0d19.activeSession.runId,
6888|            awaitingReleaseAfterLongHold: false
6889|          },
6890|          shortcutSessionFact: {
6891|            type: "shortcutKeyDown",
6892|            feature: _0x55dbd2.feature
6893|          }
6894|        });
6895|      }
6896|    case "ALL_RELEASED":
6897|      if (_0x1b0d19.activeSession === null) {
6898|        return _0x1b0d19;
6899|      } else {
6900|        return re({
6901|          shortcutSessionFact: {
6902|            type: "shortcutKeyUp",
6903|            feature: _0x1b0d19.activeSession.feature
6904|          }
6905|        });
6906|      }
6907|    case "PRESSED_KEYS_CHANGED":
6908|      if (_0x1b0d19.activeSession === null) {
6909|        return _0x1b0d19;
6910|      } else if (_0x55dbd2.pressedKeys.length === 0) {
6911|        return re({
6912|          shortcutSessionFact: {
6913|            type: "shortcutKeyUp",
6914|            feature: _0x1b0d19.activeSession.feature
6915|          }
6916|        });
6917|      } else if (_0x1b0d19.activeSession.awaitingReleaseAfterLongHold) {
6918|        return re({
6919|          activeSession: _0x1b0d19.activeSession
6920|        });
6921|      } else if (_0x3e1405.some(_0x2f70aa => {
6922|        const _0x1042eb = _0x55dbd2.pressedKeys.map(_0x181411);
6923|        const _0x5be1db = _0x2f70aa.keys.map(_0x181411);
6924|        return _0x1042eb.every(_0x1b49be => _0x5be1db.includes(_0x1b49be));
6925|      })) {
6926|        return re({
6927|          activeSession: _0x1b0d19.activeSession
6928|        });
6929|      } else {
6930|        return re({
6931|          shortcutSessionFact: {
6932|            type: "wrongKeyDown"
6933|          }
6934|        });
6935|      }
6936|    case "RESET_SESSION":
6937|      return re({});
6938|    case "DETECTION_TIMEOUT":
6939|      if (_0x1b0d19.activeSession === null) {
6940|        return re({});
6941|      } else if (_0x55dbd2.runId !== _0x1b0d19.activeSession.runId) {
6942|        return re({
6943|          activeSession: _0x1b0d19.activeSession
6944|        });
6945|      } else if (_0x1b0d19.activeSession.awaitingReleaseAfterLongHold) {
6946|        return re({
6947|          activeSession: _0x1b0d19.activeSession
6948|        });
6949|      } else {
6950|        return re({
6951|          activeSession: {
6952|            ..._0x1b0d19.activeSession,
6953|            awaitingReleaseAfterLongHold: true
6954|          },
6955|          shortcutSessionFact: {
6956|            type: "longHold",
6957|            feature: _0x1b0d19.activeSession.feature
6958|          }
6959|        });
6960|      }
6961|  }
6962|};
6963|const Qs = ({
6964|  shortcutCandidates: _0x2c9006,
6965|  pressedKeys: _0x3cba7a
6966|}) => {
6967|  var _0x1a38ea;
6968|  var _0x1b82f0;
6969|  const [_0xb65b06, _0x563d3d] = _0x7ab73.useReducer((_0x182eb3, _0x7e2d10) => qs(_0x182eb3, _0x7e2d10, _0x2c9006), re({}));
6970|  _0x7ab73.useEffect(() => {
6971|    _0x563d3d({
6972|      type: "PRESSED_KEYS_CHANGED",
6973|      pressedKeys: _0x3cba7a
6974|    });
6975|  }, [_0x3cba7a]);
6976|  _0x7ab73.useEffect(() => {
6977|    const _0x27dc3a = _0xb65b06.activeSession;
6978|    if (_0x27dc3a === null || _0x27dc3a.awaitingReleaseAfterLongHold) {
6979|      return;
6980|    }
6981|    const _0x2c31a7 = _0x27dc3a.runId;
6982|    const _0x2e2307 = setTimeout(() => {
6983|      _0x563d3d({
6984|        type: "DETECTION_TIMEOUT",
6985|        runId: _0x2c31a7
6986|      });
6987|    }, we.LONG_PRESS_MS);
6988|    return () => {
6989|      clearTimeout(_0x2e2307);
6990|    };
6991|  }, [(_0x1a38ea = _0xb65b06.activeSession) == null ? undefined : _0x1a38ea.runId, (_0x1b82f0 = _0xb65b06.activeSession) == null ? undefined : _0x1b82f0.awaitingReleaseAfterLongHold]);
6992|  const _0x120dac = _0x7ab73.useCallback((_0x3b9690, _0x5b013b) => {
6993|    _0x563d3d({
6994|      type: "SHORTCUT_HIT",
6995|      feature: _0x3b9690,
6996|      shortcut: _0x5b013b
6997|    });
6998|  }, []);
6999|  const _0x2bdc5d = _0x7ab73.useCallback(() => {
7000|    _0x563d3d({
7001|      type: "ALL_RELEASED"
7002|    });
7003|  }, []);
7004|  const _0x25c655 = _0x7ab73.useCallback(() => {
7005|    _0x563d3d({
7006|      type: "RESET_SESSION"
7007|    });
7008|  }, []);
7009|  return {
7010|    activeSession: _0xb65b06.activeSession,
7011|    shortcutSessionFact: _0xb65b06.shortcutSessionFact,
7012|    dispatchShortcutHit: _0x120dac,
7013|    dispatchAllReleased: _0x2bdc5d,
7014|    resetSession: _0x25c655
7015|  };
7016|};
7017|const ea = 300;
7018|const ta = async () => {
7019|  try {
7020|    return true;
7021|  } catch {
7022|    return false;
7023|  }
7024|};
7025|const nr = (_0x145a40, _0x1551b2) => {
7026|  if (_0x145a40.length >= _0x1551b2.length) {
7027|    return false;
7028|  }
7029|  const _0x30acb9 = _0x1551b2.map(_0x181411);
7030|  return _0x145a40.map(_0x181411).every(_0x2beeaa => _0x30acb9.includes(_0x2beeaa));
7031|};
7032|const na = (_0x379325, _0x4a2303) => _0x4a2303.some(_0x2d6e38 => nr(_0x379325, _0x2d6e38.keys));
7033|const ra = () => {
7034|  var _0x9b7cdb;
7035|  const {
7036|    pressingKeys: _0x39c416
7037|  } = _0x225e78();
7038|  const _0x2703a6 = _0x1297f9();
7039|  const _0xc4461f = _0x2703a6.isLogin && _0x2703a6.loaded;
7040|  const [_0x1dfc71, _0x3895c0] = _0x7ab73.useState(null);
7041|  const [_0x7ac1ed, _0x9b7c06] = _0x7ab73.useState(null);
7042|  const _0x44cd2e = _0x7ab73.useCallback(_0x4567ab => {
7043|    if (typeof _0x4567ab == "object") {
7044|      _0x3895c0(false);
7045|      _0x9b7c06(_0x4567ab.allowedFeatures);
7046|      return;
7047|    }
7048|    _0x3895c0(_0x4567ab);
7049|    _0x9b7c06(null);
7050|  }, []);
7051|  const _0x98922f = _0x7ab73.useRef(null);
7052|  const _0x4460be = _0x7ab73.useRef(0);
7053|  const _0x3cb569 = _0x7ab73.useCallback(() => {
7054|    window.ipcRenderer.invoke("page:floating-bar-set-always-on-top-for-windows").catch(_0x4760e5 => {});
7055|  }, []);
7056|  const _0xe2deaf = _0x7ab73.useMemo(() => {
7057|    var _0x1d8904;
7058|    return {
7059|      authChecker: {
7060|        userToken: ((_0x1d8904 = _0x2703a6.authInfo) == null ? undefined : _0x1d8904.refresh_token) || "",
7061|        checkLoginStatus: async () => _0x2703a6.loaded ? _0x2703a6.isLogin : false,
7062|        checkPermissions: ta
7063|      }
7064|    };
7065|  }, [_0x2703a6.loaded, _0x2703a6.isLogin, (_0x9b7cdb = _0x2703a6.authInfo) == null ? undefined : _0x9b7cdb.refresh_token]);
7066|  const [_0x3f5fe4, _0x7b5b18] = cs(Zs, {
7067|    input: _0xe2deaf,
7068|    inspect: _0xab47a5 => {
7069|      try {
7070|        _0xab47a5.type;
7071|      } catch {}
7072|    }
7073|  });
7074|  const _0x39c47e = _0x4f77cc(_0x3f5fe4);
7075|  const _0x3a8b72 = _0x7ab73.useCallback(_0x47c656 => {
7076|    if (_0x47c656 === "dictationMode") {
7077|      _0x7b5b18({
7078|        type: "PRIMARY_KEY.DOWN"
7079|      });
7080|      return;
7081|    }
7082|    if (_0x47c656 === "askAnythingMode") {
7083|      _0x7b5b18({
7084|        type: "HANDSFREE_KEY.DOWN"
7085|      });
7086|      return;
7087|    }
7088|    _0x7b5b18({
7089|      type: "TRANSLATION_KEY.DOWN"
7090|    });
7091|  }, [_0x7b5b18]);
7092|  const _0x8ef7a = _0x7ab73.useCallback(_0x42df4a => {
7093|    if (_0x42df4a === "dictationMode") {
7094|      _0x7b5b18({
7095|        type: "PRIMARY_KEY.UP"
7096|      });
7097|      return;
7098|    }
7099|    if (_0x42df4a === "askAnythingMode") {
7100|      _0x7b5b18({
7101|        type: "HANDSFREE_KEY.UP"
7102|      });
7103|      return;
7104|    }
7105|    _0x7b5b18({
7106|      type: "TRANSLATION_KEY.UP"
7107|    });
7108|  }, [_0x7b5b18]);
7109|  const _0x1dab4c = _0x7ab73.useMemo(() => _0x3f5fe4.matches("recording_active"), [_0x3f5fe4]);
7110|  const {
7111|    pressedKeys: _0x4386fd,
7112|    event: _0x40ae96,
7113|    shortcutCandidates: _0x12e69e
7114|  } = _0x55c429({
7115|    featureKeys: ["dictationMode", "askAnythingMode", "translationMode"]
7116|  });
7117|  const _0x19b05f = _0x1dfc71 === null || _0x1dfc71 === true;
7118|  const _0x4e6be3 = _0x7ab73.useMemo(() => _0x7ac1ed === null ? _0x12e69e : _0x12e69e.filter(_0x4e966e => _0x7ac1ed.includes(_0x4e966e.feature)), [_0x7ac1ed, _0x12e69e]);
7119|  const {
7120|    activeSession: _0x55f9b7,
7121|    shortcutSessionFact: _0x29b3ac,
7122|    dispatchShortcutHit: _0x5b7c5b,
7123|    dispatchAllReleased: _0x4890ee,
7124|    resetSession: _0x352db3
7125|  } = Qs({
7126|    shortcutCandidates: _0x12e69e,
7127|    pressedKeys: _0x4386fd
7128|  });
7129|  const _0x38dcbd = (_0x55f9b7 == null ? undefined : _0x55f9b7.feature) ?? null;
7130|  const _0x597b39 = (_0x55f9b7 == null ? undefined : _0x55f9b7.shortcut) ?? null;
7131|  const _0x19822a = _0x7ab73.useMemo(() => !_0x40ae96 || _0x40ae96.type !== "shortcutHit" || _0x7ac1ed === null || _0x38dcbd !== null || _0x7ac1ed.includes(_0x40ae96.feature) || _0x1dab4c ? false : na(_0x40ae96.shortcut, _0x4e6be3), [_0x4e6be3, _0x7ac1ed, _0x38dcbd, _0x40ae96, _0x1dab4c]);
7132|  const _0x514eb7 = _0x7ab73.useRef(null);
7133|  const {
7134|    acceptedShortcutEvent: _0x54cc28,
7135|    shortcutFeedback: _0x5b933d
7136|  } = _0x7ab73.useMemo(() => _0x40ae96 ? _0x40ae96.type === "allReleased" ? {
7137|    acceptedShortcutEvent: _0x55f9b7 !== null ? _0x40ae96 : null,
7138|    shortcutFeedback: null
7139|  } : _0x19b05f ? {
7140|    acceptedShortcutEvent: null,
7141|    shortcutFeedback: null
7142|  } : _0x1dab4c ? {
7143|    acceptedShortcutEvent: _0x40ae96,
7144|    shortcutFeedback: null
7145|  } : _0x597b39 !== null && nr(_0x40ae96.shortcut, _0x597b39) ? {
7146|    acceptedShortcutEvent: null,
7147|    shortcutFeedback: null
7148|  } : _0x19822a ? {
7149|    acceptedShortcutEvent: null,
7150|    shortcutFeedback: null
7151|  } : _0x7ac1ed === null || _0x7ac1ed.includes(_0x40ae96.feature) ? {
7152|    acceptedShortcutEvent: _0x40ae96,
7153|    shortcutFeedback: null
7154|  } : _0x514eb7.current === _0x40ae96 ? {
7155|    acceptedShortcutEvent: null,
7156|    shortcutFeedback: null
7157|  } : {
7158|    acceptedShortcutEvent: null,
7159|    shortcutFeedback: _0x38dcbd === null ? "useCorrectStepShortcut" : "trySimplerShortcut"
7160|  } : {
7161|    acceptedShortcutEvent: null,
7162|    shortcutFeedback: null
7163|  }, [_0x55f9b7, _0x7ac1ed, _0x38dcbd, _0x597b39, _0x19b05f, _0x1dab4c, _0x40ae96, _0x19822a]);
7164|  _0x7ab73.useEffect(() => {
7165|    if (_0x54cc28) {
7166|      if (_0x54cc28.type === "shortcutHit") {
7167|        _0x514eb7.current = _0x54cc28;
7168|        _0x5b7c5b(_0x54cc28.feature, _0x54cc28.shortcut);
7169|        return;
7170|      }
7171|      _0x514eb7.current = null;
7172|      _0x4890ee();
7173|    }
7174|  }, [_0x54cc28, _0x5b7c5b, _0x4890ee]);
7175|  _0x7ab73.useEffect(() => {
7176|    if ((_0x54cc28 == null ? undefined : _0x54cc28.type) === "shortcutHit") {
7177|      _0x98922f.current = null;
7178|    }
7179|  }, [_0x54cc28]);
7180|  _0x7ab73.useEffect(() => {
7181|    if (_0x19822a) {
7182|      _0x98922f.current = "useCorrectStepShortcut";
7183|    }
7184|  }, [_0x19822a]);
7185|  const _0x2e68b3 = _0x7ab73.useRef(_0x1dfc71);
7186|  _0x7ab73.useEffect(() => {
7187|    const _0x48ac7f = _0x2e68b3.current === true;
7188|    const _0x529fba = _0x1dfc71 === true;
7189|    _0x2e68b3.current = _0x1dfc71;
7190|    if (!_0x48ac7f && !!_0x529fba && _0x55f9b7 !== null) {
7191|      _0x352db3();
7192|      _0x7b5b18({
7193|        type: "ESC"
7194|      });
7195|      _0x98922f.current = null;
7196|    }
7197|  }, [_0x55f9b7, _0x1dfc71, _0x352db3, _0x7b5b18]);
7198|  _0x7ab73.useEffect(() => {
7199|    if (_0x1dab4c) {
7200|      _0x29bb1e.reloadKeyboardShortcuts([["Escape"]]);
7201|    } else {
7202|      _0x29bb1e.reloadKeyboardShortcuts();
7203|    }
7204|  }, [_0x1dab4c]);
7205|  _0x7ab73.useEffect(() => {
7206|    if (!_0xc4461f) {
7207|      _0x7b5b18({
7208|        type: "INITIALIZATION.AUTH_REQUIRED"
7209|      });
7210|    }
7211|  }, [_0xc4461f, _0x7b5b18]);
7212|  _0x7ab73.useEffect(() => {
7213|    if (_0x29b3ac) {
7214|      switch (_0x29b3ac.type) {
7215|        case "shortcutKeyDown":
7216|          {
7217|            _0x3cb569();
7218|            if (_0x29b3ac.feature === "dictationMode") {
7219|              const _0x412f39 = Date.now();
7220|              if (_0x412f39 - _0x4460be.current < ea) {
7221|                return;
7222|              }
7223|              _0x4460be.current = _0x412f39;
7224|            }
7225|            _0x3a8b72(_0x29b3ac.feature);
7226|            return;
7227|          }
7228|        case "shortcutKeyUp":
7229|          {
7230|            _0x8ef7a(_0x29b3ac.feature);
7231|            return;
7232|          }
7233|        case "wrongKeyDown":
7234|          {
7235|            _0x7b5b18({
7236|              type: "WRONG_KEY.DOWN"
7237|            });
7238|            return;
7239|          }
7240|        case "longHold":
7241|          {
7242|            _0x7b5b18({
7243|              type: "LONG_HOLD"
7244|            });
7245|            return;
7246|          }
7247|      }
7248|    }
7249|  }, [_0x3cb569, _0x29b3ac, _0x7b5b18, _0x3a8b72, _0x8ef7a]);
7250|  _0x7ab73.useEffect(() => {
7251|    if (_0x1dab4c) {
7252|      return;
7253|    }
7254|    const _0x4bd45e = _0x40ff7a => {
7255|      const _0x5f4a67 = new BroadcastChannel("recording-machine");
7256|      _0x5f4a67.postMessage({
7257|        type: "shortcutFeedback",
7258|        feedback: _0x40ff7a
7259|      });
7260|      _0x5f4a67.close();
7261|    };
7262|    if (_0x5b933d) {
7263|      _0x4bd45e(_0x5b933d);
7264|      return;
7265|    }
7266|    if ((_0x40ae96 == null ? undefined : _0x40ae96.type) === "allReleased") {
7267|      const _0x5774a9 = _0x98922f.current;
7268|      _0x98922f.current = null;
7269|      if (_0x5774a9) {
7270|        _0x4bd45e(_0x5774a9);
7271|      }
7272|    }
7273|  }, [_0x5b933d, _0x40ae96, _0x1dab4c]);
7274|  _0x7ab73.useEffect(() => {
7275|    if (_0x39c416.includes("Escape")) {
7276|      _0x7b5b18({
7277|        type: "ESC"
7278|      });
7279|    }
7280|  }, [_0x39c416, _0x7b5b18]);
7281|  _0x7ab73.useEffect(() => {
7282|    _0x7b5b18({
7283|      type: "UPDATE_STATE_INPUT",
7284|      stateInput: _0xe2deaf
7285|    });
7286|  }, [_0xe2deaf, _0x7b5b18]);
7287|  _0x7ab73.useEffect(() => {
7288|    _0x4305ad.loadSounds();
7289|  }, []);
7290|  _0x7ab73.useEffect(() => {
7291|    let _0x1c5fcf = false;
7292|    const _0x3c26bb = (_0x3cd85c, _0x33e722) => {
7293|      _0x44cd2e(_0x33e722);
7294|    };
7295|    window.ipcRenderer.on(_0x10af14.DISABLED_CHANGED, _0x3c26bb);
7296|    window.ipcRenderer.invoke(_0x10af14.GET_DISABLED).then(_0x4a846a => {
7297|      if (!_0x1c5fcf) {
7298|        _0x44cd2e(_0x4a846a);
7299|      }
7300|    }).catch(_0x43846d => {
7301|      if (!_0x1c5fcf) {
7302|        _0x44cd2e(false);
7303|      }
7304|    });
7305|    return () => {
7306|      _0x1c5fcf = true;
7307|      window.ipcRenderer.off(_0x10af14.DISABLED_CHANGED, _0x3c26bb);
7308|    };
7309|  }, [_0x44cd2e]);
7310|  _0x7ab73.useEffect(() => {
7311|    const _0x592813 = new BroadcastChannel("recording-machine");
7312|    _0x592813.onmessage = _0x1561b5 => {
7313|      const {
7314|        type: _0x306200,
7315|        force: _0x3fba7d
7316|      } = _0x1561b5.data;
7317|      if (_0x306200) {
7318|        switch (_0x306200) {
7319|          case "ESCAPE":
7320|            if (_0x3fba7d || _0x39c47e.current.matches("error") || _0x39c47e.current.matches("failure")) {
7321|              _0x7b5b18({
7322|                type: "ESC"
7323|              });
7324|            }
7325|            break;
7326|        }
7327|      }
7328|    };
7329|    return () => {
7330|      _0x592813.close();
7331|    };
7332|  }, []);
7333|  return {
7334|    send: _0x7b5b18,
7335|    state: _0x3f5fe4
7336|  };
7337|};
7338|const un = ["LeftCmd", "LeftCtrl", "RightCmd", "RightCtrl"];
7339|class ia {
7340|  constructor(_0x486c98) {
7341|    pe(this, "eventQueue", []);
7342|    pe(this, "checkTimer", null);
7343|    pe(this, "currentApp", null);
7344|    pe(this, "currentInput", null);
7345|    pe(this, "lastPressKeys", null);
7346|    pe(this, "config");
7347|    pe(this, "handleGlobalKeyboard", (_0x38819c, _0x5300da) => {
7348|      var _0x490d9c;
7349|      try {
7350|        this.cleanOldEvents();
7351|        if ((_0x490d9c = this.currentInput) == null || !_0x490d9c.input_capabilities.is_editable || !_0x5300da.length || un.includes(_0x5300da[0].keyName)) {
7352|          return;
7353|        }
7354|        let _0x31ab76 = -1;
7355|        let _0x2c2d2c = true;
7356|        const _0x50e684 = _0x5300da.filter((_0x51f3ef, _0x263d35) => {
7357|          var _0x386ae7;
7358|          if (_0x31ab76 < 0 && un.includes(_0x51f3ef.keyName)) {
7359|            _0x31ab76 = _0x263d35;
7360|          }
7361|          if (!_0x51f3ef.isKeydown || (_0x386ae7 = this.lastPressKeys) != null && _0x386ae7.find(_0x5217d8 => _0x5217d8.keyName === _0x51f3ef.keyName)) {
7362|            return false;
7363|          }
7364|          const _0x1b1fb1 = _0x51f3ef.keyName === "Space" || /^[a-zA-Z0-9[\]\\;',.\-=/]$/.test(_0x51f3ef.keyName);
7365|          if (_0x1b1fb1 && _0x31ab76 >= 0 && _0x31ab76 < _0x263d35) {
7366|            _0x2c2d2c = false;
7367|          }
7368|          return _0x1b1fb1;
7369|        });
7370|        if (_0x2c2d2c && _0x50e684.length) {
7371|          _0x50e684.forEach(_0x863d27 => {
7372|            this.processEvent(_0x863d27.keyName);
7373|          });
7374|        }
7375|      } catch {} finally {
7376|        this.lastPressKeys = _0x5300da;
7377|      }
7378|    });
7379|    this.config = {
7380|      threshold: 60,
7381|      maxAgeMs: 60000,
7382|      ..._0x486c98
7383|    };
7384|  }
7385|  init() {
7386|    _0x49540c("global-keyboard", this.handleGlobalKeyboard);
7387|    this.checkTimer = setInterval(() => {
7388|      Ve.getLastFocusedInfo().then(_0x3e9c30 => {
7389|        var _0x2d0e02;
7390|        var _0x2fbb49;
7391|        if (((_0x2d0e02 = this.currentApp) == null ? undefined : _0x2d0e02.app_identifier) !== ((_0x2fbb49 = _0x3e9c30.appInfo) == null ? undefined : _0x2fbb49.app_identifier)) {
7392|          this.clearQueue();
7393|        }
7394|        this.currentApp = _0x3e9c30.appInfo;
7395|        this.currentInput = _0x3e9c30.inputInfo;
7396|      });
7397|    }, 1000);
7398|  }
7399|  destroy() {
7400|    this.clearQueue();
7401|    _0x1b621f("global-keyboard", this.handleGlobalKeyboard);
7402|    if (this.checkTimer) {
7403|      clearInterval(this.checkTimer);
7404|      this.checkTimer = null;
7405|    }
7406|  }
7407|  processEvent(_0x44fc0c) {
7408|    var _0x553955;
7409|    const _0x18fb20 = Date.now();
7410|    const _0x1be4ce = (_0x553955 = this.currentApp) == null ? undefined : _0x553955.app_identifier;
7411|    this.eventQueue.push({
7412|      timestamp: _0x18fb20,
7413|      appId: _0x1be4ce,
7414|      pressKey: _0x44fc0c
7415|    });
7416|    if (this.eventQueue.length > this.config.threshold) {
7417|      this.triggerHint();
7418|      this.clearQueue();
7419|    }
7420|  }
7421|  cleanOldEvents() {
7422|    const _0x2c651a = Date.now();
7423|    this.eventQueue = this.eventQueue.filter(_0xc94a40 => _0x2c651a - _0xc94a40.timestamp < this.config.maxAgeMs);
7424|  }
7425|  clearQueue() {
7426|    if (this.eventQueue.length > 0) {
7427|      this.eventQueue = [];
7428|    }
7429|  }
7430|  triggerHint() {
7431|    if (this.config.onHint) {
7432|      this.config.onHint();
7433|    }
7434|  }
7435|}
7436|const oa = (_0x45dd8c, _0x1cda72, _0x427dae) => {
7437|  try {
7438|    if (_0x45dd8c.startsWith("all")) {
7439|      return _0x45dd8c + ", " + _0x1cda72 + " " + _0x427dae + " ease-in-out";
7440|    }
7441|    const _0x54f922 = _0x45dd8c.split(",");
7442|    const _0x40f2cf = _0x54f922.findIndex(_0x58b1e4 => _0x58b1e4.includes(_0x1cda72));
7443|    let _0x127c85 = _0x54f922[_0x40f2cf].trim().split(" ");
7444|    _0x127c85 = _0x127c85.map((_0x1b0d8a, _0x7d8522) => _0x7d8522 === 1 ? _0x427dae : _0x1b0d8a);
7445|    _0x54f922[_0x40f2cf] = _0x127c85.join(" ");
7446|    return _0x54f922.join(",");
7447|  } catch {
7448|    return _0x45dd8c;
7449|  }
7450|};
7451|const sa = () => {
7452|  var _0x1f7fa1;
7453|  var _0x32a958;
7454|  const [_0x2d5e63, _0x2a7232] = _0x7ab73.useState(false);
7455|  const [_0x1e35c7, _0x4aa4b1] = _0x7ab73.useState(false);
7456|  const {
7457|    appSettings: _0x475523
7458|  } = _0x540937();
7459|  const {
7460|    loaded: _0x2395ed,
7461|    isLogin: _0x1e5dd4
7462|  } = _0x1297f9();
7463|  const {
7464|    checkAndDownloadSilently: _0x5327f8
7465|  } = _0x1321c8(true);
7466|  const {
7467|    retryState: _0x1a21d5,
7468|    setRetrying: _0x563ec0,
7469|    resetRetry: _0x17719a
7470|  } = _0x3b8ea5();
7471|  const _0xa94ac3 = (_0x475523 == null ? undefined : _0x475523.enableInteractionSoundEffects) ?? false;
7472|  const _0x290cde = (_0x475523 == null ? undefined : _0x475523.enabledMuteBackgroundAudio) !== false;
7473|  const _0x5a18b9 = false;
7474|  const {
7475|    currentSelectedDevice: _0x507e5b
7476|  } = _0x344f97();
7477|  const {
7478|    state: _0xe83729,
7479|    send: _0x5cd353
7480|  } = ra();
7481|  const _0xa5c90c = _0x7ab73.useMemo(() => new ia({
7482|    onHint: () => {
7483|      _0x33bdfc();
7484|    }
7485|  }), []);
7486|  const _0x3286be = ((_0x1f7fa1 = _0xe83729.context.recorderState) == null ? undefined : _0x1f7fa1.isStartingMicrophone) ?? false;
7487|  const _0xcd2f98 = _0xe83729.matches("finishing");
7488|  const _0x4d0ca7 = _0xe83729.matches("error");
7489|  const _0x19124c = _0xe83729.matches("failure");
7490|  const _0x578cac = _0xe83729.matches("idle");
7491|  const _0x3f84c1 = _0xe83729.matches("long_pressing");
7492|  const _0x4814da = !_0x578cac && !_0xcd2f98 && !_0x4d0ca7 && !_0x19124c && !_0x3f84c1;
7493|  const _0x4d3d8c = _0x4814da && !_0x3286be;
7494|  const _0xff0ab = _0xe83729.matches({
7495|    recording_active: "handsFree"
7496|  }) || _0xe83729.matches({
7497|    recording_active: "translationModeHandsFree"
7498|  });
7499|  const _0x201feb = _0x7ab73.useMemo(() => {
7500|    var _0x5bfdc0;
7501|