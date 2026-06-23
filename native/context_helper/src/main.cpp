#include <windows.h>
#include <psapi.h>
#include <ole2.h>
#include <oleacc.h>
#include <UIAutomation.h>

#include <algorithm>
#include <cctype>
#include <codecvt>
#include <cstdio>
#include <cstdint>
#include <iostream>
#include <locale>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {

std::wstring utf8ToWide(const std::string& value) {
  if (value.empty()) return L"";
  int size = MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0);
  if (size <= 0) return L"";
  std::wstring out(size, L'\0');
  MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), out.data(), size);
  return out;
}

std::string wideToUtf8(const std::wstring& value) {
  if (value.empty()) return "";
  int size = WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
  if (size <= 0) return "";
  std::string out(size, '\0');
  WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), out.data(), size, nullptr, nullptr);
  return out;
}

std::string jsonEscape(const std::string& value) {
  std::ostringstream os;
  for (unsigned char c : value) {
    switch (c) {
      case '\\': os << "\\\\"; break;
      case '"': os << "\\\""; break;
      case '\b': os << "\\b"; break;
      case '\f': os << "\\f"; break;
      case '\n': os << "\\n"; break;
      case '\r': os << "\\r"; break;
      case '\t': os << "\\t"; break;
      default:
        if (c < 0x20) {
          char buf[8];
          sprintf_s(buf, "\\u%04x", c);
          os << buf;
        } else {
          os << c;
        }
    }
  }
  return os.str();
}

std::string quote(const std::string& value) {
  return "\"" + jsonEscape(value) + "\"";
}

void sleepMs(DWORD ms) {
  Sleep(ms);
}

std::string lowerAscii(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
    return static_cast<char>(std::tolower(c));
  });
  return value;
}

std::string basenameLower(const std::wstring& path) {
  size_t pos = path.find_last_of(L"\\/");
  std::wstring name = pos == std::wstring::npos ? path : path.substr(pos + 1);
  return lowerAscii(wideToUtf8(name));
}

std::string jsonStringField(const std::string& line, const std::string& key) {
  std::string needle = "\"" + key + "\"";
  size_t pos = line.find(needle);
  if (pos == std::string::npos) return "";
  pos = line.find(':', pos + needle.size());
  if (pos == std::string::npos) return "";
  pos = line.find('"', pos + 1);
  if (pos == std::string::npos) return "";
  std::ostringstream out;
  bool escape = false;
  for (size_t i = pos + 1; i < line.size(); ++i) {
    char c = line[i];
    if (escape) {
      switch (c) {
        case 'n': out << '\n'; break;
        case 'r': out << '\r'; break;
        case 't': out << '\t'; break;
        default: out << c; break;
      }
      escape = false;
    } else if (c == '\\') {
      escape = true;
    } else if (c == '"') {
      break;
    } else {
      out << c;
    }
  }
  return out.str();
}

std::uintptr_t jsonUintField(const std::string& line, const std::string& key) {
  std::string needle = "\"" + key + "\"";
  size_t pos = line.find(needle);
  if (pos == std::string::npos) return 0;
  pos = line.find(':', pos + needle.size());
  if (pos == std::string::npos) return 0;
  ++pos;
  while (pos < line.size() && std::isspace(static_cast<unsigned char>(line[pos]))) ++pos;
  bool quoted = pos < line.size() && line[pos] == '"';
  if (quoted) ++pos;
  std::string digits;
  while (pos < line.size()) {
    char c = line[pos++];
    if (quoted && c == '"') break;
    if (!quoted && !std::isdigit(static_cast<unsigned char>(c))) break;
    if (std::isdigit(static_cast<unsigned char>(c))) digits.push_back(c);
  }
  if (digits.empty()) return 0;
  try {
    return static_cast<std::uintptr_t>(std::stoull(digits));
  } catch (...) {
    return 0;
  }
}

std::string rectJson(const RECT& rect) {
  long width = std::max<LONG>(0, rect.right - rect.left);
  long height = std::max<LONG>(0, rect.bottom - rect.top);
  std::ostringstream os;
  os << "{\"x\":" << rect.left
     << ",\"y\":" << rect.top
     << ",\"width\":" << width
     << ",\"height\":" << height << "}";
  return os.str();
}

