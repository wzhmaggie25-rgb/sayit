# SayIt Account, Distribution, Update and Community Roadmap

> 状态：DISCUSSION_DRAFT
> 日期：2026-06-27
> 说明：本文件只记录产品和架构方向，不在当前 runtime bugfix 分支实施。

## 一、用户需求

用户希望未来 SayIt 支持：

1. 微信登录；
2. 用户可以下载安装；
3. 软件可以检测并安装升级；
4. 用户可以加入微信群或用户社群；
5. 后续可能扩展试用、授权、订阅、设备管理和云同步。

## 二、推荐拆分

不能把“登录、下载、升级、进群”做成一个 Electron 页面加几个按钮。这实际上需要三套系统：

```text
SayIt Windows 客户端
SayIt 账号与发布后端
SayIt 官网/下载与运营后台
```

## 三、账号系统

### 3.1 第一阶段账号目标

账号先只承担：

- 识别用户；
- 记录设备；
- 获取当前版本和更新渠道；
- 展示用户群入口；
- 后续承接试用/授权。

第一版不上传：

- 语音录音；
- 输入正文；
- 本地历史；
- 个人词典；
- API key。

### 3.2 微信登录推荐流程

桌面客户端不能保存微信 AppSecret。

推荐：

```text
客户端请求一次性 login_session
→ 打开 SayIt 登录网页/显示官方微信登录二维码
→ 用户用微信扫码确认
→ SayIt 后端完成微信 OAuth 回调
→ 后端把 login_session 标记为成功
→ 客户端轮询或通过 WebSocket 收到一次性 exchange_code
→ 客户端换取 SayIt access_token + refresh_token
```

客户端只保存 SayIt 自己签发的 token，使用 Windows Credential Manager/DPAPI，不把长期 token 明文写入 config.json。

需要后端数据：

```text
users
wechat_identities
devices
login_sessions
refresh_tokens
licenses/entitlements（后续）
```

### 3.3 登录策略

推荐第一版：

- 基础本地输入功能可以游客使用；
- 登录用于更新、社群、设备管理、试用授权；
- 不要一开始强制登录后才能录音，避免发布时登录故障导致软件完全不可用；
- 商业化后再决定免费额度或试用到期策略。

## 四、下载与安装

### 4.1 官网

至少包括：

- 产品介绍；
- Windows 下载；
- 当前版本；
- 更新日志；
- 系统要求；
- 隐私说明；
- 常见问题；
- 登录入口；
- 联系客服/加入群聊。

### 4.2 Windows 安装包

推荐生成：

```text
SayIt-Setup-x.y.z.exe
```

要求：

- 安装/卸载；
- 开始菜单和桌面快捷方式；
- 单实例；
- 保留用户本地数据库和配置；
- 升级不覆盖用户词典、历史和密钥；
- 代码签名；
- 安装包 SHA-256；
- 发布清单和 SBOM（后续）。

不要让普通用户运行源码、Python 或 Agent Bridge。发布包只包含正式客户端和后端可执行文件。

## 五、版本检测与升级

### 5.1 更新元数据

后端/对象存储提供签名 manifest：

```json
{
  "channel": "stable",
  "version": "1.0.3",
  "minimum_supported_version": "1.0.0",
  "mandatory": false,
  "notes_url": "...",
  "installer_url": "...",
  "sha256": "...",
  "signature": "..."
}
```

### 5.2 客户端行为

- 启动后延迟检查，不阻塞主功能；
- 设置页支持手动检查；
- stable/beta 两个渠道；
- 下载前校验 HTTPS、签名和 SHA-256；
- 下载完成后提示安装，不在录音或处理中强制退出；
- 更新失败继续运行旧版本；
- 强制更新只用于真正不兼容/安全问题；
- 保留最近一个可回滚安装包或提供重新下载旧稳定版。

### 5.3 发布基础设施

中国大陆用户优先使用自有对象存储/CDN，而不是把 GitHub Releases 当唯一下载源。

发布流程：

```text
CI 构建
→ 自动测试
→ 生成签名安装包
→ 生成哈希和 manifest
→ 上传对象存储/CDN
→ 发布版本记录
→ 客户端检测更新
```

## 六、加入用户群

第一版不要尝试让 Windows 客户端直接“调用微信自动加群”。

推荐：

- 设置页/关于页提供“加入用户群”；
- 从后端获取当前有效群二维码、说明和有效期；
- 弹出二维码供手机微信扫码；
- 二维码失效时运营后台可立即替换，不发新版客户端；
- 群满或二维码失效时显示客服微信二维码/公众号作为兜底；
- 后端记录二维码版本和点击次数，不记录用户聊天内容。

后端表：

```text
community_entries
- type: wechat_group / customer_service / official_account
- image_url
- title
- description
- starts_at
- expires_at
- enabled
- priority
```

## 七、管理后台

最小运营后台需要：

- 用户和设备查看；
- 登录状态/封禁；
- 版本发布；
- 更新渠道；
- 强制更新开关；
- 下载统计；
- 群二维码替换；
- 公告；
- 后续授权和订阅。

## 八、隐私与安全

- 微信 AppSecret 只在服务端；
- 客户端 token 使用 DPAPI/Credential Manager；
- refresh token 可撤销并按设备管理；
- 所有下载和登录接口 HTTPS；
- 更新包必须签名并校验哈希；
- 客户端不得把真实输入正文作为登录/更新遥测上传；
- 崩溃报告默认脱敏；
- 明确隐私政策和数据删除流程；
- 后续云同步必须单独征得用户同意。

## 九、推荐开发顺序

### Release Foundation 1

- 稳定版安装包；
- 代码签名；
- 官网下载页；
- 版本号和更新日志；
- 手动检查更新；
- 社群二维码由远端配置管理。

### Account Foundation 2

- SayIt 后端；
- 微信扫码登录；
- token/device；
- 登录页；
- 游客与登录用户状态。

### Update Foundation 3

- 自动检查和后台下载；
- stable/beta；
- 签名 manifest；
- 安装确认与失败恢复。

### Commercial Foundation 4

- 试用；
- 授权/订阅；
- 设备数量；
- 支付和发票；
- 云端功能开关。

## 十、分支建议

运行时 bug 修复完成并打稳定 tag 后，新建：

```text
feature/release-foundation
```

账号系统另建：

```text
feature/account-wechat-login
```

不要在 `feature/silent-learning-stabilization` 中混入发布和账号代码。