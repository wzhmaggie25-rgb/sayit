// Source: typeless_src/cracked/deobfuscated.js, lines 3600-4280
// Typeless injection strategy system
// APP_STRATEGIES: app_blacklist, app_whitelist, url_blacklist, url_whitelist
// Matching functions: Ja (app match), Ya (URL match)
// Keyboard input: insert-text via keyboard hook + SendMessage
// Contains: blacklist domain fetching from server, local config merging

3600|    let _0x5ccf69 = _0x4811c7;
3601|    if (_0x5d8529.cacheKey) {
3602|      const _0x343c2c = _0x5d8529.cacheKey(..._0x4ded8c);
3603|      if (_0x343c2c) {
3604|        _0x5ccf69 = _0x4811c7 + "_" + _0x343c2c;
3605|      } else {
3606|        _0x5ccf69 = null;
3607|      }
3608|    } else if (_0x5d8529.cacheArgs) {
3609|      _0x5ccf69 = _0x4811c7 + "_" + JSON.stringify(_0x4ded8c);
3610|    }
3611|    if (!_0x5ccf69) {
3612|      return _0x35e758.apply(this, _0x4ded8c);
3613|    }
3614|    if (_0x28656d.has(_0x5ccf69)) {
3615|      return _0x28656d.get(_0x5ccf69);
3616|    }
3617|    const _0x4e48bf = _0x35e758.apply(this, _0x4ded8c).finally(() => {
3618|      _0x28656d.delete(_0x5ccf69);
3619|    });
3620|    _0x28656d.set(_0x5ccf69, _0x4e48bf);
3621|    return _0x4e48bf;
3622|  };
3623|  return _0x513b62;
3624|};
3625|const yd = {
3626|  version: "1.0.2",
3627|  app_blacklist: {
3628|    macos: {
3629|      exact: ["com.sublimetext.4", "com.tencent.xinWeChat", "com.microsoft.Excel", "com.kingsoft.wpsoffice.mac", "dev.zed.Zed"],
3630|      regex: []
3631|    },
3632|    windows: {
3633|      exact: ["weixin.exe", "dingtalk.exe", "warp.exe", "tencentdocs.exe", "cloudmusic.exe", "winword.exe", "powerpnt.exe", "excel.exe", "cmd.exe", "powershell.exe", "wt.exe", "WindowsTerminal.exe", "mintty.exe", "onenote.exe", "notepad++.exe", "sublime_text.exe", "Zoom.exe", "wps.exe", "et.exe", "wpp.exe", "wpspdf.exe", "soffice.bin", "WhatsApp.Root.exe", "WhatsApp.exe", "XshellCore.exe", "Xshell.exe"],
3634|      regex: []
3635|    }
3636|  },
3637|  app_whitelist: {
3638|    macos: {
3639|      exact: ["com.todesktop.230313mzl4w4u92", "com.tinyspeck.slackmacgap", "com.apple.mail", "com.figma.Desktop", "com.openai.atlas", "com.conductor.app", "com.github.wez.wezterm"],
3640|      regex: []
3641|    },
3642|    windows: {
3643|      exact: ["Cursor.exe", "WXWork.exe", "WeMail.exe", "AliIM.exe", "Zed.exe"],
3644|      regex: ["web.whatsapp.com"]
3645|    }
3646|  },
3647|  url_blacklist: {
3648|    exact: [],
3649|    prefix: ["https://docs.google.com/document/d", "https://docs.qq.com/doc/", "https://docs.qq.com/sheet/"],
3650|    domain: [],
3651|    regex: []
3652|  },
3653|  url_whitelist: {
3654|    exact: [],
3655|    prefix: ["https://www.figma.com/design/"],
3656|    domain: [],
3657|    regex: []
3658|  }
3659|};
3660|const Ja = (_0x4bcdb4, _0x3abba7) => {
3661|  if (!_0x4bcdb4 || !_0x3abba7) {
3662|    return false;
3663|  }
3664|  const _0x14d454 = _0x4bcdb4.windows;
3665|  return !!_0x14d454.exact.some(_0x1c6857 => _0x1c6857.toLowerCase() === _0x3abba7.toLowerCase()) || !!_0x14d454.regex.some(_0x2263d3 => new RegExp(_0x2263d3).test(_0x3abba7));
3666|};
3667|const Ya = (_0x22b24c, _0x184c1b) => !_0x22b24c || !_0x184c1b ? false : !!_0x22b24c.exact.some(_0x427679 => _0x427679.toLowerCase() === _0x184c1b.toLowerCase()) || !!_0x22b24c.regex.some(_0x4bab08 => new RegExp(_0x4bab08).test(_0x184c1b)) || !!_0x22b24c.prefix.some(_0x152e99 => _0x184c1b.toLowerCase().startsWith(_0x152e99.toLowerCase()));
3668|const _d = (_0x357c08, _0x2e78a9) => {
3669|  const _0x227b0 = _0x357c08.split(".").map(Number);
3670|  const _0x9168d6 = _0x2e78a9.split(".").map(Number);
3671|  const _0x3d6ead = Math.max(_0x227b0.length, _0x9168d6.length);
3672|  for (let _0x4fe07e = 0; _0x4fe07e < _0x3d6ead; _0x4fe07e++) {
3673|    const _0x509e23 = _0x227b0[_0x4fe07e] || 0;
3674|    const _0x4d02d8 = _0x9168d6[_0x4fe07e] || 0;
3675|    if (_0x509e23 > _0x4d02d8) {
3676|      return 1;
3677|    }
3678|    if (_0x509e23 < _0x4d02d8) {
3679|      return -1;
3680|    }
3681|  }
3682|  return 0;
3683|};
3684|class bd {
3685|  constructor(_0x26fece) {
3686|    f(this, "rsaCryptoService");
3687|    f(this, "inFlightPromise", null);
3688|    this.rsaCryptoService = _0x26fece;
3689|  }
3690|  async ensureConfigReady() {
3691|    if (this.rsaCryptoService.getConfig().publicKey !== null) {
3692|      return this.rsaCryptoService.getConfig();
3693|    }
3694|    if (!Qe.isLoggedIn()) {
3695|      return this.rsaCryptoService.getConfig();
3696|    }
3697|    if (this.inFlightPromise) {
3698|      return this.inFlightPromise;
3699|    }
3700|    this.inFlightPromise = this.fetchAndSetConfig();
3701|    try {
3702|      return await this.inFlightPromise;
3703|    } finally {
3704|      this.inFlightPromise = null;
3705|    }
3706|  }
3707|  async fetchAndSetConfig() {
3708|    var _0x5c49c4;
3709|    var _0x18a9c9;
3710|    var _0x3af1da;
3711|    var _0x48e469;
3712|    try {
3713|      const _0x194018 = await Ze.get("/user/get_user_info");
3714|      if (!_0x194018.success || (_0x5c49c4 = _0x194018.response) == null || !_0x5c49c4.ok) {
3715|        throw new Error(((_0x18a9c9 = _0x194018.error) == null ? undefined : _0x18a9c9.detail) || "Failed to fetch RSA key");
3716|      }
3717|      const _0x5be6e7 = ((_0x48e469 = (_0x3af1da = _0x194018.data) == null ? undefined : _0x3af1da.data) == null ? undefined : _0x48e469.rsa_public_key) ?? null;
3718|      const _0x394c45 = _0x5be6e7 !== null;
3719|      this.rsaCryptoService.setConfig(_0x5be6e7, _0x394c45);
3720|      return this.rsaCryptoService.getConfig();
3721|    } catch (_0x2f2400) {
3722|      throw _0x2f2400;
3723|    }
3724|  }
3725|}
3726|function Xa(_0x4576aa) {
3727|  if (typeof _0x4576aa != "object" || _0x4576aa === null) {
3728|    return false;
3729|  }
3730|  const _0x58b94b = _0x4576aa;
3731|  return _0x58b94b._encrypted === true && _0x58b94b._v === 1 && (_0x58b94b._type === "str" || _0x58b94b._type === "json") && typeof _0x58b94b._key == "string" && typeof _0x58b94b._data == "string";
3732|}
3733|const wd = 32;
3734|const vd = Buffer.alloc(12, 0);
3735|class Td {
3736|  constructor() {
3737|    f(this, "publicKey", null);
3738|    f(this, "enabled", false);
3739|    f(this, "rsaConfigCoordinatorService");
3740|    this.rsaConfigCoordinatorService = new bd(this);
3741|  }
3742|  setConfig(_0x226f42, _0x572d37) {
3743|    this.publicKey = _0x226f42;
3744|    this.enabled = _0x572d37;
3745|  }
3746|  getConfig() {
3747|    return {
3748|      publicKey: this.publicKey,
3749|      enabled: this.enabled
3750|    };
3751|  }
3752|  isEnabled() {
3753|    return this.enabled && this.publicKey !== null;
3754|  }
3755|  clear() {
3756|    this.publicKey = null;
3757|    this.enabled = false;
3758|  }
3759|  hasUsableKey() {
3760|    return this.enabled && this.publicKey !== null;
3761|  }
3762|  checkFailedReason(_0x4e7405, _0x4c15eb, _0x3fd8e6) {
3763|    if (_0x4e7405) {
3764|      if (_0x3fd8e6) {
3765|        return "node_crypto_error";
3766|      } else {
3767|        return "unknown_error";
3768|      }
3769|    } else if (_0x4c15eb) {
3770|      return "userinfo_fetch_failed";
3771|    } else {
3772|      return "missing_public_key";
3773|    }
3774|  }
3775|  async trackEncryptionFailure(_0x3ca04d) {
3776|    try {
3777|      const _0x4a9701 = await ni.getInstance().getCurrentUser();
3778|      if (_0x4a9701 == null || !_0x4a9701.user_id) {
3779|        return;
3780|      }
3781|      const _0x2c7a83 = {
3782|        event_key: "error_monitoring_rsa_encryption_failed",
3783|        client_user_id: _0x4a9701.client_user_id || _0x4a9701.user_id,
3784|        data: {
3785|          environment: aa === "now.typeless.desktop" ? "production" : "development",
3786|          event_source: Bi ? "desktop_macos" : "desktop_windows",
3787|          typeless_app_version: Ht,
3788|          ..._0x3ca04d
3789|        }
3790|      };
3791|      const _0x4db169 = qi(_0x2c7a83);
3792|      await Ze.post("/app/metrics_mp", {
3793|        body: JSON.stringify({
3794|          info: _0x4db169
3795|        })
3796|      });
3797|    } catch {}
3798|  }
3799|  async encryptValue(_0x42f27d, _0x89ff6a) {
3800|    if (_0x42f27d == null || Xa(_0x42f27d) || Oc(_0x42f27d)) {
3801|      return _0x42f27d;
3802|    }
3803|    const _0x5da78e = _0x89ff6a.fallback ?? true;
3804|    const _0x271023 = _0x89ff6a.context ?? "";
3805|    let _0x337870;
3806|    let _0x2113ad;
3807|    if (!this.hasUsableKey()) {
3808|      try {
3809|        await this.rsaConfigCoordinatorService.ensureConfigReady();
3810|      } catch (_0x23bfad) {
3811|        _0x337870 = _0x23bfad;
3812|      }
3813|    }
3814|    if (this.hasUsableKey()) {
3815|      try {
3816|        return await this.rsaAesEncrypt(_0x42f27d, this.publicKey);
3817|      } catch (_0x9bcde5) {
3818|        _0x2113ad = _0x9bcde5;
3819|      }
3820|    }
3821|    const _0xce47e8 = this.checkFailedReason(this.hasUsableKey(), _0x337870, _0x2113ad);
3822|    const _0xea78d7 = _0x2113ad instanceof Error ? _0x2113ad.message : _0x337870 instanceof Error ? _0x337870.message : undefined;
3823|    let _0x1f50ba = _0x42f27d;
3824|    let _0x3b2a52 = false;
3825|    if (_0x5da78e) {
3826|      _0x1f50ba = qi(_0x42f27d);
3827|      _0x3b2a52 = true;
3828|    }
3829|    this.trackEncryptionFailure({
3830|      reason: _0xce47e8,
3831|      context: _0x271023,
3832|      fallback_enabled: _0x5da78e,
3833|      fallback_used: _0x3b2a52,
3834|      has_public_key: this.hasUsableKey(),
3835|      error_message: _0xea78d7
3836|    });
3837|    return _0x1f50ba;
3838|  }
3839|  async rsaAesEncrypt(_0x13ab9c, _0x2e5097) {
3840|    const _0x5a7402 = typeof _0x13ab9c == "string" ? "str" : "json";
3841|    const _0x480e49 = typeof _0x13ab9c == "string" ? _0x13ab9c : JSON.stringify(_0x13ab9c);
3842|    const _0x6f8441 = _0x4dea1d(wd);
3843|    const _0x5a85fb = _0x31f5a5({
3844|      key: _0x2e5097,
3845|      padding: _0x1d4479.RSA_PKCS1_OAEP_PADDING,
3846|      oaepHash: "sha256"
3847|    }, _0x6f8441);
3848|    const _0x32fb6e = _0x15cd8f("aes-256-gcm", _0x6f8441, vd);
3849|    let _0x1dcf2d = _0x32fb6e.update(_0x480e49, "utf8");
3850|    _0x1dcf2d = Buffer.concat([_0x1dcf2d, _0x32fb6e.final()]);
3851|    const _0x2f4549 = _0x32fb6e.getAuthTag();
3852|    const _0x274b0a = Buffer.concat([_0x1dcf2d, _0x2f4549]);
3853|    return {
3854|      _encrypted: true,
3855|      _v: 1,
3856|      _type: _0x5a7402,
3857|      _key: _0x5a85fb.toString("base64"),
3858|      _data: _0x274b0a.toString("base64")
3859|    };
3860|  }
3861|  async getRSAConfig() {
3862|    return this.getConfig();
3863|  }
3864|}
3865|const lt = new Td();
3866|async function rn(_0x3f6cd6, _0x5db952 = {}) {
3867|  return await lt.encryptValue(_0x3f6cd6, _0x5db952);
3868|}
3869|const Mt = new _0x291121({
3870|  name: "app-storage",
3871|  schema: {},
3872|  migrations: {}
3873|});
3874|const Sd = () => {
3875|  const _0x1eeffd = _0x94e596.hostname();
3876|  const _0x295e72 = _0x94e596.platform();
3877|  const _0x32aedc = _0x94e596.arch();
3878|  const _0x34df02 = _0x94e596.userInfo();
3879|  const _0x2adf28 = _0x535c7c.createHash("sha256").update(_0x1eeffd + "-" + _0x295e72 + "-" + _0x32aedc + "-" + _0x34df02.username).digest("hex");
3880|  const _0x32fbdd = _0x9f44d5.getName();
3881|  return _0x535c7c.pbkdf2Sync(_0x2adf28 + _0x32fbdd, "electron-user-service", 10000, 32, "sha256");
3882|};
3883|const Id = _0x9f44d5.getPath("userData");
3884|const ii = Id + "/user-data.json";
3885|const Qa = class Rs {
3886|  constructor() {
3887|    f(this, "currentUser", null);
3888|    f(this, "store");
3889|    f(this, "encryptionKey");
3890|    this.encryptionKey = this.generateEncryptionKey();
3891|    this.migrateUserData();
3892|    try {
3893|      this.store = new _0x291121({
3894|        name: "user-data",
3895|        encryptionKey: this.encryptionKey
3896|      });
3897|    } catch {
3898|      if (_0xae798e.existsSync(ii)) {
3899|        _0xae798e.unlinkSync(ii);
3900|      }
3901|      this.store = new _0x291121({
3902|        name: "user-data",
3903|        encryptionKey: this.encryptionKey
3904|      });
3905|    }
3906|    if (this.currentUser) {
3907|      this.saveUserData();
3908|    }
3909|    this.loadUserData();
3910|  }
3911|  static getInstance() {
3912|    Rs.instance ||= new Rs();
3913|    return Rs.instance;
3914|  }
3915|  async getUserId() {
3916|    if (this.currentUser && this.currentUser.user_id) {
3917|      return this.currentUser.user_id;
3918|    } else {
3919|      return null;
3920|    }
3921|  }
3922|  generateEncryptionKey() {
3923|    const _0x55bbef = _0x94e596.platform();
3924|    const _0x4d3ab2 = _0x94e596.arch();
3925|    const _0x3ae470 = _0x535c7c.createHash("sha256").update(_0x55bbef + "-" + _0x4d3ab2).digest("hex");
3926|    const _0x330b33 = _0x9f44d5.getName();
3927|    return _0x535c7c.pbkdf2Sync(_0x3ae470 + _0x330b33, "typeless-user-service", 10000, 32, "sha256");
3928|  }
3929|  async login(_0x539d17) {
3930|    try {
3931|      lt.clear();
3932|      this.currentUser = {
3933|        ..._0x539d17,
3934|        login_time: Date.now()
3935|      };
3936|      await this.saveUserData();
3937|      this.notifyUserStateChange("login", this.currentUser);
3938|      return true;
3939|    } catch {
3940|      return false;
3941|    }
3942|  }
3943|  async logout() {
3944|    try {
3945|      const _0x232fbe = this.currentUser;
3946|      this.currentUser = null;
3947|      await this.clearUserData();
3948|      this.notifyUserStateChange("logout", _0x232fbe);
3949|      Mt.clear();
3950|      lt.clear();
3951|      return true;
3952|    } catch {
3953|      return false;
3954|    }
3955|  }
3956|  getCurrentUser() {
3957|    return this.currentUser;
3958|  }
3959|  isLoggedIn() {
3960|    return this.currentUser !== null;
3961|  }
3962|  async saveUserData() {
3963|    if (this.currentUser) {
3964|      try {
3965|        const _0x290949 = JSON.stringify(this.currentUser);
3966|        this.store.set("userData", _0x290949);
3967|      } catch (_0x239fb2) {
3968|        throw _0x239fb2;
3969|      }
3970|    }
3971|  }
3972|  loadUserData() {
3973|    try {
3974|      const _0x456583 = this.store.get("userData");
3975|      if (!_0x456583) {
3976|        return;
3977|      }
3978|      this.currentUser = JSON.parse(_0x456583);
3979|    } catch {
3980|      this.clearUserData();
3981|    }
3982|  }
3983|  async clearUserData() {
3984|    try {
3985|      this.store.delete("userData");
3986|    } catch {}
3987|  }
3988|  migrateUserData() {
3989|    const _0x439750 = Sd();
3990|    if (_0x439750 && _0xae798e.existsSync(ii)) {
3991|      try {
3992|        const _0x2a8258 = new _0x291121({
3993|          name: "user-data",
3994|          encryptionKey: _0x439750
3995|        }).get("userData");
3996|        if (_0x2a8258) {
3997|          this.currentUser = JSON.parse(_0x2a8258);
3998|        }
3999|        _0xae798e.unlinkSync(ii);
4000|      } catch {}
4001|    }
4002|  }
4003|  notifyUserStateChange(_0x2368ff, _0xe2574d) {
4004|    _0x1ec5f7.getAllWindows().forEach(_0x46f696 => {
4005|      _0x46f696.webContents.send("user-state-change", {
4006|        action: _0x2368ff,
4007|        user: _0x2368ff === "login" ? _0xe2574d : null,
4008|        timestamp: Date.now()
4009|      });
4010|    });
4011|  }
4012|};
4013|f(Qa, "instance");
4014|let ni = Qa;
4015|const Qe = ni.getInstance();
4016|const on = {
4017|  darwin: {
4018|    dictationMode: ["Fn"],
4019|    askAnythingMode: ["Fn+Space"],
4020|    translationMode: ["Fn+LeftShift"],
4021|    pasteLastTranscript: ["Ctrl+Cmd+V"]
4022|  },
4023|  win32: {
4024|    dictationMode: ["RightAlt"],
4025|    askAnythingMode: ["RightAlt+Space"],
4026|    translationMode: ["RightAlt+RightShift"],
4027|    pasteLastTranscript: ["LeftCtrl+RightShift+V"]
4028|  },
4029|  linux: {
4030|    dictationMode: ["RightAlt"],
4031|    askAnythingMode: ["RightAlt+Space"],
4032|    translationMode: ["RightAlt+RightShift"],
4033|    pasteLastTranscript: ["LeftCtrl+RightShift+V"]
4034|  }
4035|};
4036|const ai = () => {
4037|  switch (yt) {
4038|    case "darwin":
4039|      return on.darwin;
4040|    case "win32":
4041|      return on.win32;
4042|    default:
4043|      return on.linux;
4044|  }
4045|};
4046|function kd(_0x2ad756) {
4047|  return ai()[_0x2ad756][0];
4048|}
4049|const j = new _0x291121({
4050|  name: "app-settings",
4051|  schema: {
4052|    featureShortcutBindings: {
4053|      default: ai()
4054|    },
4055|    microphoneDevices: {
4056|      default: []
4057|    },
4058|    selectedMicrophoneDevice: {
4059|      default: null
4060|    },
4061|    preferredLanguage: {
4062|      default: ""
4063|    },
4064|    autoSelectLanguages: {
4065|      default: false
4066|    },
4067|    selectedLanguages: {
4068|      default: []
4069|    },
4070|    launchAtSystemStartup: {
4071|      default: true
4072|    },
4073|    showFlowBarOnDesktop: {
4074|      default: false
4075|    },
4076|    enableInteractionSoundEffects: {
4077|      default: true
4078|    },
4079|    enableShowAppInDock: {
4080|      default: true
4081|    },
4082|    historyDurationSeconds: {
4083|      default: -1
4084|    },
4085|    enabledMuteBackgroundAudio: {
4086|      default: true
4087|    },
4088|    __DEV_API_HOST: {
4089|      default: ""
4090|    },
4091|    releaseNotesShownVersions: {
4092|      default: {}
4093|    },
4094|    __COMPATIBLE_V0_3_0_SELECTED_LANGUAGES_FLAG: {
4095|      default: false
4096|    },
4097|    enabledOpusCompression: {
4098|      default: true
4099|    },
4100|    dynamicMicrophoneDegradationEnabled: {
4101|      default: true
4102|    },
4103|    preferredBuiltInMicId: {
4104|      default: null
4105|    },
4106|    translationModeTargetLanguageCode: {
4107|      default: null
4108|    },
4109|    __COMPATIBLE_TRANSLATION_MODE_SHORTCUT_CHECKED_FLAG: {
4110|      default: false
4111|    },
4112|    __COMPATIBLE_FEATURE_SHORTCUT_BINDINGS_MIGRATED_FLAG: {
4113|      default: false
4114|    }
4115|  },
4116|  migrations: {}
4117|});
4118|class Ed {
4119|  constructor() {
4120|    f(this, "API_HOST", Ni);
4121|    f(this, "isDev", false);
4122|    ws.request.use(sn(async () => {
4123|      const _0x4ce771 = await Qe.getCurrentUser();
4124|      return {
4125|        userId: _0x4ce771?.user_id,
4126|        token: _0x4ce771?.refresh_token
4127|      };
4128|    }, ["/oauth/refresh_access_token", "/get_blacklist_domain"]));
4129|    ws.response.use(nn(() => {}));
4130|    const _0x1081d8 = j.get("__DEV_API_HOST");
4131|    if (_0x1081d8) {
4132|      this.API_HOST = _0x1081d8;
4133|      this.isDev = !_0x1081d8.includes("typeless.com") && !_0x1081d8.includes("typeless.now");
4134|    }
4135|  }
4136|  getHttpApiHost() {
4137|    if (this.API_HOST.startsWith("http")) {
4138|      return this.API_HOST;
4139|    } else if (this.API_HOST.includes("typeless.com") || this.API_HOST.includes("typeless.now")) {
4140|      return "https://" + this.API_HOST;
4141|    } else {
4142|      return "http://" + this.API_HOST;
4143|    }
4144|  }
4145|  getWssApiHost() {
4146|    const _0x578563 = this.API_HOST.replace(/^https?:\/\//, "");
4147|    return (this.API_HOST.startsWith("https") || this.API_HOST.includes("typeless.com") || this.API_HOST.includes("typeless.now") ? "wss:" : "ws:") + "//" + _0x578563;
4148|  }
4149|  buildUrl(_0x14c153) {
4150|    const _0x417525 = this.getHttpApiHost();
4151|    if (_0x14c153.startsWith("http")) {
4152|      return _0x14c153;
4153|    } else {
4154|      return "" + _0x417525 + (_0x14c153.startsWith("/") ? _0x14c153 : "/" + _0x14c153);
4155|    }
4156|  }
4157|  async get(_0x3cb4b8, _0x310cec = {}) {
4158|    return ws.fetch(this.buildUrl(_0x3cb4b8), {
4159|      method: "GET",
4160|      ..._0x310cec
4161|    });
4162|  }
4163|  async post(_0x1840f8, _0x3d5f58 = {}) {
4164|    return ws.fetch(this.buildUrl(_0x1840f8), {
4165|      method: "POST",
4166|      ..._0x3d5f58,
4167|      params: {
4168|        ..._0x3d5f58.params
4169|      }
4170|    });
4171|  }
4172|  async delete(_0x555527, _0x423768 = {}) {
4173|    return ws.fetch(this.buildUrl(_0x555527), {
4174|      method: "DELETE",
4175|      ..._0x423768
4176|    });
4177|  }
4178|}
4179|const Ze = new Ed();
4180|var xd = Object.defineProperty;
4181|var Cd = Object.getOwnPropertyDescriptor;
4182|var Ad = (_0x8225cd, _0x1dac75, _0xb8024c, _0x3723be) => {
4183|  var _0xa3cec = Cd(_0x1dac75, _0xb8024c);
4184|  for (var _0x2a08da = _0x8225cd.length - 1, _0x5076a6; _0x2a08da >= 0; _0x2a08da--) {
4185|    if (_0x5076a6 = _0x8225cd[_0x2a08da]) {
4186|      _0xa3cec = _0x5076a6(_0x1dac75, _0xb8024c, _0xa3cec) || _0xa3cec;
4187|    }
4188|  }
4189|  if (_0xa3cec) {
4190|    xd(_0x1dac75, _0xb8024c, _0xa3cec);
4191|  }
4192|  return _0xa3cec;
4193|};
4194|class Za {
4195|  constructor() {
4196|    f(this, "cacheService", new ma({
4197|      saveKey: "accessibilityConfig",
4198|      cacheTime: ma.DAILY
4199|    }));
4200|  }
4201|  async fetchAccessibilityConfig() {
4202|    const _0xae1b11 = await Ze.get("/app/get_blacklist_domain", {
4203|      method: "POST",
4204|      params: {}
4205|    });
4206|    if (_0xae1b11.success && _0xae1b11.data) {
4207|      const _0x4b248b = Lc(_0xae1b11.data.data);
4208|      if (Object.keys(_0x4b248b).length === 0) {
4209|        return null;
4210|      } else {
4211|        return _0x4b248b;
4212|      }
4213|    }
4214|    return null;
4215|  }
4216|  async checkAccessibilityConfig(_0x11f94a) {
4217|    let _0x5bd21f = await this.cacheService.get();
4218|    if (_0x11f94a || _0x5bd21f.expired) {
4219|      const _0x2a026a = await this.fetchAccessibilityConfig();
4220|      if (_0x2a026a) {
4221|        _0x5bd21f = await this.cacheService.sync(_0x2a026a);
4222|      }
4223|    }
4224|    return _0x5bd21f;
4225|  }
4226|  async getAccessibilityConfig() {
4227|    let _0x50938c = yd;
4228|    const _0x459773 = await this.cacheService.get();
4229|    if (_0x459773.data && _d(_0x50938c.version, _0x459773.data.version) < 0) {
4230|      _0x50938c = _0x459773.data;
4231|    }
4232|    return _0x50938c;
4233|  }
4234|  async getAppConfig(_0x4afa20) {
4235|    if (!_0x4afa20) {
4236|      return {
4237|        isWhitelist: false,
4238|        isBlacklist: false
4239|      };
4240|    }
4241|    const _0x1045ad = await this.getAccessibilityConfig();
4242|    const _0x4682cf = Ja(_0x1045ad.app_whitelist, _0x4afa20);
4243|    const _0x120fde = Ja(_0x1045ad.app_blacklist, _0x4afa20);
4244|    return {
4245|      isWhitelist: _0x4682cf,
4246|      isBlacklist: _0x120fde
4247|    };
4248|  }
4249|  async getUrlConfig(_0x406c51) {
4250|    if (!_0x406c51) {
4251|      return {
4252|        isBlacklist: false,
4253|        isWhitelist: false
4254|      };
4255|    }
4256|    const _0x3b82d3 = await this.getAccessibilityConfig();
4257|    const _0x4f4888 = Ya(_0x3b82d3.url_whitelist, _0x406c51);
4258|    const _0x2661b6 = Ya(_0x3b82d3.url_blacklist, _0x406c51);
4259|    return {
4260|      isWhitelist: _0x4f4888,
4261|      isBlacklist: _0x2661b6
4262|    };
4263|  }
4264|}
4265|Ad([md()], Za.prototype, "checkAccessibilityConfig");
4266|const Qt = new Za();
4267|const ln = new _0x291121({
4268|  name: "app-settings",
4269|  schema: {
4270|    windowSizeMap: {
4271|      default: {}
4272|    }
4273|  },
4274|  migrations: {}
4275|});
4276|class Zt {
4277|  constructor() {
4278|    f(this, "windowInstance");
4279|    this.windowInstance = null;
4280|  }
4281|