std::wstring windowText(HWND hwnd) {
  wchar_t buf[1024] = {0};
  GetWindowTextW(hwnd, buf, 1024);
  return buf;
}

std::wstring className(HWND hwnd) {
  wchar_t buf[256] = {0};
  GetClassNameW(hwnd, buf, 256);
  return buf;
}

std::wstring processPath(DWORD pid) {
  HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, FALSE, pid);
  if (!process) return L"";
  wchar_t buf[2048] = {0};
  DWORD size = 2048;
  BOOL ok = QueryFullProcessImageNameW(process, 0, buf, &size);
  CloseHandle(process);
  return ok ? std::wstring(buf, size) : L"";
}

bool isBrowserProc(const std::string& proc) {
  return proc == "chrome.exe" || proc == "msedge.exe" || proc == "firefox.exe" ||
         proc == "opera.exe" || proc == "brave.exe";
}

std::string browserUrlFromWindow(HWND hwnd);

std::string domainFromUrl(const std::string& url) {
  std::string value = url;
  std::string lower = lowerAscii(value);
  size_t scheme = lower.find("://");
  size_t start = scheme == std::string::npos ? 0 : scheme + 3;
  if (lower.compare(start, 4, "www.") == 0) start += 4;
  size_t end = lower.find_first_of("/:?#", start);
  if (end == std::string::npos) end = lower.size();
  if (end <= start) return "";
  return value.substr(start, end - start);
}

std::string stripBrowserSuffix(std::string title) {
  const std::vector<std::string> suffixes = {
    " - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox", " - Opera", " - Brave"
  };
  for (const auto& suffix : suffixes) {
    if (title.size() >= suffix.size() &&
        title.compare(title.size() - suffix.size(), suffix.size(), suffix) == 0) {
      return title.substr(0, title.size() - suffix.size());
    }
  }
  return title;
}

struct AppInfo {
  HWND hwnd = nullptr;
  DWORD pid = 0;
  std::string proc;
  std::string procPath;
  std::string title;
  std::string cls;
  RECT rect{0, 0, 0, 0};
};

AppInfo getAppInfoForWindow(HWND hwnd) {
  AppInfo info;
  info.hwnd = hwnd;
  if (!info.hwnd) return info;
  GetWindowThreadProcessId(info.hwnd, &info.pid);
  GetWindowRect(info.hwnd, &info.rect);
  std::wstring path = processPath(info.pid);
  info.procPath = wideToUtf8(path);
  info.proc = basenameLower(path);
  info.title = wideToUtf8(windowText(info.hwnd));
  info.cls = wideToUtf8(className(info.hwnd));
  return info;
}

AppInfo getAppInfoRaw() {
  return getAppInfoForWindow(GetForegroundWindow());
}

std::string appInfoJson(const AppInfo& info) {
  std::ostringstream os;
  bool browser = isBrowserProc(info.proc);
  std::string pageUrl = browser ? browserUrlFromWindow(info.hwnd) : "";
  std::string domain = domainFromUrl(pageUrl);
  os << "{";
  os << "\"app_name\":" << quote(info.proc) << ",";
  os << "\"app_identifier\":" << quote(info.proc) << ",";
  os << "\"window_title\":" << quote(info.title) << ",";
  os << "\"window_position\":" << rectJson(info.rect) << ",";
  os << "\"app_type\":" << quote(browser ? "web_browser" : "native_app") << ",";
  os << "\"app_metadata\":{";
  os << "\"process_id\":" << info.pid << ",";
  os << "\"app_path\":" << quote(info.procPath) << ",";
  os << "\"window_id\":" << reinterpret_cast<std::uintptr_t>(info.hwnd);
  os << "},";
  if (browser) {
    os << "\"browser_context\":{";
    os << "\"page_title\":" << quote(stripBrowserSuffix(info.title)) << ",";
    os << "\"page_url\":" << quote(pageUrl) << ",";
    os << "\"domain\":" << quote(domain);
    os << "},";
  } else {
    os << "\"browser_context\":null,";
  }
  os << "\"hwnd\":" << reinterpret_cast<std::uintptr_t>(info.hwnd) << ",";
  os << "\"process_id\":" << info.pid << ",";
  os << "\"window_class\":" << quote(info.cls);
  os << "}";
  return os.str();
}

