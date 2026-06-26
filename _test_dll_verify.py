import ctypes, json, os
dll_path = r"D:\code\sayit_zcode\native\context_helper\build\Release\sayit_context_helper_dll.dll"
lib = ctypes.CDLL(dll_path)
lib.get_full_context_json.argtypes = [ctypes.c_void_p]
lib.get_full_context_json.restype = ctypes.c_char_p
lib.free_string.argtypes = [ctypes.c_char_p]
lib.free_string.restype = None
raw = lib.get_full_context_json(ctypes.c_void_p(0))
if raw:
    d = json.loads(raw.decode("utf-8"))
    with open(r"D:\code\sayit_zcode\_dll_result.txt", "w") as f:
        f.write(f"OK title={d.get('active_application',{}).get('window_title','?')}")
    lib.free_string(raw)
else:
    with open(r"D:\code\sayit_zcode\_dll_result.txt", "w") as f:
        f.write("EMPTY from DLL")