"use client";

import React, { useState, useEffect, useRef } from "react";
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
  Link as LinkIcon,
  X
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
  const [taskStatusMsg, setTaskStatusMsg] = useState<string>("");

  // AI Auto-Fix (Diff & PR) State
  const [isApplyingFix, setIsApplyingFix] = useState<boolean>(false);
  const [fixResult, setFixResult] = useState<{
    original_snippet: string;
    fixed_snippet: string;
    explanation: string;
    stale_warning: boolean;
    language: string;
  } | null>(null);
  const [fixError, setFixError] = useState<{ message: string; tip: string } | null>(null);
  const [createdPRInfo, setCreatedPRInfo] = useState<{ branch_name: string; pr_url: string; pr_number: number; message?: string } | null>(null);
  const [isCreatingPR, setIsCreatingPR] = useState<boolean>(false);
  const [prError, setPrError] = useState<{ message: string; tip: string } | null>(null);

  // Helper to change selected violation and reset all related AI suggestion / fix state variables
  const selectViolationAndClearState = (v: Violation) => {
    setSelectedViolation(v);
    setAiFixText("");
    setFixResult(null);
    setFixError(null);
    setCreatedPRInfo(null);
    setPrError(null);
    setIsFixModalOpen(false);
  };

  // Ref for auto-scrolling inspector into view when a violation is selected
  const inspectorRef = useRef<HTMLDivElement>(null);

  // Studio Modal State
  const [isFixModalOpen, setIsFixModalOpen] = useState<boolean>(false);

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

  // Reset Violation Inspector state when repository selection, scan mode, or active tab changes
  useEffect(() => {
    setSelectedViolation(null);
    setAiFixText("");
    setFixResult(null);
    setFixError(null);
    setCreatedPRInfo(null);
    setPrError(null);
  }, [selectedRepo, publicRepoUrl, scanMode, activeTab]);

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

  // Helper to poll background Celery tasks
  const pollTaskStatus = (
    taskId: string,
    onSuccess: (result: any) => void,
    onError: (err: string) => void,
    onProgress: (status: string) => void
  ) => {
    setTaskStatusMsg("Enqueued. Waiting for background worker...");
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/v1/review/task-status/${taskId}`);
        if (!response.ok) {
          throw new Error(`Failed to check task status. Server returned ${response.status}`);
        }
        const data = await response.json();
        
        if (data.status === "PENDING") {
          onProgress("Enqueued. Waiting for background worker...");
        } else if (data.status === "STARTED") {
          onProgress("Cloning repository and running AST audits...");
        } else if (data.status === "SUCCESS") {
          clearInterval(interval);
          if (data.result && data.result.status === "error") {
            onError(data.result.error);
          } else {
            onSuccess(data.result);
          }
        } else if (data.status === "FAILURE") {
          clearInterval(interval);
          onError(data.error || "Background task execution failed.");
        }
      } catch (e: any) {
        clearInterval(interval);
        onError(e.message || "Error polling task status.");
      }
    }, 1200);
    return interval;
  };

  // Run Codebase Analysis (Stage 1-4) using Celery background queue
  const runAnalysis = async () => {
    setIsLoading(true);
    setTaskStatusMsg("Contacting server...");
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

      const res = await fetch("http://localhost:8000/api/v1/review/analyze-async", {
        method: "POST",
        headers: getApiHeaders(),
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error("Failed to queue analysis task.");
      }

      const taskData = await res.json();
      const taskId = taskData.task_id;

      pollTaskStatus(
        taskId,
        (result) => {
          setScore(result.score || 100);
          setViolations(result.violations || []);
          setGraphData(result.graph);
          setIsLoading(false);
          setTaskStatusMsg("");
          if (result.score === 100) {
            confetti({ particleCount: 150, spread: 80, colors: ["#10b981", "#3b82f6"] });
          }
        },
        (err) => {
          console.error(err);
          alert(`Analysis failed: ${err}`);
          setIsLoading(false);
          setTaskStatusMsg("");
        },
        (status) => {
          setTaskStatusMsg(status);
        }
      );
    } catch (e) {
      console.error(e);
      alert("Backend API is unreachable. Verify FastAPI server is running.");
      setIsLoading(false);
      setTaskStatusMsg("");
    }
  };

  // Run Public Repo Scan using Celery background queue
  const runPublicScan = async () => {
    if (!publicRepoUrl.trim()) {
      setScanError("Please paste a GitHub repository URL.");
      return;
    }
    setScanError("");
    setIsLoading(true);
    setScannedRepoName("");
    setTaskStatusMsg("Contacting server...");

    try {
      const payload = { repo_url: publicRepoUrl.trim() };

      const res = await fetch("http://localhost:8000/api/v1/review/scan-public-async", {
        method: "POST",
        headers: getApiHeaders(),
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error("Failed to queue public scan task.");
      }

      const taskData = await res.json();
      const taskId = taskData.task_id;

      pollTaskStatus(
        taskId,
        (result) => {
          setScore(result.score || 100);
          setViolations(result.violations || []);
          setGraphData(result.graph);
          setScannedRepoName(`${result.owner}/${result.repo}`);
          setIsLoading(false);
          setTaskStatusMsg("");
          if (result.score === 100) {
            confetti({ particleCount: 150, spread: 80, colors: ["#10b981", "#3b82f6"] });
          }
        },
        (err) => {
          console.error(err);
          if (err.includes("PRIVATE_REPO_AUTH_REQUIRED")) {
            const parts = err.split(":");
            const host = parts[1] || "github.com";
            const owner = parts[2] || "";
            const repo = parts[3] || "";
            setAuthModalDetails({ platform: host, owner, repo });
            setIsAuthModalOpen(true);
          } else {
            setScanError(err || "Failed to scan the repository. Make sure it is a valid Git URL.");
          }
          setIsLoading(false);
          setTaskStatusMsg("");
        },
        (status) => {
          setTaskStatusMsg(status);
        }
      );
    } catch (e: any) {
      console.error(e);
      setScanError(e.message || "Failed to scan the repository.");
      setIsLoading(false);
      setTaskStatusMsg("");
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
    setTaskStatusMsg("Queueing PR review task...");

    try {
      const payload = {
        owner: owner,
        repo: targetRepo,
        pull_number: parseInt(prNumber) || 1,
        installation_id: null
      };

      const response = await fetch("http://localhost:8000/api/v1/review/pr-async", {
        method: "POST",
        headers: getApiHeaders(),
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned error ${response.status}`);
      }

      const taskData = await response.json();
      const taskId = taskData.task_id;

      pollTaskStatus(
        taskId,
        (result) => {
          setAiReview(result.review_body || "PR Audit completed, no critique generated.");
          // Update violations/score if returned from PR scan
          if (result.violations) {
            setViolations(result.violations);
          }
          if (result.score !== undefined) {
            setScore(result.score);
          }
          setIsReviewing(false);
          setTaskStatusMsg("");
        },
        (err) => {
          console.error(err);
          setAiReview(`PR Review Error: ${err}`);
          setIsReviewing(false);
          setTaskStatusMsg("");
        },
        (status) => {
          setTaskStatusMsg(status);
        }
      );
    } catch (e: any) {
      console.error(e);
      setAiReview(`PR Review Error: ${e.message || "Error connecting to backend API."}`);
      setIsReviewing(false);
      setTaskStatusMsg("");
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
          severity: v.severity,
          suggested_fix: v.suggested_fix || "",
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

  // Resolve owner and repo for current repository
  const getOwnerAndRepo = () => {
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
    return { owner, repo };
  };

  // Preview AI Code Fix
  const triggerPreviewFix = async (v: Violation) => {
    setIsApplyingFix(true);
    setFixResult(null);
    setFixError(null);
    setCreatedPRInfo(null);
    setPrError(null);

    const { owner, repo } = getOwnerAndRepo();

    try {
      const response = await fetch("http://localhost:8000/api/v1/review/preview-fix", {
        method: "POST",
        headers: getApiHeaders(),
        body: JSON.stringify({
          file_path: v.file_path,
          rule_name: v.rule_name,
          message: v.message,
          severity: v.severity,
          suggested_fix: v.suggested_fix || "",
          code_snippet: v.code_snippet || "",
          violation_line: v.line,
          owner: owner || null,
          repo: repo || null,
          pull_number: prNumber ? parseInt(prNumber) : null,
          installation_id: null
        })
      });

      const data = await response.json();
      if (response.ok) {
        setFixResult(data);
      } else {
        setFixError({
          message: data.message || "Failed to generate preview fix.",
          tip: data.tip || "Please review your LLM/Ollama settings and try again."
        });
      }
    } catch (e: any) {
      setFixError({
        message: "Connection failed.",
        tip: "Verify that the backend is running at http://localhost:8000."
      });
    } finally {
      setIsApplyingFix(false);
    }
  };

  // Apply Fix Locally (Option A - No Commit)
  const triggerApplyLocalFix = async (v: Violation) => {
    if (!fixResult) return;
    setIsCreatingPR(true);
    setCreatedPRInfo(null);
    setPrError(null);

    const { owner, repo } = getOwnerAndRepo();

    try {
      const response = await fetch("http://localhost:8000/api/v1/review/apply-local-fix", {
        method: "POST",
        headers: getApiHeaders(),
        body: JSON.stringify({
          file_path: v.file_path,
          original_snippet: fixResult.original_snippet,
          fixed_code: fixResult.fixed_snippet,
          owner: owner || "",
          repo: repo || ""
        })
      });

      const data = await response.json();
      if (response.ok) {
        setCreatedPRInfo({
          branch_name: "", // Not used
          pr_url: "", // Not used
          pr_number: 0, // Not used
          message: data.message || "Applied successfully."
        } as any);
      } else {
        setPrError({
          message: data.message || "Failed to apply local fix.",
          tip: data.tip || "Ensure the backend has write permission to the local file."
        });
      }
    } catch (e: any) {
      setPrError({
        message: "Connection failed.",
        tip: "Check your backend server status."
      });
    } finally {
      setIsCreatingPR(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-800 selection:bg-indigo-500 selection:text-white pb-16 font-sans antialiased relative overflow-hidden">
      
      {/* Google Fonts Import & Global Reset */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
      <style jsx global>{`
        body {
          font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background-color: #f8fafc;
        }
        pre, code {
          font-family: 'JetBrains Mono', monospace !important;
        }
      `}</style>

      {/* Decorative Background Glows */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-200/20 rounded-full blur-3xl pointer-events-none -z-10 animate-pulse" />
      <div className="absolute top-[20%] right-[10%] w-[600px] h-[600px] bg-violet-200/20 rounded-full blur-3xl pointer-events-none -z-10" />

      {/* STYLISH FLOATING HEADER */}
      <header className="sticky top-4 z-30 px-6 max-w-7xl mx-auto mt-4">
        <div className="flex items-center justify-between px-6 h-16 bg-white border border-slate-200/60 rounded-2xl shadow-sm transition-all duration-300">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-xl text-white shadow-md shadow-indigo-500/20">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <span className="font-extrabold text-base text-slate-900 tracking-tight flex items-center gap-2">
                AI Code Architect
                <span className="text-[10px] bg-indigo-50 border border-indigo-200 text-indigo-600 font-bold px-2 py-0.5 rounded-full">
                  v1.0.0
                </span>
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            {/* Active Provider Badge */}
            <div className="hidden sm:flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-slate-50 border border-slate-200 text-xs font-semibold text-slate-600">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>
                AI Provider: <strong className="text-slate-800 capitalize font-bold">{currentSettings.llmProvider}</strong>
                {currentSettings.llmProvider === "ollama" && currentSettings.ollamaModel && (
                  <span className="text-slate-400 font-mono ml-1.5 text-[11px]">({currentSettings.ollamaModel})</span>
                )}
              </span>
            </div>

            {/* Settings Button */}
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-indigo-50/60 hover:bg-indigo-50 hover:text-indigo-700 text-indigo-600 border border-indigo-200/60 text-xs font-bold transition shadow-sm cursor-pointer"
            >
              <span>⚙ Settings</span>
            </button>
          </div>
        </div>
      </header>

      {/* DASHBOARD CONTAINER */}
      <main className="max-w-7xl mx-auto px-6 mt-8">

        {/* ONBOARDING FLOW TIMELINE */}
        <div className="p-5 rounded-2xl border border-slate-200/80 bg-white shadow-sm mb-8">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-extrabold tracking-wider uppercase text-indigo-600 flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-500" />
              Getting Started Checklist
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-3.5 bg-slate-50 border border-slate-200/60 rounded-xl flex items-start space-x-3.5 hover:shadow-xs transition">
              <div className="w-7 h-7 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-600 font-extrabold text-xs flex items-center justify-center flex-shrink-0">
                1
              </div>
              <div>
                <div className="text-xs font-bold text-slate-800">Select Code Base</div>
                <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">Input your repo link or select an installed GitHub App repo.</div>
              </div>
            </div>

            <div className="p-3.5 bg-slate-50 border border-slate-200/60 rounded-xl flex items-start space-x-3.5 hover:shadow-xs transition">
              <div className="w-7 h-7 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-600 font-extrabold text-xs flex items-center justify-center flex-shrink-0">
                2
              </div>
              <div>
                <div className="text-xs font-bold text-slate-800">Configure LLM</div>
                <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                  Active connection: <span className="text-emerald-600 font-extrabold uppercase">{currentSettings.llmProvider}</span>
                </div>
              </div>
            </div>

            <div className="p-3.5 bg-slate-50 border border-slate-200/60 rounded-xl flex items-start space-x-3.5 hover:shadow-xs transition">
              <div className="w-7 h-7 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-600 font-extrabold text-xs flex items-center justify-center flex-shrink-0">
                3
              </div>
              <div>
                <div className="text-xs font-bold text-slate-800">Review Audits</div>
                <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">Audit architecture violations and trigger AI Auto-Fix.</div>
              </div>
            </div>
          </div>
        </div>
        
        {/* REPOSITORY SELECTION BAR */}
        <div className="p-6 rounded-2xl border border-slate-200 bg-white space-y-6 shadow-sm">
          
          {/* Segmented Mode Picker */}
          <div className="flex items-center bg-slate-100 p-1.5 rounded-xl border border-slate-200/60 w-fit">
            <button
              onClick={() => setScanMode("public")}
              className={`flex items-center space-x-2 px-5 py-2 rounded-lg text-xs font-bold transition duration-200 cursor-pointer ${
                scanMode === "public"
                  ? "bg-white text-indigo-600 shadow-sm border border-slate-200/40"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              <Globe className="w-4 h-4" />
              <span>Public Scan</span>
            </button>
            <button
              onClick={() => setScanMode("github")}
              className={`flex items-center space-x-2 px-5 py-2 rounded-lg text-xs font-bold transition duration-200 cursor-pointer ${
                scanMode === "github"
                  ? "bg-white text-indigo-600 shadow-sm border border-slate-200/40"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              <Layers className="w-4 h-4" />
              <span>GitHub App Repos</span>
            </button>
          </div>

          {/* Public URL Input layout */}
          {scanMode === "public" && (
            <div className="space-y-3.5">
              <div className="flex flex-col md:flex-row md:items-center gap-3">
                <div className="flex-1 flex items-center space-x-3.5 bg-slate-50 border border-slate-200 rounded-xl px-4.5 py-3 focus-within:ring-2 focus-within:ring-indigo-500 shadow-inner transition">
                  <LinkIcon className="w-4.5 h-4.5 text-slate-400 flex-shrink-0" />
                  <input
                    type="text"
                    value={publicRepoUrl}
                    onChange={(e) => { setPublicRepoUrl(e.target.value); setScanError(""); }}
                    onKeyDown={(e) => { if (e.key === "Enter" && !isLoading) runPublicScan(); }}
                    placeholder="Paste public GitHub URL (e.g. https://github.com/owner/repo)"
                    className="bg-transparent text-slate-800 text-sm font-semibold w-full focus:outline-none placeholder:text-slate-400"
                  />
                </div>
                <button
                  type="button"
                  onClick={runPublicScan}
                  disabled={isLoading}
                  className="flex items-center justify-center space-x-2 px-7 py-3 rounded-xl font-bold bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white shadow-md shadow-indigo-600/10 hover:shadow-indigo-500/20 disabled:opacity-50 transition-all duration-200 cursor-pointer disabled:cursor-not-allowed"
                >
                  <Search className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                  <span>{isLoading ? "Analyzing..." : "Analyze Code"}</span>
                </button>
              </div>
              {scanError && (
                <div className="flex items-center space-x-2 text-rose-600 text-xs font-bold px-1 animate-pulse">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>{scanError}</span>
                </div>
              )}
              {scannedRepoName && !isLoading && (
                <div className="flex items-center space-x-2 text-emerald-600 text-xs font-bold px-1">
                  <CheckCircle className="w-3.5 h-3.5" />
                  <span>Repository analyzed successfully: {scannedRepoName}</span>
                </div>
              )}
            </div>
          )}

          {/* GitHub App Select layout */}
          {scanMode === "github" && (
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center space-x-4">
                <Layers className="w-5 h-5 text-slate-400" />
                <div className="text-xs font-extrabold text-slate-500 uppercase tracking-wider">Select Active Repository:</div>
                <select
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm cursor-pointer"
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
                className="flex items-center justify-center space-x-2 px-6 py-2.5 rounded-xl font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/10 disabled:opacity-50 transition duration-200 cursor-pointer"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                <span>{isLoading ? "Scanning Codebase..." : "Trigger Codebase Scan"}</span>
              </button>
            </div>
          )}

        </div>

        {/* PROGRESS BANNER */}
        {(isLoading || isReviewing) && taskStatusMsg && (
          <div className="mt-4 p-4 rounded-xl border border-indigo-100 bg-indigo-50/50 flex items-center space-x-3.5 shadow-sm animate-pulse">
            <RefreshCw className="w-5 h-5 text-indigo-600 animate-spin flex-shrink-0" />
            <div>
              <div className="text-xs font-bold text-indigo-900">Background Job Processing...</div>
              <div className="text-[11px] text-indigo-700/80 font-semibold mt-0.5">{taskStatusMsg}</div>
            </div>
          </div>
        )}

        {/* TABS DESIGN - Segmented pills */}
        <div className="flex bg-slate-100 p-1 rounded-2xl border border-slate-200/60 w-fit mt-10">
          <button 
            onClick={() => setActiveTab("violations")}
            className={`flex items-center space-x-2 px-6 py-2.5 rounded-xl text-xs font-bold transition duration-200 cursor-pointer ${
              activeTab === "violations" 
                ? "bg-white text-indigo-600 shadow-sm border border-slate-200/40" 
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            <ShieldAlert className="w-4 h-4" />
            <span>Architecture Violations</span>
          </button>
          <button 
            onClick={() => setActiveTab("review")}
            className={`flex items-center space-x-2 px-6 py-2.5 rounded-xl text-xs font-bold transition duration-200 cursor-pointer ${
              activeTab === "review" 
                ? "bg-white text-indigo-600 shadow-sm border border-slate-200/40" 
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            <GitPullRequest className="w-4 h-4" />
            <span>Automated AI Reviews</span>
          </button>
        </div>

        {/* CONTENT CHANNELS */}
        <div className="mt-8">
          
          {/* TAB 1: VIOLATIONS OVERVIEW */}
          {activeTab === "violations" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              
              {/* LEFT & CENTER CARD: SCORECARD & LIST */}
              <div className="lg:col-span-2 space-y-6">
                
                {/* METRICS & SCORE */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                  
                  {/* SCORE CARD WITH CIRCULAR SVG LOADER */}
                  <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm flex items-center justify-between hover:shadow-md hover:border-slate-350/80 hover:-translate-y-0.5 transition-all duration-300 group">
                    <div className="space-y-2">
                      <span className="text-slate-400 text-[10px] font-bold uppercase tracking-widest block">Architecture Score</span>
                      <div className="flex items-baseline space-x-1">
                        <span className="text-4xl font-extrabold text-slate-900 tracking-tight">{score}</span>
                        <span className="text-slate-400 text-sm">/100</span>
                      </div>
                      <div className="flex items-center space-x-1.5 pt-2">
                        <div className={`w-2 h-2 rounded-full ${score >= 90 ? "bg-emerald-500" : score >= 75 ? "bg-amber-500" : "bg-rose-500"} animate-pulse`} />
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                          {score >= 90 ? "Excellent" : score >= 75 ? "Medium Risk" : "High Warning"}
                        </span>
                      </div>
                    </div>

                    {/* Circular Score Ring */}
                    <div className="relative w-16 h-16 flex items-center justify-center">
                      <svg className="w-full h-full transform -rotate-90">
                        <circle cx="32" cy="32" r="28" stroke="#f1f5f9" strokeWidth="6" fill="transparent" />
                        <circle 
                          cx="32" 
                          cy="32" 
                          r="28" 
                          stroke={score >= 90 ? "#10b981" : score >= 75 ? "#f59e0b" : "#ef4444"} 
                          strokeWidth="6" 
                          fill="transparent" 
                          strokeDasharray={2 * Math.PI * 28}
                          strokeDashoffset={2 * Math.PI * 28 - (score / 100) * (2 * Math.PI * 28)}
                          className="transition-all duration-1000 ease-out"
                        />
                      </svg>
                      <span className="absolute text-xs font-extrabold text-slate-700">{score}%</span>
                    </div>
                  </div>

                  {/* COUPLING METRIC CARD */}
                  <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col justify-between hover:shadow-md hover:border-slate-350/80 hover:-translate-y-0.5 transition-all duration-300">
                    <span className="text-slate-400 text-[10px] font-bold uppercase tracking-widest">Circular Imports</span>
                    <div className="flex items-baseline space-x-1 mt-3">
                      <span className="text-4xl font-extrabold text-slate-900 tracking-tight">{graphData.circular_dependencies.length}</span>
                    </div>
                    <span className="text-[11px] text-slate-400 mt-4 leading-relaxed font-medium block">Active dependency loop cycles detected in AST.</span>
                  </div>

                  {/* CODE QUALITY VIOLATIONS */}
                  <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm flex flex-col justify-between hover:shadow-md hover:border-slate-350/80 hover:-translate-y-0.5 transition-all duration-300">
                    <span className="text-slate-400 text-[10px] font-bold uppercase tracking-widest">Total Violations</span>
                    <div className="flex items-baseline space-x-1 mt-3">
                      <span className="text-4xl font-extrabold text-slate-900 tracking-tight">{violations.length}</span>
                    </div>
                    <span className="text-[11px] text-slate-400 mt-4 leading-relaxed font-medium block">Lint & architecture boundary warnings.</span>
                  </div>

                </div>

                {/* VIOLATIONS LIST */}
                <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className="px-6 py-4.5 border-b border-slate-200 bg-slate-50/70 flex items-center justify-between">
                    <h3 className="font-extrabold text-sm text-slate-800 tracking-tight">Detected Rule Violations</h3>
                    <span className="text-xs font-bold px-3 py-1 rounded-full bg-slate-200 text-slate-700">
                      {violations.length} Issues
                    </span>
                  </div>

                  {violations.length === 0 ? (
                    <div className="p-16 text-center text-slate-500 space-y-4">
                      <CheckCircle className="w-14 h-14 text-emerald-500 mx-auto" />
                      <div className="text-base font-bold text-slate-900">No Architectural Violations Detected</div>
                      <p className="text-xs max-w-sm mx-auto text-slate-500 leading-relaxed">Your repository cleanly complies with N+1 query limits, async boundaries, and layer constraints.</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100 max-h-[520px] overflow-y-auto">
                      {violations.map((v, i) => (
                        <div 
                          key={i}
                          onClick={() => selectViolationAndClearState(v)}
                          className={`p-5 hover:bg-slate-50/70 transition cursor-pointer flex items-center justify-between border-l-4 ${
                            selectedViolation === v 
                              ? "bg-indigo-50/40 border-l-indigo-600 text-slate-900" 
                              : "border-l-transparent text-slate-700"
                          }`}
                        >
                          <div className="flex items-center space-x-4">
                            <AlertTriangle className={`w-5.5 h-5.5 flex-shrink-0 ${
                              v.severity === "CRITICAL" || v.severity === "HIGH" ? "text-rose-500" : "text-amber-500"
                            }`} />
                            <div>
                              <div className="font-extrabold text-sm text-slate-900">{v.rule_name}</div>
                              <div className="text-xs text-slate-500 font-mono mt-1">{v.file_path}:{v.line}</div>
                            </div>
                          </div>

                          <div className="flex items-center space-x-3.5">
                            <span className={`text-[10px] font-black px-2.5 py-1 rounded-md tracking-wider ${
                              v.severity === "CRITICAL" || v.severity === "HIGH" 
                                ? "bg-rose-50 border border-rose-200 text-rose-600" 
                                : "bg-amber-50 border border-amber-250 text-amber-700"
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

              </div>              {/* RIGHT SIDEBAR: CODE SNIPPET INSPECTOR */}
              <div className="space-y-6">
                <div
                  ref={inspectorRef}
                  className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden sticky top-6 max-h-[calc(100vh-3rem)] flex flex-col text-slate-800"
                >
                  {/* Panel Header - Clean Light Theme */}
                  <div className="flex items-center justify-between px-5 py-4 bg-slate-50 border-b border-slate-200 flex-shrink-0">
                    <div className="flex items-center gap-2.5">
                      <FileCode className="w-4.5 h-4.5 text-indigo-600" />
                      <span className="text-sm font-bold text-slate-800 tracking-wide">Violation Inspector</span>
                    </div>
                    {selectedViolation && (
                      <span className={`text-[10px] font-extrabold px-2.5 py-1 rounded-md tracking-wide ${
                        selectedViolation.severity === "CRITICAL" || selectedViolation.severity === "HIGH"
                          ? "bg-rose-50 border border-rose-200 text-rose-700"
                          : "bg-amber-50 border border-amber-250 text-amber-800"
                      }`}>
                        {selectedViolation.severity}
                      </span>
                    )}
                  </div>

                  {/* Scrollable Inspector Content */}
                  <div className="overflow-y-auto flex-1">
                    {selectedViolation ? (
                      <div className="p-5 space-y-4">
                        
                        {/* Rule Title */}
                        <div>
                          <div className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Rule Violation</div>
                          <div className="text-sm font-bold text-slate-900 leading-tight tracking-tight">{selectedViolation.rule_name}</div>
                        </div>

                        {/* Path Pill - Clean Light Pill */}
                        <div>
                          <div className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Location</div>
                          <div className="inline-flex items-center gap-2 bg-indigo-50 px-3.5 py-2 rounded-lg border border-indigo-150 max-w-full overflow-x-auto">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-600 flex-shrink-0" />
                            <span className="text-[11px] font-mono text-indigo-600 whitespace-nowrap">{selectedViolation.file_path}:{selectedViolation.line}</span>
                          </div>
                        </div>

                        {/* Verdict */}
                        <div>
                          <div className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Description &amp; Verdict</div>
                          <p className="text-xs text-slate-650 leading-relaxed break-words">{selectedViolation.message}</p>
                        </div>

                        {/* Suggested Refactoring fix - Green Box */}
                        {selectedViolation.suggested_fix && (
                          <div className="rounded-xl border border-[#bbf7d0] bg-[#f0fdf4] p-4 space-y-2.5 shadow-xs">
                            <div className="flex items-center gap-2">
                              <div className="w-5 h-5 rounded-full bg-[#22c55e] flex items-center justify-center flex-shrink-0 shadow-sm shadow-emerald-500/10">
                                <span className="text-white text-[9px] font-bold">✓</span>
                              </div>
                              <span className="text-[10px] font-extrabold text-[#166534] tracking-wide uppercase">Recommended Fix</span>
                            </div>
                            <p className="text-xs text-[#14532d] leading-relaxed font-semibold break-words pl-7">{selectedViolation.suggested_fix}</p>
                          </div>
                        )}

                        {/* Interactive Studio Trigger Button */}
                        <button
                          onClick={() => {
                            setIsFixModalOpen(true);
                            if (!fixResult && !isApplyingFix) {
                              triggerPreviewFix(selectedViolation);
                            }
                            if (!aiFixText && !isGeneratingAiFix) {
                              triggerAiFix(selectedViolation);
                            }
                          }}
                          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-bold text-xs rounded-xl shadow-md shadow-indigo-600/10 hover:shadow-indigo-600/20 transition-all duration-200 cursor-pointer mt-2"
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Resolve in AI Studio</span>
                        </button>

                        {/* Code Context */}
                        {selectedViolation.code_snippet && (
                          <div className="space-y-2.5 pt-2">
                            <div className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Code Context</div>
                            <div className="rounded-xl overflow-hidden border border-slate-200 shadow-sm">
                              <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 border-b border-slate-200">
                                <div className="flex gap-1.5">
                                  <div className="w-2.5 h-2.5 rounded-full bg-slate-300" />
                                  <div className="w-2.5 h-2.5 rounded-full bg-slate-300" />
                                  <div className="w-2.5 h-2.5 rounded-full bg-slate-300" />
                                </div>
                              </div>
                              <pre className="p-4 bg-slate-50 text-slate-700 font-mono text-[11px] overflow-x-auto leading-5">
                                <code>{selectedViolation.code_snippet}</code>
                              </pre>
                            </div>
                          </div>
                        )}

                      </div>
                    ) : (
                      <div className="py-20 text-center space-y-3.5 px-6">
                        <div className="w-12 h-12 rounded-full bg-slate-50 border border-slate-200/60 flex items-center justify-center mx-auto">
                          <Search className="w-5 h-5 text-slate-400" />
                        </div>
                        <div className="space-y-1">
                          <p className="text-sm font-bold text-slate-500">No violation selected</p>
                          <p className="text-xs text-slate-400 leading-relaxed max-w-xs mx-auto">Click any rule violation to inspect the code context and AI fix advice.</p>
                        </div>
                      </div>
                    )}
                  </div>
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
                  <h3 className="text-lg font-bold text-slate-900 tracking-tight">Audit Pull Request Changes & Comment</h3>
                  <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                    Connects to your repository's Pull Request page, analyzes proposed code diffs, evaluates architecture rules, and publishes automated review critiques to GitHub.
                  </p>
                </div>

                {/* What is a PR Banner */}
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 flex items-start gap-3">
                  <GitPullRequest className="w-5 h-5 text-indigo-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-extrabold text-slate-800">What is a Pull Request (PR)?</span>
                    <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                      A Pull Request is a set of code changes submitted by a developer. Each PR has a unique number (e.g. PR #1). Select an open PR below or enter its number to generate and publish an AI review directly to GitHub.
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
                  
                  {/* PR Selector Dropdown or Enter PR number manually */}
                  <div className="md:col-span-2">
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider">
                        {openPRs.length > 0 ? `Select Pull Request (${openPRs.length} available)` : "Pull Request Selection"}
                      </label>
                      {isLoadingPRs && (
                        <span className="text-[10px] text-slate-400 animate-pulse font-bold">Fetching PRs...</span>
                      )}
                    </div>

                    {openPRs.length > 0 ? (
                      <select
                        value={prNumber}
                        onChange={(e) => setPrNumber(e.target.value)}
                        className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-800 focus:outline-none focus:border-indigo-500 shadow-sm cursor-pointer"
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
                        <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl flex items-center justify-between text-xs text-amber-800 font-medium">
                          <span className="flex items-center gap-1.5">
                            ⚠️ No Pull Requests found in this repository.
                          </span>
                        </div>

                        <div className="flex items-center space-x-2.5 bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 focus-within:ring-2 focus-within:ring-indigo-500 shadow-inner">
                          <span className="text-xs text-slate-500 font-bold whitespace-nowrap">Enter PR # manually:</span>
                          <input
                            type="number"
                            value={prNumber}
                            onChange={(e) => setPrNumber(e.target.value)}
                            placeholder="1"
                            className="bg-transparent text-slate-800 font-bold text-sm w-full focus:outline-none"
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Trigger Button */}
                  <div className="md:col-span-1 pt-4 md:pt-0">
                    <label className="hidden md:block text-xs font-semibold text-transparent mb-1.5">Action</label>
                    <button
                      onClick={triggerPRReview}
                      disabled={isReviewing || !prNumber}
                      className="w-full flex items-center justify-center space-x-2 px-5 py-2.5 rounded-xl font-bold bg-indigo-600 hover:bg-indigo-700 text-white shadow-md disabled:opacity-50 transition text-xs cursor-pointer disabled:cursor-not-allowed"
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
                <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm text-sm leading-relaxed space-y-4 text-slate-800">
                  <div className="pb-4 border-b border-slate-200 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-emerald-800 bg-emerald-50 border border-emerald-200 px-4 py-2 rounded-xl text-xs font-bold shadow-xs">
                      <CheckCircle className="w-4 h-4 text-emerald-650 flex-shrink-0" />
                      <span>Code Review Published to Pull Request #{prNumber}</span>
                    </div>
                  </div>

                  {/* Displaying review markup */}
                  <div className="whitespace-pre-wrap font-sans text-slate-700 text-xs leading-relaxed bg-slate-50/50 border border-slate-200/50 rounded-xl p-4.5">
                    {aiReview}
                  </div>
                </div>
              )}

            </div>
          )}

        </div>

      </main>

      {/* RESOLUTION STUDIO MODAL (WebStorm-style Side-by-Side Diff) */}
      {isFixModalOpen && selectedViolation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 md:p-6 overflow-y-auto">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl max-w-6xl w-full h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-205">
            
            {/* Modal Header */}
            <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between flex-shrink-0">
              <div className="flex items-center space-x-3">
                <Sparkles className="w-5 h-5 text-indigo-600 animate-pulse" />
                <span className="font-extrabold text-slate-900 text-sm md:text-base tracking-tight">
                  Resolution Studio: {selectedViolation.rule_name}
                </span>
                <span className="hidden sm:inline-flex items-center gap-1.5 bg-indigo-50 px-2.5 py-1 rounded-md border border-indigo-150 text-[10px] font-mono text-indigo-600">
                  {selectedViolation.file_path}:{selectedViolation.line}
                </span>
              </div>
              <button
                onClick={() => setIsFixModalOpen(false)}
                className="p-1.5 rounded-full hover:bg-slate-200 text-slate-400 hover:text-slate-700 transition cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body - Side by Side layout */}
            <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-0 bg-[#fafbfe]">
              
              {/* Left Column: AI Refactoring Suggestion Guidance (lg:col-span-4) */}
              <div className="lg:col-span-4 flex flex-col space-y-4 overflow-y-auto pr-1">
                <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm space-y-3">
                  <h4 className="text-[10px] font-black uppercase tracking-wider text-slate-400">Issue Overview</h4>
                  <p className="text-xs text-slate-600 leading-relaxed">{selectedViolation.message}</p>
                </div>

                {/* Recommended Fix Box */}
                {selectedViolation.suggested_fix && (
                  <div className="rounded-xl border border-[#bbf7d0] bg-[#f0fdf4] p-4 space-y-2 shadow-xs">
                    <div className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded-full bg-[#22c55e] flex items-center justify-center flex-shrink-0">
                        <span className="text-white text-[9px] font-bold">✓</span>
                      </div>
                      <span className="text-[10px] font-extrabold text-[#166534] tracking-wide uppercase">Recommended Fix</span>
                    </div>
                    <p className="text-xs text-[#14532d] leading-relaxed font-semibold break-words pl-7">
                      {selectedViolation.suggested_fix}
                    </p>
                  </div>
                )}

                {/* AI Suggestions Section */}
                <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex-1 flex flex-col space-y-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-[10px] font-black uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                      AI Refactoring Suggestions
                    </h4>
                  </div>

                  {!aiFixText && !isGeneratingAiFix && (
                    <button
                      onClick={() => triggerAiFix(selectedViolation)}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold bg-indigo-50 hover:bg-indigo-100 text-indigo-600 border border-indigo-200 transition cursor-pointer"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Generate AI Suggestion</span>
                    </button>
                  )}

                  {isGeneratingAiFix && (
                    <div className="flex items-center justify-center gap-2.5 py-4 bg-slate-50 rounded-xl border border-slate-200">
                      <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                      <span className="text-xs text-slate-500 font-semibold">AI Architect analysis...</span>
                    </div>
                  )}

                  {aiFixText && (() => {
                    const sectionDefs = [
                      { key: "ROOT CAUSE",    icon: "🔍", label: "Root Cause",    color: "bg-rose-50 border-rose-100",      labelColor: "text-rose-700",    textColor: "text-rose-800" },
                      { key: "IMPACT",        icon: "⚡", label: "Impact",        color: "bg-amber-50 border-amber-100",    labelColor: "text-amber-700",   textColor: "text-amber-800" },
                      { key: "HOW TO FIX",    icon: "🛠️", label: "How to Fix",    color: "bg-indigo-50 border-indigo-100",  labelColor: "text-indigo-700",  textColor: "text-indigo-800" },
                      { key: "BEST PRACTICE", icon: "✅", label: "Best Practice", color: "bg-emerald-50 border-emerald-100", labelColor: "text-emerald-700", textColor: "text-emerald-805" },
                    ];

                    const parseSections = (raw: string) => {
                      const result: Record<string, string> = {};
                      sectionDefs.forEach(({ key }) => {
                        const regex = new RegExp(`\\[${key}\\]([\\s\\S]*?)(?=\\[(?:${sectionDefs.map(s => s.key).join("|")})\\]|$)`, "i");
                        const match = raw.match(regex);
                        if (match) result[key] = match[1].trim();
                      });
                      return result;
                    };

                    const sections = parseSections(aiFixText);
                    const hasSections = Object.keys(sections).length > 0;

                    return (
                      <div className="space-y-3 overflow-y-auto max-h-[360px]">
                        {hasSections ? (
                          sectionDefs.map(({ key, icon, label, color, labelColor, textColor }) =>
                            sections[key] ? (
                              <div key={key} className={`rounded-xl border p-3.5 space-y-1.5 ${color}`}>
                                <div className={`text-[10px] font-black uppercase tracking-widest flex items-center gap-1.5 ${labelColor}`}>
                                  <span>{icon}</span>
                                  <span>{label}</span>
                                </div>
                                <div className={`text-xs leading-relaxed ${textColor}`}>
                                  {sections[key].split("\n").map((line, idx) => (
                                    <p key={idx} className={line.trim() ? "mb-1" : ""}>{line}</p>
                                  ))}
                                </div>
                              </div>
                            ) : null
                          )
                        ) : (
                          <div className="rounded-xl border border-slate-200 bg-white p-3.5 text-xs text-slate-600 leading-relaxed">
                            {aiFixText.split("\n").map((line, idx) => (
                              <p key={idx} className={line.trim() ? "mb-1" : ""}>{line}</p>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              </div>

              {/* Right Column: Codebase Auto-Fix & WebStorm conflict resolution (lg:col-span-8) */}
              <div className="lg:col-span-8 flex flex-col space-y-4 min-h-0">
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex-1 flex flex-col overflow-hidden min-h-0 space-y-4">
                  
                  {/* Panel Header */}
                  <div className="flex items-center justify-between flex-shrink-0">
                    <div className="flex items-center gap-2">
                      <FileCode className="w-4.5 h-4.5 text-indigo-600" />
                      <span className="text-xs font-extrabold uppercase tracking-wider text-slate-500">
                        Code Conflict Resolution (WebStorm Diff Style)
                      </span>
                    </div>

                    {/* Confidence tag */}
                    {(() => {
                      const fileExt = selectedViolation.file_path.split('.').pop()?.toLowerCase() || '';
                      const isLowConfidence = ["c", "cpp", "rust", "swift", "php"].includes(fileExt);
                      const isMediumConfidence = ["java", "go", "kotlin", "dart", "csharp"].includes(fileExt);

                      return (
                        <div className="flex items-center">
                          {isMediumConfidence && (
                            <span className="text-[9px] bg-amber-50 border border-amber-200 text-amber-700 px-2.5 py-0.5 rounded-md font-bold uppercase tracking-wider">
                              ⚠️ Medium Confidence
                            </span>
                          )}
                          {isLowConfidence && (
                            <span className="text-[9px] bg-rose-50 border border-rose-200 text-rose-700 px-2.5 py-0.5 rounded-md font-bold uppercase tracking-wider">
                              ✕ Unsupported
                            </span>
                          )}
                          {!isLowConfidence && !isMediumConfidence && (
                            <span className="text-[9px] bg-emerald-50 border border-emerald-250 text-emerald-700 px-2.5 py-0.5 rounded-md font-bold uppercase tracking-wider">
                              ✓ Supported
                            </span>
                          )}
                        </div>
                      );
                    })()}
                  </div>

                  {/* Fix triggers */}
                  {!fixResult && !isApplyingFix && (
                    <div className="flex-1 flex flex-col items-center justify-center border border-dashed border-slate-300 rounded-xl p-10 bg-slate-50/50">
                      <FileCode className="w-12 h-12 text-slate-400 mb-3" />
                      <div className="text-xs font-bold text-slate-700 mb-1.5">No Fix Preview Generated Yet</div>
                      <p className="text-[11px] text-slate-500 text-center max-w-sm mb-4 leading-relaxed">
                        Trigger the AI Codebase Auto-Fix generator to create a side-by-side conflict diff comparison.
                      </p>
                      <button
                        onClick={() => triggerPreviewFix(selectedViolation)}
                        className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl font-bold bg-indigo-600 hover:bg-indigo-500 text-white text-xs shadow-md transition-all cursor-pointer"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Generate Code Fix Preview</span>
                      </button>
                    </div>
                  )}

                  {/* Loading */}
                  {isApplyingFix && (
                    <div className="flex-1 flex flex-col items-center justify-center bg-slate-50 border border-slate-200 rounded-xl p-8">
                      <RefreshCw className="w-8 h-8 animate-spin text-indigo-600 mb-3" />
                      <span className="text-xs font-bold text-slate-600 animate-pulse">
                        Analyzing source AST and drafting file changes...
                      </span>
                    </div>
                  )}

                  {/* Fix Error */}
                  {fixError && (
                    <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl space-y-1.5">
                      <div className="font-bold text-rose-800 text-xs flex items-center gap-2">
                        <span>⚠️ Error generating patch:</span>
                        <span>{fixError.message}</span>
                      </div>
                      <p className="text-[11px] text-rose-700 leading-relaxed">{fixError.tip}</p>
                    </div>
                  )}

                  {/* Fix Result (WebStorm Style Diff Container) */}
                  {fixResult && (
                    <div className="flex-1 flex flex-col min-h-0 space-y-4 animate-in fade-in duration-300">
                      {fixResult.stale_warning && (
                        <div className="px-3.5 py-2.5 bg-amber-50 border border-amber-200 rounded-xl text-[10px] text-amber-700 font-semibold">
                          ⚠️ Warning: This file was updated on GitHub since the last scan. Diffs might have conflict offsets.
                        </div>
                      )}

                      {/* WebStorm Conflict resolution side-by-side layout */}
                      <div className="flex-1 border border-slate-200 rounded-xl overflow-hidden shadow-sm bg-white flex flex-col min-h-0 font-mono text-[11px] leading-5">
                        
                        {/* Conflict Header */}
                        <div className="flex items-center bg-slate-100 border-b border-slate-200 px-4 py-2 flex-shrink-0 justify-between">
                          <span className="text-[9px] text-slate-500 font-sans font-black uppercase tracking-widest">
                            Side-by-Side Merge Compare
                          </span>
                          <span className="text-[10px] font-bold bg-slate-200 text-slate-700 px-2 py-0.5 rounded font-sans">
                            {fixResult.language?.toUpperCase() || "SOURCE"}
                          </span>
                        </div>

                        {/* Side by Side editor boxes */}
                        <div className="flex-1 grid grid-cols-2 divide-x divide-slate-200 min-h-0 overflow-hidden">
                          {/* Original Column */}
                          <div className="bg-[#fff8f7] flex flex-col min-h-0 overflow-hidden">
                            <div className="flex items-center gap-1.5 px-4 py-2 bg-[#ffebe9] border-b border-[#ffd7d5] sticky top-0 flex-shrink-0">
                              <div className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                              <span className="text-[9px] text-[#8a1c1c] font-sans font-bold uppercase tracking-widest">Before</span>
                            </div>
                            <div className="flex-1 overflow-auto p-4.5">
                              <pre className="text-[#6e1e1d] whitespace-pre leading-relaxed">{fixResult.original_snippet}</pre>
                            </div>
                          </div>

                          {/* Fixed Column */}
                          <div className="bg-[#f6fff8] flex flex-col min-h-0 overflow-hidden">
                            <div className="flex items-center gap-1.5 px-4 py-2 bg-[#e6ffed] border-b border-[#d1f9d8] sticky top-0 flex-shrink-0">
                              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                              <span className="text-[9px] text-[#1c7a2e] font-sans font-bold uppercase tracking-widest">After</span>
                            </div>
                            <div className="flex-1 overflow-auto p-4.5">
                              <pre className="text-[#1e6e2f] whitespace-pre leading-relaxed">{fixResult.fixed_snippet}</pre>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Explanation box */}
                      {fixResult.explanation && (
                        <div className="flex gap-3 p-4 bg-slate-50 border border-slate-200 rounded-xl flex-shrink-0">
                          <div className="w-5 h-5 rounded-full bg-indigo-50 border border-indigo-150 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <span className="text-indigo-600 text-[8px] font-black">AI</span>
                          </div>
                          <p className="text-[11px] text-slate-600 leading-relaxed font-sans">{fixResult.explanation}</p>
                        </div>
                      )}

                      {/* Action buttons footer */}
                      <div className="flex items-center justify-between pt-2 border-t border-slate-100 flex-shrink-0">
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              navigator.clipboard.writeText(fixResult.fixed_snippet);
                              alert("Copied fixed snippet to clipboard!");
                            }}
                            className="flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 transition duration-150 cursor-pointer"
                          >
                            <span>📋 Copy Code</span>
                          </button>
                        </div>

                        <div className="flex gap-2">
                          <button
                            onClick={() => triggerApplyLocalFix(selectedViolation)}
                            disabled={isCreatingPR || !!createdPRInfo}
                            className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 shadow-md shadow-indigo-500/10 disabled:opacity-50 disabled:cursor-not-allowed transition duration-200 cursor-pointer"
                          >
                            {isCreatingPR ? (
                              <>
                                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                <span>Applying Code Changes...</span>
                              </>
                            ) : (
                              <>
                                <Sparkles className="w-3.5 h-3.5" />
                                <span>Apply Locally</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>

                      {/* Action Feedback Results */}
                      {createdPRInfo && (
                        <div className="flex items-start gap-3 p-4 bg-emerald-50 border border-[#bbf7d0] rounded-xl flex-shrink-0 animate-in zoom-in-95 duration-200">
                          <CheckCircle className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
                          <div className="space-y-0.5 text-left">
                            <div className="text-xs font-bold text-emerald-800">Local Fix Succeeded</div>
                            <p className="text-[10px] text-emerald-900 leading-relaxed font-sans">
                              {createdPRInfo.message || "File changes applied directly to your local workspace disk."}
                            </p>
                            <p className="text-[10px] text-slate-500 leading-relaxed mt-1 font-sans">
                              Verification recommended — run <span className="font-mono text-slate-600 font-bold">git status</span> to view differences.
                            </p>
                          </div>
                        </div>
                      )}

                      {prError && (
                        <div className="flex items-start gap-3 p-4 bg-rose-50 border border-[#fecaca] rounded-xl flex-shrink-0">
                          <div className="w-4.5 h-4.5 rounded-full bg-rose-100 border border-rose-200 flex-shrink-0 mt-0.5 flex items-center justify-center">
                            <span className="text-rose-700 text-[9px] font-black">!</span>
                          </div>
                          <div className="space-y-0.5 text-left">
                            <div className="text-xs font-bold text-rose-800">{prError.message}</div>
                            <p className="text-[10px] text-rose-700 leading-relaxed">{prError.tip}</p>
                          </div>
                        </div>
                      )}

                    </div>
                  )}

                </div>
              </div>

            </div>

          </div>
        </div>
      )}

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
