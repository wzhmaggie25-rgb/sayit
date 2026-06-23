// Source: typeless_src/cracked/deobfuscated.js, lines 6160-6710
// Typeless focused-context system
// IPC channels: focused-context:get-full-context, get-focused-app_info, etc.
// Key methods: getFullContext, prepareAccessibility, getFocusedAppInfo
// Data collected: app_name, window_title, web_url, web_domain, input_info
// Integration: feeds into injection strategy (blacklist/whitelist matching)

6160|    return ((_0x245711 = (_0x9ca9ea = _0xa8a4f8?.onboarding) == null ? undefined : _0x9ca9ea[_0x1ac707]) == null ? undefined : _0x245711.completed) === true;
6161|  } else {
6162|    return false;
6163|  }
6164|};
6165|var wt = (_0x5b7202 => {
6166|  _0x5b7202.SET_LAST_FOCUSED_INFO_TIMER = "focused-context:set-last-focused-info-timer";
6167|  _0x5b7202.EXECUTE_LAST_FOCUSED_INFO_TASK = "focused-context:execute-last-focused-info-task";
6168|  _0x5b7202.GET_LAST_FOCUSED_INFO = "focused-context:get-last-focused-info";
6169|  _0x5b7202.GET_FOCUSED_APP_INFO = "focused-context:get-focused-app_info";
6170|  _0x5b7202.GET_FOCUSED_INPUT_INFO = "focused-context:get-focused-input-info";
6171|  _0x5b7202.GET_SELECTED_TEXT = "focused-context:get-selected-text";
6172|  _0x5b7202.GET_FULL_CONTEXT = "focused-context:get-full-context";
6173|  return _0x5b7202;
6174|})(wt || {});
6175|function or(_0x480d35, _0x839b2e = 5000, _0x14e0f7 = "...") {
6176|  if (!_0x480d35) {
6177|    return _0x480d35;
6178|  }
6179|  const _0xc45241 = _0x480d35.slice(0, 30000);
6180|  if (ss(_0xc45241) <= _0x839b2e) {
6181|    return _0xc45241;
6182|  }
6183|  const _0x458080 = ss(_0x14e0f7);
6184|  if (_0x839b2e <= _0x458080) {
6185|    return lr(_0xc45241, Math.max(0, _0x839b2e - _0x458080)) + "...";
6186|  }
6187|  const _0x354699 = _0x839b2e - _0x458080;
6188|  const _0x5fd242 = Math.ceil(_0x354699 / 2);
6189|  const _0x5a4dcb = Math.floor(_0x354699 / 2);
6190|  const _0x352b6f = lr(_0xc45241, _0x5fd242);
6191|  const _0x59d578 = sh(_0xc45241, _0x5a4dcb);
6192|  return "" + _0x352b6f + _0x14e0f7 + _0x59d578;
6193|}
6194|function lr(_0x183e52, _0x244173) {
6195|  if (_0x244173 <= 0) {
6196|    return "";
6197|  }
6198|  const _0x4ff4a5 = _0x183e52.length;
6199|  const _0x185e23 = ss(_0x183e52);
6200|  if (_0x185e23 <= _0x244173) {
6201|    return _0x183e52;
6202|  }
6203|  const _0xfc9cc5 = _0x244173 / _0x185e23;
6204|  const _0x52cb2b = Math.floor(_0x4ff4a5 * _0xfc9cc5);
6205|  let _0x3cf467 = Math.max(0, Math.floor(_0x52cb2b * 0.8));
6206|  let _0x4a15ff = Math.min(_0x4ff4a5, Math.ceil(_0x52cb2b * 1.2));
6207|  let _0x3abaae = 0;
6208|  let _0x5ba0d4 = 0;
6209|  const _0x465c84 = 10;
6210|  while (_0x3cf467 <= _0x4a15ff && _0x5ba0d4 < _0x465c84) {
6211|    const _0x44d9ad = Math.floor((_0x3cf467 + _0x4a15ff) / 2);
6212|    const _0x3dcb94 = _0x183e52.slice(0, _0x44d9ad);
6213|    if (ss(_0x3dcb94) <= _0x244173) {
6214|      _0x3abaae = _0x44d9ad;
6215|      _0x3cf467 = _0x44d9ad + 1;
6216|    } else {
6217|      _0x4a15ff = _0x44d9ad - 1;
6218|    }
6219|    _0x5ba0d4++;
6220|  }
6221|  return _0x183e52.slice(0, _0x3abaae);
6222|}
6223|function sh(_0x3fd17b, _0x460f70) {
6224|  if (_0x460f70 <= 0) {
6225|    return "";
6226|  }
6227|  const _0xb99ba9 = _0x3fd17b.length;
6228|  const _0x198385 = ss(_0x3fd17b);
6229|  if (_0x198385 <= _0x460f70) {
6230|    return _0x3fd17b;
6231|  }
6232|  const _0x149292 = _0x460f70 / _0x198385;
6233|  const _0x1db73b = Math.floor(_0xb99ba9 * _0x149292);
6234|  const _0xba9e8c = _0xb99ba9 - _0x1db73b;
6235|  let _0x16c7ed = Math.max(0, Math.floor(_0xba9e8c * 0.8));
6236|  let _0x3a2520 = Math.min(_0xb99ba9, Math.ceil(_0xba9e8c * 1.2));
6237|  let _0x4cb20a = _0xb99ba9;
6238|  let _0x3b40a9 = 0;
6239|  const _0x218614 = 10;
6240|  while (_0x16c7ed <= _0x3a2520 && _0x3b40a9 < _0x218614) {
6241|    const _0xda086 = Math.floor((_0x16c7ed + _0x3a2520) / 2);
6242|    const _0x417c2c = _0x3fd17b.slice(_0xda086);
6243|    if (ss(_0x417c2c) <= _0x460f70) {
6244|      _0x4cb20a = _0xda086;
6245|      _0x3a2520 = _0xda086 - 1;
6246|    } else {
6247|      _0x16c7ed = _0xda086 + 1;
6248|    }
6249|    _0x3b40a9++;
6250|  }
6251|  return _0x3fd17b.slice(_0x4cb20a);
6252|}
6253|function ss(_0x1f3ef4) {
6254|  if (!_0x1f3ef4 || _0x1f3ef4.length === 0) {
6255|    return 0;
6256|  }
6257|  const _0xa1bf18 = _0x1f3ef4.length;
6258|  const _0x35de30 = _0x1f3ef4.split(/\s+/).filter(_0x2b175b => _0x2b175b.length > 0).length;
6259|  if ((_0x1f3ef4.match(/[\u4e00-\u9fff]/g) || []).length / _0xa1bf18 > 0.3) {
6260|    return Math.ceil(_0xa1bf18 / 1.3);
6261|  } else {
6262|    return Math.ceil(Math.max(_0x35de30 * 1.3, _0xa1bf18 / 4));
6263|  }
6264|}
6265|const ih = _0x3a5d49 => {
6266|  if (!_0x3a5d49) {
6267|    return "";
6268|  }
6269|  try {
6270|    return new URL(_0x3a5d49).hostname;
6271|  } catch {
6272|    return "";
6273|  }
6274|};
6275|const ci = {
6276|  app_name: "Desktop App",
6277|  app_identifier: "-1",
6278|  window_title: "",
6279|  window_position: {
6280|    x: 0,
6281|    y: 0,
6282|    width: 0,
6283|    height: 0
6284|  },
6285|  app_type: "native_app",
6286|  app_metadata: {
6287|    process_id: 0,
6288|    app_path: "",
6289|    window_id: -1
6290|  },
6291|  visible_screen_content: undefined,
6292|  browser_context: undefined
6293|};
6294|const _n = {
6295|  input_area_type: "text_field",
6296|  accessibility_role: "",
6297|  position_on_screen: {
6298|    x: 0,
6299|    y: 0,
6300|    width: 0,
6301|    height: 0
6302|  },
6303|  input_capabilities: {
6304|    is_editable: true,
6305|    supports_markdown: false,
6306|    dom_id: undefined,
6307|    dom_classes: undefined
6308|  },
6309|  cursor_state: {
6310|    cursor_position: -1,
6311|    has_text_selected: false,
6312|    selected_text: "",
6313|    text_before_cursor: "",
6314|    text_after_cursor: "",
6315|    full_field_content: ""
6316|  },
6317|  surrounding_context: {
6318|    text_before_input_area: "",
6319|    text_after_input_area: ""
6320|  }
6321|};
6322|const cr = new Map();
6323|class nh extends ga {
6324|  constructor() {
6325|    super();
6326|    f(this, "lastFocusedStartTime", 0);
6327|    f(this, "lastFocusedEndTime", 0);
6328|    f(this, "lastFocusedAppInfo", {
6329|      ...ci
6330|    });
6331|    f(this, "lastFocusedInputInfo", {
6332|      ..._n
6333|    });
6334|    f(this, "timer", null);
6335|    f(this, "intervalTime", 1000);
6336|    f(this, "timerGetAppOptions", null);
6337|    f(this, "timerGetInputOptions", null);
6338|    f(this, "lastFocusedInfoTaskScheduler", new rc(2));
6339|    _0x9f44d5.whenReady().then(() => {
6340|      this.resetTimer();
6341|    });
6342|    _0x53e868.handle(wt.SET_LAST_FOCUSED_INFO_TIMER, (_0x1eaf4a, _0x2e2b0b) => this.setLastFocusedInfoTimer(_0x2e2b0b));
6343|    _0x53e868.handle(wt.GET_LAST_FOCUSED_INFO, () => this.getLastFocusedInfo());
6344|    _0x53e868.handle(wt.GET_FOCUSED_APP_INFO, (_0x430455, _0x4dbdf0) => this.getFocusedAppInfo(_0x4dbdf0));
6345|    _0x53e868.handle(wt.GET_FOCUSED_INPUT_INFO, (_0x5c6718, _0xb148ca) => this.getFocusedInputInfo(_0xb148ca));
6346|    _0x53e868.handle(wt.GET_SELECTED_TEXT, (_0x2af577, _0x416db0) => this.getSelectedText(_0x416db0));
6347|    _0x53e868.handle(wt.EXECUTE_LAST_FOCUSED_INFO_TASK, () => this.executeLastFocusedInfoTask());
6348|    _0x53e868.handle(wt.GET_FULL_CONTEXT, (_0x4307e4, _0x42b6e1) => this.getFullContext(_0x42b6e1));
6349|  }
6350|  resetTimer() {
6351|    if (this.timer) {
6352|      clearInterval(this.timer);
6353|      this.timer = null;
6354|    }
6355|    this.timer = setInterval(async () => {
6356|      this.executeLastFocusedInfoTask();
6357|    }, this.intervalTime);
6358|  }
6359|  async executeLastFocusedInfoTask() {
6360|    if (this.lastFocusedInfoTaskScheduler.pendingTasks.length > 0) {
6361|      this.lastFocusedInfoTaskScheduler.pendingTasks = [];
6362|    }
6363|    this.lastFocusedInfoTaskScheduler.scheduleTask(async () => {
6364|      const _0x491973 = await Nt.getInstance().getFocusedAppInfoAsync();
6365|      const _0x5d8f74 = Date.now();
6366|      const [_0x4010a9, _0x5bd1c0] = await Promise.all([this.getFocusedAppInfo({
6367|        appInfo: _0x491973,
6368|        ...this.timerGetAppOptions
6369|      }), this.getFocusedInputInfo({
6370|        appInfo: _0x491973,
6371|        ...this.timerGetInputOptions
6372|      })]);
6373|      const _0x5e5bfe = Date.now();
6374|      this.lastFocusedStartTime = _0x5d8f74;
6375|      this.lastFocusedEndTime = _0x5e5bfe;
6376|      this.lastFocusedAppInfo = _0x4010a9;
6377|      this.lastFocusedInputInfo = _0x5bd1c0;
6378|      const _0x322888 = {
6379|        appInfo: _0x4010a9,
6380|        inputInfo: _0x5bd1c0,
6381|        startTime: _0x5d8f74,
6382|        endTime: _0x5e5bfe
6383|      };
6384|      this.emit("onPollingFocusedInfo", _0x322888);
6385|    });
6386|  }
6387|  stopTimer() {
6388|    if (this.timer) {
6389|      clearInterval(this.timer);
6390|      this.timer = null;
6391|    }
6392|  }
6393|  async stopAndWait() {
6394|    this.stopTimer();
6395|    await this.lastFocusedInfoTaskScheduler.drainAndWait();
6396|  }
6397|  async setLastFocusedInfoTimer(_0x192153) {
6398|    if (typeof _0x192153.intervalTime == "number") {
6399|      this.intervalTime = _0x192153.intervalTime;
6400|    }
6401|    if (typeof _0x192153.timerGetAppOptions !== "undefined") {
6402|      this.timerGetAppOptions = _0x192153.timerGetAppOptions;
6403|    }
6404|    if (typeof _0x192153.timerGetInputOptions !== "undefined") {
6405|      this.timerGetInputOptions = _0x192153.timerGetInputOptions;
6406|    }
6407|    this.resetTimer();
6408|  }
6409|  async getLastFocusedInfo() {
6410|    return {
6411|      startTime: this.lastFocusedStartTime,
6412|      endTime: this.lastFocusedEndTime,
6413|      appInfo: this.lastFocusedAppInfo,
6414|      inputInfo: this.lastFocusedInputInfo
6415|    };
6416|  }
6417|  async getFocusedAppInfo(_0x21cf85) {
6418|    try {
6419|      const {
6420|        visibleTextParams: _0x993046
6421|      } = _0x21cf85 || {};
6422|      const _0x576604 = Nt.getInstance();
6423|      const _0x3f8818 = _0x21cf85?.appInfo || (await _0x576604.getFocusedAppInfoAsync());
6424|      if (_0x3f8818 == null || !_0x3f8818.appName) {
6425|        return {
6426|          ...ci
6427|        };
6428|      }
6429|      const _0x551dcf = _0x3f8818.appName === _0x9f44d5.getName();
6430|      let _0x3c3ba0;
6431|      if (_0x993046 && !_0x551dcf) {
6432|        const _0x2e5b88 = await Qt.getAppConfig(_0x3f8818.bundleId);
6433|        const _0x5d54c2 = await Qt.getUrlConfig(_0x3f8818.webURL);
6434|        if ((_0x2e5b88.isWhitelist || !_0x2e5b88.isBlacklist) && (_0x5d54c2.isWhitelist || !_0x5d54c2.isBlacklist)) {
6435|          _0x3c3ba0 = await _0x576604.getFocusedVisibleTextAsync(..._0x993046);
6436|        }
6437|      }
6438|      const _0x37dbae = ih(_0x3f8818.webURL);
6439|      return {
6440|        app_name: _0x3f8818.appName || "",
6441|        app_identifier: _0x3f8818.bundleId || "",
6442|        window_title: _0x3f8818.windowTitle || "",
6443|        window_position: _0x3f8818.windowBounds || {
6444|          x: 0,
6445|          y: 0,
6446|          width: 0,
6447|          height: 0
6448|        },
6449|        app_type: _0x3f8818.isWebBrowser ? "web_browser" : "native_app",
6450|        app_metadata: {
6451|          process_id: _0x3f8818.processId || -1,
6452|          app_path: _0x3f8818.bundlePath || "",
6453|          window_id: _0x3f8818.windowId || -1
6454|        },
6455|        visible_screen_content: _0x3c3ba0 || undefined,
6456|        browser_context: _0x3f8818.isWebBrowser || _0x3f8818.webTitle || _0x3f8818.webURL ? {
6457|          page_title: _0x3f8818.webTitle || "",
6458|          page_url: _0x37dbae && _0x3f8818.webURL || "",
6459|          domain: _0x37dbae
6460|        } : undefined
6461|      };
6462|    } catch {
6463|      return {
6464|        ...ci
6465|      };
6466|    }
6467|  }
6468|  async getFocusedInputInfo(_0x275a00) {
6469|    var _0x24a2ce;
6470|    try {
6471|      const _0x3a7426 = performance.now();
6472|      const {
6473|        inputStateParams: _0x2a3919,
6474|        relatedContentParams: _0x5e1ecc,
6475|        enableUploadMixpanel: _0x56d053,
6476|        maxSelectedTextTokens: _0x480bdb
6477|      } = _0x275a00 || {};
6478|      const _0x150094 = Nt.getInstance();
6479|      const _0x12d4c4 = _0x275a00?.appInfo || (await _0x150094.getFocusedAppInfoAsync());
6480|      const _0x333e1c = performance.now() - _0x3a7426;
6481|      let _0x53db7b = _0x12d4c4?.appName === _0x9f44d5.getName();
6482|      const _0x55e769 = performance.now() - _0x3a7426 - _0x333e1c;
6483|      let _0x3dba71 = {};
6484|      let _0x2dec61 = {};
6485|      let _0x4770aa = {};
6486|      if (_0x53db7b) {
6487|        _0x3dba71 = {
6488|          editable: true
6489|        };
6490|      } else {
6491|        _0x3dba71 = await _0x150094.getFocusedElementInfoAsync();
6492|      }
6493|      const _0x4dc2a6 = performance.now() - _0x3a7426 - _0x55e769;
6494|      if (_0x2a3919 && !_0x53db7b) {
6495|        _0x2dec61 = Ss.getInstance().getCurrentInputState(..._0x2a3919);
6496|        const _0x4e5a1c = performance.now() - _0x3a7426 - _0x4dc2a6;
6497|        he.log("inputState", _0x4e5a1c, _0x2dec61, "timeUsage", _0x4e5a1c, _0x4dc2a6, _0x55e769, _0x333e1c, _0x3a7426);
6498|      } else {
6499|        he.log("inputState", "NO", _0x2a3919, _0x53db7b);
6500|      }
6501|      if (_0x3dba71.editable && _0x5e1ecc && !_0x53db7b) {
6502|        const _0x4ea625 = await Qt.getAppConfig(_0x12d4c4.bundleId);
6503|        const _0x59b5fb = await Qt.getUrlConfig(_0x12d4c4.webURL);
6504|        if ((_0x4ea625.isWhitelist || !_0x4ea625.isBlacklist) && (_0x59b5fb.isWhitelist || !_0x59b5fb.isBlacklist)) {
6505|          _0x4770aa = await _0x150094.getFocusedElementRelatedContentAsync(..._0x5e1ecc);
6506|        }
6507|      }
6508|      if (!_0x53db7b && !_0x3dba71.editable && !_0x2dec61.beforeText && !_0x2dec61.afterText && _0x12d4c4.appName && _0x56d053) {
6509|        const _0x55e87c = _0x12d4c4.appName + (_0x12d4c4?.webURL || "");
6510|        if (!cr.get(_0x55e87c)) {
6511|          cr.set(_0x55e87c, "1");
6512|          bt("error_monitoring_undetectable_textbox_found", {
6513|            appName: _0x12d4c4.appName,
6514|            appBundleId: _0x12d4c4.bundleId,
6515|            webURL: _0x12d4c4.webURL,
6516|            webDomain: _0x12d4c4.webURL ? Qd(_0x12d4c4.webURL) : ""
6517|          });
6518|        }
6519|      }
6520|      if (_0x53db7b) {
6521|        _0x2dec61.startIndex = 0;
6522|        const _0x552312 = Ut.get();
6523|        const _0xba7c31 = Mt.get("userData");
6524|        if (!yn(_0xba7c31) && _0x552312 != null && _0x552312.onboardingStep) {
6525|          switch (_0x552312.onboardingStep) {
6526|            case z.DICTATION__EXAMPLE_1:
6527|              _0x3dba71.domIdentifier = fn.inputId;
6528|              _0x3dba71.editable = true;
6529|              break;
6530|            case z.DICTATION__EXAMPLE_2:
6531|              _0x3dba71.domIdentifier = gn.inputId;
6532|              _0x3dba71.editable = true;
6533|              break;
6534|            case z.DICTATION__EXAMPLE_3:
6535|              _0x3dba71.domIdentifier = pn.inputId;
6536|              _0x3dba71.editable = true;
6537|              break;
6538|            case z.TRANSLATION_MODE__EXAMPLE_1:
6539|              _0x3dba71.domIdentifier = mn.inputId;
6540|              _0x3dba71.editable = true;
6541|              break;
6542|            case z.ASK_ANYTHING__EXAMPLE_1:
6543|              _0x3dba71.domIdentifier = Zd.inputId;
6544|              _0x3dba71.editable = true;
6545|              break;
6546|            case z.ASK_ANYTHING__EXAMPLE_2:
6547|              _0x3dba71.editable = false;
6548|              break;
6549|            case z.ASK_ANYTHING__EXAMPLE_3:
6550|              _0x3dba71.editable = false;
6551|              break;
6552|            default:
6553|              break;
6554|          }
6555|        }
6556|      }
6557|      _0x2dec61.selectedText = _0x2dec61.selectedText ? or(_0x2dec61.selectedText, _0x480bdb) : "";
6558|      if (_0x12d4c4.isWebBrowser && (_0x24a2ce = _0x12d4c4.webURL) != null && _0x24a2ce.startsWith("https://www.notion.so/") && _0x3dba71.role === "AXWebArea") {
6559|        _0x2dec61.startIndex = 0;
6560|        _0x2dec61.endIndex = 0;
6561|        _0x2dec61.beforeText = "";
6562|        _0x2dec61.afterText = "";
6563|      }
6564|      return {
6565|        input_area_type: Gd(_0x12d4c4, _0x3dba71),
6566|        accessibility_role: _0x3dba71.role || "",
6567|        position_on_screen: _0x3dba71.bounds || {
6568|          x: 0,
6569|          y: 0,
6570|          width: 0,
6571|          height: 0
6572|        },
6573|        input_capabilities: {
6574|          is_editable: _0x3dba71.editable || false,
6575|          supports_markdown: $d(_0x12d4c4, _0x3dba71),
6576|          dom_id: _0x3dba71.domIdentifier,
6577|          dom_classes: _0x3dba71.domClassList
6578|        },
6579|        cursor_state: {
6580|          cursor_position: _0x2dec61.startIndex ?? -1,
6581|          has_text_selected: !!_0x2dec61.selectedText,
6582|          selected_text: _0x2dec61.selectedText,
6583|          text_before_cursor: _0x2dec61.beforeText || "",
6584|          text_after_cursor: _0x2dec61.afterText || "",
6585|          full_field_content: "" + (_0x2dec61.beforeText || "") + (_0x2dec61.selectedText || "") + (_0x2dec61.afterText || "")
6586|        },
6587|        surrounding_context: {
6588|          text_before_input_area: _0x4770aa?.beforeContent || "",
6589|          text_after_input_area: _0x4770aa?.afterContent || ""
6590|        }
6591|      };
6592|    } catch {
6593|      return {
6594|        ..._n
6595|      };
6596|    }
6597|  }
6598|  async getSelectedText(_0x4d830a) {
6599|    try {
6600|      const {
6601|        maxTokens: _0x2b9d20 = 5000,
6602|        disableSimulateCopy: _0x4629f8 = false
6603|      } = _0x4d830a || {};
6604|      let _0x360a99 = Ss.getInstance().getSelectedText();
6605|      if (!_0x4629f8) {
6606|        if (!_0x360a99 || _0x360a99.trim() === "") {
6607|          _0x360a99 = await Ss.getInstance().getSelectedTextBySimulateCopyAsync();
6608|        }
6609|      }
6610|      _0x360a99 = or(_0x360a99, _0x2b9d20);
6611|      return _0x360a99 || "";
6612|    } catch {
6613|      return "";
6614|    }
6615|  }
6616|  async prepareAccessibility() {
6617|    Nt.getInstance().setFocusedWindowEnhancedUserInterface();
6618|    await new Promise(_0x976560 => setTimeout(_0x976560, 30));
6619|    Qt.checkAccessibilityConfig();
6620|  }
6621|  async getFullContext(_0x416a1d) {
6622|    var _0x34350b;
6623|    try {
6624|      const {
6625|        focusedAppOptions: _0x2f0cfa,
6626|        focusedInputOptions: _0x4c982e
6627|      } = _0x416a1d || {};
6628|      await this.prepareAccessibility();
6629|      const _0x109f54 = Date.now();
6630|      const _0x100dac = await un.getSystemInfo();
6631|      const _0x3ba38d = Date.now() - _0x109f54;
6632|      const _0x584f02 = Nt.getInstance();
6633|      const _0x32302d = Date.now();
6634|      const _0xff737d = Date.now();
6635|      const _0xda255a = await _0x584f02.getFocusedAppInfoAsync();
6636|      let _0x13af37 = 0;
6637|      let _0x4921dc = 0;
6638|      const [_0x301d58, _0x35a9f1] = await Promise.all([this.getFocusedAppInfo({
6639|        appInfo: _0xda255a,
6640|        ..._0x2f0cfa
6641|      }).then(_0x5807b7 => {
6642|        _0x13af37 = Date.now() - _0x32302d;
6643|        return _0x5807b7;
6644|      }), this.getFocusedInputInfo({
6645|        appInfo: _0xda255a,
6646|        ..._0x4c982e
6647|      }).then(_0xbaa99b => {
6648|        _0x4921dc = Date.now() - _0xff737d;
6649|        return _0xbaa99b;
6650|      })]);
6651|      if (_0x301d58 && (_0x34350b = _0x35a9f1?.input_capabilities) != null && _0x34350b.dom_id) {
6652|        const _0x5f5778 = eh[_0x35a9f1.input_capabilities.dom_id];
6653|        if (_0x5f5778) {
6654|          hs(_0x301d58, {
6655|            ..._0x5f5778.appInfo
6656|          }, {
6657|            clone: false
6658|          });
6659|          hs(_0x35a9f1, {
6660|            ..._0x5f5778.focusedInput
6661|          }, {
6662|            clone: false
6663|          });
6664|        }
6665|      }
6666|      return {
6667|        device_environment: _0x100dac,
6668|        active_application: _0x301d58,
6669|        text_insertion_point: _0x35a9f1,
6670|        context_metadata: {
6671|          is_own_application: _0x301d58?.app_name === _0x9f44d5.getName(),
6672|          capture_timestamp: new Date().toISOString(),
6673|          capture_frequency: {
6674|            app_focus_count: _0x13af37,
6675|            input_field_focus_count: _0x4921dc,
6676|            system_info_refresh_count: _0x3ba38d
6677|          }
6678|        }
6679|      };
6680|    } catch {
6681|      return {
6682|        device_environment: {
6683|          ...tr
6684|        },
6685|        active_application: {
6686|          ...ci
6687|        },
6688|        text_insertion_point: {
6689|          ..._n
6690|        },
6691|        context_metadata: {
6692|          is_own_application: false,
6693|          capture_timestamp: new Date().toISOString(),
6694|          capture_frequency: {
6695|            app_focus_count: 0,
6696|            input_field_focus_count: 0,
6697|            system_info_refresh_count: 0
6698|          }
6699|        }
6700|      };
6701|    }
6702|  }
6703|}
6704|const Ae = new nh();
6705|const Is = _0x2d8e5b(import.meta.url)("koffi");
6706|const ah = () => _0x42ef8d.join(Se, "keyboard-helper", "build", "libKeyboardHelper.dylib");
6707|var vt;
6708|vt = class {
6709|  constructor() {
6710|    f(this, "lib");
6711|