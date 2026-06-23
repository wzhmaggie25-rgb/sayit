# Sayit 浮窗重构 — 按核心度抄 Typeless

## 不动文件（已对）

- `D:\Soft\code\sayiy1.1\sayit_cg\frontend\main.js` — 窗口管理、鼠标追踪、WS 转发 ✅
- `D:\Soft\code\sayiy1.1\sayit_cg\frontend\preload.js` — IPC 桥 ✅
- `D:\Soft\code\sayiy1.1\sayit_cg\server.py` — 后端 API ✅
- `D:\Soft\code\sayiy1.1\sayit_cg\application\pipeline.py` — 音视频管道 ✅

## 唯一重构文件

**`D:\Soft\code\sayiy1.1\sayit_cg\frontend\ui\float.html`** — 完全重写

## 参考源（只读）

- `D:\Soft\code\sayiy1.1\sayit_cg\reference\XState_machine.js` — XState 状态机 1650 行
- `D:\Soft\code\sayiy1.1\typeless_src\cracked_float\deobfuscated.js` — 浮窗组件源码
  - 770-815 行：Ni AudioVisualizer 声纹条
  - 818-827 行：_Component2 IdleBars 空闲条
  - 829-850 行：Mi ShimmerText 闪烁文字
  - 8051-8327 行：_Component4 录音条主组件
- `D:\Soft\code\sayiy1.1\typeless_src\cracked\deobfuscated.js` — 主进程
  - 8409-8819 行：Ch 类浮窗管理

---

## 技术方案

React 18 + XState 5，全部 CDN，零构建。

```html
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<script src="https://unpkg.com/xstate@5/dist/xstate.min.js"></script>
```

Babel standalone 在浏览器里编译 JSX。开发阶段用 development 版方便调试，完成后切 production。

---

## P0 — 核心渲染（抄完就能看到 Typeless 同款）

### P0.1 搭环境并验证事件通道

**产出**：`float.html` 最小可运行版

```html
<!doctype html>
<html>
<head><meta charset="utf-8">
<style>body{margin:0;background:transparent;color:#fff;font-family:system-ui}</style>
<script src="https://unpkg.com/react@18/umd/react.development.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
</head>
<body><div id="root"></div>
<script type="text/babel">
const {useState} = React;
function App(){
  const [label,setLabel]=useState('idle');
  window.sayitOnRecordingStarted=()=>setLabel('REC');
  window.sayitOnRecordingStopped=()=>setLabel('THINK');
  window.sayitOnPipelineDone=()=>setLabel('DONE');
  window.sayitOnError=()=>setLabel('ERR');
  window.sayitOnRmsLevel=()=>{};
  window.sayitOnTick=()=>{};
  return React.createElement('div',{style:{padding:8,background:'rgba(0,0,0,.8)',borderRadius:16,display:'inline-block'}},label);
}
ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
</script></body></html>
```

**验证**：启动 Electron，按 RightAlt，看到 idel → REC → THINK → DONE 切换。

### P0.2 抄 IdleBars 空闲条

**Typeless 参考**：deobfuscated.js 818-827

**追加到 float.html**：

```jsx
function IdleBars(){
  return React.createElement('div',{style:{display:'flex',gap:2,alignItems:'center',justifyContent:'center',height:24}},
    Array.from({length:10},(_,i)=>
      React.createElement('div',{key:i,style:{width:2,height:2,background:'#808080'}})
    )
  );
}
```

**验证**：刷新页面，看到 10 根灰色短条。

### P0.3 抄 Ni AudioVisualizer 声纹条

**Typeless 参考**：deobfuscated.js 770-815

**追加到 float.html**：

```jsx
function AudioVisualizer({volume}){
  const barsRef = React.useRef([]);
  const [tick,setTick] = React.useState(0);
  
  React.useEffect(()=>{
    let id;
    function loop(){ id=requestAnimationFrame(loop); setTick(Date.now()); }
    loop();
    return ()=>cancelAnimationFrame(id);
  },[]);

  return React.createElement('div',{style:{display:'flex',alignItems:'flex-end',gap:2,height:24,overflow:'hidden',justifyContent:'center',width:54,position:'relative'}},
    Array.from({length:26},(_,i)=>{
      const h = Math.max(2, Math.min(24, 2 + volume*22*(0.3+0.7*Math.sin(i*0.4+tick*0.008))));
      const active = volume > 0.1;
      return React.createElement('div',{key:i,style:{width:2,height:h,borderRadius:9999,flexShrink:0,background:active?'rgba(255,255,255,1)':'rgba(255,255,255,0.5)',transition:'height 0.05s, background 0.2s'}});
    }),
    // Fade masks
    volume>0.3 && React.createElement('div',{style:{position:'absolute',left:0,top:0,width:12,height:'100%',background:'linear-gradient(to left, transparent, rgba(0,0,0,1))',pointerEvents:'none'}}),
    volume>0.3 && React.createElement('div',{style:{position:'absolute',right:0,top:0,width:12,height:'100%',background:'linear-gradient(to right, transparent, rgba(0,0,0,1))',pointerEvents:'none'}})
  );
}
```

**验证**：写死 volume=0.6，看到 26 根白条跳动，两端有渐变遮罩。

### P0.4 抄 Mi ShimmerText 闪烁文字

**Typeless 参考**：deobfuscated.js 829-850

**追加到 float.html**：

```jsx
function ShimmerText({text}){
  return React.createElement('style',null,`
    @keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
    .shimmer{font-size:14px;line-height:16px;font-weight:450;
      background:linear-gradient(90deg,rgba(242,241,240,.5) 0%,rgba(242,241,240,.3) 50%,rgba(242,241,240,.5) 100%);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;
      background-size:200% 100%;animation:shimmer 1.5s ease-out infinite;
      white-space:nowrap;filter:blur(3.4px)}
  `,null,
  React.createElement('span',{className:'shimmer'},text));
}
```

