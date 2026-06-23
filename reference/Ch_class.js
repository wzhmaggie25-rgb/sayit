// Source: typeless_src/cracked/deobfuscated.js, lines 8409-8819
// Typeless floating window Ch class (extends Zt)
// Methods: createWindow, getWindowOptions, setupMouseTracking,
//   startMouseDetection, stopMouseDetection, moveWindowToDisplay,
//   calculateWindowHeight, destroyWindow, setIgnoreMouseEvents wrapper

8409|class Ch extends Zt {
8410|  constructor() {
8411|    super(...arguments);
8412|    f(this, "mouseTracker", null);
8413|    f(this, "currentDisplay", null);
8414|    f(this, "mouseDetectorInterval", null);
8415|    f(this, "elementPositions", []);
8416|    f(this, "lastIsMouseInside", null);
8417|  }
8418|  setAlwaysOnTopForWindows() {
8419|    {
8420|      const _0x126a28 = this.getWindow();
8421|      if (_0x126a28) {
8422|        _0x126a28.setAlwaysOnTop(true, "screen-saver", 1);
8423|        _0x126a28.setVisibleOnAllWorkspaces(true, {
8424|          visibleOnFullScreen: true,
8425|          skipTransformProcessType: true
8426|        });
8427|      }
8428|    }
8429|  }
8430|  calculateWindowHeight(_0x301c57) {
8431|    return gr;
8432|  }
8433|  getWindowOptions() {
8434|    const _0x32eb7f = _0xebb37d.getPrimaryDisplay();
8435|    const {
8436|      x: _0x31b872,
8437|      y: _0x2d0be9,
8438|      width: _0x1feb66,
8439|      height: _0x2feaf4
8440|    } = _0x32eb7f.workArea;
8441|    return {
8442|      x: _0x31b872,
8443|      y: _0x2d0be9,
8444|      type: "panel",
8445|      width: bn,
8446|      height: gr,
8447|      transparent: true,
8448|      frame: false,
8449|      hasShadow: false,
8450|      maximizable: false,
8451|      resizable: false,
8452|      minimizable: false,
8453|      focusable: false,
8454|      fullscreen: false,
8455|      webPreferences: {
8456|        nodeIntegration: false,
8457|        contextIsolation: true,
8458|        preload: xh
8459|      }
8460|    };
8461|  }
8462|  getWindowRoute() {
8463|    return Kt.FLOATING_BAR;
8464|  }
8465|  getWindowTitle() {
8466|    return ke("client:floating_bar__window__title");
8467|  }
8468|  createWindow() {
8469|    const _0x8f4e83 = super.createWindow();
8470|    if (_0x8f4e83) {
8471|      _0x8f4e83.setIgnoreMouseEvents(true, {
8472|        forward: false
8473|      });
8474|      _0x8f4e83.setAlwaysOnTop(true, "screen-saver", 1);
8475|      _0x8f4e83.setVisibleOnAllWorkspaces(true, {
8476|        visibleOnFullScreen: true,
8477|        skipTransformProcessType: true
8478|      });
8479|      _0x8f4e83.setFullScreenable(false);
8480|      this.setupMouseTracking();
8481|      this.startMouseDetection();
8482|      return _0x8f4e83;
8483|    } else {
8484|      return null;
8485|    }
8486|  }
8487|  setupMouseTracking() {
8488|    const _0x5b7666 = _0xebb37d.getCursorScreenPoint();
8489|    const _0x5e8b15 = _0xebb37d.getDisplayNearestPoint(_0x5b7666);
8490|    this.currentDisplay = _0x5e8b15;
8491|    this.moveWindowToDisplay(_0x5e8b15);
8492|    this.mouseTracker = setInterval(() => {
8493|      const _0x213ad5 = _0xebb37d.getCursorScreenPoint();
8494|      const _0x3f073a = _0xebb37d.getDisplayNearestPoint(_0x213ad5);
8495|      if (!this.currentDisplay || this.currentDisplay.id !== _0x3f073a.id) {
8496|        this.currentDisplay = _0x3f073a;
8497|        this.moveWindowToDisplay(_0x3f073a);
8498|      }
8499|    }, 100);
8500|  }
8501|  moveWindowToDisplay(_0x8c1bbe) {
8502|    var _0x54438d;
8503|    const {
8504|      x: _0x45b1e7,
8505|      y: _0x13834f,
8506|      width: _0x1ffa45,
8507|      height: _0x3ed78a
8508|    } = _0x8c1bbe.workArea;
8509|    const _0x49fd0d = this.calculateWindowHeight(_0x8c1bbe);
8510|    let _0x4d6eed = Math.floor(_0x45b1e7 + (_0x1ffa45 - bn) / 2);
8511|    if (!_0x9f44d5.isPackaged) {
8512|      _0x4d6eed -= 200;
8513|    }
8514|    const _0x4c970e = Math.floor(_0x13834f + _0x3ed78a - _0x49fd0d);
8515|    if ((_0x54438d = this.getWindow()) != null) {
8516|      _0x54438d.setBounds({
8517|        x: _0x4d6eed,
8518|        y: _0x4c970e,
8519|        width: bn,
8520|        height: _0x49fd0d
8521|      });
8522|    }
8523|  }
8524|  closeWindow() {
8525|    this.stopMouseDetection();
8526|    super.closeWindow();
8527|  }
8528|  updateElementPositions(_0x4dded6) {
8529|    this.elementPositions = _0x4dded6;
8530|  }
8531|  startMouseDetection() {
8532|    this.mouseDetectorInterval = setInterval(() => {
8533|      if (this.elementPositions.length === 0) {
8534|        const _0x2c5e73 = this.getWindow();
8535|        _0x2c5e73?.setIgnoreMouseEvents(true, {
8536|          forward: false
8537|        });
8538|        return;
8539|      }
8540|      const _0x2e4c1e = _0xebb37d.getCursorScreenPoint();
8541|      const _0x190f1b = this.elementPositions.some(_0x55b7ef => _0x2e4c1e.x >= _0x55b7ef.left && _0x2e4c1e.x <= _0x55b7ef.right && _0x2e4c1e.y >= _0x55b7ef.top && _0x2e4c1e.y <= _0x55b7ef.bottom);
8542|      if (_0x190f1b !== this.lastIsMouseInside) {
8543|        this.lastIsMouseInside = _0x190f1b;
8544|      }
8545|      const _0x5ab428 = this.getWindow();
8546|      _0x5ab428?.setIgnoreMouseEvents(!_0x190f1b, {
8547|        forward: false
8548|      });
8549|    }, 100);
8550|  }
8551|  stopMouseDetection() {
8552|    if (this.mouseDetectorInterval !== null) {
8553|      clearInterval(this.mouseDetectorInterval);
8554|      this.mouseDetectorInterval = null;
8555|    }
8556|    this.lastIsMouseInside = null;
8557|  }
8558|}
8559|const ce = new Ch();
8560|const Ah = _0x1dd89f.join(rt, "../preload/index.mjs");
8561|const Lh = 800;
8562|const wn = 800;
8563|const Oh = 500;
8564|const Ph = 20;
8565|const Dh = 80;
8566|const vn = 2;
8567|class Rh extends Zt {
8568|  constructor() {
8569|    super(...arguments);
8570|    f(this, "mouseTracker", null);
8571|    f(this, "currentDisplay", null);
8572|    f(this, "pendingCardPayload", null);
8573|    f(this, "rendererBoundsDebounceTimer", null);
8574|    f(this, "pendingReportedContentHeight", null);
8575|    f(this, "lastReportedContentHeight", null);
8576|  }
8577|  getTargetDisplay() {
8578|    try {
8579|      const _0x3fcbb5 = _0xebb37d.getCursorScreenPoint();
8580|      return _0xebb37d.getDisplayNearestPoint(_0x3fcbb5);
8581|    } catch {
8582|      return _0xebb37d.getPrimaryDisplay();
8583|    }
8584|  }
8585|  getLayoutContext(_0x8fa8c9) {
8586|    const _0xa07312 = _0x8fa8c9.workArea;
8587|    const _0x134130 = _0xa07312.y + _0xa07312.height - Ph;
8588|    const _0x2d1fb5 = Math.max(0, _0x134130 - _0xa07312.y);
8589|    return {
8590|      workArea: _0xa07312,
8591|      windowBottomY: _0x134130,
8592|      maxWindowHeight: _0x2d1fb5
8593|    };
8594|  }
8595|  moveWindowToDisplay(_0x2a3ad0) {
8596|    const _0x57b525 = this.getWindow();
8597|    if (!_0x57b525 || _0x57b525.isDestroyed()) {
8598|      return;
8599|    }
8600|    const _0x2f7e25 = _0x57b525.getBounds().height;
8601|    const _0x3f7b4a = this.lastReportedContentHeight ?? _0x2f7e25;
8602|    const _0x581b63 = this.getLayoutContext(_0x2a3ad0);
8603|    const _0x591949 = this.buildBounds({
8604|      ..._0x581b63,
8605|      height: _0x3f7b4a
8606|    });
8607|    _0x57b525.setBounds(_0x591949);
8608|  }
8609|  setupMouseTracking() {
8610|    const _0x46ac02 = _0xebb37d.getCursorScreenPoint();
8611|    const _0x3fc7bf = _0xebb37d.getDisplayNearestPoint(_0x46ac02);
8612|    this.currentDisplay = _0x3fc7bf;
8613|    this.moveWindowToDisplay(_0x3fc7bf);
8614|    this.mouseTracker = setInterval(() => {
8615|      const _0x44d452 = this.getWindow();
8616|      if (!_0x44d452 || _0x44d452.isDestroyed()) {
8617|        return;
8618|      }
8619|      const _0xf7d44f = _0xebb37d.getCursorScreenPoint();
8620|      const _0x5d4786 = _0xebb37d.getDisplayNearestPoint(_0xf7d44f);
8621|      if (!this.currentDisplay || this.currentDisplay.id !== _0x5d4786.id) {
8622|        this.currentDisplay = _0x5d4786;
8623|        this.moveWindowToDisplay(_0x5d4786);
8624|      }
8625|    }, 100);
8626|  }
8627|  stopMouseTracking() {
8628|    if (this.mouseTracker !== null) {
8629|      clearInterval(this.mouseTracker);
8630|      this.mouseTracker = null;
8631|    }
8632|    this.currentDisplay = null;
8633|  }
8634|  chooseInitialWindowHeight(_0x1c3972) {
8635|    if (_0x1c3972 >= wn) {
8636|      return wn;
8637|    } else {
8638|      return Math.min(Oh, _0x1c3972);
8639|    }
8640|  }
8641|  buildBounds(_0x1f3a80) {
8642|    const {
8643|      workArea: _0x4b08f2,
8644|      windowBottomY: _0x3f8f7e,
8645|      maxWindowHeight: _0x50fed9
8646|    } = _0x1f3a80;
8647|    let _0x38b1b3 = Math.round(_0x1f3a80.height);
8648|    _0x38b1b3 = Math.min(Math.max(_0x38b1b3, 1), _0x50fed9);
8649|    const _0x12da18 = Lh;
8650|    let _0x7c1e6a = _0x4b08f2.x + Math.floor(_0x4b08f2.width / 2) - Math.floor(_0x12da18 / 2);
8651|    _0x7c1e6a = Math.max(_0x4b08f2.x, Math.min(_0x7c1e6a, _0x4b08f2.x + _0x4b08f2.width - _0x12da18));
8652|    let _0x3beb64 = _0x3f8f7e - _0x38b1b3;
8653|    if (_0x3beb64 < _0x4b08f2.y) {
8654|      _0x3beb64 = _0x4b08f2.y;
8655|    }
8656|    if (_0x3beb64 + _0x38b1b3 > _0x4b08f2.y + _0x4b08f2.height) {
8657|      _0x3beb64 = _0x4b08f2.y + _0x4b08f2.height - _0x38b1b3;
8658|    }
8659|    return {
8660|      x: _0x7c1e6a,
8661|      y: _0x3beb64,
8662|      width: _0x12da18,
8663|      height: _0x38b1b3
8664|    };
8665|  }
8666|  computeInitialBounds() {
8667|    const _0x5be023 = this.getTargetDisplay();
8668|    const _0x4ad1eb = this.getLayoutContext(_0x5be023);
8669|    const _0x2d65c9 = this.chooseInitialWindowHeight(_0x4ad1eb.maxWindowHeight);
8670|    return this.buildBounds({
8671|      ..._0x4ad1eb,
8672|      height: _0x2d65c9
8673|    });
8674|  }
8675|  computeContentBounds(_0x33ab66) {
8676|    const _0x242728 = this.getWindow();
8677|    if (!_0x242728 || _0x242728.isDestroyed()) {
8678|      return null;
8679|    }
8680|    const _0x216b98 = this.getTargetDisplay();
8681|    const _0x3b7198 = this.getLayoutContext(_0x216b98);
8682|    const _0x261b13 = Math.round(_0x33ab66);
8683|    const _0x196e74 = Math.min(_0x261b13, _0x3b7198.maxWindowHeight);
8684|    return this.buildBounds({
8685|      ..._0x3b7198,
8686|      height: _0x196e74
8687|    });
8688|  }
8689|  getWindowOptions() {
8690|    const {
8691|      width: _0xd16c1f,
8692|      height: _0x3e0c09,
8693|      x: _0x5f279b,
8694|      y: _0x55f7d7
8695|    } = this.computeInitialBounds();
8696|    return {
8697|      x: _0x5f279b,
8698|      y: _0x55f7d7,
8699|      type: "panel",
8700|      width: _0xd16c1f,
8701|      height: _0x3e0c09,
8702|      title: this.getWindowTitle(),
8703|      frame: false,
8704|      transparent: true,
8705|      backgroundColor: "#00000000",
8706|      hasShadow: false,
8707|      maximizable: false,
8708|      minimizable: false,
8709|      resizable: false,
8710|      fullscreenable: false,
8711|      focusable: true,
8712|      show: false,
8713|      alwaysOnTop: true,
8714|      webPreferences: {
8715|        preload: Ah,
8716|        nodeIntegration: false,
8717|        contextIsolation: true
8718|      }
8719|    };
8720|  }
8721|  getWindowRoute() {
8722|    return Kt.INTERACTIVE_CARD;
8723|  }
8724|  getWindowTitle() {
8725|    return ke("client:floating_bar__window__title");
8726|  }
8727|  createWindow() {
8728|    const _0x330c54 = super.createWindow();
8729|    if (_0x330c54) {
8730|      _0x330c54.setAlwaysOnTop(true, "screen-saver", 1);
8731|      _0x330c54.setFullScreenable(false);
8732|      this.setupMouseTracking();
8733|      return _0x330c54;
8734|    } else {
8735|      return null;
8736|    }
8737|  }
8738|  getPendingPayload() {
8739|    return this.pendingCardPayload;
8740|  }
8741|  clearRendererBoundsDebounce() {
8742|    if (this.rendererBoundsDebounceTimer !== null) {
8743|      clearTimeout(this.rendererBoundsDebounceTimer);
8744|      this.rendererBoundsDebounceTimer = null;
8745|    }
8746|    this.pendingReportedContentHeight = null;
8747|    this.lastReportedContentHeight = null;
8748|  }
8749|  applyContentBounds(_0x982ee4) {
8750|    const _0x17abd3 = Math.round(_0x982ee4);
8751|    if (!Number.isFinite(_0x17abd3)) {
8752|      return false;
8753|    }
8754|    const _0x7192ae = Math.min(Math.max(_0x17abd3, 1), wn);
8755|    this.lastReportedContentHeight = _0x7192ae;
8756|    this.pendingReportedContentHeight = _0x7192ae;
8757|    if (this.rendererBoundsDebounceTimer !== null) {
8758|      clearTimeout(this.rendererBoundsDebounceTimer);
8759|    }
8760|    this.rendererBoundsDebounceTimer = setTimeout(() => {
8761|      this.rendererBoundsDebounceTimer = null;
8762|      const _0x58e094 = this.pendingReportedContentHeight;
8763|      this.pendingReportedContentHeight = null;
8764|      if (_0x58e094 === null || !Number.isFinite(_0x58e094)) {
8765|        return;
8766|      }
8767|      const _0x4db4ce = this.getWindow();
8768|      if (!_0x4db4ce || _0x4db4ce.isDestroyed()) {
8769|        return;
8770|      }
8771|      const _0x40b4e6 = this.computeContentBounds(_0x58e094);
8772|      if (!_0x40b4e6) {
8773|        return;
8774|      }
8775|      const _0x1c6622 = _0x4db4ce.getBounds();
8776|      if (!(Math.abs(_0x1c6622.height - _0x40b4e6.height) <= vn) || !(Math.abs(_0x1c6622.x - _0x40b4e6.x) <= vn) || !(Math.abs(_0x1c6622.y - _0x40b4e6.y) <= vn)) {
8777|        _0x4db4ce.setBounds(_0x40b4e6);
8778|      }
8779|    }, Dh);
8780|    return true;
8781|  }
8782|  updateBoundsWithContentHeight(_0x58f8d7) {
8783|    return this.applyContentBounds(_0x58f8d7);
8784|  }
8785|  openOrUpdate(_0x5343ab) {
8786|    this.pendingCardPayload = _0x5343ab;
8787|    const _0x2c4d8f = this.getWindow();
8788|    if (_0x2c4d8f && !_0x2c4d8f.isDestroyed()) {
8789|      this.clearRendererBoundsDebounce();
8790|      this.sendMessage("interactive-card:update", _0x5343ab);
8791|      _0x2c4d8f.show();
8792|      return;
8793|    }
8794|    this.clearRendererBoundsDebounce();
8795|    this.createWindow();
8796|  }
8797|  closeInteractiveCard() {
8798|    this.clearRendererBoundsDebounce();
8799|    this.pendingCardPayload = null;
8800|    this.closeWindow();
8801|  }
8802|  closeWindow() {
8803|    this.stopMouseTracking();
8804|    super.closeWindow();
8805|  }
8806|}
8807|const ut = new Rh();
8808|const Tn = _0xbd0cf1 => _0xbd0cf1.replace("KeypadAdd", "keypadadd").replace("NumpadAdd", "numpadadd").split("+").map(_0x38bd08 => _0x38bd08 === "keypadadd" ? "KeypadAdd" : _0x38bd08 === "numpadadd" ? "NumpadAdd" : _0x38bd08);
8809|var dt = (_0x34bf31 => {
8810|  _0x34bf31.START_INPUT_LISTENER = "keyboard-input:start-input-listener";
8811|  _0x34bf31.STOP_INPUT_LISTENER = "keyboard-input:stop-input-listener";
8812|  _0x34bf31.RELOAD_KEYBOARD_SHORTCUTS = "keyboard-input:reload-keyboard-shortcuts";
8813|  _0x34bf31.RESET_PRESSING_KEYCODES = "keyboard-input:reset-pressing-keycodes";
8814|  _0x34bf31.SET_WATCHER_INTERVAL = "keyboard-input:set-watcher-interval";
8815|  _0x34bf31.GET_KEYBOARD_DEVICE_LIST = "keyboard-input:get-keyboard-device-list";
8816|  _0x34bf31.INSERT_TEXT = "keyboard-input:insert-text";
8817|  _0x34bf31.INSERT_RICH_TEXT = "keyboard-input:insert-rich-text";
8818|  return _0x34bf31;
8819|})(dt || {});
8820|