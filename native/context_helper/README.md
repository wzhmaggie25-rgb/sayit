# Sayit Context Helper

Native Windows helper for Typeless-style focused context capture.

## Build

Install Visual Studio Build Tools with C++ and CMake support, then run:

```powershell
.\native\context_helper\build.ps1
```

If the toolchain is missing and `winget` is available, run this manually:

```powershell
.\native\context_helper\bootstrap_toolchain.ps1 -AcceptPackageAgreements
```

The Python client searches these locations first:

- `native/context_helper/build/Release/sayit_context_helper.exe`
- `native/context_helper/build/Debug/sayit_context_helper.exe`
- `native/context_helper/build/sayit_context_helper.exe`
- `bin/sayit_context_helper.exe`
- `$env:SAYIT_CONTEXT_HELPER`

## Probe

```powershell
.\native\context_helper\probe.ps1
```

The helper speaks newline-delimited JSON-RPC on stdin/stdout. Example:

```json
{"id":"1","method":"get_full_context","params":{}}
```

Window-targeted probes are also supported so tests and captured injection
targets do not depend on `GetForegroundWindow()`:

```json
{"id":"2","method":"get_full_context_for_window","params":{"hwnd":123456}}
```
