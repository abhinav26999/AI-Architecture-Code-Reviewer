"use client";

import React, { useState } from "react";
import { 
  X, 
  ShieldAlert, 
  Key, 
  GitPullRequest, 
  ExternalLink, 
  Check, 
  Globe, 
  Sparkles,
  Lock,
  ArrowRight
} from "lucide-react";
import { loadSettings, saveSettings, AppSettings } from "../utils/settings";

interface PrivateRepoAuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  platform: "github.com" | "gitlab.com" | "bitbucket.org" | string;
  owner: string;
  repo: string;
  onTokenSavedAndRetry: () => void;
}

export default function PrivateRepoAuthModal({
  isOpen,
  onClose,
  platform,
  owner,
  repo,
  onTokenSavedAndRetry
}: PrivateRepoAuthModalProps) {
  const [tokenInput, setTokenInput] = useState<string>("");
  const [savedSuccess, setSavedSuccess] = useState<boolean>(false);

  if (!isOpen) return null;

  const normalizedPlatform = platform.toLowerCase().includes("gitlab")
    ? "gitlab"
    : platform.toLowerCase().includes("bitbucket")
    ? "bitbucket"
    : "github";

  const handleSaveAndRetry = () => {
    if (!tokenInput.trim()) return;
    const current = loadSettings();

    const updated: AppSettings = { ...current };
    if (normalizedPlatform === "github") {
      updated.githubToken = tokenInput.trim();
    } else if (normalizedPlatform === "gitlab") {
      updated.gitlabToken = tokenInput.trim();
    } else if (normalizedPlatform === "bitbucket") {
      updated.bitbucketToken = tokenInput.trim();
    }

    saveSettings(updated);
    setSavedSuccess(true);
    setTimeout(() => {
      setSavedSuccess(false);
      onClose();
      onTokenSavedAndRetry();
    }, 500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 overflow-y-auto">
      <div className="relative w-full max-w-xl bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden text-slate-900 my-8">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-amber-50/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-100 border border-amber-200 rounded-xl text-amber-700">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Private Repository Authorization Required</h2>
              <p className="text-xs text-slate-500 font-mono mt-0.5">{owner}/{repo} on {platform}</p>
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

          {/* Explanation Alert */}
          <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 leading-relaxed">
            <p className="font-semibold text-slate-900 mb-1">Why am I seeing this?</p>
            This repository is private. To allow AI Code Architect to perform static rule checks and dependency graph analysis, grant access permissions below.
          </div>

          {/* Platform Specific Guidance */}
          {normalizedPlatform === "github" && (
            <div className="space-y-4">
              
              {/* Option 1: GitHub App Official Installation Request */}
              <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-2.5 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
                    <GitPullRequest className="w-4 h-4 text-indigo-600" />
                    <span>Option A: Request Access via GitHub App</span>
                  </div>
                  <span className="text-[10px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded">
                    Official Flow
                  </span>
                </div>
                <p className="text-xs text-slate-500 leading-normal">
                  If you are the owner, approve access in 1 click. If you are a team member, GitHub automatically emails the organization owner for permission!
                </p>
                <a
                  href="https://github.com/apps/YOUR_APP_NAME/installations/new"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs rounded-lg transition shadow-sm"
                >
                  <span>Open GitHub Permission Request</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>

              {/* Option 2: Enter GitHub PAT */}
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
                  <Key className="w-4 h-4 text-indigo-600" />
                  <span>Option B: Enter Read-Only Personal Access Token (PAT)</span>
                </div>
                <input
                  type="password"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="ghp_... or github_pat_..."
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-500 shadow-sm"
                />
                <p className="text-[11px] text-slate-500">
                  Requires fine-grained token with <code className="text-indigo-600 font-mono">Contents: Read-only</code> permission.
                </p>
              </div>

            </div>
          )}

          {normalizedPlatform === "gitlab" && (
            <div className="space-y-4">
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
                    <Globe className="w-4 h-4 text-orange-600" />
                    <span>GitLab Personal Access Token</span>
                  </div>
                  <a
                    href="https://gitlab.com/-/profile/personal_access_tokens"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] font-semibold text-orange-600 hover:underline flex items-center gap-1"
                  >
                    <span>Generate Token</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
                <input
                  type="password"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="glpat-..."
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-mono text-slate-900 focus:outline-none focus:border-orange-500 shadow-sm"
                />
                <p className="text-[11px] text-slate-500">
                  Requires token with <code className="text-orange-600 font-mono">read_repository</code> scope.
                </p>
              </div>
            </div>
          )}

          {normalizedPlatform === "bitbucket" && (
            <div className="space-y-4">
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
                    <Globe className="w-4 h-4 text-sky-600" />
                    <span>Bitbucket App Password / Access Token</span>
                  </div>
                  <a
                    href="https://bitbucket.org/account/settings/app-passwords/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] font-semibold text-sky-600 hover:underline flex items-center gap-1"
                  >
                    <span>Create App Password</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
                <input
                  type="password"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="ATATT3... or App Password"
                  className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-mono text-slate-900 focus:outline-none focus:border-sky-500 shadow-sm"
                />
                <p className="text-[11px] text-slate-500">
                  Requires token/password with <code className="text-sky-600 font-mono">Repositories: Read</code> scope.
                </p>
              </div>
            </div>
          )}

        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 bg-slate-50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 transition"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={handleSaveAndRetry}
            disabled={!tokenInput.trim()}
            className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl shadow-lg shadow-indigo-600/20 transition cursor-pointer disabled:cursor-not-allowed"
          >
            {savedSuccess ? (
              <>
                <Check className="w-4 h-4 text-white" />
                <span>Token Saved! Re-scanning...</span>
              </>
            ) : (
              <>
                <span>Save Token & Retry Scan</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>

      </div>
    </div>
  );
}