class ComInit {
 public:
  ComInit() : ok_(SUCCEEDED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED))) {}
  ~ComInit() { if (ok_) CoUninitialize(); }
  bool ok() const { return ok_; }
 private:
  bool ok_;
};

template <typename T>
void releaseIf(T*& value) {
  if (value) {
    value->Release();
    value = nullptr;
  }
}

std::string bstrToUtf8(BSTR value) {
  if (!value) return "";
  std::wstring wide(value, SysStringLen(value));
  SysFreeString(value);
  return wideToUtf8(wide);
}

bool hasPattern(IUIAutomationElement* element, PATTERNID patternId) {
  if (!element) return false;
  IUnknown* pattern = nullptr;
  bool ok = SUCCEEDED(element->GetCurrentPattern(patternId, &pattern)) && pattern;
  releaseIf(pattern);
  return ok;
}

CONTROLTYPEID elementControlType(IUIAutomationElement* element) {
  CONTROLTYPEID controlType = 0;
  if (element) element->get_CurrentControlType(&controlType);
  return controlType;
}

bool isEditableElement(IUIAutomationElement* element) {
  return hasPattern(element, UIA_ValuePatternId) || hasPattern(element, UIA_TextPatternId);
}

bool isPreferredInputElement(IUIAutomationElement* element) {
  return element && (
    elementControlType(element) == UIA_EditControlTypeId ||
    hasPattern(element, UIA_ValuePatternId)
  );
}

std::string elementAutomationId(IUIAutomationElement* element) {
  if (!element) return "";
  BSTR value = nullptr;
  if (SUCCEEDED(element->get_CurrentAutomationId(&value))) return bstrToUtf8(value);
  return "";
}

std::string elementClassName(IUIAutomationElement* element) {
  if (!element) return "";
  BSTR value = nullptr;
  if (SUCCEEDED(element->get_CurrentClassName(&value))) return bstrToUtf8(value);
  return "";
}

std::string elementName(IUIAutomationElement* element) {
  if (!element) return "";
  BSTR value = nullptr;
  if (SUCCEEDED(element->get_CurrentName(&value))) return bstrToUtf8(value);
  return "";
}

bool isOfficeChromeInput(IUIAutomationElement* element) {
  std::string automationId = elementAutomationId(element);
  std::string classNameValue = elementClassName(element);
  std::string lowerClass = lowerAscii(classNameValue);
  return automationId == "TellMeTextBoxAutomationId" ||
         automationId == "HomePageSearchBox" ||
         automationId == "Undo" ||
         automationId == "Redo" ||
         lowerClass.find("netui") == 0;
}

bool looksLikeBrowserUrl(const std::string& value) {
  std::string lower = lowerAscii(value);
  bool hasWhitespace = lower.find_first_of(" \t\r\n") != std::string::npos;
  bool looksLikeDomain = !hasWhitespace &&
                         lower.find('.') != std::string::npos &&
                         lower.find('\\') == std::string::npos;
  return lower.rfind("http://", 0) == 0 ||
         lower.rfind("https://", 0) == 0 ||
         lower.rfind("file://", 0) == 0 ||
         lower.rfind("chrome://", 0) == 0 ||
         lower.rfind("edge://", 0) == 0 ||
         lower.rfind("about:", 0) == 0 ||
         looksLikeDomain;
}

std::wstring getClipboardUnicodeText() {
  std::wstring value;
  if (!OpenClipboard(nullptr)) return value;
  HANDLE handle = GetClipboardData(CF_UNICODETEXT);
  if (handle) {
    const wchar_t* text = static_cast<const wchar_t*>(GlobalLock(handle));
    if (text) {
      value = text;
      GlobalUnlock(handle);
    }
  }
  CloseClipboard();
  return value;
}

bool setClipboardUnicodeText(const std::wstring& value) {
  if (!OpenClipboard(nullptr)) return false;
  EmptyClipboard();
  size_t bytes = (value.size() + 1) * sizeof(wchar_t);
  HGLOBAL data = GlobalAlloc(GMEM_MOVEABLE, bytes);
  if (!data) {
    CloseClipboard();
    return false;
  }
  void* locked = GlobalLock(data);
  if (!locked) {
    GlobalFree(data);
    CloseClipboard();
    return false;
  }
  memcpy(locked, value.c_str(), bytes);
  GlobalUnlock(data);
  SetClipboardData(CF_UNICODETEXT, data);
  CloseClipboard();
  return true;
}

