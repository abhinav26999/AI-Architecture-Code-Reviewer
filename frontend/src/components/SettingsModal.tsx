"use client";

import React, { useState, useEffect } from "react";
import { 
  X, 
  Settings as SettingsIcon, 
  Key, 
  Cpu, 
  GitPullRequest, 
  Check, 
  RefreshCw, 
  Eye, 
  EyeOff, 
  Copy, 
  CheckCircle2, 
  AlertCircle, 
  Sparkles,
  Terminal,
  Globe,
  Download
} from "lucide-react";
import { AppSettings, loadSettings, saveSettings } from "../utils/settings";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSettingsSaved?: (newSettings: AppSettings) => void;
}

interface InstalledModel {
  name: string;
  size_mb: number;
  parameter_size?: string;
  family?: string;
}

interface RecommendedModel {
  name: string;
  description: string;
  pull_command: string;
  category: string;
}

export default function SettingsModal({ isOpen, onClose, onSettingsSaved }: SettingsModalProps) {
  const [settings, setSettings] = useState<AppSettings>(loadSettings());
  const [showOpenAIKey, setShowOpenAIKey] = useState(false);
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [showGithubToken, setShowGithubToken] = useState(false);
  const [showGitlabToken, setShowGitlabToken] = useState(false);
  const [showBitbucketToken, setShowBitbucketToken] = useState(false);

  // Ollama status & download state
  const [ollamaStatus, setOllamaStatus] = useState<"idle" | "checking" | "online" | "offline">("idle");
  const [installedModels, setInstalledModels] = useState<InstalledModel[]>([]);
  const [recommendedModels, setRecommendedModels] = useState<RecommendedModel[]>([]);
  const [ollamaMessage, setOllamaMessage] = useState<string>("");
  const [downloadingModel, setDownloadingModel] = useState<string | null>(null);
  const [downloadSuccess, setDownloadSuccess] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [saveNotification, setSaveNotification] = useState<boolean>(false);

  const downloadOllamaModel = async (modelName: string) => {
    setDownloadingModel(modelName);
    setDownloadError(null);
    setDownloadSuccess(null);

    try {
      const res = await fetch("http://localhost:8000/api/v1/ollama/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_name: modelName,
          ollama_url: settings.ollamaUrl
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to download model.");
      }

      const data = await res.json();
      setDownloadSuccess(data.message || `Successfully downloaded '${modelName}'!`);
      // Auto refresh model list and select the newly pulled model
      await checkOllamaConnection();
      setSettings(prev => ({ ...prev, ollamaModel: modelName }));
    } catch (e: any) {
      console.error(e);
      setDownloadError(e.message || `Failed to download ${modelName}`);
    } finally {
      setDownloadingModel(null);
    }
  };

  useEffect(() => {
    if (isOpen) {
      const loaded = loadSettings();
      setSettings(loaded);
      checkOllamaConnection(loaded.ollamaUrl);
    }
  }, [isOpen]);

  const checkOllamaConnection = async (targetUrl?: string) => {
    setOllamaStatus("checking");
    const url = targetUrl || settings.ollamaUrl;
    try {
      const res = await fetch(`http://localhost:8000/api/v1/ollama/models?ollama_url=${encodeURIComponent(url)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      
      if (data.status === "online") {
        setOllamaStatus("online");
        setInstalledModels(data.installed_models || []);
        setRecommendedModels(data.recommended_models || []);
        setOllamaMessage(`Connected! Found ${data.total_installed_models} local model(s).`);
        
        if (data.installed_models.length > 0) {
          const names = data.installed_models.map((m: InstalledModel) => m.name);
          setSettings(prev => {
            if (!names.includes(prev.ollamaModel)) {
              return { ...prev, ollamaModel: data.installed_models[0].name };
            }
            return prev;
          });
        }
      } else {
        setOllamaStatus("offline");
        setOllamaMessage(data.message || "Local Ollama server is unreachable.");
      }
    } catch (e: any) {
      setOllamaStatus("offline");
      setOllamaMessage("FastAPI backend or local Ollama server is offline.");
    }
  };

  const handleSave = () => {
    saveSettings(settings);
    setSaveNotification(true);
    if (onSettingsSaved) {
      onSettingsSaved(settings);
    }
    setTimeout(() => {
      setSaveNotification(false);
      onClose();
    }, 600);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 overflow-y-auto">
      <div className="relative w-full max-w-2xl bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden text-slate-900 my-8">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-50 border border-indigo-200 rounded-xl text-indigo-600">
              <SettingsIcon className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">AI & Git Provider Settings</h2>
              <p className="text-xs text-slate-500">Configure LLM keys, local Ollama models, and Git access tokens</p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto">

          {/* Section 1: LLM Provider Selection */}
          <div>
            <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider mb-3">
              1. Choose Reasoning LLM Provider
            </label>
            <div className="grid grid-cols-3 gap-3">
              
              {/* Ollama Card */}
              <button
                type="button"
                onClick={() => setSettings({ ...settings, llmProvider: "ollama" })}
                className={`p-4 rounded-xl border text-left transition flex flex-col justify-between gap-2 ${
                  settings.llmProvider === "ollama"
                    ? "border-emerald-500 bg-emerald-50 text-slate-900 shadow-sm"
                    : "border-slate-200 bg-slate-50/50 hover:border-slate-300 text-slate-600"
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <Cpu className="w-5 h-5 text-emerald-600" />
                  {settings.llmProvider === "ollama" && <Check className="w-4 h-4 text-emerald-600" />}
                </div>
                <div>
                  <div className="font-semibold text-sm text-slate-900">Ollama (Local)</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">Free, 100% offline & private</div>
                </div>
              </button>

              {/* OpenAI Card */}
              <button
                type="button"
                onClick={() => setSettings({ ...settings, llmProvider: "openai" })}
                className={`p-4 rounded-xl border text-left transition flex flex-col justify-between gap-2 ${
                  settings.llmProvider === "openai"
                    ? "border-sky-500 bg-sky-50 text-slate-900 shadow-sm"
                    : "border-slate-200 bg-slate-50/50 hover:border-slate-300 text-slate-600"
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <Sparkles className="w-5 h-5 text-sky-600" />
                  {settings.llmProvider === "openai" && <Check className="w-4 h-4 text-sky-600" />}
                </div>
                <div>
                  <div className="font-semibold text-sm text-slate-900">OpenAI</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">GPT-4o & GPT-4o-mini API</div>
                </div>
              </button>

              {/* Gemini Card */}
              <button
                type="button"
                onClick={() => setSettings({ ...settings, llmProvider: "gemini" })}
                className={`p-4 rounded-xl border text-left transition flex flex-col justify-between gap-2 ${
                  settings.llmProvider === "gemini"
                    ? "border-purple-500 bg-purple-50 text-slate-900 shadow-sm"
                    : "border-slate-200 bg-slate-50/50 hover:border-slate-300 text-slate-600"
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <Key className="w-5 h-5 text-purple-600" />
                  {settings.llmProvider === "gemini" && <Check className="w-4 h-4 text-purple-600" />}
                </div>
                <div>
                  <div className="font-semibold text-sm text-slate-900">Google Gemini</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">Gemini 1.5 Flash API</div>
                </div>
              </button>

            </div>
          </div>

          {/* Section 2: Ollama Local Configuration */}
          {settings.llmProvider === "ollama" && (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-emerald-600" />
                  <h3 className="text-sm font-bold text-slate-900">Local Ollama Configuration</h3>
                </div>
                <button
                  type="button"
                  onClick={() => checkOllamaConnection()}
                  className="flex items-center gap-1.5 px-3 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 text-xs font-semibold rounded-lg shadow-sm transition"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${ollamaStatus === "checking" ? "animate-spin" : ""}`} />
                  Test Connection
                </button>
              </div>

              {/* Status Banner */}
              <div className={`p-3 rounded-lg text-xs flex items-center justify-between border ${
                ollamaStatus === "online" 
                  ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                  : ollamaStatus === "offline"
                  ? "bg-rose-50 border-rose-200 text-rose-800"
                  : "bg-slate-100 border-slate-200 text-slate-600"
              }`}>
                <div className="flex items-center gap-2">
                  {ollamaStatus === "online" ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                  )}
                  <span>{ollamaMessage || "Checking local Ollama availability..."}</span>
                </div>
              </div>

              {/* Host URL & Model Selector */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">Ollama Host URL</label>
                  <input
                    type="text"
                    value={settings.ollamaUrl}
                    onChange={(e) => setSettings({ ...settings, ollamaUrl: e.target.value })}
                    placeholder="http://localhost:11434"
                    className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-emerald-500 font-mono shadow-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">
                    Select System Model ({installedModels.length} installed)
                  </label>
                  {installedModels.length > 0 ? (
                    <select
                      value={settings.ollamaModel}
                      onChange={(e) => setSettings({ ...settings, ollamaModel: e.target.value })}
                      className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-emerald-500 shadow-sm"
                    >
                      {installedModels.map((m) => (
                        <option key={m.name} value={m.name}>
                          {m.name} ({m.size_mb} MB {m.parameter_size ? `| ${m.parameter_size}` : ""})
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={settings.ollamaModel}
                      onChange={(e) => setSettings({ ...settings, ollamaModel: e.target.value })}
                      placeholder="e.g. qwen2.5:7b or llama3"
                      className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-emerald-500 shadow-sm"
                    />
                  )}
                </div>
              </div>

              {/* Recommended Models & 1-Click Automated Download */}
              <div className="pt-3 border-t border-slate-200 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-slate-700 font-bold">
                    <Sparkles className="w-4 h-4 text-indigo-600" />
                    <span>Recommended Architecture Models</span>
                  </div>
                  <span className="text-[10px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
                    1-Click Auto Download
                  </span>
                </div>

                {downloadSuccess && (
                  <div className="p-2.5 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                    <span>{downloadSuccess}</span>
                  </div>
                )}

                {downloadError && (
                  <div className="p-2.5 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                    <span>{downloadError}</span>
                  </div>
                )}

                <div className="space-y-2">
                  {recommendedModels.map((rec) => {
                    const isInstalled = installedModels.some(m => m.name.startsWith(rec.name));
                    const isDownloading = downloadingModel === rec.name;

                    return (
                      <div key={rec.name} className="p-3 bg-white rounded-xl border border-slate-200 shadow-sm flex items-center justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-slate-900">{rec.name}</span>
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider ${
                              rec.category === "coding"
                                ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
                                : rec.category === "reasoning"
                                ? "bg-purple-50 text-purple-700 border border-purple-200"
                                : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            }`}>
                              {rec.category}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 mt-1 leading-snug">{rec.description}</p>
                        </div>

                        <div className="flex-shrink-0">
                          {isInstalled ? (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold rounded-lg text-xs">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                              Installed
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => downloadOllamaModel(rec.name)}
                              disabled={downloadingModel !== null}
                              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold rounded-lg transition text-xs shadow-sm cursor-pointer disabled:cursor-not-allowed"
                            >
                              {isDownloading ? (
                                <>
                                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                  <span>Downloading...</span>
                                </>
                              ) : (
                                <>
                                  <Download className="w-3.5 h-3.5" />
                                  <span>Download</span>
                                </>
                              )}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

            </div>
          )}

          {/* Section 3: Cloud API Keys (OpenAI / Gemini) */}
          {settings.llmProvider === "openai" && (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
              <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <Sparkles className="w-4 h-4 text-sky-600" />
                <span>OpenAI API Key</span>
              </div>
              <div className="relative">
                <input
                  type={showOpenAIKey ? "text" : "password"}
                  value={settings.openaiKey}
                  onChange={(e) => setSettings({ ...settings, openaiKey: e.target.value })}
                  placeholder="sk-proj-..."
                  className="w-full pl-3 pr-10 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-sky-500 font-mono shadow-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowOpenAIKey(!showOpenAIKey)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showOpenAIKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-[11px] text-slate-500">
                Keys are stored only in your browser session and sent directly to OpenAI.
              </p>
            </div>
          )}

          {settings.llmProvider === "gemini" && (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
              <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <Key className="w-4 h-4 text-purple-600" />
                <span>Google Gemini API Key</span>
              </div>
              <div className="relative">
                <input
                  type={showGeminiKey ? "text" : "password"}
                  value={settings.geminiKey}
                  onChange={(e) => setSettings({ ...settings, geminiKey: e.target.value })}
                  placeholder="AIzaSy..."
                  className="w-full pl-3 pr-10 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-purple-500 font-mono shadow-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowGeminiKey(!showGeminiKey)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showGeminiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-[11px] text-slate-500">
                Uses Gemini 1.5 Flash model for high-speed architecture review critiques.
              </p>
            </div>
          )}

          {/* Section 4: Git Provider Credentials (GitHub, GitLab, Bitbucket) */}
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <Globe className="w-4 h-4 text-indigo-600" />
                <span>Git Access Tokens (Private Repositories)</span>
              </div>
              <span className="text-[10px] uppercase font-bold tracking-wider text-slate-600 bg-slate-200 px-2 py-0.5 rounded">
                Optional
              </span>
            </div>

            {/* GitHub PAT */}
            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                <GitPullRequest className="w-3.5 h-3.5 text-slate-600" />
                GitHub Personal Access Token (PAT)
              </label>
              <div className="relative">
                <input
                  type={showGithubToken ? "text" : "password"}
                  value={settings.githubToken}
                  onChange={(e) => setSettings({ ...settings, githubToken: e.target.value })}
                  placeholder="ghp_... or github_pat_..."
                  className="w-full pl-3 pr-10 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-indigo-500 font-mono shadow-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowGithubToken(!showGithubToken)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showGithubToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* GitLab Token */}
            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-orange-600" />
                GitLab Personal Access Token
              </label>
              <div className="relative">
                <input
                  type={showGitlabToken ? "text" : "password"}
                  value={settings.gitlabToken}
                  onChange={(e) => setSettings({ ...settings, gitlabToken: e.target.value })}
                  placeholder="glpat-..."
                  className="w-full pl-3 pr-10 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-orange-500 font-mono shadow-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowGitlabToken(!showGitlabToken)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showGitlabToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Bitbucket App Password / Token */}
            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-sky-600" />
                Bitbucket App Password / Access Token
              </label>
              <div className="relative">
                <input
                  type={showBitbucketToken ? "text" : "password"}
                  value={settings.bitbucketToken}
                  onChange={(e) => setSettings({ ...settings, bitbucketToken: e.target.value })}
                  placeholder="ATATT3... or App Password"
                  className="w-full pl-3 pr-10 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-sky-500 font-mono shadow-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowBitbucketToken(!showBitbucketToken)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showBitbucketToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <p className="text-[11px] text-slate-500 pt-1">
              Allows cloning private repositories across GitHub, GitLab, or Bitbucket without installing separate OAuth apps.
            </p>
          </div>

        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 bg-slate-50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={handleSave}
            className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-lg shadow-indigo-600/20 transition"
          >
            {saveNotification ? (
              <>
                <Check className="w-4 h-4 text-white" />
                <span>Saved Settings!</span>
              </>
            ) : (
              <span>Save & Apply Settings</span>
            )}
          </button>
        </div>

      </div>
    </div>
  );
}
