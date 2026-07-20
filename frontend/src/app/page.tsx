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

// Live API Connection.

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

  // Load Repositories from backend
  useEffect(() => {
    setIsFetchingRepos(true);
    fetch("http://localhost:8000/api/v1/github/repositories")
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

      // 1. Analyze rules
      const reviewRes = await fetch("http://localhost:8000/api/v1/review/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const reviewData = await reviewRes.json();

      // 2. Analyze graph
      const graphRes = await fetch("http://localhost:8000/api/v1/graph/analyze-repo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
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

      // 1. Analyze rules
      const reviewRes = await fetch("http://localhost:8000/api/v1/review/scan-public", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!reviewRes.ok) {
        const errData = await reviewRes.json();
        throw new Error(errData.detail || "Failed to scan repository.");
      }
      const reviewData = await reviewRes.json();

      // 2. Analyze graph
      const graphRes = await fetch("http://localhost:8000/api/v1/graph/scan-public", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
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
    setIsReviewing(true);
    setAiReview("");

    try {
      const payload = {
        owner: "abhinav26999",
        repo: selectedRepo,
        pull_number: parseInt(prNumber) || 1,
        installation_id: null
      };

      const response = await fetch("http://localhost:8000/api/v1/review/pr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await response.json();
      setAiReview(data.review_body || "Failed to generate review.");
    } catch (e) {
      console.error(e);
      setAiReview("Error connecting to backend API.");
    } finally {
      setIsReviewing(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 selection:bg-indigo-500 selection:text-white pb-10">
      
      {/* HEADER SECTION */}
      <header className="border-b border-zinc-800 bg-zinc-900/40 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <span className="font-bold text-lg tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-zinc-200 to-zinc-400">
                Antigravity Reviewer
              </span>
              <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                v1.0.0
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-semibold">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>Live API Connected</span>
            </div>
          </div>
        </div>
      </header>

      {/* DASHBOARD CONTAINER */}
      <main className="max-w-7xl mx-auto px-6 mt-8">
        
        {/* REPOSITORY ACTIONS & TRIGGER */}
        <div className="p-5 rounded-2xl border border-zinc-800 bg-zinc-900/30 backdrop-blur-md space-y-5">
          
          {/* Mode Toggle */}
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setScanMode("public")}
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-semibold transition duration-200 ${
                scanMode === "public"
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/20"
                  : "bg-zinc-800 text-zinc-400 hover:text-white"
              }`}
            >
              <Globe className="w-4 h-4" />
              <span>Quick Scan (Public URL)</span>
            </button>
            <button
              onClick={() => setScanMode("github")}
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-semibold transition duration-200 ${
                scanMode === "github"
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/20"
                  : "bg-zinc-800 text-zinc-400 hover:text-white"
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
                <div className="flex-1 flex items-center space-x-3 bg-zinc-850 border border-zinc-700 rounded-xl px-4 py-2.5 focus-within:ring-2 focus-within:ring-indigo-500">
                  <LinkIcon className="w-4 h-4 text-zinc-500 flex-shrink-0" />
                  <input
                    type="text"
                    value={publicRepoUrl}
                    onChange={(e) => { setPublicRepoUrl(e.target.value); setScanError(""); }}
                    onKeyDown={(e) => { if (e.key === "Enter" && !isLoading) runPublicScan(); }}
                    placeholder="Paste public GitHub URL (e.g. https://github.com/expressjs/express)"
                    className="bg-transparent text-white text-sm font-medium w-full focus:outline-none placeholder:text-zinc-600"
                  />
                </div>
                <button
                  type="button"
                  onClick={runPublicScan}
                  disabled={isLoading}
                  className="flex items-center justify-center space-x-2 px-6 py-2.5 rounded-xl font-bold bg-gradient-to-tr from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white shadow-lg shadow-indigo-500/20 disabled:opacity-50 transition duration-200 cursor-pointer disabled:cursor-not-allowed"
                >
                  <Search className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                  <span>{isLoading ? "Scanning..." : "Scan Repository"}</span>
                </button>
              </div>
              {scanError && (
                <div className="flex items-center space-x-2 text-red-400 text-xs font-semibold px-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>{scanError}</span>
                </div>
              )}
              {scannedRepoName && !isLoading && (
                <div className="flex items-center space-x-2 text-emerald-400 text-xs font-semibold px-1">
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
                <Layers className="w-5 h-5 text-zinc-400" />
                <div className="text-sm font-semibold text-zinc-400">Select Active Repository:</div>
                <select
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="bg-zinc-850 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm font-semibold text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
                className="flex items-center justify-center space-x-2 px-5 py-2.5 rounded-xl font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-500/10 disabled:opacity-50 transition duration-200"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                <span>{isLoading ? "Running Architecture Scan..." : "Trigger Codebase Scan"}</span>
              </button>
            </div>
          )}

        </div>

        {/* TABS */}
        <div className="flex border-b border-zinc-850 mt-8 space-x-6 text-sm font-semibold">
          <button 
            onClick={() => setActiveTab("overview")}
            className={`pb-3 border-b-2 transition duration-200 flex items-center space-x-2 ${activeTab === "overview" ? "border-indigo-500 text-indigo-400" : "border-transparent text-zinc-400 hover:text-zinc-200"}`}
          >
            <ShieldAlert className="w-4 h-4" />
            <span>Architecture Violations</span>
          </button>
          <button 
            onClick={() => setActiveTab("graph")}
            className={`pb-3 border-b-2 transition duration-200 flex items-center space-x-2 ${activeTab === "graph" ? "border-indigo-500 text-indigo-400" : "border-transparent text-zinc-400 hover:text-zinc-200"}`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Dependency Graph</span>
          </button>
          <button 
            onClick={() => setActiveTab("review")}
            className={`pb-3 border-b-2 transition duration-200 flex items-center space-x-2 ${activeTab === "review" ? "border-indigo-500 text-indigo-400" : "border-transparent text-zinc-400 hover:text-zinc-200"}`}
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
                  <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 flex flex-col justify-between">
                    <span className="text-zinc-400 text-xs font-bold uppercase tracking-wider">Architecture Score</span>
                    <div className="flex items-baseline space-x-1 mt-4">
                      <span className="text-5xl font-extrabold text-white tracking-tight">{score}</span>
                      <span className="text-zinc-500 text-lg">/100</span>
                    </div>
                    <div className="mt-4 flex items-center space-x-2">
                      <div className={`w-2.5 h-2.5 rounded-full ${score >= 90 ? "bg-emerald-500 animate-pulse" : score >= 75 ? "bg-amber-500 animate-pulse" : "bg-red-500 animate-pulse"}`} />
                      <span className="text-xs font-semibold text-zinc-400">
                        {score >= 90 ? "Excellent Standards" : score >= 75 ? "Medium Risk Concerns" : "High Severity Warnings"}
                      </span>
                    </div>
                  </div>

                  {/* COUPLING METRIC CARD */}
                  <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 flex flex-col justify-between">
                    <span className="text-zinc-400 text-xs font-bold uppercase tracking-wider">Circular Imports</span>
                    <div className="flex items-baseline space-x-1 mt-4">
                      <span className="text-5xl font-extrabold text-white tracking-tight">{graphData.circular_dependencies.length}</span>
                    </div>
                    <span className="text-xs text-zinc-500 mt-4 block">Cycles increase coupling and dependency leaks.</span>
                  </div>

                  {/* CODE QUALITY VIOLATIONS */}
                  <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 flex flex-col justify-between">
                    <span className="text-zinc-400 text-xs font-bold uppercase tracking-wider">Total Violations</span>
                    <div className="flex items-baseline space-x-1 mt-4">
                      <span className="text-5xl font-extrabold text-white tracking-tight">{violations.length}</span>
                    </div>
                    <span className="text-xs text-zinc-500 mt-4 block">Issues identified by rules parser.</span>
                  </div>

                </div>

                {/* VIOLATIONS TABLE */}
                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/10 overflow-hidden">
                  <div className="p-5 border-b border-zinc-850 bg-zinc-900/30 font-semibold text-sm">
                    Structural Issues Found ({violations.length})
                  </div>
                  
                  {violations.length === 0 ? (
                    <div className="p-10 flex flex-col items-center justify-center text-zinc-500">
                      <CheckCircle className="w-10 h-10 text-emerald-500 mb-2" />
                      <div>No architectural violations found. Nice work!</div>
                    </div>
                  ) : (
                    <div className="divide-y divide-zinc-850">
                      {violations.map((v, i) => (
                        <div 
                          key={i} 
                          onClick={() => setSelectedViolation(v)}
                          className={`p-5 flex items-start justify-between cursor-pointer hover:bg-zinc-900/30 transition duration-150 ${selectedViolation?.file_path === v.file_path && selectedViolation?.line === v.line ? "bg-indigo-600/5 border-l-4 border-l-indigo-500" : ""}`}
                        >
                          <div className="space-y-1">
                            <div className="flex items-center space-x-2">
                              <span className="font-semibold text-sm text-white">{v.rule_name}</span>
                              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                v.severity === "CRITICAL" ? "bg-red-500/10 text-red-400 border border-red-500/20" :
                                v.severity === "HIGH" ? "bg-orange-500/10 text-orange-400 border border-orange-500/20" :
                                v.severity === "MEDIUM" ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" :
                                "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                              }`}>
                                {v.severity}
                              </span>
                            </div>
                            <p className="text-xs text-zinc-400 max-w-lg">{v.message}</p>
                            <div className="text-[11px] text-zinc-500 flex items-center space-x-1">
                              <FileCode className="w-3.5 h-3.5" />
                              <span>{v.file_path} : Line {v.line}</span>
                            </div>
                          </div>
                          <ArrowRight className="w-4 h-4 text-zinc-600 self-center" />
                        </div>
                      ))}
                    </div>
                  )}

                </div>

              </div>

              {/* RIGHT DRAWER: DETAILED VIEW */}
              <div className="space-y-6">
                
                {selectedViolation ? (
                  <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/30 backdrop-blur-md space-y-6">
                    <div>
                      <div className="text-xs font-bold text-indigo-400 uppercase tracking-widest">Selected Violation Details</div>
                      <h3 className="text-lg font-bold text-white mt-1">{selectedViolation.rule_name}</h3>
                    </div>

                    <div className="space-y-2">
                      <div className="text-xs text-zinc-500">Violation Path</div>
                      <div className="p-3 bg-zinc-900 rounded-xl text-xs font-mono text-zinc-300 border border-zinc-800">
                        {selectedViolation.file_path} : {selectedViolation.line}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <div className="text-xs text-zinc-500">Summary Message</div>
                      <div className="p-4 bg-zinc-900/50 rounded-xl text-xs leading-relaxed text-zinc-300 border border-zinc-800/80">
                        {selectedViolation.message}
                      </div>
                    </div>

                    {selectedViolation.code_snippet && (
                      <div className="space-y-2">
                        <div className="text-xs text-zinc-500">Code Context</div>
                        <pre className="p-4 bg-zinc-950 border border-zinc-850 rounded-xl overflow-x-auto text-[11px] font-mono text-zinc-300">
                          <code>{selectedViolation.code_snippet}</code>
                        </pre>
                      </div>
                    )}

                    <div className="p-4 rounded-xl bg-indigo-500/5 border border-indigo-500/10 text-xs text-indigo-300 leading-relaxed">
                      💡 <strong>Refactoring suggestion:</strong> Open this file locally and resolve direct dependencies. Avoid importing models/database managers directly into route controller controllers; extract DB queries to separate service interfaces.
                    </div>
                  </div>
                ) : (
                  <div className="p-10 rounded-2xl border border-zinc-800 bg-zinc-900/10 flex flex-col items-center justify-center text-zinc-500 text-center">
                    <ShieldAlert className="w-8 h-8 text-zinc-600 mb-2" />
                    <div>Select a violation to view full context and refactoring fixes.</div>
                  </div>
                )}

              </div>

            </div>
          )}

          {/* TAB 2: DEPENDENCY GRAPH */}
          {activeTab === "graph" && (
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
              
              {/* LEFT GRAPH BOARD */}
              <div className="lg:col-span-3 space-y-6">
                <DependencyGraph 
                  nodes={graphData.nodes} 
                  edges={graphData.edges} 
                  circularDependencies={graphData.circular_dependencies}
                  onSelectNode={(node) => setSelectedNode(node)}
                />
              </div>

              {/* RIGHT GRAPH STATS */}
              <div className="space-y-6">
                
                {/* GENERAL STATS */}
                <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 space-y-4">
                  <h4 className="font-bold text-sm text-white">Graph Architecture Metrics</h4>
                  <div className="divide-y divide-zinc-800 text-xs">
                    <div className="py-2.5 flex justify-between">
                      <span className="text-zinc-400">Total Codebase Files</span>
                      <span className="font-semibold text-white">{graphData.total_files}</span>
                    </div>
                    <div className="py-2.5 flex justify-between">
                      <span className="text-zinc-400">Total Connections</span>
                      <span className="font-semibold text-white">{graphData.edges.length}</span>
                    </div>
                    <div className="py-2.5 flex justify-between">
                      <span className="text-zinc-400">Average Instability</span>
                      <span className="font-semibold text-white">{(graphData.average_instability).toFixed(2)}</span>
                    </div>
                  </div>
                </div>

                {/* SELECTED NODE VIEW */}
                {selectedNode ? (
                  <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/30 backdrop-blur-md space-y-5">
                    <div>
                      <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">Selected Module</div>
                      <h4 className="text-sm font-bold text-white mt-0.5 truncate">{selectedNode.file_path.split("/").pop()}</h4>
                    </div>

                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between py-1.5 border-b border-zinc-800">
                        <span className="text-zinc-400">Afferent Coupling (Ca)</span>
                        <span className="font-semibold text-white">{selectedNode.metrics.afferent_coupling}</span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-zinc-800">
                        <span className="text-zinc-400">Efferent Coupling (Ce)</span>
                        <span className="font-semibold text-white">{selectedNode.metrics.efferent_coupling}</span>
                      </div>
                      <div className="flex justify-between py-1.5">
                        <span className="text-zinc-400">Instability Index (I)</span>
                        <span className="font-semibold text-white">{(selectedNode.metrics.instability).toFixed(2)}</span>
                      </div>
                    </div>

                    <div className="text-[11px] text-zinc-500 leading-relaxed">
                      Instability represents how susceptible this module is to changes. <strong>I = 1</strong> means it relies purely on other modules, whereas <strong>I = 0</strong> means it is highly independent.
                    </div>
                  </div>
                ) : (
                  <div className="p-6 rounded-2xl border border-zinc-850 bg-zinc-900/10 text-center text-xs text-zinc-500">
                    💡 Click on any node in the dependency graph to inspect coupling metrics and dependency instability.
                  </div>
                )}

              </div>

            </div>
          )}

          {/* TAB 3: AUTOMATED AI REVIEWS */}
          {activeTab === "review" && (
            <div className="max-w-3xl mx-auto space-y-6">
              
              {/* TRIGGER SECTION */}
              <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/20 space-y-6">
                <div>
                  <h3 className="text-lg font-bold text-white">Trigger AI Pull Request Critique</h3>
                  <p className="text-xs text-zinc-400 mt-1">
                    Connects to your repository's Pull Request page, crawls code changes, matches semantic post-mortem insights, and publishes review summaries to GitHub.
                  </p>
                </div>

                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2 bg-zinc-850 border border-zinc-700 rounded-lg px-3 py-1.5">
                    <span className="text-xs text-zinc-500">PR Number:</span>
                    <input
                      type="number"
                      value={prNumber}
                      onChange={(e) => setPrNumber(e.target.value)}
                      className="bg-transparent text-white font-bold text-sm w-16 focus:outline-none"
                    />
                  </div>

                  <button
                    onClick={triggerPRReview}
                    disabled={isReviewing}
                    className="flex-1 flex items-center justify-center space-x-2 px-5 py-2 rounded-xl font-bold bg-gradient-to-tr from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white shadow-lg disabled:opacity-50 transition duration-200"
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
                <div className="p-8 rounded-2xl border border-zinc-800 bg-zinc-900/30 backdrop-blur-md prose prose-invert max-w-none text-sm leading-relaxed space-y-4">
                  <div className="pb-4 border-b border-zinc-800 flex items-center justify-between">
                    <span className="text-xs font-bold text-indigo-400 uppercase tracking-widest flex items-center space-x-2">
                      <CheckCircle className="w-4 h-4 text-indigo-500" />
                      <span>Review Published on GitHub PR #{prNumber}</span>
                    </span>
                  </div>

                  {/* Displaying review markup */}
                  <div className="whitespace-pre-wrap font-sans text-zinc-300 text-xs">
                    {aiReview}
                  </div>
                </div>
              )}

            </div>
          )}

        </div>

      </main>
    </div>
  );
}