void sendKeyCombo(const std::vector<WORD>& keys) {
  for (WORD key : keys) {
    keybd_event(static_cast<BYTE>(key), 0, 0, 0);
  }
  for (auto it = keys.rbegin(); it != keys.rend(); ++it) {
    keybd_event(static_cast<BYTE>(*it), 0, KEYEVENTF_KEYUP, 0);
  }
}

std::string elementValue(IUIAutomationElement* element) {
  if (!element) return "";
  IUIAutomationValuePattern* valuePattern = nullptr;
  if (SUCCEEDED(element->GetCurrentPatternAs(UIA_ValuePatternId, IID_PPV_ARGS(&valuePattern))) && valuePattern) {
    BSTR value = nullptr;
    if (SUCCEEDED(valuePattern->get_CurrentValue(&value))) {
      releaseIf(valuePattern);
      return bstrToUtf8(value);
    }
  }
  releaseIf(valuePattern);
  return "";
}

bool isAddressBarCandidate(IUIAutomationElement* element) {
  if (!element || !hasPattern(element, UIA_ValuePatternId)) return false;
  if (looksLikeBrowserUrl(elementValue(element))) return true;
  std::string automationId = lowerAscii(elementAutomationId(element));
  std::string name = lowerAscii(elementName(element));
  std::string cls = lowerAscii(elementClassName(element));
  std::string haystack = automationId + " " + name + " " + cls;
  return haystack.find("address") != std::string::npos ||
         haystack.find("search") != std::string::npos ||
         haystack.find("url") != std::string::npos ||
         haystack.find("地址") != std::string::npos ||
         haystack.find("搜索") != std::string::npos;
}

IUIAutomationElement* findAddressBarElement(
    IUIAutomationTreeWalker* walker,
    IUIAutomationElement* root,
    int depth,
    int& visited) {
  if (!walker || !root || depth > 16 || visited > 3000) return nullptr;

  IUIAutomationElement* child = nullptr;
  if (FAILED(walker->GetFirstChildElement(root, &child)) || !child) return nullptr;

  while (child && visited <= 3000) {
    ++visited;
    if (isAddressBarCandidate(child)) {
      return child;
    }

    IUIAutomationElement* nested = findAddressBarElement(walker, child, depth + 1, visited);
    if (nested) {
      releaseIf(child);
      return nested;
    }

    IUIAutomationElement* next = nullptr;
    walker->GetNextSiblingElement(child, &next);
    releaseIf(child);
    child = next;
  }

  return nullptr;
}

std::string browserUrlFromWindow(HWND hwnd) {
  if (!hwnd) return "";
  ComInit com;
  IUIAutomation* uia = nullptr;
  IUIAutomationElement* root = nullptr;
  IUIAutomationTreeWalker* walker = nullptr;
  IUIAutomationElement* addressBar = nullptr;
  IUIAutomationElement* originalFocus = nullptr;
  std::string url;

  if (com.ok() && SUCCEEDED(CoCreateInstance(CLSID_CUIAutomation, nullptr, CLSCTX_INPROC_SERVER,
                                            IID_PPV_ARGS(&uia))) && uia &&
      SUCCEEDED(uia->ElementFromHandle(hwnd, &root)) && root) {
    uia->GetFocusedElement(&originalFocus);
    if (SUCCEEDED(uia->get_ControlViewWalker(&walker)) && walker) {
      int visited = 0;
      addressBar = findAddressBarElement(walker, root, 0, visited);
      url = elementValue(addressBar);
    }
    releaseIf(addressBar);
    releaseIf(walker);

    if (!looksLikeBrowserUrl(url) && SUCCEEDED(uia->get_RawViewWalker(&walker)) && walker) {
      int visited = 0;
      addressBar = findAddressBarElement(walker, root, 0, visited);
      url = elementValue(addressBar);
    }
    releaseIf(addressBar);
    releaseIf(walker);

    if (!looksLikeBrowserUrl(url)) {
      url = "";
    }
  }

  if (!looksLikeBrowserUrl(url)) {
    std::wstring clipboardBackup = getClipboardUnicodeText();
    HWND previousForeground = GetForegroundWindow();
    SetForegroundWindow(hwnd);
    sleepMs(50);
    sendKeyCombo({VK_CONTROL, 'L'});
    sleepMs(80);
    sendKeyCombo({VK_CONTROL, 'C'});
    sleepMs(80);
    std::string copied = wideToUtf8(getClipboardUnicodeText());
    if (looksLikeBrowserUrl(copied)) {
      url = copied;
    }
    sendKeyCombo({VK_ESCAPE});
    sleepMs(50);
    if (originalFocus) {
      originalFocus->SetFocus();
    } else if (previousForeground && previousForeground != hwnd) {
      SetForegroundWindow(previousForeground);
    }
    setClipboardUnicodeText(clipboardBackup);
  }

  releaseIf(originalFocus);
  releaseIf(root);
  releaseIf(uia);
  return url;
}

