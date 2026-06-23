// Source: typeless_src/cracked/deobfuscated.js, lines 14280-14670
// Typeless silent learning / track-edit mechanism
// Key logic: START_TRACK -> inject text -> monitor user edits -> diff -> extract rules
// Classes: TrackEditManager (with analysisModification, includesRefinedText, etc.)
// Key methods: startTrack, stopTrack, sendTrackResultToServer
// Data flow: original_input_box.full_field_content vs edited full_field_content
//           -> diffChars -> correction_rules extraction

14280|      }
14281|    } catch {}
14282|  }
14283|  checkFile(_0x49d19a) {
14284|    try {
14285|      const _0x2975b9 = this.fileDir;
14286|      const _0xe24a3e = _0x3235b0.join(this.fileDir, _0x49d19a);
14287|      if (!_0x1d4cc3.existsSync(_0x2975b9)) {
14288|        _0x1d4cc3.mkdirSync(_0x2975b9, {
14289|          recursive: true
14290|        });
14291|      }
14292|      if (!_0x1d4cc3.existsSync(_0xe24a3e)) {
14293|        _0x1d4cc3.writeFileSync(_0xe24a3e, "");
14294|      }
14295|    } catch {}
14296|  }
14297|}
14298|const It = new dg();
14299|var Dn = (_0x31cbcc => {
14300|  _0x31cbcc.START_TRACK = "track-edit-text:start-track";
14301|  _0x31cbcc.STOP_TRACK = "track-edit-text:stop-track";
14302|  return _0x31cbcc;
14303|})(Dn || {});
14304|const hg = new Set(["A", "S", "D", "F", "H", "G", "Z", "X", "C", "V", "B", "Q", "W", "E", "R", "Y", "T", "O", "U", "I", "P", "L", "J", "K", "N", "M", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "=", "-", "]", "[", "'", ";", "\\", ",", "/", ".", "`", "Enter", "Tab", "Space", "Delete"]);
14305|class pg {
14306|  constructor() {
14307|    f(this, "maxTrackTime", Wi.SECOND * 15);
14308|    f(this, "trackEditResult", null);
14309|    f(this, "lastFocusedInfo", null);
14310|    f(this, "lastPressedInfo", null);
14311|    f(this, "lastPressEnterTime", 0);
14312|    f(this, "stopTimer", null);
14313|    f(this, "onPollingFocusedInfo", _0x5da035 => {
14314|      var _0x1664a2;
14315|      var _0x300cfb;
14316|      if (!this.trackEditResult) {
14317|        this.stopTrack();
14318|        return;
14319|      }
14320|      if (!_0x5da035.appInfo || !_0x5da035.inputInfo || this.trackEditResult.input_box_identifier !== sr(_0x5da035.appInfo, _0x5da035.inputInfo)) {
14321|        he.log("[User Edit] 🟡 Focus switched or input box changed, stopping tracking");
14322|        this.checkEditedText("switch_input_box");
14323|        this.stopTrack();
14324|      } else if ((_0x1664a2 = _0x5da035.inputInfo) == null || !_0x1664a2.cursor_state.full_field_content) {
14325|        this.checkEditedText("clear_input_box");
14326|        this.stopTrack();
14327|      } else {
14328|        if (this.lastPressedInfo) {
14329|          const _0x3bb855 = Date.now();
14330|          const _0x277829 = this.lastPressedInfo.pressingKeys;
14331|          const _0x49320b = _0x3bb855 - this.lastPressedInfo.timestamp;
14332|          const _0x259e34 = _0x3bb855 - this.lastPressEnterTime;
14333|          if (_0x49320b < Wi.SECOND) {
14334|            const {
14335|              isLargeModify: _0x3dccbb,
14336|              addedCount: _0x3b2f20,
14337|              removedCount: _0x128d9d,
14338|              changedCount: _0x3b83ff
14339|            } = this.analysisModification(this.trackEditResult.original_input_box.full_field_content, _0x5da035.inputInfo.cursor_state.full_field_content, this.trackEditResult.refined_inserted_text);
14340|            if (_0x3dccbb) {
14341|              if (((_0x300cfb = _0x277829[_0x277829.length - 1]) == null ? undefined : _0x300cfb.keyName) === "Enter" || _0x259e34 < Wi.SECOND) {
14342|                this.checkEditedText("press_enter");
14343|                this.stopTrack();
14344|              } else {
14345|                It.saveLog({
14346|                  filename: St.TRACKING_LOG,
14347|                  type: "stop track",
14348|                  content: {
14349|                    failureReason: "large modify",
14350|                    lastPressedKeys: _0x277829,
14351|                    addedCount: _0x3b2f20,
14352|                    removedCount: _0x128d9d,
14353|                    changedCount: _0x3b83ff,
14354|                    originalFullContent: this.trackEditResult.original_input_box.full_field_content,
14355|                    currentFullContent: _0x5da035.inputInfo.cursor_state.full_field_content,
14356|                    refinedText: this.trackEditResult.refined_inserted_text
14357|                  }
14358|                });
14359|                this.stopTrack();
14360|              }
14361|              return;
14362|            }
14363|          }
14364|        }
14365|        this.lastFocusedInfo = _0x5da035;
14366|      }
14367|    });
14368|    f(this, "onPressKeyboardKeys", _0x7096fb => {
14369|      var _0x26f70c;
14370|      if (!this.trackEditResult) {
14371|        this.stopTrack();
14372|        return;
14373|      }
14374|      if (_0x7096fb.find(_0x25b8cf => hg.has(_0x25b8cf.keyName))) {
14375|        this.lastPressedInfo = {
14376|          timestamp: Date.now(),
14377|          pressingKeys: _0x7096fb
14378|        };
14379|        if (this.stopTimer && this.lastFocusedInfo && (_0x26f70c = this.lastFocusedInfo.inputInfo) != null && _0x26f70c.cursor_state.full_field_content && !this.includesRefinedText(this.lastFocusedInfo.inputInfo.cursor_state.full_field_content, this.trackEditResult.refined_inserted_text)) {
14380|          clearTimeout(this.stopTimer);
14381|          this.stopTimer = setTimeout(() => {
14382|            this.checkEditedText("track_timeout");
14383|            this.stopTrack();
14384|          }, this.maxTrackTime);
14385|          he.log("[User Edit] 🔄 Edit detected, resetting timeout timer");
14386|        }
14387|        this.debounceExecuteLastFocusedInfoTask();
14388|      }
14389|      if (_0x7096fb.length === 1 && _0x7096fb[0].keyName === "Enter") {
14390|        this.lastPressEnterTime = Date.now();
14391|        he.log("[User Edit] 🔵 Enter key pressed");
14392|      }
14393|    });
14394|    f(this, "debounceExecuteLastFocusedInfoTask", cg(async () => {
14395|      Ae.executeLastFocusedInfoTask();
14396|    }, 100));
14397|    _0x53e868.handle(Dn.START_TRACK, (_0x36178b, _0x42adb8) => this.startTrack(_0x42adb8));
14398|    _0x53e868.handle(Dn.STOP_TRACK, () => this.stopTrack());
14399|  }
14400|  normalizeText(_0x1f0e95) {
14401|    return _0x1f0e95.replace(/[\r\n]/g, "").replace(/[\u200B\u200C\u200D\u200E\u200F\uFEFF]/g, "");
14402|  }
14403|  async sendTrackResultToServer(_0x228d7e) {
14404|    var _0x4cda3f;
14405|    var _0x1c00a6;
14406|    var _0x25ff9b;
14407|    var _0x4c633b;
14408|    var _0x303a4a;
14409|    var _0x26a66e;
14410|    var _0x1c3b56;
14411|    try {
14412|      if (_0x228d7e.trigger_type) {
14413|        const _0xbf02b0 = {
14414|          refined_inserted_text: _0x228d7e.refined_inserted_text,
14415|          original_input_box: _0x228d7e.original_input_box,
14416|          edited_input_box: _0x228d7e.edited_input_box,
14417|          active_application: _0x228d7e.audio_context.active_application
14418|        };
14419|        const _0x173f75 = await rn(_0xbf02b0, {
14420|          context: "user_traits"
14421|        });
14422|        he.info("[User Edit] 🔵 Sending request", _0xbf02b0);
14423|        const _0x2ff784 = await Ze.post("/user/traits", {
14424|          body: JSON.stringify({
14425|            log: _0x173f75
14426|          })
14427|        });
14428|        he.info("[User Edit] 🔵 Response received", (_0x4cda3f = _0x2ff784.response) == null ? undefined : _0x4cda3f.status, _0x2ff784.data, _0x2ff784.options.url);
14429|        const _0x17f126 = ((_0x4c633b = (_0x25ff9b = (_0x1c00a6 = _0x2ff784.data) == null ? undefined : _0x1c00a6.data) == null ? undefined : _0x25ff9b.auto_add_dictionary) == null ? undefined : _0x4c633b[0]) || ((_0x26a66e = (_0x303a4a = _0x2ff784.data) == null ? undefined : _0x303a4a.data) == null ? undefined : _0x26a66e.auto_add_dictionary);
14430|        if (_0x17f126 != null && _0x17f126.term && _0x17f126 != null && _0x17f126.user_dictionary_id) {
14431|          const {
14432|            term: _0x280288,
14433|            user_dictionary_id: _0xf1ea49
14434|          } = _0x17f126;
14435|          he.info("[User Edit] 🟢 Auto-added dictionary word received, showing alert", {
14436|            term: _0x280288,
14437|            user_dictionary_id: _0xf1ea49
14438|          });
14439|          if ((_0x1c3b56 = ce.getWindow()) != null) {
14440|            _0x1c3b56.webContents.send("dictionary:word-auto-added", {
14441|              term: _0x280288,
14442|              user_dictionary_id: _0xf1ea49
14443|            });
14444|          }
14445|        }
14446|      } else {
14447|        he.info("[User Edit] 🟡 No trigger_type, skipping report", _0x228d7e);
14448|      }
14449|    } catch (_0x114476) {
14450|      he.error("[User Edit] 🔴 Report failed", _0x114476, _0x228d7e);
14451|    }
14452|  }
14453|  async startTrack(_0x2d7a67) {
14454|    var _0x4412f4;
14455|    var _0x5a0663;
14456|    var _0x395591;
14457|    var _0x5cec55;
14458|    var _0xae1747;
14459|    var _0x2b5cb0;
14460|    var _0x12a424;
14461|    var _0x452302;
14462|    var _0x21d759;
14463|    var _0x123870;
14464|    var _0x44f56e;
14465|    var _0x595b23;
14466|    await this.stopTrack();
14467|    he.info("[User Edit] 🟢 User edit detected, starting tracking");
14468|    const {
14469|      refinedText: _0x176759
14470|    } = _0x2d7a67;
14471|    const _0xa90676 = await Jp.getAudioContext({
14472|      focusedAppOptions: {
14473|        visibleTextParams: [10000, {
14474|          timeout: 500
14475|        }]
14476|      },
14477|      focusedInputOptions: {
14478|        relatedContentParams: [1000, 1000, {
14479|          timeout: 500
14480|        }],
14481|        inputStateParams: []
14482|      }
14483|    });
14484|    if (_0xa90676 == null || !_0xa90676.active_application || !_0xa90676.text_insertion_point || (_0x4412f4 = _0xa90676.text_insertion_point) == null || !_0x4412f4.input_capabilities.is_editable || !this.includesRefinedText(_0xa90676.text_insertion_point.cursor_state.full_field_content, _0x176759)) {
14485|      he.info("[User Edit] 🔴 Cannot start tracking (filtered non-editable input box or failed text insertion)", _0xa90676, "[full_field_content:" + ((_0x5a0663 = _0xa90676.text_insertion_point) == null ? undefined : _0x5a0663.cursor_state.full_field_content) + "]", "[refinedText:" + _0x176759 + "]");
14486|      It.saveLog({
14487|        filename: St.TRACKING_LOG,
14488|        type: "🔴start track failed",
14489|        content: {
14490|          appName: (_0x395591 = _0xa90676.active_application) == null ? undefined : _0x395591.app_name,
14491|          appIdentifier: (_0x5cec55 = _0xa90676.active_application) == null ? undefined : _0x5cec55.app_identifier,
14492|          browserContext: (_0xae1747 = _0xa90676.active_application) == null ? undefined : _0xae1747.browser_context,
14493|          isEditable: (_0x2b5cb0 = _0xa90676.text_insertion_point) == null ? undefined : _0x2b5cb0.input_capabilities.is_editable,
14494|          fullFieldContent: (_0x12a424 = _0xa90676.text_insertion_point) == null ? undefined : _0x12a424.cursor_state.full_field_content,
14495|          refinedText: _0x176759
14496|        }
14497|      });
14498|      return false;
14499|    } else {
14500|      this.trackEditResult = {
14501|        start_track_time: new Date().toISOString(),
14502|        end_track_time: "",
14503|        input_box_identifier: sr(_0xa90676.active_application, _0xa90676.text_insertion_point),
14504|        refined_inserted_text: _0x176759,
14505|        original_input_box: {
14506|          text_before_cursor: _0xa90676.text_insertion_point.cursor_state.text_before_cursor.slice(0, -_0x176759.length),
14507|          text_after_cursor: _0xa90676.text_insertion_point.cursor_state.text_after_cursor,
14508|          full_field_content: _0xa90676.text_insertion_point.cursor_state.full_field_content
14509|        },
14510|        edited_input_box: {
14511|          full_field_content: ""
14512|        },
14513|        audio_context: _0xa90676
14514|      };
14515|      Ae.setLastFocusedInfoTimer({
14516|        timerGetInputOptions: {
14517|          inputStateParams: []
14518|        }
14519|      });
14520|      Ae.addListener("onPollingFocusedInfo", this.onPollingFocusedInfo);
14521|      et.addListener("onPressKeyboardKeys", this.onPressKeyboardKeys);
14522|      this.stopTimer = setTimeout(() => {
14523|        this.checkEditedText("track_timeout");
14524|        this.stopTrack();
14525|      }, this.maxTrackTime);
14526|      It.saveLog({
14527|        filename: St.TRACKING_LOG,
14528|        type: "🟢start track success",
14529|        content: {
14530|          appName: (_0x452302 = _0xa90676.active_application) == null ? undefined : _0x452302.app_name,
14531|          appIdentifier: (_0x21d759 = _0xa90676.active_application) == null ? undefined : _0x21d759.app_identifier,
14532|          browserContext: (_0x123870 = _0xa90676.active_application) == null ? undefined : _0x123870.browser_context,
14533|          isEditable: (_0x44f56e = _0xa90676.text_insertion_point) == null ? undefined : _0x44f56e.input_capabilities.is_editable,
14534|          textBeforeCursor: (_0x595b23 = _0xa90676.text_insertion_point) == null ? undefined : _0x595b23.cursor_state.text_before_cursor,
14535|          refinedText: _0x176759
14536|        }
14537|      });
14538|      return true;
14539|    }
14540|  }
14541|  async stopTrack() {
14542|    he.info("[User Edit] 🔴 Cleaning up tracking state");
14543|    if (this.stopTimer) {
14544|      clearTimeout(this.stopTimer);
14545|    }
14546|    Ae.setLastFocusedInfoTimer({
14547|      timerGetInputOptions: null
14548|    });
14549|    Ae.removeListener("onPollingFocusedInfo", this.onPollingFocusedInfo);
14550|    et.removeListener("onPressKeyboardKeys", this.onPressKeyboardKeys);
14551|    this.trackEditResult = null;
14552|    this.lastFocusedInfo = null;
14553|    this.lastPressedInfo = null;
14554|    this.lastPressEnterTime = 0;
14555|    this.stopTimer = null;
14556|    return true;
14557|  }
14558|  checkEditedText(_0x59da33) {
14559|    var _0x35914e;
14560|    try {
14561|      he.info("[User Edit] 🔍 Triggered report check", _0x59da33);
14562|      if ((_0x35914e = this.lastFocusedInfo) == null || !_0x35914e.appInfo || !this.lastFocusedInfo.inputInfo || !this.trackEditResult || !this.trackEditResult.refined_inserted_text) {
14563|        he.info("[User Edit] 🔴 No focus info obtained, stopping tracking");
14564|        It.saveLog({
14565|          filename: St.TRACKING_LOG,
14566|          type: "🔴tracking edit failed",
14567|          content: {
14568|            triggerType: _0x59da33,
14569|            failureReason: "empty info"
14570|          }
14571|        });
14572|        this.stopTrack();
14573|        return;
14574|      }
14575|      const _0xec124a = this.trackEditResult.original_input_box.full_field_content;
14576|      const _0x3d7a46 = this.lastFocusedInfo.inputInfo.cursor_state.full_field_content;
14577|      const _0x39d68e = this.trackEditResult.refined_inserted_text;
14578|      if (!_0x3d7a46.trim()) {
14579|        he.info("[User Edit] 🟡 Content cleared, not tracking", _0x59da33);
14580|        It.saveLog({
14581|          filename: St.TRACKING_LOG,
14582|          type: "🔴tracking edit failed",
14583|          content: {
14584|            triggerType: _0x59da33,
14585|            failureReason: "clear input",
14586|            originalFullContent: _0xec124a,
14587|            currentFullContent: _0x3d7a46,
14588|            refinedText: _0x39d68e
14589|          }
14590|        });
14591|        this.stopTrack();
14592|        return;
14593|      }
14594|      if (this.includesRefinedText(_0x3d7a46, _0x39d68e)) {
14595|        he.info("[User Edit] 🟡 Content unchanged, not processing", _0x59da33);
14596|        It.saveLog({
14597|          filename: St.TRACKING_LOG,
14598|          type: "🔴tracking edit failed",
14599|          content: {
14600|            triggerType: _0x59da33,
14601|            failureReason: "not modify",
14602|            originalFullContent: _0xec124a,
14603|            currentFullContent: _0x3d7a46,
14604|            refinedText: _0x39d68e
14605|          }
14606|        });
14607|        return;
14608|      }
14609|      const {
14610|        isLargeModify: _0x10d072,
14611|        addedCount: _0x1cdc5d,
14612|        removedCount: _0x35fa77,
14613|        changedCount: _0x2a2e65
14614|      } = this.analysisModification(_0xec124a, _0x3d7a46, _0x39d68e);
14615|      if (_0x10d072) {
14616|        he.info("[User Edit] 🟡 Large-scale modification, not tracking", _0x59da33);
14617|        It.saveLog({
14618|          filename: St.TRACKING_LOG,
14619|          type: "🔴tracking edit failed",
14620|          content: {
14621|            triggerType: _0x59da33,
14622|            failureReason: "large modify",
14623|            addedCount: _0x1cdc5d,
14624|            removedCount: _0x35fa77,
14625|            changedCount: _0x2a2e65,
14626|            originalFullContent: _0xec124a,
14627|            currentFullContent: _0x3d7a46,
14628|            refinedText: _0x39d68e
14629|          }
14630|        });
14631|        this.stopTrack();
14632|        return;
14633|      }
14634|      this.trackEditResult.end_track_time = new Date().toISOString();
14635|      this.trackEditResult.trigger_type = _0x59da33;
14636|      this.trackEditResult.edited_input_box.full_field_content = _0x3d7a46;
14637|      he.info("[User Edit] 🟢 Content edited (small-scale), triggering report", _0x59da33);
14638|      It.saveLog({
14639|        filename: St.TRACKING_LOG,
14640|        type: "🟢tracking edit success",
14641|        content: this.trackEditResult
14642|      });
14643|      this.sendTrackResultToServer(this.trackEditResult);
14644|    } catch (_0x1eb5c3) {
14645|      he.error("[User Edit] 🔴 Error while checking edited text", _0x59da33, _0x1eb5c3);
14646|    }
14647|  }
14648|  includesRefinedText(_0x38fe04, _0x46db8c) {
14649|    const _0x212afa = this.normalizeText(_0x38fe04);
14650|    const _0x18f870 = this.normalizeText(_0x46db8c);
14651|    return _0x212afa.includes(_0x18f870);
14652|  }
14653|  analysisModification(_0x3d66df, _0x51cd88, _0x57f629) {
14654|    const _0x5b0889 = this.normalizeText(_0x3d66df.slice(0, 1000));
14655|    const _0x2eadcd = this.normalizeText(_0x51cd88.slice(0, 1000));
14656|    const _0xe5e847 = _0x1161e7(_0x5b0889, _0x2eadcd);
14657|    const _0x59db79 = _0x5b0889.length;
14658|    _0x2eadcd.length;
14659|    let _0x408ae8 = 0;
14660|    let _0x3f79b3 = 0;
14661|    let _0x3f4009 = 0;
14662|    _0xe5e847.forEach(_0x30704a => {
14663|      if (_0x30704a.added) {
14664|        _0x408ae8 += _0x30704a.count;
14665|        _0x3f4009 += _0x30704a.count;
14666|      } else if (_0x30704a.removed) {
14667|        _0x3f79b3 += _0x30704a.count;
14668|        _0x3f4009 += _0x30704a.count;
14669|      }
14670|    });
14671|