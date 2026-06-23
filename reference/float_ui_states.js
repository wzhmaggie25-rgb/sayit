// Source: typeless_src/dist/renderer/floating-bar.html (46 lines)
//        + typeless_src/cracked_float/deobfuscated.js, lines 4400-4500 (notification UI)
// Typeless float bar UI structure
//
// DOM structure from floating-bar.html:
//   <div id="root" />  → React mounts here
//   Entry: CAjA2tJL.mjs (210KB float module)
//
// Visual states (from XState + component rendering):
//   idle: 10 static gray bars
//   recording: card with red dot (blinking), 26 wave bars, timer, X/OK buttons
//   thinking: "Thinking..." shimmer text
//   done: green checkmark + editable text
//   error: error message + retry button
//
// CSS: Typeless uses MUI (Material UI) Box component + custom animation
// Wave bars use requestAnimationFrame for continuous animation
// ================================================================

1|<!DOCTYPE html>
2|<html lang="en">
3|<head>
4|  <meta charset="UTF-8" />
5|  <link rel="icon" type="image/x-icon" href="./static/ico/CNBhK_vC.ico" />
6|  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
7|  <meta http-equiv="Content-Security-Policy" content="script-src 'self' 'unsafe-inline';" />
8|  <title>Status</title>
9|  <style>
10|      html,body,#root {
11|          margin: 0;
12|          padding: 0;
13|          width: 100%;
14|          height: 100%;
15|          pointer-events: none;
16|          background: transparent;
17|          flex-direction: column;
18|          display: flex;
19|      }
20|      * {
21|          font-family: -apple-system,BlinkMacSystemFont,Arial,sans-serif;
22|          box-sizing: border-box;
23|      }
24|  </style>
25|  <script type="module" crossorigin src="./static/js/CAjA2tJL.mjs"></script>
26|  <link rel="modulepreload" crossorigin href="./static/js/DarVuflY.js">
27|  <link rel="modulepreload" crossorigin href="./static/js/CFti6bqn.js">
28|  <link rel="modulepreload" crossorigin href="./static/js/B5BPRaTp.js">
29|  <link rel="modulepreload" crossorigin href="./static/js/Cf50eVN1.js">
30|  <link rel="modulepreload" crossorigin href="./static/js/CWH6uQLJ.js">
31|  <link rel="modulepreload" crossorigin href="./static/js/C9io8i90.js">
32|  <link rel="modulepreload" crossorigin href="./static/js/C9CQjUuU.js">
33|  <link rel="modulepreload" crossorigin href="./static/js/InH8cUTc.js">
34|  <link rel="modulepreload" crossorigin href="./static/js/CSQqv-L0.js">
35|  <link rel="modulepreload" crossorigin href="./static/js/Dtp6nu0B.js">
36|  <link rel="stylesheet" crossorigin href="./static/css/C18_jUIn.css">
37|  <link rel="stylesheet" crossorigin href="./static/css/DX4YKr20.css">
38|</head>
39|<body>
40|<div id="root"></div>
41|</body>
42|</html>
43|
44|
45|
46|
47|

// ================================================================
// NOTIFICATION UI COMPONENT (for recording errors/messages)
// ================================================================