**验证**：显示 "Thinking" 文字，看到闪烁效果。

### P0.5 抄 XState 状态机

**Typeless 参考**：XState_machine.js

**追加到 float.html**，引入 xstate CDN 后用 `createMachine` 定义核心状态流转：

```js
// 只抄核心流转，不抄 alert/onboarding/translation
const recordingMachine = createMachine({
  id: 'recording',
  initial: 'idle',
  states: {
    idle: {
      on: { 'RECORD.START': 'starting_microphone' }
    },
    starting_microphone: {
      // 模拟异步权限检查，立即进入 recording_active
      after: { 100: 'recording_active' }
    },
    recording_active: {
      initial: 'pushToTalk',
      states: {
        pushToTalk: {
          on: { 'RECORD.STOP': '#recording.stopping' }
        },
        handsFree: {
          on: { 'RECORD.STOP': '#recording.stopping' }
        }
      },
      on: { 'RECORD.STOP': 'stopping' }
    },
    stopping: {
      entry: 'stopRecording',
      after: { 500: 'done' }
    },
    done: {
      entry: 'markDone',
      after: { 2000: 'idle' }
    },
    error: {
      entry: 'markError',
      after: { 3000: 'idle' }
    }
  }
});
```

**验证**：状态机独立可测，发送事件能正确切换。

### P0.6 抄 _Component4 主组件组装

**Typeless 参考**：deobfuscated.js 8051-8327

**目标**：用 XState `useMachine` hook 驱动 UI，状态 → 对应的子组件。

```jsx
function RecordingBar(){
  const [state, send] = useMachine(recordingMachine);
  const [volume, setVolume] = useState(0);
  const [countdown, setCountdown] = useState(0);
  const isRecording = state.matches('recording_active');
  const isTransition = state.matches('stopping') || state.matches('done') || state.matches('error');
  const isHandsFree = state.matches({recording_active:'handsFree'});

  // Wire to main.js callbacks
  window.sayitOnRecordingStarted = () => send('RECORD.START');
  window.sayitOnRecordingStopped = () => send('RECORD.STOP');
  window.sayitOnPipelineDone = () => send('RECORD.STOP');
  window.sayitOnError = () => send('ERROR');
  window.sayitOnRmsLevel = (v) => setVolume(v);
  window.sayitOnTick = (s) => setCountdown(s);

  const containerStyle = {
    display:'flex',flexDirection:'row',alignItems:'center',justifyContent:'center',
    borderRadius:16,overflow:'hidden',position:'relative',
    ...(isTransition ? {
      width:92,height:34,background:'rgba(0,0,0,1)',padding:4,
      border:'1px solid rgba(255,255,255,0.32)'
    } : isRecording ? {
      width:92,transition:'width 0.2s ease-in-out'
    } : {})
  };

  return React.createElement('div',{style:containerStyle},
    // idle: 10 gray bars
    !isRecording && !isTransition && React.createElement(IdleBars),
    // recording or transition: audio bars + countdown + thinking
    (isRecording || isTransition) && React.createElement('div',{
      style:{display:'flex',flexDirection:'row',alignItems:'center',justifyContent:'center',height:24,overflow:'hidden'}
    },
      // Audio bars (hidden during transition)
      !isTransition && React.createElement(AudioVisualizer,{volume}),
      // Countdown
      isRecording && React.createElement('span',{style:{fontSize:12,color:'#FFF',minWidth:32,textAlign:'center'}},
        String(Math.floor(countdown/60)).padStart(2,'0')+':'+String(countdown%60).padStart(2,'0')
      ),
      // Thinking shimmer
      isTransition && React.createElement(ShimmerText,{text:'Thinking'}),
    )
  );
}
```

**验证**：按 RightAlt → idle 灰条消失 → 声纹条跳动 + 计时器 → 松 Alt → 黑底白框 + Thinking shimmer → Done → idle。

---

## P1 — 交互打磨

### P1.1 Close / Done 按钮

Typeless deobfuscated.js 8098-8110, 8175-8186

```jsx
function CloseButton({onClick}){
  return React.createElement('button',{
    onClick,
    style:{display:'flex',alignItems:'center',justifyContent:'center',width:24,height:24,
      borderRadius:12,border:'none',cursor:'pointer',background:'rgba(66,66,66,1)',color:'#fff',
      fontSize:14,flexShrink:0,zIndex:2,transition:'width .2s,height .2s,opacity .1s,transform .2s'}
  },'✕');
}
function DoneButton({onClick}){
  return React.createElement('button',{
    onClick,
    style:{display:'flex',alignItems:'center',justifyContent:'center',width:24,height:24,
      borderRadius:12,border:'none',cursor:'pointer',background:'#fff',color:'#000',
      fontSize:14,fontWeight:700,flexShrink:0,zIndex:2,transition:'width .2s,height .2s,opacity .1s,transform .2s'}
  },'✓');
}
```

仅在 `isHandsFree` 时渲染。

### P1.2 Countdown 动画

Typeless deobfuscated.js 8111-8117：width 0→32px, opacity 0→1, scale(0)→scale(1), margin-right 0→8px，transition 同步。

### P1.3 Hover idle bars

在 Container 上绑定 `onMouseEnter`/`onMouseLeave`，空闲时鼠标进入才显示 IdleBars。

---

## 执行

全部在一个文件 `D:\Soft\code\sayiy1.1\sayit_cg\frontend\ui\float.html` 里完成。

P0.1 先验证 React + 事件通道能跑，再逐步追加 P0.2→P0.6。

每步追加完，重启 Electron 看效果。