enum class InputSearchMode {
  Preferred,
  TextPattern,
};

bool matchesInputSearchMode(IUIAutomationElement* element, InputSearchMode mode) {
  if (!element || isOfficeChromeInput(element) || isAddressBarCandidate(element)) return false;
  if (mode == InputSearchMode::Preferred) return isPreferredInputElement(element);
  return hasPattern(element, UIA_TextPatternId);
}

IUIAutomationElement* findDescendantByMode(
    IUIAutomationTreeWalker* walker,
    IUIAutomationElement* root,
    InputSearchMode mode,
    int depth,
    int& visited) {
  if (!walker || !root || depth > 8 || visited > 500) return nullptr;

  IUIAutomationElement* child = nullptr;
  if (FAILED(walker->GetFirstChildElement(root, &child)) || !child) return nullptr;

  while (child && visited <= 500) {
    ++visited;
    if (matchesInputSearchMode(child, mode)) {
      return child;
    }

    IUIAutomationElement* nested = findDescendantByMode(walker, child, mode, depth + 1, visited);
    if (nested) {
      releaseIf(child);
      return nested;
    }

    IUIAutomationElement* next = nullptr;
    walker->GetNextSiblingElement(child, &next);
    releaseIf(child);
    child = next;
  }

  return nullptr;
}

IUIAutomationElement* findEditableDescendant(IUIAutomation* uia, IUIAutomationElement* root) {
  if (!uia || !root) return nullptr;

  IUIAutomationTreeWalker* walker = nullptr;
  if (FAILED(uia->get_ControlViewWalker(&walker)) || !walker) return nullptr;

  int visited = 0;
  IUIAutomationElement* preferred = findDescendantByMode(walker, root, InputSearchMode::Preferred, 0, visited);
  if (preferred) {
    releaseIf(walker);
    return preferred;
  }

  visited = 0;
  IUIAutomationElement* textElement = findDescendantByMode(walker, root, InputSearchMode::TextPattern, 0, visited);
  releaseIf(walker);
  return textElement;
}

IUIAutomationElement* bestInputElement(IUIAutomation* uia) {
  if (!uia) return nullptr;
  IUIAutomationElement* focused = nullptr;
  if (SUCCEEDED(uia->GetFocusedElement(&focused)) && focused) {
    if (isPreferredInputElement(focused)) {
      return focused;
    }
  }

  HWND hwnd = GetForegroundWindow();
  IUIAutomationElement* windowElement = nullptr;
  IUIAutomationElement* descendant = nullptr;
  if (hwnd && SUCCEEDED(uia->ElementFromHandle(hwnd, &windowElement)) && windowElement) {
    descendant = findEditableDescendant(uia, windowElement);
  }
  releaseIf(windowElement);

  if (descendant) {
    releaseIf(focused);
    return descendant;
  }
  if (focused && isEditableElement(focused)) {
    return focused;
  }
  return focused;
}