4400|      }} closeOnAction={_0xd6451d} buttonText={_0x546181.text || _0x39fa11("client:microphone__notification__button__close")} disabledRefocusWindow={true} onClick={() => {
4401|        _0x54afa0(_0x546181.action);
4402|      }} key={_0x36cc9e} />;
4403|    })}</_0x102b70>;
4404|};
4405|const an = _0x536f62 => {
4406|  var _0x1b08f4;
4407|  var _0x58f995;
4408|  var _0x408a87;
4409|  var _0x19e85;
4410|  var _0x1f704c;
4411|  var _0x3e559e;
4412|  var _0x3b017d;
4413|  var _0x3fb3c7;
4414|  const _0x3a46d2 = _0x536f62.display.title;
4415|  const _0x3742e3 = _0x536f62.display.description;
4416|  if (_0x3a46d2 && _0x3742e3) {
4417|    const _0x41428d = ((_0x1b08f4 = _0x536f62.actions) == null ? undefined : _0x1b08f4.primary) || ((_0x58f995 = _0x536f62.actions) == null ? undefined : _0x58f995.secondary);
4418|    const _0xaecb2f = (_0x408a87 = _0x536f62.actions) == null ? undefined : _0x408a87.primary;
4419|    const _0x426718 = (_0x19e85 = _0x536f62.actions) == null ? undefined : _0x19e85.secondary;
4420|    const _0x1555e5 = ((_0x1f704c = _0x536f62.actions) == null ? undefined : _0x1f704c.additional) || [];
4421|    return {
4422|      type: _0x536f62.type,
4423|      title: _0x3a46d2,
4424|      description: _0x3742e3,
4425|      duration: ((_0x3e559e = _0x536f62.behavior) == null ? undefined : _0x3e559e.duration) ?? 5000,
4426|      closable: (_0x3b017d = _0x536f62.behavior) == null ? undefined : _0x3b017d.closable,
4427|      footer: _0x41428d && <Is primaryButtonAction={_0xaecb2f} secondaryButtonAction={_0x426718} additionalActions={_0x1555e5} closeOnAction={(_0x3fb3c7 = _0x536f62.behavior) == null ? undefined : _0x3fb3c7.closeOnAction} onActionClick={Jn} />
4428|    };
4429|  }
4430|  return null;
4431|};
4432|const As = () => <_0x11c754 viewBox="0 0 32 32" sx={{
4433|  fontSize: "32px"
4434|}}><svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32" fill="none"><path d="M21.9028 4.34424C22.0047 4.34422 22.3065 4.33348 22.6037 4.41344C22.8309 4.47456 23.0452 4.57494 23.2377 4.71031C23.4888 4.88709 23.6744 5.12488 23.7399 5.20362L29.2711 11.842C29.355 11.9426 29.467 12.0756 29.5568 12.2014C29.6316 12.3062 29.7239 12.4477 29.7979 12.6277L29.8649 12.8219L29.9229 13.0965C29.9613 13.3725 29.9419 13.6547 29.8649 13.9246C29.7866 14.199 29.6567 14.4052 29.5568 14.5451C29.467 14.671 29.355 14.8039 29.2711 14.9045L17.8359 28.6255C17.717 28.7681 17.5733 28.945 17.4341 29.0853C17.286 29.2345 17.043 29.4513 16.6885 29.5809C16.2432 29.7436 15.7545 29.7436 15.3091 29.5809C14.9546 29.4513 14.7116 29.2345 14.5635 29.0853C14.4243 28.945 14.2806 28.7681 14.1618 28.6255L2.72649 14.9045C2.64266 14.8039 2.53062 14.671 2.44078 14.5451C2.34095 14.4052 2.21103 14.199 2.13274 13.9246C2.02996 13.5643 2.02998 13.1822 2.13274 12.8219L2.19971 12.6277C2.27368 12.4477 2.36602 12.3062 2.44078 12.2014C2.5306 12.0755 2.64267 11.9426 2.72649 11.842L8.25774 5.20362C8.32327 5.12488 8.50879 4.88709 8.75997 4.71031L9.06355 4.53397C9.16975 4.48422 9.28022 4.44403 9.3939 4.41344L9.61489 4.3688C9.8298 4.33822 10.0185 4.34423 10.0948 4.34424H21.9028ZM15.9988 23.8777L19.1752 14.7438H12.8225L15.9988 23.8777ZM12.606 22.4759L9.91622 14.7438H6.16399L12.606 22.4759ZM19.3894 22.4759L25.8336 14.7438H22.0814L19.3894 22.4759ZM22.0926 12.0027H25.8359L21.7377 7.08531H20.4542L22.0926 12.0027ZM12.7957 12.0027H19.2019L17.5635 7.08531H14.4341L12.7957 12.0027ZM6.16176 12.0027H9.90506L11.5435 7.08531H10.26L6.16176 12.0027Z" fill="#1F5DF2" /></svg></_0x11c754>;
4435|const ys = _0x41c419 => {
4436|  const {
4437|    display: _0x3aa354,
4438|    behavior: _0x2ba826,
4439|    actions: _0x2983c5
4440|  } = _0x41c419;
4441|  const _0xacf9df = _0x2983c5 == null ? undefined : _0x2983c5.primary;
4442|  const _0x1feca2 = !!_0xacf9df;
4443|  const _0x4bcc1d = window.ipcRenderer.platform === "darwin";
4444|  const _0x4215cf = <_0x102b70 sx={{
4445|    width: 360,
4446|    backgroundColor: "#1D1A1A",
4447|    border: "1px solid rgba(119, 119, 119, 0.3)",
4448|    borderRadius: "8px",
4449|    padding: "16px",
4450|    gap: "12px",
4451|    boxShadow: _0x4bcc1d ? "0px 25px 30px 0px rgba(0, 0, 0, 0.25), 0px 0px 20px 0px rgba(0, 0, 0, 0.15)" : "",
4452|    position: "relative",
4453|    overflow: "hidden",
4454|    alignItems: "center",
4455|    justifyContent: "center",
4456|    pointerEvents: "auto"
4457|  }}><_0x102b70 sx={{
4458|      position: "absolute",
4459|      top: "16px",
4460|      left: "16px",
4461|      alignItems: "center",
4462|      justifyContent: "center"
4463|    }}><_0x9df55e logoType="logo-with-text" color="white" logoSize={64} /></_0x102b70>{(_0x2ba826 == null ? undefined : _0x2ba826.closable) !== false && <_0x28cfb4 onClick={() => _0x4037c7()} sx={{
4464|      position: "absolute",
4465|      top: "16px",
4466|      right: "16px",
4467|      width: "14px",
4468|      height: "14px",
4469|      zIndex: 2,
4470|      flexShrink: 0
4471|    }}><_0x34e580 sx={{
4472|        fontSize: "14px",
4473|        color: "#8F8F8F"
4474|      }} /></_0x28cfb4>}<_0x102b70 sx={{
4475|      zIndex: 1,
4476|      alignItems: "center",
4477|      gap: "8px",
4478|      width: "100%"
4479|    }}><_0x102b70 sx={{
4480|        width: 32,
4481|        height: 32,
4482|        flexShrink: 0
4483|      }}><As /></_0x102b70><_0x102b70 sx={{
4484|        alignItems: "center",
4485|        gap: "8px",
4486|        width: "100%"
4487|      }}><_0x852dc5 component="div" fontSize="14px" fontWeight={500} lineHeight="20px" color="#fff" sx={{
4488|          wordBreak: "break-word",
4489|          whiteSpace: "pre-wrap"
4490|        }}>{_0x3aa354.title}</_0x852dc5>{_0x3aa354.description && <_0x852dc5 component="div" color="#C9C9C9" fontSize="12px" fontWeight={400} lineHeight="16px" textAlign="center" sx={{
4491|          display: "-webkit-box",
4492|          WebkitBoxOrient: "vertical",
4493|          WebkitLineClamp: "5",
4494|          overflow: "hidden",
4495|          textOverflow: "ellipsis",
4496|          wordBreak: "break-word"
4497|        }}>{_0x3aa354.description}</_0x852dc5>}</_0x102b70></_0x102b70>{_0x1feca2 && _0xacf9df && <_0x102b70 sx={{
4498|      zIndex: 1,
4499|      gap: "12px",
4500|      alignItems: "center",
4501|