"use client";

import React, { useState, useEffect } from "react";
import { 
  ShieldAlert, 
  BarChart3, 
  GitPullRequest, 
  RefreshCw, 
  Search, 
  FileCode, 
  AlertTriangle, 
  CheckCircle,
  Database,
  ArrowRight,
  Sparkles,
  Activity,
  Layers,
  Globe,
  Link as LinkIcon
} from "lucide-react";
import confetti from "canvas-confetti";
import DependencyGraph from "../components/DependencyGraph";
import SettingsModal from "../components/SettingsModal";
import PrivateRepoAuthModal from "../components/PrivateRepoAuthModal";
import { getApiHeaders, loadSettings, AppSettings } from "../utils/settings";

interface Violation {
  file_path: string;
  line: number;
  rule_name: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  message: string;
  suggested_fix?: string;
  code_snippet?: string;
}

interface Repository {
  id?: number;
  name: string;
  full_name: string;
  owner: { login: string };
  default_branch: string;
}

interface PRReviewResponse {
  status: string;
  message: string;
  review_body: string;
  score?: number;
  violations?: string[];
  modified_files?: string[];
  owner?: string;
  repo?: string;
  pull_number?: number;
}

export default function Home() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"violations" | "review">("violations");
  
  const [score, setScore] = useState<number>(100);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [graphData, setGraphData] = useState<any>({ total_files: 0, nodes: [], edges: [], circular_dependencies: [], average_instability: 0.0 });
  
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [prNumber, setPrNumber] = useState<string>("1");
  const [aiReview, setAiReview] = useState<string>("");
  const [prReviewData, setPrReviewData] = useState<PRReviewResponse | null>(null);
  const [isReviewing, setIsReviewing] = useState<boolean>(false);
  
  const [selectedViolation, setSelectedViolation] = useState<Violation | null>(null);
  const [selectedNode, setSelectedNode] = useState<{ file_path: string; metrics: any } | null>(null);

  // Public Scan State
  const [scanMode, setScanMode] = useState<"public" | "github">("public");
  const [publicRepoUrl, setPublicRepoUrl] = useState<string>("");
  const [scanError, setScanError] = useState<string>("");
  const [scannedRepoName, setScannedRepoName] = useState<string>("");
  const [isFetchingRepos, setIsFetchingRepos] = useState<boolean>(false);

  // PR Selection State
  const [openPRs, setOpenPRs] = useState<any[]>([]);
  const [isLoadingPRs, setIsLoadingPRs] = useState<boolean>(false);

  // Settings Modal State
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [currentSettings, setCurrentSettings] = useState<AppSettings>(loadSettings());

  // AI Refactoring Fix State
  const [isGeneratingAiFix, setIsGeneratingAiFix] = useState<boolean>(false);
  const [aiFixText, setAiFixText] = useState<string>("");

  // Private Repo Authorization Modal State
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [authModalDetails, setAuthModalDetails] = useState<{ platform: string; owner: string; repo: string }>({
    platform: "github.com",
    owner: "",
    repo: ""
  });

  useEffect(() => {
    setCurrentSettings(loadSettings());
  }, []);

  // Fetch PRs when selectedRepo, publicRepoUrl, or scanMode changes
  useEffect(() => {
    setIsLoadingPRs(true);
    let fetchUrl = "";

    if (scanMode === "public" && publicRepoUrl.trim()) {
      fetchUrl = `http://localhost:8000/api/v1/github/public-pulls?repo_url=${encodeURIComponent(publicRepoUrl.trim())}`;
    } else if (selectedRepo) {
      let owner = "";
      let repo = selectedRepo;
      if (selectedRepo.includes("/")) {
        const parts = selectedRepo.split("/");
        owner = parts[0];
        repo = parts[1];
      } else {
        const target = repositories.find(r => r.name === selectedRepo || r.full_name === selectedRepo);
        if (target) {
          owner = target.owner?.login || target.full_name.split("/")[0];
          repo = target.name;
        }
      }
      if (owner && repo) {
        fetchUrl = `http://localhost:8000/api/v1/github/repos/${owner}/${repo}/pulls`;
      }
    }

    if (!fetchUrl) {
      setIsLoadingPRs(false);
      return;
    }

    fetch(fetchUrl, { headers: getApiHeaders() })
      .then(res => res.ok ? res.json() : [])
      .then(data => {
        if (Array.isArray(data)) {
          setOpenPRs(data);
          if (data.length > 0) {
            setPrNumber(data[0].number.toString());
          }
        }
      })
      .catch(err => console.error("Failed to load PRs:", err))
      .finally(() => setIsLoadingPRs(false));
  }, [selectedRepo, publicRepoUrl, scanMode, scannedRepoName, repositories]);

  // Load Repositories from backend
  useEffect(() => {
    setIsFetchingRepos(true);
    fetch("http://localhost:8000/api/v1/github/repositories", {
      headers: getApiHeaders()
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load live repositories");
        return res.json();
      })
      .then((data) => {
        setRepositories(data);
        if (data.length > 0) {
          setSelectedRepo(data[0].full_name || data[0].name);
        }
      })
      .catch((err) => {
        console.error(err);
      })
      .finally(() => setIsFetchingRepos(false));
  }, []);

  // Run Codebase Analysis (Stage 1-4)
  const runAnalysis = async () => {
    setIsLoading(true);
    try {
      let owner = "";
      let repo = selectedRepo;
      if (selectedRepo.includes("/")) {
        const parts = selectedRepo.split("/");
        owner = parts[0];
        repo = parts[1];
      } else {
        const target = repositories.find(r => r.name === selectedRepo || r.full_name === selectedRepo);
        if (target) {
          owner = target.owner?.login || target.full_name.split("/")[0];
          repo = target.name;
        }
      }

      const payload = {
        owner: owner,
        repo: repo,
        installation_id: null
      };

      const customHeaders = getApiHeaders();

      const [reviewRes, graphRes] = await Promise.all([
        fetch("http://localhost:8000/api/v1/review/analyze", {
          method: "POST",
          headers: customHeaders,
          body: JSON.stringify(payload)
        }),
        fetch("http://localhost:8000/api/v1/graph/analyze-repo", {
          method: "POST",
          headers: customHeaders,
          body: JSON.stringify(payload)
        })
      ]);

      const reviewData = await reviewRes.json();
      const graphDataJson = await graphRes.json();

      setScore(reviewData.score || 100);
      setViolations(reviewData.violations || []);
      setGraphData(graphDataJson);

      if (reviewData.score === 100) {
        confetti({ particleCount: 150, spread: 80, colors: ["#10b981", "#3b82f6"] });
      }
    } catch (e) {
      console.error(e);
      alert("Backend API is unreachable. Verify FastAPI server is running on port 8000.");
    } finally {
      setIsLoading(false);
    }
  };

  // Run Public Repo Scan
  const runPublicScan = async () => {
    if (!publicRepoUrl.trim()) {
      setScanError("Please paste a GitHub repository URL.");
      return;
    }
    setScanError("");
    setIsLoading(true);
    setScannedRepoName("");
    try {
      const payload = { repo_url: publicRepoUrl.trim() };
      const customHeaders = getApiHeaders();

      const [reviewRes, graphRes] = await Promise.all([
        fetch("http://localhost:8000/api/v1/review/scan-public", {
          method: "POST",
          headers: customHeaders,
          body: JSON.stringify(payload)
        }),
        fetch("http://localhost:8000/api/v1/graph/scan-public", {
          method: "POST",
          headers: customHeaders,
          body: JSON.stringify(payload)
        })
      ]);

      if (!reviewRes.ok) {
        const errData = await reviewRes.json().catch(() => ({}));
        const detail = errData.detail || "";
        if (detail.includes("PRIVATE_REPO_AUTH_REQUIRED")) {
          const parts = detail.split(":");
          const host = parts[1] || "github.com";
          const owner = parts[2] || "";
          const repo = parts[3] || "";
          setAuthModalDetails({ platform: host, owner, repo });
          setIsAuthModalOpen(true);
          setIsLoading(false);
          return;
        }
        throw new Error(detail || "Failed to scan repository.");
      }

      const reviewData = await reviewRes.json();
      const graphDataJson = await graphRes.json();

      setScore(reviewData.score || 100);
      setViolations(reviewData.violations || []);
      setGraphData(graphDataJson);
      setScannedRepoName(`${reviewData.owner}/${reviewData.repo}`);

      if (reviewData.score === 100) {
        confetti({ particleCount: 150, spread: 80, colors: ["#10b981", "#3b82f6"] });
      }
    } catch (e: any) {
      console.error(e);
      setScanError(e.message || "Failed to scan the repository. Make sure it is a valid public GitHub URL.");
    } finally {
      setIsLoading(false);
    }
  };

  // Run AI PR Review (Stage 6)
  const triggerPRReview = async () => {
    let owner = "";
    let targetRepo = "";

    if (scanMode === "public" && scannedRepoName && scannedRepoName.includes("/")) {
      const parts = scannedRepoName.split("/");
      owner = parts[0];
      targetRepo = parts[1];
    } else if (selectedRepo) {
      if (selectedRepo.includes("/")) {
        const parts = selectedRepo.split("/");
        owner = parts[0];
        targetRepo = parts[1];
      } else {
        const target = repositories.find(r => r.name === selectedRepo || r.full_name === selectedRepo);
        if (target) {
          owner = target.owner?.login || target.full_name.split("/")[0];
          targetRepo = target.name;
        }
      }
    }

    if (!targetRepo || !owner) {
      setAiReview("Please select a repository from the 'GitHub App Repos' tab or run a Quick Scan first.");
      return;
    }

    setIsReviewing(true);
    setAiReview("");

    try {
      const payload = {
        owner: owner,
        repo: targetRepo,
        pull_number: parseInt(prNumber) || 1,
        installation_id: null
      };

      const response = await fetch("http://localhost:8000/api/v1/review/pr", {
        method: "POST",
        headers: getApiHeaders(),
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned error ${response.status}`);
      }

      const data = await response.json();
      setAiReview(data.review_body || "Failed to generate review.");
    } catch (e: any) {
      console.error(e);
      setAiReview(`PR Review Error: ${e.message || "Error connecting to backend API."}`);
    } finally {
      setIsReviewing(false);
    }
  };

  // Generate AI Refactoring Fix for selected violation
  const triggerAiFix = async (v: Violation) => {
    setIsGeneratingAiFix(true);
    setAiFixText("");
    try {
      const response = await fetch("http://localhost:8000/api/v1/review/fix-suggestion", {
        method: "POST",
        headers: getApiHeaders(),
        body: JSON.stringify({
          rule_name: v.rule_name,
          message: v.message,
          file_path: v.file_path,
          code_snippet: v.code_snippet || ""
        })
      });
      if (response.ok) {
        const data = await response.json();
        setAiFixText(data.fix_suggestion || "No fix generated.");
      } else {
        setAiFixText("Failed to generate AI refactoring fix.");
      }
    } catch (e) {
      setAiFixText("Error connecting to AI service.");
    } finally {
      setIsGeneratingAiFix(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 selection:bg-indigo-500 selection:text-white pb-10">
      
      {/* HEADER SECTION */}
      <header className="border-b border-slate-200 bg-white sticky top-0 z-30 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
              <div className="p-2 bg-indigo-600 rounded-xl text-white shadow-md shadow-indigo-600/20">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <span className="font-bold text-lg text-slate-900 tracking-tight">
                  AI Code Architect
                </span>
                <span className="ml-2 text-[10px] bg-indigo-50 border border-indigo-200 text-indigo-700 font-semibold px-2 py-0.5 rounded-full">
                  v1.0.0
                </span>
              </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* Active Provider Badge */}
            <div className="hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-full bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>
                AI: <strong className="text-slate-900 capitalize">{currentSettings.llmProvider}</strong>
                {currentSettings.llmProvider === "ollama" && currentSettings.ollamaModel && (
                  <span className="text-slate-500 font-mono ml-1 text-[11px]">({currentSettings.ollamaModel})</span>
                )}
              </span>
            </div>

            {/* Settings Button */}
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="flex items-center space-x-2 px-3.5 py-1.5 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 text-xs font-bold transition shadow-sm"
            >
              <span>⚙️ Settings</span>
            </button>
          </div>
        </div>
      </header>

      {/* DASHBOARD CONTAINER */}
      <main className="max-w-7xl mx-auto px-6 mt-6">

        {/* ONBOARDING STEPPER BANNER */}
        <div className="p-4 rounded-2xl border border-indigo-200 bg-indigo-50/70 shadow-sm mb-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold tracking-wider uppercase text-indigo-800 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
              Quick Onboarding Workflow
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="p-3 bg-white border border-slate-200 rounded-xl flex items-start space-x-3 shadow-sm">
              <div className="w-6 h-6 rounded-full bg-indigo-600 text-white font-bold text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                1
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900">Select Code Base</div>
                <div className="text-[11px] text-slate-500 mt-0.5">Paste any public URL or select installed GitHub App repo</div>
              </div>
            </div>

            <div className="p-3 bg-white border border-slate-200 rounded-xl flex items-start space-x-3 shadow-sm">
              <div className="w-6 h-6 rounded-full bg-indigo-600 text-white font-bold text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                2
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900">Configure AI Provider</div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  Currently: <span className="text-emerald-700 font-bold uppercase">{currentSettings.llmProvider}</span>
                </div>
              </div>
            </div>

            <div className="p-3 bg-white border border-slate-200 rounded-xl flex items-start space-x-3 shadow-sm">
              <div className="w-6 h-6 rounded-full bg-indigo-600 text-white font-bold text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                3
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900">Analyze Architecture</div>
                <div className="text-[11px] text-slate-500 mt-0.5">Run AST rule engine & view dependency graph & AI PR reviews</div>
              </div>
            </div>
          </div>
        </div>
        
        {/* REPOSITORY ACTIONS & TRIGGER */}
        <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-sm space-y-5">
          
          {/* Mode Toggle */}
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setScanMode("public")}
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-bold transition duration-200 ${
                scanMode === "public"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              <Globe className="w-4 h-4" />
              <span>Quick Scan (Public URL)</span>
            </button>
            <button
              onClick={() => setScanMode("github")}
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-bold transition duration-200 ${
                scanMode === "github"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              <Layers className="w-4 h-4" />
              <span>GitHub App Repos</span>
            </button>
          </div>

          {/* Public URL Scan */}
          {scanMode === "public" && (
            <div className="space-y-3">
              <div className="flex flex-col md:flex-row md:items-center gap-3">
                <div className="flex-1 flex items-center space-x-3 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 focus-within:ring-2 focus-within:ring-indigo-500 shadow-sm">
                  <LinkIcon className="w-4 h-4 text-slate-400 flex-shrink-0" />
                  <input
                    type="text"
                    value={publicRepoUrl}
                    onChange={(e) => { setPublicRepoUrl(e.target.value); setScanError(""); }}
                    onKeyDown={(e) => { if (e.key === "Enter" && !isLoading) runPublicScan(); }}
                    placeholder="Paste public GitHub, Bitbucket, or GitLab URL (e.g. https://bitbucket.org/workspace/repo)"
                    className="bg-transparent text-slate-900 text-sm font-medium w-full focus:outline-none placeholder:text-slate-400"
                  />
                </div>
                <button
                  type="button"
                  onClick={runPublicScan}
                  disabled={isLoading}
                  className="flex items-center justify-center space-x-2 px-6 py-2.5 rounded-xl font-bold bg-gradient-to-tr from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white shadow-md shadow-indigo-500/20 disabled:opacity-50 transition duration-200 cursor-pointer disabled:cursor-not-allowed"
                >
                  <Search className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                  <span>{isLoading ? "Scanning..." : "Scan Repository"}</span>
                </button>
              </div>
              {scanError && (
                <div className="flex items-center space-x-2 text-rose-600 text-xs font-semibold px-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>{scanError}</span>
                </div>
              )}
              {scannedRepoName && !isLoading && (
                <div className="flex items-center space-x-2 text-emerald-600 text-xs font-semibold px-1">
                  <CheckCircle className="w-3.5 h-3.5" />
                  <span>Scan complete for {scannedRepoName}</span>
                </div>
              )}
            </div>
          )}

          {/* GitHub App Repos */}
          {scanMode === "github" && (
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center space-x-3">
                <Layers className="w-5 h-5 text-slate-500" />
                <div className="text-sm font-bold text-slate-700">Select Active Repository:</div>
                <select
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm"
                >
                  {repositories.map((repo) => (
                    <option key={repo.full_name || repo.name} value={repo.full_name || repo.name}>
                      {repo.full_name || repo.name}
                    </option>
                  ))}
                </select>
              </div>

              <button
                onClick={runAnalysis}
                disabled={isLoading}
                className="flex items-center justify-center space-x-2 px-5 py-2.5 rounded-xl font-bold bg-indigo-600 hover:bg-indigo-700 text-white shadow-md shadow-indigo-600/20 disabled:opacity-50 transition duration-200"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                <span>{isLoading ? "Running Architecture Scan..." : "Trigger Codebase Scan"}</span>
              </button>
            </div>
          )}

        </div>

        {/* TABS */}
        <div className="flex border-b border-slate-200 mt-8 space-x-6 text-sm font-bold">
          <button 
            onClick={() => setActiveTab("violations")}
            className={`pb-3 border-b-2 transition duration-200 flex items-center space-x-2 ${activeTab === "violations" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}
          >
            <ShieldAlert className="w-4 h-4" />
            <span>Architecture Violations</span>
          </button>
          <button 
            onClick={() => setActiveTab("review")}
            className={`pb-3 border-b-2 transition duration-200 flex items-center space-x-2 ${activeTab === "review" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}
          >
            <GitPullRequest className="w-4 h-4" />
            <span>Automated AI Reviews</span>
          </button>
        </div>

        {/* CONTENT TABS */}
        <div className="mt-8">
          
          {/* TAB 1: VIOLATIONS OVERVIEW */}
          {activeTab === "violations" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              
              {/* LEFT & CENTER CARD: SCORECARD & LIST */}
              <div className="lg:col-span-2 space-y-6">
                
                {/* METRICS & SCORE */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                  
                  {/* SCORE CARD */}
                  <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col justify-between">
                    <span className="text-slate-500 text-xs font-bold uppercase tracking-wider">Architecture Score</span>
                    <div className="flex items-baseline space-x-1 mt-4">
                      <span className="text-5xl font-extrabold text-slate-900 tracking-tight">{score}</span>
                      <span className="text-slate-400 text-lg">/100</span>
                    </div>
                    <div className="mt-4 flex items-center space-x-2">
                      <div className={`w-2.5 h-2.5 rounded-full ${score >= 90 ? "bg-emerald-500 animate-pulse" : score >= 75 ? "bg-amber-500 animate-pulse" : "bg-rose-500 animate-pulse"}`} />
                      <span className="text-xs font-semibold text-slate-600">
                        {score >= 90 ? "Excellent Standards" : score >= 75 ? "Medium Risk Concerns" : "High Severity Warnings"}
                      </span>
                    </div>
                  </div>

                  {/* COUPLING METRIC CARD */}
                  <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col justify-between">
                    <span className="text-slate-500 text-xs font-bold uppercase tracking-wider">Circular Imports</span>
                    <div className="flex items-baseline space-x-1 mt-4">
                      <span className="text-5xl font-extrabold text-slate-900 tracking-tight">{graphData.circular_dependencies.length}</span>
                    </div>
                    <span className="text-xs text-slate-500 mt-4 block">Cycles increase coupling and dependency leaks.</span>
                  </div>

                  {/* CODE QUALITY VIOLATIONS */}
                  <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col justify-between">
                    <span className="text-slate-500 text-xs font-bold uppercase tracking-wider">Total Violations</span>
                    <div className="flex items-baseline space-x-1 mt-4">
                      <span className="text-5xl font-extrabold text-slate-900 tracking-tight">{violations.length}</span>
                    </div>
                    <span className="text-xs text-slate-500 mt-4 block">Issues identified by rules parser.</span>
                  </div>

                </div>

                {/* VIOLATIONS TABLE */}
                <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
                    <h3 className="font-bold text-sm text-slate-900">Detected Rule Violations</h3>
                    <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-slate-200 text-slate-700">
                      {violations.length} Issues
                    </span>
                  </div>

                  {violations.length === 0 ? (
                    <div className="p-12 text-center text-slate-500 space-y-3">
                      <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto" />
                      <div className="text-base font-bold text-slate-900">No Architectural Violations Detected</div>
                      <p className="text-xs max-w-sm mx-auto">Your repository cleanly complies with N+1 query limits, async boundaries, and layer constraints.</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {violations.map((v, i) => (
                        <div 
                          key={i}
                          onClick={() => setSelectedViolation(v)}
                          className={`p-4 hover:bg-indigo-50/50 transition cursor-pointer flex items-center justify-between ${selectedViolation === v ? "bg-indigo-50/80" : ""}`}
                        >
                          <div className="flex items-center space-x-3.5">
                            <AlertTriangle className={`w-5 h-5 flex-shrink-0 ${v.severity === "CRITICAL" || v.severity === "HIGH" ? "text-rose-500" : "text-amber-500"}`} />
                            <div>
                              <div className="font-bold text-sm text-slate-900">{v.rule_name}</div>
                              <div className="text-xs text-slate-500 font-mono mt-0.5">{v.file_path}:{v.line}</div>
                            </div>
                          </div>

                          <div className="flex items-center space-x-3">
                            <span className={`text-[10px] font-extrabold px-2.5 py-0.5 rounded-md ${
                              v.severity === "CRITICAL" || v.severity === "HIGH" 
                                ? "bg-rose-100 text-rose-700 border border-rose-200" 
                                : "bg-amber-100 text-amber-800 border border-amber-200"
                            }`}>
                              {v.severity}
                            </span>
                            <ArrowRight className="w-4 h-4 text-slate-400" />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

              </div>

              {/* RIGHT SIDEBAR: CODE SNIPPET INSPECTOR */}
              <div className="space-y-6">
                <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm space-y-4">
                  <h3 className="font-bold text-sm text-slate-900 border-b border-slate-200 pb-3 flex items-center space-x-2">
                    <FileCode className="w-4 h-4 text-indigo-600" />
                    <span>Violation Inspector</span>
                  </h3>

                  {selectedViolation ? (
                    <div className="space-y-4">
                      <div>
                        <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Rule</div>
                        <div className="text-sm font-bold text-slate-900 mt-1">{selectedViolation.rule_name}</div>
                      </div>

                      <div>
                        <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Location</div>
                        <div className="text-xs font-mono text-indigo-600 mt-1 bg-indigo-50 px-2.5 py-1.5 rounded-lg border border-indigo-200 break-all inline-block max-w-full">
                          {selectedViolation.file_path}:{selectedViolation.line}
                        </div>
                      </div>

                      <div>
                        <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Description & Verdict</div>
                        <p className="text-xs text-slate-700 mt-1 leading-relaxed break-words">{selectedViolation.message}</p>
                      </div>

                      {selectedViolation.suggested_fix && (
                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl space-y-1">
                          <div className="text-[11px] font-bold text-emerald-800 flex items-center gap-1">
                            <span>💡 Recommended Refactoring Fix</span>
                          </div>
                          <p className="text-xs text-emerald-900 leading-relaxed font-medium break-words">
                            {selectedViolation.suggested_fix}
                          </p>
                        </div>
                      )}

                      {/* AI REFACTORING CODE FIX GENERATOR */}
                      <div className="pt-2">
                        <button
                          onClick={() => triggerAiFix(selectedViolation)}
                          disabled={isGeneratingAiFix}
                          className="w-full flex items-center justify-center space-x-2 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm disabled:opacity-50 transition"
                        >
                          <Sparkles className={`w-3.5 h-3.5 ${isGeneratingAiFix ? "animate-spin" : ""}`} />
                          <span>{isGeneratingAiFix ? "AI Architect Generating Suggestions..." : "🤖 Generate AI Refactoring Suggestion"}</span>
                        </button>
                      </div>

                      {aiFixText && (
                        <div className="p-4 bg-slate-900 text-slate-100 rounded-xl space-y-2 border border-slate-800">
                          <div className="text-xs font-bold text-indigo-400 flex items-center gap-1.5 border-b border-slate-800 pb-2">
                            <Sparkles className="w-3.5 h-3.5" />
                            <span>AI Architect Refactoring Guidance</span>
                          </div>
                          <div className="prose prose-invert prose-xs max-w-none text-xs text-slate-200 whitespace-pre-wrap leading-relaxed break-words">
                            {aiFixText}
                          </div>
                        </div>
                      )}

                      {selectedViolation.code_snippet && (
                        <div>
                          <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Code Context</div>
                          <pre className="p-3 rounded-xl bg-slate-900 text-slate-100 font-mono text-[11px] overflow-x-auto border border-slate-800">
                            <code>{selectedViolation.code_snippet}</code>
                          </pre>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="py-12 text-center text-slate-400 space-y-2">
                      <Search className="w-8 h-8 mx-auto text-slate-300" />
                      <p className="text-xs">Click on any rule violation to inspect code context and fix advice.</p>
                    </div>
                  )}
                </div>
              </div>

            </div>
          )}

          {/* TAB 2: AUTOMATED AI PR REVIEWS */}
          {activeTab === "review" && (
            <div className="max-w-3xl mx-auto space-y-6">
              
              {/* TRIGGER SECTION */}
              <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm space-y-5">
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Audit Pull Request Changes & Comment</h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Connects to your repository's Pull Request page, analyzes proposed code diffs, evaluates architecture rules, and publishes automated review critiques to GitHub.
                  </p>
                </div>

                {/* What is a PR Banner */}
                <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 flex items-start gap-2.5">
                  <GitPullRequest className="w-4 h-4 text-indigo-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-slate-900">What is a Pull Request (PR)?</span>
                    <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                      A Pull Request is a set of code changes submitted by a developer. Each PR has a unique number (e.g. PR #1). Select an open PR below or enter its number to generate and publish an AI review directly to GitHub.
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
                  
                  {/* PR Selector Dropdown or No PRs Found state */}
                  <div className="md:col-span-2">
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs font-semibold text-slate-700">
                        {openPRs.length > 0 ? `Select Pull Request (${openPRs.length} available)` : "Pull Request Selection"}
                      </label>
                      {isLoadingPRs && (
                        <span className="text-[10px] text-slate-400 animate-pulse font-semibold">Fetching PRs...</span>
                      )}
                    </div>

                    {openPRs.length > 0 ? (
                      <select
                        value={prNumber}
                        onChange={(e) => setPrNumber(e.target.value)}
                        className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-900 focus:outline-none focus:border-indigo-500 shadow-sm font-sans"
                      >
                        {openPRs.map((pr) => {
                          const stateLabel = pr.merged_at ? "MERGED" : pr.state ? pr.state.toUpperCase() : "OPEN";
                          const author = pr.user?.login ? `@${pr.user.login}` : "author";
                          const branch = pr.head?.ref ? `[${pr.head.ref}]` : "";
                          return (
                            <option key={pr.id || pr.number} value={pr.number}>
                              PR #{pr.number}: {pr.title} ({author}) {branch} — {stateLabel}
                            </option>
                          );
                        })}
                      </select>
                    ) : (
                      <div className="space-y-2">
                        <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-xl flex items-center justify-between text-xs text-amber-800">
                          <span className="font-semibold flex items-center gap-1.5">
                            ⚠️ No Pull Requests found in this repository.
                          </span>
                        </div>

                        <div className="flex items-center space-x-2 bg-white border border-slate-200 rounded-xl px-3 py-1.5 shadow-sm">
                          <span className="text-xs text-slate-400 font-semibold whitespace-nowrap">Enter PR # manually:</span>
                          <input
                            type="number"
                            value={prNumber}
                            onChange={(e) => setPrNumber(e.target.value)}
                            placeholder="1"
                            className="bg-transparent text-slate-900 font-bold text-sm w-full focus:outline-none"
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Trigger Button */}
                  <div className="md:col-span-1 pt-4 md:pt-0">
                    <label className="hidden md:block text-xs font-semibold text-transparent mb-1">Action</label>
                    <button
                      onClick={triggerPRReview}
                      disabled={isReviewing || !prNumber}
                      className="w-full flex items-center justify-center space-x-2 px-4 py-2.5 rounded-xl font-bold bg-indigo-600 hover:bg-indigo-700 text-white shadow-md disabled:opacity-50 transition text-xs cursor-pointer disabled:cursor-not-allowed"
                    >
                      {isReviewing ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          <span>Reviewing...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Audit PR #{prNumber}</span>
                        </>
                      )}
                    </button>
                  </div>

                </div>
              </div>

              {/* REVIEW BOARD */}
              {aiReview && (
                <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm text-sm leading-relaxed space-y-4">
                  <div className="pb-4 border-b border-slate-200 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-emerald-800 bg-emerald-50 border border-emerald-200 px-3.5 py-1.5 rounded-xl text-xs font-bold shadow-sm">
                      <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                      <span>Code Review Published to Pull Request #{prNumber}</span>
                    </div>
                  </div>

                  {/* Displaying review markup */}
                  <div className="whitespace-pre-wrap font-sans text-slate-800 text-xs">
                    {aiReview}
                  </div>
                </div>
              )}

            </div>
          )}

        </div>

      </main>

      {/* SETTINGS MODAL */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onSettingsSaved={(newSettings) => setCurrentSettings(newSettings)}
      />

      {/* PRIVATE REPO AUTHORIZATION MODAL */}
      <PrivateRepoAuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        platform={authModalDetails.platform}
        owner={authModalDetails.owner}
        repo={authModalDetails.repo}
        onTokenSavedAndRetry={() => {
          setCurrentSettings(loadSettings());
          runPublicScan();
        }}
      />
    </div>
  );
}