IUIAutomationElement* bestInputElementForWindow(IUIAutomation* uia, HWND hwnd) {
  if (!uia || !hwnd) return nullptr;
  IUIAutomationElement* windowElement = nullptr;
  IUIAutomationElement* descendant = nullptr;
  if (SUCCEEDED(uia->ElementFromHandle(hwnd, &windowElement)) && windowElement) {
    descendant = findEditableDescendant(uia, windowElement);
  }
  releaseIf(windowElement);
  return descendant;
}

std::string readFocusedText(IUIAutomationElement* element) {
  if (!element) return "";
  IUIAutomationValuePattern* valuePattern = nullptr;
  if (SUCCEEDED(element->GetCurrentPatternAs(UIA_ValuePatternId, IID_PPV_ARGS(&valuePattern))) && valuePattern) {
    BSTR value = nullptr;
    if (SUCCEEDED(valuePattern->get_CurrentValue(&value))) {
      releaseIf(valuePattern);
      return bstrToUtf8(value);
    }
  }
  releaseIf(valuePattern);

  IUIAutomationTextPattern* textPattern = nullptr;
  if (SUCCEEDED(element->GetCurrentPatternAs(UIA_TextPatternId, IID_PPV_ARGS(&textPattern))) && textPattern) {
    IUIAutomationTextRange* range = nullptr;
    if (SUCCEEDED(textPattern->get_DocumentRange(&range)) && range) {
      BSTR text = nullptr;
      HRESULT hr = range->GetText(10000, &text);
      releaseIf(range);
      releaseIf(textPattern);
      if (SUCCEEDED(hr)) return bstrToUtf8(text);
    }
  }
  releaseIf(textPattern);
  return "";
}

std::string readSelectedText(IUIAutomationElement* element) {
  if (!element) return "";
  IUIAutomationTextPattern* textPattern = nullptr;
  if (FAILED(element->GetCurrentPatternAs(UIA_TextPatternId, IID_PPV_ARGS(&textPattern))) || !textPattern) {
    return "";
  }
  IUIAutomationTextRangeArray* ranges = nullptr;
  std::string selected;
  if (SUCCEEDED(textPattern->GetSelection(&ranges)) && ranges) {
    int length = 0;
    ranges->get_Length(&length);
    if (length > 0) {
      IUIAutomationTextRange* range = nullptr;
      if (SUCCEEDED(ranges->GetElement(0, &range)) && range) {
        BSTR text = nullptr;
        if (SUCCEEDED(range->GetText(5000, &text))) selected = bstrToUtf8(text);
        releaseIf(range);
      }
    }
  }
  releaseIf(ranges);
  releaseIf(textPattern);
  return selected;
}

std::string inputJsonForWindow(HWND hwnd) {
  ComInit com;
  IUIAutomation* uia = nullptr;
  IUIAutomationElement* element = nullptr;
  std::string role;
  std::string automationId;
  std::string classNameValue;
  std::string fullText;
  std::string selectedText;
  RECT bounds{0, 0, 0, 0};
  bool editable = false;

  if (com.ok() && SUCCEEDED(CoCreateInstance(CLSID_CUIAutomation, nullptr, CLSCTX_INPROC_SERVER,
                                            IID_PPV_ARGS(&uia))) && uia) {
    element = hwnd ? bestInputElementForWindow(uia, hwnd) : bestInputElement(uia);
    if (element) {
      CONTROLTYPEID controlType = 0;
      if (SUCCEEDED(element->get_CurrentControlType(&controlType))) {
        role = std::to_string(controlType);
      }
      BSTR autoId = nullptr;
      if (SUCCEEDED(element->get_CurrentAutomationId(&autoId))) automationId = bstrToUtf8(autoId);
      BSTR cls = nullptr;
      if (SUCCEEDED(element->get_CurrentClassName(&cls))) classNameValue = bstrToUtf8(cls);
      element->get_CurrentBoundingRectangle(&bounds);
      editable = isEditableElement(element);
      fullText = readFocusedText(element);
      selectedText = readSelectedText(element);
    }
  }
  releaseIf(element);
  releaseIf(uia);

  bool hasSelected = !selectedText.empty();
  std::ostringstream os;
  os << "{";
  os << "\"input_area_type\":\"text_field\",";
  os << "\"accessibility_role\":" << quote(role) << ",";
  os << "\"position_on_screen\":" << rectJson(bounds) << ",";
  os << "\"input_capabilities\":{";
  os << "\"is_editable\":" << (editable || !fullText.empty() ? "true" : "false") << ",";
  os << "\"supports_markdown\":false,";
  os << "\"dom_id\":" << quote(automationId) << ",";
  os << "\"dom_classes\":" << quote(classNameValue);
  os << "},";
  os << "\"cursor_state\":{";
  os << "\"cursor_position\":-1,";
  os << "\"has_text_selected\":" << (hasSelected ? "true" : "false") << ",";
  os << "\"selected_text\":" << quote(selectedText) << ",";
  os << "\"text_before_cursor\":\"\",";
  os << "\"text_after_cursor\":\"\",";
  os << "\"full_field_content\":" << quote(fullText);
  os << "},";
  os << "\"surrounding_context\":{";
  os << "\"text_before_input_area\":\"\",";
  os << "\"text_after_input_area\":\"\"";
  os << "}";
  os << "}";
  return os.str();
}

