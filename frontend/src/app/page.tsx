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
import { getApiHeaders, loadSettings, AppSettings } from "../utils/settings";

interface Violation {
  file_path: string;
  line: number;
  rule_name: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  message: string;
  code_snippet?: string;
}

interface Repository {
  name: string;
  full_name: string;
  owner: { login: string };
  default_branch: string;
}

export default function Home() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"overview" | "graph" | "review">("overview");
  
  const [score, setScore] = useState<number>(100);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [graphData, setGraphData] = useState<any>({ total_files: 0, nodes: [], edges: [], circular_dependencies: [], average_instability: 0.0 });
  
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [prNumber, setPrNumber] = useState<string>("1");
  const [aiReview, setAiReview] = useState<string>("");
  const [isReviewing, setIsReviewing] = useState<boolean>(false);
  
  const [selectedViolation, setSelectedViolation] = useState<Violation | null>(null);
  const [selectedNode, setSelectedNode] = useState<{ file_path: string; metrics: any } | null>(null);

  // Public Scan State
  const [scanMode, setScanMode] = useState<"public" | "github">("public");
  const [publicRepoUrl, setPublicRepoUrl] = useState<string>("");
  const [scanError, setScanError] = useState<string>("");
  const [scannedRepoName, setScannedRepoName] = useState<string>("");
  const [isFetchingRepos, setIsFetchingRepos] = useState<boolean>(false);

  // Settings Modal State
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [currentSettings, setCurrentSettings] = useState<AppSettings>(loadSettings());

  useEffect(() => {
    setCurrentSettings(loadSettings());
  }, []);

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
          setSelectedRepo(data[0].name);
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
      const payload = {
        owner: "abhinav26999",
        repo: selectedRepo,
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
        throw new Error(errData.detail || "Failed to scan repository.");
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
    const targetRepo = scanMode === "github" ? selectedRepo : scannedRepoName ? scannedRepoName.split("/")[1] : selectedRepo;

    if (!targetRepo) {
      setAiReview("Please select a repository from the 'GitHub App Repos' tab or run a Quick Scan first.");
      return;
    }

    setIsReviewing(true);
    setAiReview("");

    const owner = scannedRepoName ? scannedRepoName.split("/")[0] : "abhinav26999";

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

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 selection:bg-indigo-500 selection:text-white pb-10">
      
      {/* HEADER SECTION */}
      <header className="border-b border-slate-200 bg-white sticky top-0 z-30 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-indigo-600 to-purple-600 flex items-center justify-center shadow-md shadow-indigo-500/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <span className="font-bold text-lg tracking-tight text-slate-900">
                Antigravity Reviewer
              </span>
              <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
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
                    <option key={repo.name} value={repo.name}>
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
            onClick={() => setActiveTab("overview")}
            className={`pb-3 border-b-2 transition duration-200 flex items-center space-x-2 ${activeTab === "overview" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}
          >
            <ShieldAlert className="w-4 h-4" />
            <span>Architecture Violations</span>
          </button>
          <button 
            onClick={() => setActiveTab("graph")}
            className={`pb-3 border-b-2 transition duration-200 flex items-center space-x-2 ${activeTab === "graph" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Dependency Graph</span>
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
          {activeTab === "overview" && (
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
                        <div className="text-xs font-mono text-indigo-600 mt-1 bg-indigo-50 px-2 py-1 rounded border border-indigo-200">
                          {selectedViolation.file_path}:{selectedViolation.line}
                        </div>
                      </div>

                      <div>
                        <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Description</div>
                        <p className="text-xs text-slate-700 mt-1 leading-relaxed">{selectedViolation.message}</p>
                      </div>

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

          {/* TAB 2: DEPENDENCY GRAPH */}
          {activeTab === "graph" && (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-slate-900 text-base">Interactive Codebase Dependency Graph</h3>
                  <p className="text-xs text-slate-500 mt-1">Directed graph visualization of module couplings, instability indexes, and circular dependencies.</p>
                </div>
                <div className="flex items-center space-x-2 text-xs font-bold px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 border border-slate-200">
                  <Activity className="w-3.5 h-3.5 text-indigo-600" />
                  <span>{graphData.total_files} Code Files Analyzed</span>
                </div>
              </div>

              <div className="border border-slate-200 rounded-xl bg-slate-50 overflow-hidden h-[500px]">
                <DependencyGraph 
                  nodes={graphData.nodes} 
                  edges={graphData.edges} 
                  circularDependencies={graphData.circular_dependencies || []}
                  onSelectNode={(node) => setSelectedNode(node)} 
                />
              </div>
            </div>
          )}

          {/* TAB 3: AUTOMATED AI PR REVIEWS */}
          {activeTab === "review" && (
            <div className="max-w-3xl mx-auto space-y-6">
              
              {/* TRIGGER SECTION */}
              <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm space-y-6">
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Trigger AI Pull Request Critique</h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Connects to your repository's Pull Request page, crawls code changes, matches semantic post-mortem insights, and publishes review summaries to GitHub.
                  </p>
                </div>

                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
                    <span className="text-xs text-slate-500 font-semibold">PR Number:</span>
                    <input
                      type="number"
                      value={prNumber}
                      onChange={(e) => setPrNumber(e.target.value)}
                      className="bg-transparent text-slate-900 font-bold text-sm w-16 focus:outline-none"
                    />
                  </div>

                  <button
                    onClick={triggerPRReview}
                    disabled={isReviewing}
                    className="flex-1 flex items-center justify-center space-x-2 px-5 py-2.5 rounded-xl font-bold bg-gradient-to-tr from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white shadow-md disabled:opacity-50 transition duration-200"
                  >
                    {isReviewing ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        <span>Synthesizing AI Review...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        <span>Generate & Comment PR Review</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* REVIEW BOARD */}
              {aiReview && (
                <div className="p-8 rounded-2xl border border-slate-200 bg-white shadow-sm text-sm leading-relaxed space-y-4">
                  <div className="pb-4 border-b border-slate-200 flex items-center justify-between">
                    <span className="text-xs font-bold text-indigo-600 uppercase tracking-widest flex items-center space-x-2">
                      <CheckCircle className="w-4 h-4 text-indigo-600" />
                      <span>Review Published on GitHub PR #{prNumber}</span>
                    </span>
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
    </div>
  );
}
