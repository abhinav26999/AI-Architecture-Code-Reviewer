export interface AppSettings {
  llmProvider: "ollama" | "openai" | "gemini";
  openaiKey: string;
  geminiKey: string;
  ollamaUrl: string;
  ollamaModel: string;
  githubToken: string;
  gitlabToken: string;
  bitbucketToken: string;
}

const STORAGE_KEY = "antigravity_app_settings";

export const DEFAULT_SETTINGS: AppSettings = {
  llmProvider: "ollama",
  openaiKey: "",
  geminiKey: "",
  ollamaUrl: "http://localhost:11434",
  ollamaModel: "qwen2.5:7b",
  githubToken: "",
  gitlabToken: "",
  bitbucketToken: "",
};

export function loadSettings(): AppSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_SETTINGS, ...parsed };
  } catch (e) {
    console.error("Failed to load settings from sessionStorage:", e);
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(settings: AppSettings): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (e) {
    console.error("Failed to save settings to sessionStorage:", e);
  }
}

export function getApiHeaders(customSettings?: AppSettings): Record<string, string> {
  const settings = customSettings || loadSettings();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-LLM-Provider": settings.llmProvider,
  };

  if (settings.llmProvider === "openai" && settings.openaiKey.trim()) {
    headers["X-OpenAI-Key"] = settings.openaiKey.trim();
  } else if (settings.llmProvider === "gemini" && settings.geminiKey.trim()) {
    headers["X-Gemini-Key"] = settings.geminiKey.trim();
  }

  if (settings.ollamaUrl.trim()) {
    headers["X-Ollama-Url"] = settings.ollamaUrl.trim();
  }

  if (settings.ollamaModel.trim()) {
    headers["X-Ollama-Model"] = settings.ollamaModel.trim();
  }

  if (settings.githubToken.trim()) {
    headers["X-GitHub-Token"] = settings.githubToken.trim();
  }

  if (settings.gitlabToken.trim()) {
    headers["X-GitLab-Token"] = settings.gitlabToken.trim();
  }

  if (settings.bitbucketToken.trim()) {
    headers["X-Bitbucket-Token"] = settings.bitbucketToken.trim();
  }

  return headers;
}