std::string focusedInputJson() {
  return inputJsonForWindow(nullptr);
}

std::string emptyInputJson() {
  RECT bounds{0, 0, 0, 0};
  std::ostringstream os;
  os << "{";
  os << "\"input_area_type\":\"text_field\",";
  os << "\"accessibility_role\":\"\",";
  os << "\"position_on_screen\":" << rectJson(bounds) << ",";
  os << "\"input_capabilities\":{";
  os << "\"is_editable\":false,";
  os << "\"supports_markdown\":false,";
  os << "\"dom_id\":\"\",";
  os << "\"dom_classes\":\"\"";
  os << "},";
  os << "\"cursor_state\":{";
  os << "\"cursor_position\":-1,";
  os << "\"has_text_selected\":false,";
  os << "\"selected_text\":\"\",";
  os << "\"text_before_cursor\":\"\",";
  os << "\"text_after_cursor\":\"\",";
  os << "\"full_field_content\":\"\"";
  os << "},";
  os << "\"surrounding_context\":{";
  os << "\"text_before_input_area\":\"\",";
  os << "\"text_after_input_area\":\"\"";
  os << "}";
  os << "}";
  return os.str();
}

std::string fullContextJson() {
  AppInfo app = getAppInfoRaw();
  std::string inputJson = focusedInputJson();
  std::string appJson = appInfoJson(app);
  std::ostringstream os;
  os << "{";
  os << "\"device_environment\":{";
  os << "\"platform\":\"windows\"";
  os << "},";
  os << "\"active_application\":" << appJson << ",";
  os << "\"text_insertion_point\":" << inputJson << ",";
  os << "\"context_metadata\":{";
  os << "\"is_own_application\":false,";
  os << "\"capture_timestamp\":\"\",";
  os << "\"capture_frequency\":{";
  os << "\"app_focus_count\":0,";
  os << "\"input_field_focus_count\":0,";
  os << "\"system_info_refresh_count\":0";
  os << "}";
  os << "}";
  os << "}";
  return os.str();
}

std::string fullContextJsonForWindow(HWND hwnd) {
  AppInfo app = getAppInfoForWindow(hwnd);
  std::string inputJson = hwnd ? inputJsonForWindow(hwnd) : emptyInputJson();
  std::string appJson = appInfoJson(app);
  std::ostringstream os;
  os << "{";
  os << "\"device_environment\":{";
  os << "\"platform\":\"windows\"";
  os << "},";
  os << "\"active_application\":" << appJson << ",";
  os << "\"text_insertion_point\":" << inputJson << ",";
  os << "\"context_metadata\":{";
  os << "\"is_own_application\":false,";
  os << "\"capture_timestamp\":\"\",";
  os << "\"capture_frequency\":{";
  os << "\"app_focus_count\":0,";
  os << "\"input_field_focus_count\":0,";
  os << "\"system_info_refresh_count\":0";
  os << "}";
  os << "}";
  os << "}";
  return os.str();
}

std::string keyboardEventsJson() {
  static std::map<int, bool> lastDown;
  struct KeySpec { int vk; const char* name; };
  const std::vector<KeySpec> keys = {
    {VK_RETURN, "Enter"}, {VK_TAB, "Tab"}, {VK_SPACE, "Space"}, {VK_DELETE, "Delete"},
    {'A', "A"}, {'S', "S"}, {'D', "D"}, {'F', "F"}, {'H', "H"}, {'G', "G"},
    {'Z', "Z"}, {'X', "X"}, {'C', "C"}, {'V', "V"}, {'B', "B"}, {'Q', "Q"},
    {'W', "W"}, {'E', "E"}, {'R', "R"}, {'Y', "Y"}, {'T', "T"}, {'O', "O"},
    {'U', "U"}, {'I', "I"}, {'P', "P"}, {'L', "L"}, {'J', "J"}, {'K', "K"},
    {'N', "N"}, {'M', "M"}, {'0', "0"}, {'1', "1"}, {'2', "2"}, {'3', "3"},
    {'4', "4"}, {'5', "5"}, {'6', "6"}, {'7', "7"}, {'8', "8"}, {'9', "9"},
  };
  std::ostringstream os;
  os << "[";
  bool first = true;
  for (const auto& key : keys) {
    bool down = (GetAsyncKeyState(key.vk) & 0x8000) != 0;
    bool wasDown = lastDown[key.vk];
    if (down && !wasDown) {
      if (!first) os << ",";
      first = false;
      os << "{\"keyName\":" << quote(key.name) << "}";
    }
    lastDown[key.vk] = down;
  }
  os << "]";
  return os.str();
}

std::string response(const std::string& id, const std::string& resultJson) {
  return "{\"id\":" + quote(id) + ",\"ok\":true,\"result\":" + resultJson + "}";
}

std::string errorResponse(const std::string& id, const std::string& message) {
  return "{\"id\":" + quote(id) + ",\"ok\":false,\"error\":" + quote(message) + "}";
}

}  // namespace

int main() {
  SetConsoleOutputCP(CP_UTF8);
  SetConsoleCP(CP_UTF8);

  std::string line;
  while (std::getline(std::cin, line)) {
    std::string id = jsonStringField(line, "id");
    std::string method = jsonStringField(line, "method");
    if (id.empty()) id = "0";

    try {
      if (method == "ping") {
        std::cout << response(id, "{\"pong\":true}") << std::endl;
      } else if (method == "get_focused_app_info") {
        std::cout << response(id, appInfoJson(getAppInfoRaw())) << std::endl;
      } else if (method == "get_window_app_info") {
        HWND hwnd = reinterpret_cast<HWND>(jsonUintField(line, "hwnd"));
        std::cout << response(id, appInfoJson(getAppInfoForWindow(hwnd))) << std::endl;
      } else if (method == "get_focused_input_info") {
        std::cout << response(id, focusedInputJson()) << std::endl;
      } else if (method == "get_window_input_info") {
        HWND hwnd = reinterpret_cast<HWND>(jsonUintField(line, "hwnd"));
        std::cout << response(id, hwnd ? inputJsonForWindow(hwnd) : emptyInputJson()) << std::endl;
      } else if (method == "get_full_context") {
        std::cout << response(id, fullContextJson()) << std::endl;
      } else if (method == "get_full_context_for_window") {
        HWND hwnd = reinterpret_cast<HWND>(jsonUintField(line, "hwnd"));
        std::cout << response(id, fullContextJsonForWindow(hwnd)) << std::endl;
      } else if (method == "get_selected_text") {
        ComInit com;
        IUIAutomation* uia = nullptr;
        IUIAutomationElement* element = nullptr;
        std::string selected;
        if (com.ok() && SUCCEEDED(CoCreateInstance(CLSID_CUIAutomation, nullptr, CLSCTX_INPROC_SERVER,
                                                  IID_PPV_ARGS(&uia))) && uia &&
            SUCCEEDED(uia->GetFocusedElement(&element)) && element) {
          selected = readSelectedText(element);
        }
        releaseIf(element);
        releaseIf(uia);
        std::cout << response(id, quote(selected)) << std::endl;
      } else if (method == "poll_keyboard_events") {
        std::cout << response(id, keyboardEventsJson()) << std::endl;
      } else {
        std::cout << errorResponse(id, "unknown method") << std::endl;
      }
    } catch (...) {
      std::cout << errorResponse(id, "native exception") << std::endl;
    }
  }
  return 0;
}
