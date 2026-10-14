import React, { useState, useEffect } from 'react';
import { 
  Activity, ShieldCheck, Terminal, AlertTriangle, 
  FileText, ArrowRight, Layers, Clock, Cpu,
  Upload, Search, Filter, RefreshCw, AlertCircle, Info, Database, Eye,
  Key, CheckCircle2, Copy, Check, ExternalLink, GitBranch, Play, Lock, Server, Link, X
} from 'lucide-react';

const API_BASE = "http://localhost:8000/api/v1";

const AUTHENTIC_PRESETS = [
  {
    title: "1. HPE Jenkins Qualification Failure (Build #157)",
    file: "Jenkins_Log_Under_1MB.txt",
    snippet: `2026-02-25 21:12:39 MST test_vme_storage_plugin_e2e.py:320 ERROR : Actual error is: storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation assert 'hpe_storage_cluster_id' in {'***GMAIL_APP_PASSWORD***': False, 'hpe_storage_cpg': 'SSD_r6', 'protocolType': 'iSCSI'}\nAssertionError: storage cluster id is missing from config in datastore alletra_datastore_abgrdg_dnd creation\nFAILED morpheus_automation/tests/api/test_vme_storage_plugin_e2e.py::TestVMEStoragePlugin::test_create_update_delete_datastore[False]`
  },
  {
    title: "2. Microservice Payment Dependency Cascade",
    file: "1130.txt",
    snippet: `2026-09-15T09:04:30.123Z ERROR [notification-service] request_id=req-820221 status=503 latency_ms=3371 Connection refused by payment service\n2026-09-15T09:06:30.123Z ERROR [order-service] request_id=req-810250 status=502 latency_ms=1634 Connection refused by payment service`
  },
  {
    title: "3. Jenkins Core JVM Startup Crash (GitHub Gist)",
    file: "jenkins_gist_crash.log",
    snippet: `2022-10-04 19:25:40.961+0000 [id=19] WARNING h.i.i.InstallUncaughtExceptionHandler#handleException: Caught unhandled exception with ID 2f2d9bc5-7c14-4d3f-9790-b57a5c14d6f7\njava.lang.AssertionError: class hudson.security.csrf.DefaultCrumbIssuer is missing its descriptor\n\tat jenkins.model.Jenkins.getDescriptorOrDie(Jenkins.java:1633)\n\tat hudson.security.csrf.CrumbIssuer.getDescriptor(CrumbIssuer.java:141)`
  }
];

export default function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'upload' | 'jenkins' | 'privacy' | 'parser' | 'analysis' | 'model'>('dashboard');
  const [healthData, setHealthData] = useState<any>(null);
  const [metricsData, setMetricsData] = useState<any>(null);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [ingestedLogs, setIngestedLogs] = useState<any[]>([]);
  const [eventsData, setEventsData] = useState<any>({ total: 0, events: [] });
  const [backendError, setBackendError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Jenkins Integration State
  const [jenkinsTokens, setJenkinsTokens] = useState<any[]>([]);
  const [jenkinsBuilds, setJenkinsBuilds] = useState<any[]>([]);
  const [newTokenName, setNewTokenName] = useState("");
  const [createdTokenSecret, setCreatedTokenSecret] = useState<string | null>(null);
  const [copiedToken, setCopiedToken] = useState(false);
  const [copiedSnippet, setCopiedSnippet] = useState(false);
  const [isCreatingToken, setIsCreatingToken] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [selectedBuildDetail, setSelectedBuildDetail] = useState<any | null>(null);

  // Jenkins Test Simulator State
  const [simToken, setSimToken] = useState("");
  const [simJobName, setSimJobName] = useState("qualification-cluster-e2e");
  const [simBuildNum, setSimBuildNum] = useState("101");
  const [simBuildStatus, setSimBuildStatus] = useState("FAILURE");
  const [simLogText, setSimLogText] = useState(
    "2026-09-15T09:04:30.123Z ERROR [order-service] status=503 Connection refused by payment service\n" +
    "AssertionError: storage cluster id is missing from config in datastore creation\n" +
    "FAILED morpheus_automation/tests/api/test_vme_storage_plugin_e2e.py::TestVMEStoragePlugin::test_create_update_delete_datastore"
  );
  const [simResult, setSimResult] = useState<any>(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);

  // Upload State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<any>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [logOriginFilter, setLogOriginFilter] = useState<'ALL' | 'JENKINS' | 'MANUAL'>('ALL');

  // Privacy View State
  const [privacyLogId, setPrivacyLogId] = useState<number | null>(null);
  const [privacyData, setPrivacyData] = useState<any | null>(null);
  const [isPrivacyLoading, setIsPrivacyLoading] = useState(false);
  const [privacyError, setPrivacyError] = useState<string | null>(null);

  // Parser Filter State
  const [eventSeverity, setEventSeverity] = useState<string>("");
  const [eventService, setEventService] = useState<string>("");
  const [eventFileId, setEventFileId] = useState<string>("");

  // Incident & RCA State
  const [rcaViewMode, setRcaViewMode] = useState<'persisted' | 'interactive'>('persisted');
  const [selectedIncidentCode, setSelectedIncidentCode] = useState<string | null>(null);
  const [analysisInput, setAnalysisInput] = useState(AUTHENTIC_PRESETS[0].snippet);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // Data Fetching Functions
  const fetchHealthAndMetrics = async () => {
    try {
      setBackendError(null);
      const [hRes, mRes, iRes, lRes] = await Promise.all([
        fetch(`${API_BASE}/health`),
        fetch(`${API_BASE}/metrics`),
        fetch(`${API_BASE}/incidents?limit=50`),
        fetch(`${API_BASE}/ingest/logs?limit=50`)
      ]);
      if (hRes.ok) setHealthData(await hRes.json());
      if (mRes.ok) setMetricsData(await mRes.json());
      if (iRes.ok) {
        const incList = await iRes.json();
        setIncidents(incList);
        if (incList.length > 0 && !selectedIncidentCode) {
          setSelectedIncidentCode(incList[0].incident_code);
        }
      }
      if (lRes.ok) {
        const logsList = await lRes.json();
        setIngestedLogs(logsList);
        if (logsList.length > 0 && privacyLogId === null) {
          setPrivacyLogId(logsList[0].id);
        }
      }
    } catch (err: any) {
      setBackendError(`Cannot connect to FastAPI backend at ${API_BASE}. Ensure server is running on port 8000.`);
    }
  };

  const fetchJenkinsData = async () => {
    try {
      const [tRes, bRes] = await Promise.all([
        fetch(`${API_BASE}/jenkins/tokens`),
        fetch(`${API_BASE}/jenkins/builds?limit=50`)
      ]);
      if (tRes.ok) setJenkinsTokens(await tRes.json());
      if (bRes.ok) setJenkinsBuilds(await bRes.json());
    } catch (err) {
      // Handled silently
    }
  };

  const fetchEvents = async () => {
    try {
      let url = `${API_BASE}/events?limit=50`;
      if (eventSeverity) url += `&severity=${eventSeverity}`;
      if (eventService) url += `&service=${encodeURIComponent(eventService)}`;
      if (eventFileId) url += `&file_id=${eventFileId}`;
      const res = await fetch(url);
      if (res.ok) {
        setEventsData(await res.json());
      }
    } catch (err) {
      // handled
    }
  };

  const fetchPrivacyAudit = async (fId: number) => {
    setIsPrivacyLoading(true);
    setPrivacyError(null);
    try {
      const res = await fetch(`${API_BASE}/ingest/logs/${fId}/privacy`);
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to fetch privacy audit.");
      }
      const data = await res.json();
      setPrivacyData(data);
    } catch (err: any) {
      setPrivacyData(null);
      setPrivacyError(err.message || "Failed to load privacy audit.");
    } finally {
      setIsPrivacyLoading(false);
    }
  };

  const refreshAllData = async () => {
    setIsRefreshing(true);
    await Promise.all([
      fetchHealthAndMetrics(),
      fetchJenkinsData(),
      fetchEvents()
    ]);
    if (privacyLogId) {
      await fetchPrivacyAudit(privacyLogId);
    }
    setIsRefreshing(false);
  };

  useEffect(() => {
    fetchHealthAndMetrics();
    fetchJenkinsData();
  }, []);

  useEffect(() => {
    if (activeTab === 'parser') {
      fetchEvents();
    }
    if (activeTab === 'jenkins' || activeTab === 'dashboard') {
      fetchJenkinsData();
    }
    if (activeTab === 'privacy') {
      if (privacyLogId) {
        fetchPrivacyAudit(privacyLogId);
      } else if (ingestedLogs.length > 0) {
        setPrivacyLogId(ingestedLogs[0].id);
        fetchPrivacyAudit(ingestedLogs[0].id);
      }
    }
  }, [activeTab, eventSeverity, eventService, eventFileId, privacyLogId]);

  const handleRunAnalysis = async () => {
    setIsAnalyzing(true);
    setAnalysisError(null);
    try {
      const res = await fetch(`${API_BASE}/analysis/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ log_text: analysisInput })
      });
      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || "Analysis request failed.");
      }
      const data = await res.json();
      setAnalysisResult(data);
    } catch (err: any) {
      setAnalysisResult(null);
      setAnalysisError(err.message || "Failed to reach model inference API.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    setIsUploading(true);
    setUploadStatus(null);
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const res = await fetch(`${API_BASE}/ingest/upload`, {
        method: "POST",
        body: formData
      });
      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || "Upload failed");
      }
      const data = await res.json();
      setUploadStatus(data);
      refreshAllData();
    } catch (err: any) {
      setUploadStatus({ error: err.message || "Upload failed." });
    } finally {
      setIsUploading(false);
    }
  };

  const handleCreateToken = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTokenName.trim()) return;
    setIsCreatingToken(true);
    setTokenError(null);
    try {
      const res = await fetch(`${API_BASE}/jenkins/tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newTokenName.trim() })
      });
      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || "Failed to generate token.");
      }
      const data = await res.json();
      setCreatedTokenSecret(data.token);
      setSimToken(data.token);
      setNewTokenName("");
      fetchJenkinsData();
    } catch (err: any) {
      setTokenError(err.message || "Token generation failed.");
    } finally {
      setIsCreatingToken(false);
    }
  };

  const handleRevokeToken = async (tokenId: number) => {
    try {
      const res = await fetch(`${API_BASE}/jenkins/tokens/${tokenId}/revoke`, { method: "POST" });
      if (res.ok) {
        fetchJenkinsData();
      }
    } catch (err) {
      // Ignored
    }
  };

  const handleRunSimulator = async () => {
    if (!simToken.trim()) {
      setSimError("Please provide an integration token (generate one above or paste your token).");
      return;
    }
    setIsSimulating(true);
    setSimError(null);
    setSimResult(null);
    try {
      const res = await fetch(`${API_BASE}/jenkins/ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${simToken.trim()}`
        },
        body: JSON.stringify({
          job_name: simJobName.trim(),
          build_number: simBuildNum.trim(),
          build_status: simBuildStatus,
          build_url: `http://jenkins.corp.internal/job/${encodeURIComponent(simJobName.trim())}/${simBuildNum.trim()}/`,
          log_text: simLogText
        })
      });
      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || "Jenkins log ingestion failed.");
      }
      const data = await res.json();
      setSimResult(data);
      fetchJenkinsData();
      fetchHealthAndMetrics();
    } catch (err: any) {
      setSimError(err.message || "Simulation failed.");
    } finally {
      setIsSimulating(false);
    }
  };

  const handleTestConnection = async () => {
    if (!simToken.trim()) {
      setSimError("Please enter a token to test connection.");
      return;
    }
    setIsSimulating(true);
    setSimError(null);
    try {
      const res = await fetch(`${API_BASE}/jenkins/test-connection`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${simToken.trim()}` }
      });
      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || "Authentication failed.");
      }
      const data = await res.json();
      alert(`Connection Verified: ${data.message}`);
    } catch (err: any) {
      setSimError(err.message || "Connection test failed.");
    } finally {
      setIsSimulating(false);
    }
  };

  // Find currently active incident in RCA view
  const activeIncident = incidents.find(i => i.incident_code === selectedIncidentCode) || incidents[0] || null;

  // Filtered logs list for Log Ingestion view
  const filteredIngestedLogs = ingestedLogs.filter(l => {
    if (logOriginFilter === 'JENKINS') return l.origin === 'JENKINS';
    if (logOriginFilter === 'MANUAL') return l.origin === 'MANUAL';
    return true;
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Application Header */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 sticky top-0 z-50">
        <div className="flex items-center space-x-3.5">
          <div className="p-2.5 bg-indigo-600 rounded-lg shadow-lg shadow-indigo-500/20 flex-shrink-0">
            <Activity className="h-6 w-6 text-white" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-bold text-base md:text-lg tracking-tight text-white leading-snug">
                Automated Log Analysis and Root Cause Detection System
              </h1>
              <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/30 font-mono">
                Current Baseline
              </span>
            </div>
            <p className="text-xs text-slate-400 font-medium tracking-wide">
              using Machine Learning — Live Ingestion & Persisted Telemetry
            </p>
          </div>
        </div>

        {/* Tab Controls & Global Refresh */}
        <div className="flex items-center space-x-2 self-start md:self-auto">
          <div className="flex items-center space-x-1 bg-slate-800/60 p-1 rounded-lg border border-slate-700 text-xs">
            {[
              { id: 'dashboard', label: 'Dashboard' },
              { id: 'upload', label: 'Log Ingestion' },
              { id: 'jenkins', label: 'Jenkins Integration' },
              { id: 'privacy', label: 'Privacy View' },
              { id: 'parser', label: 'Parser View' },
              { id: 'analysis', label: 'Incident & RCA' },
              { id: 'model', label: 'Model Evaluation' }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-3 py-1.5 rounded-md font-medium transition ${
                  activeTab === tab.id ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <button
            onClick={refreshAllData}
            disabled={isRefreshing}
            title="Refresh All Backend Data"
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 text-xs transition flex items-center justify-center"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        </div>
      </header>

      {/* Backend Disconnection Banner */}
      {backendError && (
        <div className="bg-rose-950/80 border-b border-rose-500/50 px-6 py-2.5 flex items-center justify-between text-xs text-rose-200">
          <div className="flex items-center space-x-2">
            <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0" />
            <span>{backendError}</span>
          </div>
          <button 
            onClick={refreshAllData}
            className="px-2.5 py-1 bg-rose-900/60 hover:bg-rose-900 rounded border border-rose-700 text-white font-medium"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">

        {/* =========================================================================
            VIEW 1: DASHBOARD
            ========================================================================= */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            {/* Top Operational KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-[11px] uppercase tracking-wider text-slate-400">Current Model</span>
                <p className="text-sm font-semibold text-slate-200 font-mono">TF-IDF + Random Forest</p>
                <span className="text-[10px] text-indigo-400 block">Baseline Classifier (10 Categories)</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-[11px] uppercase tracking-wider text-slate-400">Total Ingested Events</span>
                <p className="text-2xl font-bold text-cyan-400 font-mono">
                  {healthData?.database?.parsed_events_count !== undefined 
                    ? healthData.database.parsed_events_count.toLocaleString() 
                    : (healthData ? "0" : "...")}
                </p>
                <span className="text-[10px] text-slate-400 block">
                  Across {healthData?.database?.source_files_count ?? 0} persisted log files
                </span>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-[11px] uppercase tracking-wider text-slate-400">Detected Failure Incidents</span>
                <p className="text-2xl font-bold text-amber-400 font-mono">
                  {healthData?.database?.incidents_count !== undefined 
                    ? healthData.database.incidents_count.toLocaleString() 
                    : (healthData ? "0" : "...")}
                </p>
                <span className="text-[10px] text-slate-400 block">Identified by structural failure parser</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-[11px] uppercase tracking-wider text-slate-400">Held-Out Test Macro-F1</span>
                <p className="text-2xl font-bold text-emerald-400 font-mono">
                  {metricsData?.f1_macro !== undefined 
                    ? `${(metricsData.f1_macro * 100).toFixed(2)}%` 
                    : (metricsData ? "N/A" : "...")}
                </p>
                <span className="text-[10px] text-slate-400 block">
                  Offline Benchmark ({metricsData?.sample_count ?? 57} test partition samples)
                </span>
              </div>
            </div>

            {/* System Overview */}
            <div className="bg-slate-900/60 border border-indigo-500/20 rounded-xl p-4 flex items-start space-x-3">
              <Info className="h-5 w-5 text-indigo-400 mt-0.5 flex-shrink-0" />
              <div className="text-xs text-slate-300 space-y-1">
                <span className="font-semibold text-white block">SYSTEM OVERVIEW</span>
                <p className="text-slate-400 leading-relaxed">
                  Incoming CI/CD and telemetry logs are sanitized via Zero-PII masking, parsed into structured events, scanned for failure blocks, classified using the academic Random Forest baseline, and enriched with deterministic root-cause candidates stored in SQLite WAL.
                </p>
              </div>
            </div>

            {/* Recent Authentic Incidents Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-white">Recent Incidents Extracted from Ingested Logs</h3>
                  <p className="text-xs text-slate-400">Live persisted incident records from uploaded and Jenkins-forwarded logs</p>
                </div>
                <div className="flex items-center space-x-3 text-xs text-slate-400 font-mono">
                  <span>Total: {incidents.length}</span>
                  <button 
                    onClick={refreshAllData}
                    className="p-1 hover:text-white transition"
                    title="Refresh Incidents"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-950/60 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                    <tr>
                      <th className="py-2.5 px-3">Incident Code</th>
                      <th className="py-2.5 px-3">Source / Build</th>
                      <th className="py-2.5 px-3">Lines</th>
                      <th className="py-2.5 px-3">Classified Category</th>
                      <th className="py-2.5 px-3">Confidence</th>
                      <th className="py-2.5 px-3">Predicted Root Cause Candidate</th>
                      <th className="py-2.5 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {incidents.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-6 text-center text-slate-500 font-sans">
                          No failure incidents detected in currently ingested logs.
                        </td>
                      </tr>
                    ) : (
                      incidents.slice(0, 10).map((inc) => (
                        <tr key={inc.id} className="hover:bg-slate-800/40 transition">
                          <td className="py-2 px-3 text-indigo-300 font-semibold">{inc.incident_code}</td>
                          <td className="py-2 px-3 text-slate-300 font-sans">
                            {inc.job_name ? (
                              <span className="text-cyan-300 font-mono text-[11px]">{inc.job_name} #{inc.build_number}</span>
                            ) : (
                              <span className="text-slate-300 truncate max-w-[160px] inline-block">{inc.source_file}</span>
                            )}
                          </td>
                          <td className="py-2 px-3 text-slate-400">{inc.start_line}-{inc.end_line}</td>
                          <td className="py-2 px-3 text-amber-300 font-semibold">{inc.failure_category}</td>
                          <td className="py-2 px-3 text-cyan-300">{(inc.confidence * 100).toFixed(1)}%</td>
                          <td className="py-2 px-3 text-slate-300 truncate max-w-xs">{inc.root_cause_candidate}</td>
                          <td className="py-2 px-3 text-right font-sans">
                            <button
                              onClick={() => {
                                setSelectedIncidentCode(inc.incident_code);
                                setRcaViewMode('persisted');
                                setActiveTab('analysis');
                              }}
                              className="text-indigo-400 hover:text-indigo-300 hover:underline text-[11px] font-medium"
                            >
                              View RCA &rarr;
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            VIEW 2: LOG INGESTION & UPLOAD
            ========================================================================= */}
        {activeTab === 'upload' && (
          <div className="space-y-6">
            {/* Jenkins Integration Callout Card */}
            <div className="bg-gradient-to-r from-indigo-950/50 to-slate-900 border border-indigo-500/30 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center space-x-3">
                <Server className="h-5 w-5 text-indigo-400 flex-shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-white">Automate Ingestion with Remote Jenkins Pipelines</p>
                  <p className="text-[11px] text-slate-400">Transmit console logs automatically upon build completion via token authentication.</p>
                </div>
              </div>
              <button 
                onClick={() => setActiveTab('jenkins')}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium flex items-center space-x-1.5 transition self-start sm:self-auto"
              >
                <span>Setup Jenkins</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Manual Upload Section */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="border-b border-slate-800 pb-3">
                <h2 className="text-base font-bold text-white flex items-center space-x-2">
                  <Upload className="h-5 w-5 text-indigo-400" />
                  <span>Manual CI/CD Build Log Ingestion</span>
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Upload a raw <code className="text-indigo-300 font-mono">.log</code> or <code className="text-indigo-300 font-mono">.txt</code> build output. The pipeline scrubs secrets, parses structured fields, and saves events to SQLite.
                </p>
              </div>

              <form onSubmit={handleFileUpload} className="space-y-4">
                <div className="border-2 border-dashed border-slate-700 hover:border-indigo-500 rounded-xl p-8 text-center space-y-3 transition">
                  <FileText className="h-10 w-10 text-slate-600 mx-auto" />
                  <div>
                    <input
                      type="file"
                      accept=".log,.txt"
                      onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                      className="hidden"
                      id="log-file-input"
                    />
                    <label 
                      htmlFor="log-file-input"
                      className="cursor-pointer px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium inline-block transition"
                    >
                      Choose .log or .txt File
                    </label>
                    <p className="text-xs text-slate-400 mt-2 font-mono">
                      {selectedFile ? `${selectedFile.name} (${(selectedFile.size / 1024).toFixed(1)} KB)` : "No file chosen yet"}
                    </p>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={!selectedFile || isUploading}
                  className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium rounded-lg text-xs transition flex items-center justify-center space-x-2"
                >
                  {isUploading ? <span>Ingesting and Parsing...</span> : <span>Execute Ingestion & SQLite Persistence</span>}
                </button>
              </form>

              {uploadStatus && (
                <div className={`p-4 rounded-lg border text-xs font-mono space-y-2 ${
                  uploadStatus.error 
                    ? 'bg-rose-950/60 border-rose-500 text-rose-300' 
                    : 'bg-slate-950 border-slate-800 text-slate-200'
                }`}>
                  {uploadStatus.error ? (
                    <p className="text-rose-400 font-sans font-medium flex items-center space-x-1.5">
                      <AlertCircle className="h-4 w-4" />
                      <span>Upload Error: {uploadStatus.error}</span>
                    </p>
                  ) : (
                    <>
                      <p className="text-emerald-400 font-semibold font-sans flex items-center space-x-1.5">
                        <CheckCircle2 className="h-4 w-4" />
                        <span>Ingestion & Persistence Successful</span>
                      </p>
                      <p>Filename: {uploadStatus.filename}</p>
                      <p>Source Type: {uploadStatus.source_type}</p>
                      <p>Byte Size: {uploadStatus.byte_size.toLocaleString()} bytes</p>
                      <p>Line Count: {uploadStatus.line_count.toLocaleString()} lines</p>
                      <p>SHA-256: {uploadStatus.sha256_hash}</p>
                      <p>Structured Events Persisted: {uploadStatus.events_inserted.toLocaleString()}</p>
                      <p>Failures Detected: {uploadStatus.incidents_detected}</p>
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Ingested Logs Registry Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                    <Database className="h-4 w-4 text-indigo-400" />
                    <span>Ingested Logs & Telemetry Feed</span>
                  </h3>
                  <p className="text-xs text-slate-400">All logs actually received and persisted by the backend ({ingestedLogs.length} total)</p>
                </div>
                
                {/* Filter buttons */}
                <div className="flex items-center space-x-2">
                  <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-[11px]">
                    <button
                      onClick={() => setLogOriginFilter('ALL')}
                      className={`px-2.5 py-1 rounded ${logOriginFilter === 'ALL' ? 'bg-indigo-600 text-white' : 'text-slate-400'}`}
                    >
                      All ({ingestedLogs.length})
                    </button>
                    <button
                      onClick={() => setLogOriginFilter('JENKINS')}
                      className={`px-2.5 py-1 rounded ${logOriginFilter === 'JENKINS' ? 'bg-indigo-600 text-white' : 'text-slate-400'}`}
                    >
                      Jenkins ({ingestedLogs.filter(l => l.origin === 'JENKINS').length})
                    </button>
                    <button
                      onClick={() => setLogOriginFilter('MANUAL')}
                      className={`px-2.5 py-1 rounded ${logOriginFilter === 'MANUAL' ? 'bg-indigo-600 text-white' : 'text-slate-400'}`}
                    >
                      Manual ({ingestedLogs.filter(l => l.origin === 'MANUAL').length})
                    </button>
                  </div>
                  <button
                    onClick={refreshAllData}
                    className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700"
                    title="Refresh Logs List"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-950/60 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                    <tr>
                      <th className="py-2.5 px-3">Log Name / Job</th>
                      <th className="py-2.5 px-3">Origin</th>
                      <th className="py-2.5 px-3">Size</th>
                      <th className="py-2.5 px-3">Lines</th>
                      <th className="py-2.5 px-3">Events</th>
                      <th className="py-2.5 px-3">Incidents</th>
                      <th className="py-2.5 px-3">Ingested At</th>
                      <th className="py-2.5 px-3 text-right">Inspect Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredIngestedLogs.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-6 text-center text-slate-500 font-sans">
                          No logs found matching filter.
                        </td>
                      </tr>
                    ) : (
                      filteredIngestedLogs.map((log) => (
                        <tr key={log.id} className="hover:bg-slate-800/40 transition">
                          <td className="py-2.5 px-3 font-sans">
                            <div className="font-medium text-slate-200">
                              {log.job_name ? (
                                <span className="text-indigo-300 font-mono text-[11px] font-semibold">
                                  {log.job_name} #{log.build_number}
                                </span>
                              ) : (
                                <span className="font-mono text-slate-300 text-[11px]">{log.filename}</span>
                              )}
                            </div>
                            <span className="text-[10px] text-slate-500 font-mono block">{log.source_type}</span>
                          </td>
                          <td className="py-2.5 px-3">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                              log.origin === 'JENKINS' 
                                ? 'bg-purple-500/10 text-purple-300 border border-purple-500/30' 
                                : 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                            }`}>
                              {log.origin === 'JENKINS' ? 'Jenkins Build' : 'Manual Upload'}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-slate-400">
                            {log.byte_size > 1024 * 1024 
                              ? `${(log.byte_size / (1024 * 1024)).toFixed(2)} MB` 
                              : `${(log.byte_size / 1024).toFixed(1)} KB`}
                          </td>
                          <td className="py-2.5 px-3 text-slate-400">{log.line_count.toLocaleString()}</td>
                          <td className="py-2.5 px-3 text-cyan-400">{log.events_count}</td>
                          <td className="py-2.5 px-3">
                            <span className={log.incidents_count > 0 ? 'text-amber-400 font-semibold' : 'text-slate-500'}>
                              {log.incidents_count}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-slate-400 text-[11px]">{log.ingested_at}</td>
                          <td className="py-2.5 px-3 text-right font-sans space-x-2">
                            <button
                              onClick={() => {
                                setPrivacyLogId(log.id);
                                setActiveTab('privacy');
                              }}
                              className="text-emerald-400 hover:text-emerald-300 text-[11px] hover:underline"
                            >
                              Privacy
                            </button>
                            <span className="text-slate-700">|</span>
                            <button
                              onClick={() => {
                                setEventFileId(log.id.toString());
                                setActiveTab('parser');
                              }}
                              className="text-indigo-400 hover:text-indigo-300 text-[11px] hover:underline"
                            >
                              Parser
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            VIEW 3: JENKINS INTEGRATION
            ========================================================================= */}
        {activeTab === 'jenkins' && (
          <div className="space-y-6">
            {/* Header & Architecture Card */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2.5 bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 rounded-lg">
                    <Server className="h-6 w-6" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-white flex items-center space-x-2">
                      <span>Jenkins CI/CD Pipeline Integration</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-mono">
                        Active Ingestion Endpoint
                      </span>
                    </h2>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Stream automated build console logs from your Jenkins instance directly into TRACE for privacy sanitization, failure detection, and root-cause analysis.
                    </p>
                  </div>
                </div>
                <button
                  onClick={fetchJenkinsData}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition self-start md:self-auto border border-slate-700"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span>Refresh Data</span>
                </button>
              </div>

              {/* Crucial Push-Architecture Clarification Banner */}
              <div className="bg-indigo-950/40 border border-indigo-500/30 rounded-lg p-3.5 flex items-start space-x-3 text-xs">
                <Info className="h-5 w-5 text-indigo-400 flex-shrink-0 mt-0.5" />
                <div className="space-y-1 text-slate-300">
                  <span className="font-semibold text-white block">Connection Model Notice</span>
                  <p className="text-slate-400 leading-relaxed">
                    TRACE receives telemetry pushed from your Jenkins agent over HTTP/HTTPS. The TRACE server does <strong>not</strong> require inbound network access or direct credentials into your Jenkins master/controller. To connect, generate an integration token below and configure your Jenkins pipeline with the provided post-build step.
                  </p>
                </div>
              </div>

              {/* Ingestion Endpoint URL Reference */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                <div className="bg-slate-950 border border-slate-800 p-3.5 rounded-lg space-y-1 font-mono text-xs">
                  <span className="text-[10px] text-slate-400 uppercase font-sans font-semibold">Backend Ingestion Endpoint</span>
                  <p className="text-emerald-400 break-all select-all font-semibold">{`${API_BASE}/jenkins/ingest`}</p>
                  <span className="text-[10px] text-slate-500 font-sans block">HTTP Method: POST (JSON or multipart/form-data)</span>
                </div>
                <div className="bg-slate-950 border border-slate-800 p-3.5 rounded-lg space-y-1 font-mono text-xs">
                  <span className="text-[10px] text-slate-400 uppercase font-sans font-semibold">Authentication Header</span>
                  <p className="text-cyan-400 break-all font-semibold">Authorization: Bearer &lt;YOUR_INTEGRATION_TOKEN&gt;</p>
                  <span className="text-[10px] text-slate-500 font-sans block">Or via custom header: X-TRACE-API-KEY</span>
                </div>
              </div>
            </div>

            {/* Token Generation & Management */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Token Creation Form */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 md:col-span-1">
                <div className="border-b border-slate-800 pb-3 flex items-center space-x-2">
                  <Key className="h-4 w-4 text-amber-400" />
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">Generate Integration Token</h3>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Generate a high-entropy secret token for your Jenkins instance. Tokens are stored as SHA-256 hashes and displayed only once.
                </p>

                <form onSubmit={handleCreateToken} className="space-y-3">
                  <div>
                    <label className="text-[11px] text-slate-300 font-medium block mb-1">Integration Label / Name</label>
                    <input
                      type="text"
                      placeholder="e.g. Jenkins Master - Production"
                      value={newTokenName}
                      onChange={(e) => setNewTokenName(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={!newTokenName.trim() || isCreatingToken}
                    className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition flex items-center justify-center space-x-2"
                  >
                    <Lock className="h-3.5 w-3.5" />
                    <span>{isCreatingToken ? "Generating..." : "Generate New Token"}</span>
                  </button>
                </form>

                {tokenError && (
                  <p className="text-xs text-rose-400 bg-rose-950/40 p-2.5 rounded border border-rose-800">{tokenError}</p>
                )}

                {/* Single-display Token Secret Alert */}
                {createdTokenSecret && (
                  <div className="bg-amber-950/40 border border-amber-500/50 rounded-lg p-3.5 space-y-2 text-xs font-mono">
                    <div className="flex items-center justify-between">
                      <span className="text-amber-300 font-semibold font-sans flex items-center space-x-1">
                        <CheckCircle2 className="h-3.5 w-3.5 text-amber-400" />
                        <span>Token Generated Successfully</span>
                      </span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(createdTokenSecret);
                          setCopiedToken(true);
                          setTimeout(() => setCopiedToken(false), 2000);
                        }}
                        className="px-2 py-0.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 rounded text-[10px] font-sans flex items-center space-x-1"
                      >
                        {copiedToken ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                        <span>{copiedToken ? "Copied" : "Copy"}</span>
                      </button>
                    </div>
                    <p className="text-slate-100 bg-slate-950 p-2 rounded border border-amber-500/30 break-all select-all text-[11px]">
                      {createdTokenSecret}
                    </p>
                    <p className="text-[10px] text-amber-400/90 font-sans leading-normal">
                      Copy and store this secret in your Jenkins Credentials store (as Secret text ID <code className="text-white bg-slate-900 px-1 rounded">trace-api-token</code>). For security, it will not be shown again.
                    </p>
                  </div>
                )}
              </div>

              {/* Active Tokens Table */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 md:col-span-2">
                <div className="border-b border-slate-800 pb-3 flex items-center justify-between">
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">Active Jenkins Tokens</h3>
                  <span className="text-[11px] text-slate-400">{jenkinsTokens.length} registered</span>
                </div>

                <div className="overflow-x-auto max-h-60">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-slate-950/60 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                      <tr>
                        <th className="py-2 px-3">Label</th>
                        <th className="py-2 px-3">Token Mask</th>
                        <th className="py-2 px-3">Created</th>
                        <th className="py-2 px-3">Last Active</th>
                        <th className="py-2 px-3">Status</th>
                        <th className="py-2 px-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {jenkinsTokens.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-4 text-center text-slate-500 font-sans">
                            No tokens generated yet. Create a token to connect Jenkins.
                          </td>
                        </tr>
                      ) : (
                        jenkinsTokens.map((t) => (
                          <tr key={t.id} className="hover:bg-slate-800/40 transition">
                            <td className="py-2 px-3 text-slate-200 font-sans font-medium">{t.name}</td>
                            <td className="py-2 px-3 text-indigo-300">{t.token_preview}</td>
                            <td className="py-2 px-3 text-slate-400">{t.created_at.split(' ')[0]}</td>
                            <td className="py-2 px-3 text-slate-400">{t.last_used_at ? t.last_used_at.split(' ')[0] : 'Never'}</td>
                            <td className="py-2 px-3">
                              <span className={`px-2 py-0.5 rounded-full text-[10px] ${
                                t.is_active ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                              }`}>
                                {t.is_active ? 'ACTIVE' : 'REVOKED'}
                              </span>
                            </td>
                            <td className="py-2 px-3 text-right">
                              {t.is_active && (
                                <button
                                  onClick={() => handleRevokeToken(t.id)}
                                  className="text-rose-400 hover:text-rose-300 text-[11px] font-sans hover:underline"
                                >
                                  Revoke
                                </button>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Step-by-Step Jenkins Configuration Guide */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="border-b border-slate-800 pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center space-x-2">
                    <Terminal className="h-4 w-4 text-indigo-400" />
                    <span>Copyable Jenkinsfile Integration Snippet</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Add this post-build action to your Declarative Pipeline. Transmits console logs upon failure or success without failing your build.
                  </p>
                </div>
                <button
                  onClick={() => {
                    const snippet = `post {
    always {
        withCredentials([string(credentialsId: 'trace-api-token', variable: 'TRACE_TOKEN')]) {
            sh '''
                set +x
                CONSOLE_LOG="jenkins_\${BUILD_NUMBER}.log"
                if [ -n "\$BUILD_URL" ]; then
                    curl -s -k --globoff "\${BUILD_URL}consoleText" > "\$CONSOLE_LOG" 2>/dev/null || true
                fi
                if [ ! -s "\$CONSOLE_LOG" ]; then
                    echo "Build \${JOB_NAME} #\${BUILD_NUMBER} completed with status: \${currentBuild.currentResult}" > "\$CONSOLE_LOG"
                fi
                curl -s -X POST "${API_BASE}/jenkins/ingest" \\
                    -H "Authorization: Bearer \${TRACE_TOKEN}" \\
                    -F "job_name=\${JOB_NAME}" \\
                    -F "build_number=\${BUILD_NUMBER}" \\
                    -F "build_status=\${currentBuild.currentResult}" \\
                    -F "build_url=\${BUILD_URL}" \\
                    -F "file=@\${CONSOLE_LOG}" || true
                rm -f "\$CONSOLE_LOG"
            '''
        }
    }
}`;
                    navigator.clipboard.writeText(snippet);
                    setCopiedSnippet(true);
                    setTimeout(() => setCopiedSnippet(false), 2000);
                  }}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition"
                >
                  {copiedSnippet ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  <span>{copiedSnippet ? "Copied" : "Copy Snippet"}</span>
                </button>
              </div>

              {/* 3 Step Instruction Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 space-y-1">
                  <span className="text-indigo-400 font-bold block">STEP 1: Add Jenkins Credential</span>
                  <p className="text-slate-400 leading-relaxed">
                    Navigate to <strong>Manage Jenkins &gt; Credentials &gt; Global</strong>. Add a <em>Secret text</em> credential with ID <code className="text-indigo-300">trace-api-token</code> containing your generated TRACE token.
                  </p>
                </div>
                <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 space-y-1">
                  <span className="text-indigo-400 font-bold block">STEP 2: Configure Jenkinsfile</span>
                  <p className="text-slate-400 leading-relaxed">
                    Embed the post-action block into your <code className="text-indigo-300">Jenkinsfile</code>. It retrieves the console text and executes a sanitized POST to TRACE.
                  </p>
                </div>
                <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 space-y-1">
                  <span className="text-indigo-400 font-bold block">STEP 3: Run & View RCA</span>
                  <p className="text-slate-400 leading-relaxed">
                    Trigger your build. When the job finishes (or fails), TRACE automatically scrubs credentials, detects failure stack traces, and outputs RCA predictions below.
                  </p>
                </div>
              </div>

              {/* Code Snippet Box */}
              <pre className="bg-slate-950 border border-slate-800 p-4 rounded-lg font-mono text-xs text-slate-300 overflow-x-auto leading-relaxed">
{`post {
    always {
        withCredentials([string(credentialsId: 'trace-api-token', variable: 'TRACE_TOKEN')]) {
            sh '''
                set +x
                CONSOLE_LOG="jenkins_\${BUILD_NUMBER}.log"
                if [ -n "\$BUILD_URL" ]; then
                    curl -s -k --globoff "\${BUILD_URL}consoleText" > "\$CONSOLE_LOG" 2>/dev/null || true
                fi
                if [ ! -s "\$CONSOLE_LOG" ]; then
                    echo "Build \${JOB_NAME} #\${BUILD_NUMBER} completed with status: \${currentBuild.currentResult}" > "\$CONSOLE_LOG"
                fi
                curl -s -X POST "${API_BASE}/jenkins/ingest" \\
                    -H "Authorization: Bearer \${TRACE_TOKEN}" \\
                    -F "job_name=\${JOB_NAME}" \\
                    -F "build_number=\${BUILD_NUMBER}" \\
                    -F "build_status=\${currentBuild.currentResult}" \\
                    -F "build_url=\${BUILD_URL}" \\
                    -F "file=@\${CONSOLE_LOG}" || true
                rm -f "\$CONSOLE_LOG"
            '''
        }
    }
}`}
              </pre>
            </div>

            {/* Test Connection & Ingestion Simulator */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="border-b border-slate-800 pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center space-x-2">
                    <Play className="h-4 w-4 text-emerald-400" />
                    <span>Interactive Jenkins Telemetry Simulator</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Test your integration token or simulate an external Jenkins build post-action directly from the UI.
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={handleTestConnection}
                    disabled={isSimulating}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-xs font-medium transition"
                  >
                    Test Token Auth Only
                  </button>
                  <button
                    onClick={handleRunSimulator}
                    disabled={isSimulating}
                    className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition flex items-center space-x-1.5"
                  >
                    <Play className="h-3 w-3" />
                    <span>{isSimulating ? "Ingesting..." : "Simulate Build Upload"}</span>
                  </button>
                </div>
              </div>

              {simError && (
                <p className="text-xs text-rose-400 bg-rose-950/40 p-2.5 rounded border border-rose-800">{simError}</p>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="space-y-3 md:col-span-1">
                  <div>
                    <label className="text-[11px] text-slate-300 font-medium block mb-1">Bearer Token</label>
                    <input
                      type="text"
                      placeholder="trc_..."
                      value={simToken}
                      onChange={(e) => setSimToken(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 font-mono"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-slate-300 font-medium block mb-1">Job Name</label>
                    <input
                      type="text"
                      value={simJobName}
                      onChange={(e) => setSimJobName(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[11px] text-slate-300 font-medium block mb-1">Build Number</label>
                      <input
                        type="text"
                        value={simBuildNum}
                        onChange={(e) => setSimBuildNum(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                      />
                    </div>
                    <div>
                      <label className="text-[11px] text-slate-300 font-medium block mb-1">Status</label>
                      <select
                        value={simBuildStatus}
                        onChange={(e) => setSimBuildStatus(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white"
                      >
                        <option value="FAILURE">FAILURE</option>
                        <option value="UNSTABLE">UNSTABLE</option>
                        <option value="SUCCESS">SUCCESS</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="md:col-span-2 space-y-1">
                  <label className="text-[11px] text-slate-300 font-medium block">Console Output Snippet to Ingest</label>
                  <textarea
                    rows={6}
                    value={simLogText}
                    onChange={(e) => setSimLogText(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Simulation Result Box */}
              {simResult && (
                <div className="bg-slate-950 border border-emerald-500/30 rounded-lg p-4 space-y-2 text-xs font-mono">
                  <div className="flex items-center justify-between font-sans">
                    <span className="text-emerald-400 font-bold flex items-center space-x-1.5">
                      <CheckCircle2 className="h-4 w-4" />
                      <span>Ingestion & Analysis Successful</span>
                    </span>
                    <span className="text-slate-400 text-xs">Build ID: {simResult.build_id}</span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2 text-[11px]">
                    <div>
                      <span className="text-slate-500 block uppercase font-sans">Failure Detected</span>
                      <span className={simResult.is_failure ? "text-rose-400 font-bold" : "text-emerald-400 font-bold"}>
                        {simResult.is_failure ? "YES (FAILED)" : "NO (CLEAN)"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block uppercase font-sans">Category</span>
                      <span className="text-amber-300 font-semibold">{simResult.failure_category || "N/A"}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block uppercase font-sans">Confidence</span>
                      <span className="text-cyan-400">{simResult.confidence ? `${(simResult.confidence * 100).toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block uppercase font-sans">Incidents</span>
                      <span className="text-slate-200">{simResult.incidents_count} detected</span>
                    </div>
                  </div>
                  {simResult.root_cause_candidate && (
                    <div className="mt-2 pt-2 border-t border-slate-800 text-slate-300 font-sans">
                      <span className="text-slate-400 font-semibold">Probable Root Cause: </span>
                      {simResult.root_cause_candidate}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Ingested Jenkins Builds Registry Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                    <Layers className="h-4 w-4 text-indigo-400" />
                    <span>Ingested Jenkins Builds Feed</span>
                  </h3>
                  <p className="text-xs text-slate-400">Chronological history of builds received via Jenkins webhook</p>
                </div>
                <span className="text-xs text-slate-400 font-mono">Table: jenkins_builds ({jenkinsBuilds.length})</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-950/60 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                    <tr>
                      <th className="py-2.5 px-3">Job & Build</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Events</th>
                      <th className="py-2.5 px-3">Classified Category</th>
                      <th className="py-2.5 px-3">Confidence</th>
                      <th className="py-2.5 px-3">Predicted Root Cause</th>
                      <th className="py-2.5 px-3">Ingested At</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {jenkinsBuilds.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-6 text-center text-slate-500 font-sans">
                          No builds received from Jenkins yet. Connect a pipeline or run the simulator above.
                        </td>
                      </tr>
                    ) : (
                      jenkinsBuilds.map((b) => (
                        <tr key={b.id} className="hover:bg-slate-800/40 transition">
                          <td className="py-2.5 px-3 font-sans font-medium text-slate-200">
                            <div className="flex items-center space-x-1.5">
                              <span className="text-indigo-300 font-semibold">{b.job_name}</span>
                              <span className="text-slate-400 font-mono text-[11px]">#{b.build_number}</span>
                            </div>
                          </td>
                          <td className="py-2.5 px-3">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                              b.is_failure ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30' : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                            }`}>
                              {b.build_status || (b.is_failure ? "FAILURE" : "SUCCESS")}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-slate-400">{b.events_count}</td>
                          <td className="py-2.5 px-3 text-amber-300 font-semibold">
                            {b.primary_failure_category || "—"}
                          </td>
                          <td className="py-2.5 px-3 text-cyan-300">
                            {b.confidence ? `${(b.confidence * 100).toFixed(1)}%` : "—"}
                          </td>
                          <td className="py-2.5 px-3 text-slate-300 truncate max-w-xs">
                            {b.root_cause_candidate || "No failure detected"}
                          </td>
                          <td className="py-2.5 px-3 text-slate-400 text-[11px]">{b.ingested_at}</td>
                          <td className="py-2.5 px-3 text-right font-sans space-x-2">
                            <button
                              onClick={async () => {
                                try {
                                  const res = await fetch(`${API_BASE}/jenkins/builds/${encodeURIComponent(b.build_id)}`);
                                  if (res.ok) setSelectedBuildDetail(await res.json());
                                } catch (err) {}
                              }}
                              className="text-indigo-400 hover:text-indigo-300 text-xs font-medium hover:underline"
                            >
                              Details
                            </button>
                            {b.build_url && (
                              <a
                                href={b.build_url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-slate-400 hover:text-slate-300 text-xs inline-flex items-center space-x-0.5"
                              >
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Jenkins Build Inspection Modal */}
            {selectedBuildDetail && (
              <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-2xl w-full p-6 space-y-4 max-h-[85vh] overflow-y-auto">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div>
                      <h3 className="text-sm font-bold text-white flex items-center space-x-2">
                        <span>Jenkins Build Details: {selectedBuildDetail.job_name} #{selectedBuildDetail.build_number}</span>
                      </h3>
                      <p className="text-xs text-slate-400">Build ID: {selectedBuildDetail.build_id}</p>
                    </div>
                    <button
                      onClick={() => setSelectedBuildDetail(null)}
                      className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] uppercase font-sans">Status</span>
                      <span className={selectedBuildDetail.is_failure ? 'text-rose-400 font-bold' : 'text-emerald-400 font-bold'}>
                        {selectedBuildDetail.build_status}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] uppercase font-sans">Category</span>
                      <span className="text-amber-300 font-semibold">{selectedBuildDetail.primary_failure_category || 'N/A'}</span>
                    </div>
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] uppercase font-sans">Confidence</span>
                      <span className="text-cyan-400">
                        {selectedBuildDetail.confidence ? `${(selectedBuildDetail.confidence * 100).toFixed(1)}%` : 'N/A'}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] uppercase font-sans">Events</span>
                      <span className="text-slate-200">{selectedBuildDetail.events_count}</span>
                    </div>
                  </div>

                  {selectedBuildDetail.root_cause_candidate && (
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1 text-xs">
                      <span className="text-slate-400 font-semibold block">Predicted Root Cause Candidate:</span>
                      <p className="text-slate-200">{selectedBuildDetail.root_cause_candidate}</p>
                    </div>
                  )}

                  {/* Incidents within this build */}
                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-white block">
                      Detected Incidents in this Build ({selectedBuildDetail.incidents?.length || 0})
                    </span>
                    {selectedBuildDetail.incidents && selectedBuildDetail.incidents.length > 0 ? (
                      <div className="space-y-2 max-h-48 overflow-y-auto">
                        {selectedBuildDetail.incidents.map((inc: any, idx: number) => (
                          <div key={idx} className="bg-slate-950 p-3 rounded border border-slate-800 text-xs font-mono space-y-1">
                            <div className="flex justify-between text-indigo-300">
                              <span className="font-bold">{inc.incident_code}</span>
                              <span className="text-slate-400">Lines {inc.start_line}-{inc.end_line}</span>
                            </div>
                            <p className="text-amber-300">{inc.failure_category} ({(inc.confidence * 100).toFixed(1)}%)</p>
                            <p className="text-slate-400 truncate">{inc.detected_signature}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500">No discrete failure blocks detected in build console text.</p>
                    )}
                  </div>

                  <div className="pt-2 flex justify-end space-x-2 text-xs">
                    <button
                      onClick={() => {
                        setEventFileId(selectedBuildDetail.file_id?.toString() || "");
                        setSelectedBuildDetail(null);
                        setActiveTab('parser');
                      }}
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium"
                    >
                      Inspect in Parser View
                    </button>
                    <button
                      onClick={() => setSelectedBuildDetail(null)}
                      className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg"
                    >
                      Close
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =========================================================================
            VIEW 4: PRIVACY & SANITIZATION VIEW
            ========================================================================= */}
        {activeTab === 'privacy' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div className="flex items-center space-x-2 text-emerald-400">
                  <ShieldCheck className="h-5 w-5" />
                  <h2 className="text-sm font-bold text-white">Live Zero-PII Secret Sanitization Audit</h2>
                </div>
                {/* Real Ingested Log Selector */}
                <div className="flex items-center space-x-2">
                  <label className="text-xs text-slate-400 font-sans">Select Ingested Log:</label>
                  <select
                    value={privacyLogId ?? ""}
                    onChange={(e) => {
                      const id = Number(e.target.value);
                      if (id) {
                        setPrivacyLogId(id);
                        fetchPrivacyAudit(id);
                      }
                    }}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono"
                  >
                    {ingestedLogs.length === 0 ? (
                      <option value="">No logs ingested yet</option>
                    ) : (
                      ingestedLogs.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.job_name ? `[Jenkins] ${l.job_name} #${l.build_number}` : `[Manual] ${l.filename}`} ({l.line_count} lines)
                        </option>
                      ))
                    )}
                  </select>
                </div>
              </div>

              {/* Zero-PII Policy Clarification */}
              <div className="bg-emerald-950/30 border border-emerald-500/30 rounded-lg p-3 text-xs text-slate-300 flex items-start space-x-2.5">
                <Info className="h-4 w-4 text-emerald-400 mt-0.5 flex-shrink-0" />
                <div className="space-y-0.5">
                  <span className="font-semibold text-emerald-300 block">TRACE Zero-PII Data Protection Architecture:</span>
                  <p className="text-slate-400 leading-relaxed">
                    Passwords, JWT tokens, AWS/GitHub keys, authorization headers, and IP addresses are masked <strong>in-flight</strong> before SQLite persistence or ML inference. Real credentials (including Jenkins Bearer tokens) are never stored in plain text.
                  </p>
                </div>
              </div>

              {/* Security Metrics Strip */}
              {privacyData && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1 text-xs font-mono">
                  <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px] font-sans">Selected Log</span>
                    <span className="text-slate-200 font-semibold truncate block">{privacyData.filename}</span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px] font-sans">Source Classification</span>
                    <span className="text-indigo-300 font-semibold">{privacyData.source_type}</span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px] font-sans">Detected Leaks Scrubbed</span>
                    <span className={privacyData.leak_count > 0 ? "text-amber-400 font-bold" : "text-emerald-400 font-bold"}>
                      {privacyData.leak_count} detected & masked
                    </span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px] font-sans">Database Secret Storage</span>
                    <span className="text-emerald-400 font-bold">0 Plaintext Secrets</span>
                  </div>
                </div>
              )}
            </div>

            {/* Error / Loading State */}
            {isPrivacyLoading && (
              <div className="py-12 text-center text-slate-500 font-mono text-xs">
                Auditing selected log with SecretMasker...
              </div>
            )}

            {privacyError && (
              <div className="bg-rose-950/60 border border-rose-500 p-4 rounded-xl text-xs text-rose-300">
                {privacyError}
              </div>
            )}

            {/* Empty State */}
            {!isPrivacyLoading && ingestedLogs.length === 0 && (
              <div className="bg-slate-900 border border-dashed border-slate-800 rounded-xl p-12 text-center space-y-2">
                <ShieldCheck className="h-10 w-10 text-slate-600 mx-auto" />
                <p className="text-sm font-semibold text-slate-300">No Ingested Logs Available</p>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Upload a CI/CD log in Log Ingestion or trigger a Jenkins build to audit the live secret masking pipeline.
                </p>
              </div>
            )}

            {/* Live Side-by-Side Comparison on Persisted Data */}
            {!isPrivacyLoading && privacyData && (
              <div className="space-y-3">
                <p className="text-xs text-slate-400 font-mono italic">
                  {privacyData.security_notice}
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Left Pane */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-rose-400 flex items-center space-x-1 font-mono">
                        <span>INPUT LOG STREAM</span>
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {privacyData.is_raw_available ? "Authentic Raw Storage" : "In-Flight Pre-Persistence Stream"}
                      </span>
                    </div>
                    <pre className="bg-slate-950 border border-slate-800 p-3 rounded-lg text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap h-96">
                      {privacyData.raw_sample || "No log content"}
                    </pre>
                  </div>

                  {/* Right Pane */}
                  <div className="bg-slate-900 border border-emerald-500/30 rounded-xl p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-emerald-400 flex items-center space-x-1 font-mono">
                        <span>SANITIZED PIPELINE OUTPUT (SECRETS REDACTED)</span>
                      </span>
                      <span className="text-[10px] text-emerald-400/80 font-mono">
                        Scrubbed by SecretMasker
                      </span>
                    </div>
                    <pre className="bg-slate-950 border border-slate-800 p-3 rounded-lg text-xs font-mono text-emerald-300 overflow-x-auto whitespace-pre-wrap h-96">
                      {privacyData.sanitized_sample || "No sanitized content"}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =========================================================================
            VIEW 5: STRUCTURED PARSER VIEW
            ========================================================================= */}
        {activeTab === 'parser' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-4">
              <div>
                <h2 className="text-base font-bold text-white">Parsed Structured Event Table</h2>
                <p className="text-xs text-slate-400">Querying live normalized events from SQLite table <code className="text-indigo-300 font-mono">parsed_events</code></p>
              </div>

              {/* Multi-Filters */}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {/* Filter by Log File */}
                <select
                  value={eventFileId}
                  onChange={(e) => setEventFileId(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-md px-2.5 py-1 text-slate-200 font-mono"
                >
                  <option value="">All Ingested Logs</option>
                  {ingestedLogs.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.job_name ? `[Jenkins] ${l.job_name} #${l.build_number}` : l.filename}
                    </option>
                  ))}
                </select>

                {/* Severity Filter */}
                <select 
                  value={eventSeverity} 
                  onChange={(e) => setEventSeverity(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-md px-2.5 py-1 text-slate-200"
                >
                  <option value="">All Severities</option>
                  <option value="ERROR">ERROR</option>
                  <option value="WARN">WARN</option>
                  <option value="INFO">INFO</option>
                  <option value="DEBUG">DEBUG</option>
                </select>

                {/* Service Filter */}
                <input
                  type="text"
                  placeholder="Filter service..."
                  value={eventService}
                  onChange={(e) => setEventService(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-md px-2.5 py-1 text-slate-200"
                />

                <button 
                  onClick={fetchEvents}
                  className="p-1.5 bg-slate-800 hover:bg-slate-700 rounded-md text-slate-300"
                  title="Apply / Refresh Events"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="py-2.5 px-3">ID</th>
                    <th className="py-2.5 px-3">Source File / Log</th>
                    <th className="py-2.5 px-3">Line</th>
                    <th className="py-2.5 px-3">Timestamp</th>
                    <th className="py-2.5 px-3">Severity</th>
                    <th className="py-2.5 px-3">Service / Logger</th>
                    <th className="py-2.5 px-3">Sanitized Message</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {eventsData.events.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="text-center py-6 text-slate-500 font-sans">
                        No parsed events found matching selected log or filter criteria.
                      </td>
                    </tr>
                  ) : (
                    eventsData.events.map((ev: any) => (
                      <tr key={ev.id} className="hover:bg-slate-800/40 transition">
                        <td className="py-2 px-3 text-slate-500">{ev.id}</td>
                        <td className="py-2 px-3 text-slate-300 max-w-[150px] truncate">{ev.source_file}</td>
                        <td className="py-2 px-3 text-slate-400">{ev.line_number}</td>
                        <td className="py-2 px-3 text-slate-400">{ev.timestamp || "N/A"}</td>
                        <td className="py-2 px-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            ev.severity === 'ERROR' ? 'bg-rose-500/20 text-rose-300' :
                            ev.severity === 'WARN' ? 'bg-amber-500/20 text-amber-300' :
                            'bg-slate-800 text-slate-300'
                          }`}>
                            {ev.severity}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-indigo-300 max-w-[140px] truncate">{ev.service || "unknown"}</td>
                        <td className="py-2 px-3 text-slate-300 max-w-md truncate">{ev.sanitized_message}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="text-[11px] text-slate-500 text-right">
              Showing {eventsData.events.length} of {eventsData.total} matching events
            </div>
          </div>
        )}

        {/* =========================================================================
            VIEW 6: INCIDENT & ROOT CAUSE ANALYSIS
            ========================================================================= */}
        {activeTab === 'analysis' && (
          <div className="space-y-4">
            {/* View Mode Toggle Bar */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h2 className="text-base font-bold text-white">Incident & Root Cause Analysis (RCA)</h2>
                <p className="text-xs text-slate-400">
                  Inspect failure blocks, predicted failure categories, and candidate root causes from real ingested logs
                </p>
              </div>

              <div className="flex items-center space-x-1 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs font-medium">
                <button
                  onClick={() => setRcaViewMode('persisted')}
                  className={`px-3 py-1.5 rounded-md transition ${
                    rcaViewMode === 'persisted' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Persisted Incidents ({incidents.length})
                </button>
                <button
                  onClick={() => setRcaViewMode('interactive')}
                  className={`px-3 py-1.5 rounded-md transition ${
                    rcaViewMode === 'interactive' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Interactive Snippet Analyzer
                </button>
              </div>
            </div>

            {/* MODE 1: PERSISTED INCIDENTS FROM REAL UPLOADED / JENKINS LOGS */}
            {rcaViewMode === 'persisted' && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Left Column: List of Real Detected Incidents */}
                <div className="lg:col-span-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono">
                      Detected Incidents Feed
                    </span>
                    <span className="text-[11px] text-slate-500 font-mono">Total: {incidents.length}</span>
                  </div>

                  {incidents.length === 0 ? (
                    <div className="bg-slate-900 border border-dashed border-slate-800 rounded-xl p-8 text-center text-xs text-slate-500 space-y-2">
                      <AlertTriangle className="h-8 w-8 text-slate-600 mx-auto" />
                      <p className="font-semibold text-slate-400">No Incidents Detected</p>
                      <p>Upload a log containing failure events to populate live incidents.</p>
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-[680px] overflow-y-auto pr-1">
                      {incidents.map((inc) => (
                        <button
                          key={inc.id}
                          onClick={() => setSelectedIncidentCode(inc.incident_code)}
                          className={`w-full text-left p-3 rounded-xl border transition space-y-1.5 ${
                            (activeIncident && activeIncident.incident_code === inc.incident_code)
                              ? 'bg-indigo-950/70 border-indigo-500/60 text-white shadow-lg shadow-indigo-950/40'
                              : 'bg-slate-900 border-slate-800 text-slate-300 hover:bg-slate-800/60'
                          }`}
                        >
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-mono font-bold text-indigo-300">{inc.incident_code}</span>
                            <span className="text-[11px] text-slate-400 font-mono">
                              Lines {inc.start_line}-{inc.end_line}
                            </span>
                          </div>
                          <div className="text-xs font-sans text-slate-200">
                            {inc.job_name ? (
                              <span className="text-cyan-300 font-medium">Jenkins: {inc.job_name} #{inc.build_number}</span>
                            ) : (
                              <span className="text-slate-300 truncate max-w-xs block">{inc.source_file}</span>
                            )}
                          </div>
                          <div className="flex items-center justify-between text-[11px] pt-0.5">
                            <span className="text-amber-400 font-semibold font-mono">{inc.failure_category}</span>
                            <span className="text-cyan-400 font-mono">{(inc.confidence * 100).toFixed(1)}%</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Right Column: Real Incident RCA Detail */}
                <div className="lg:col-span-7 space-y-4">
                  {activeIncident ? (
                    <div className="space-y-4">
                      {/* Classification & Prediction Card */}
                      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                          <div>
                            <span className="text-[10px] uppercase tracking-wider text-slate-400 font-mono">
                              Incident Code: {activeIncident.incident_code}
                            </span>
                            <h2 className="text-lg font-bold text-amber-400 font-mono mt-0.5">
                              {activeIncident.failure_category}
                            </h2>
                            <p className="text-xs text-slate-400 mt-0.5 font-sans">
                              Source: <code className="text-slate-300">{activeIncident.source_file}</code> (Lines {activeIncident.start_line}-{activeIncident.end_line})
                            </p>
                          </div>
                          <div className="text-right">
                            <span className="text-xs text-slate-400 block font-sans">Model Confidence</span>
                            <span className="text-lg font-bold text-cyan-400 font-mono">
                              {(activeIncident.confidence * 100).toFixed(1)}%
                            </span>
                          </div>
                        </div>

                        {/* Associated Jenkins Trace */}
                        {activeIncident.job_name && (
                          <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs flex items-center justify-between font-mono">
                            <div>
                              <span className="text-slate-400 font-sans block text-[10px]">Jenkins Build Association:</span>
                              <span className="text-cyan-300 font-bold">{activeIncident.job_name} #{activeIncident.build_number}</span>
                            </div>
                            {activeIncident.build_url && (
                              <a
                                href={activeIncident.build_url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-indigo-400 hover:text-indigo-300 flex items-center space-x-1"
                              >
                                <span>Open Build</span>
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            )}
                          </div>
                        )}

                        {/* Root Cause Candidate Layer */}
                        <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-indigo-300 font-mono">
                              PREDICTED ROOT CAUSE CANDIDATE
                            </span>
                            <span className="text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded font-sans">
                              Unverified Prediction
                            </span>
                          </div>
                          <p className="text-sm font-semibold text-white">
                            {activeIncident.root_cause_candidate}
                          </p>
                          <p className="text-[11px] text-slate-400 leading-relaxed font-sans italic border-t border-slate-800/80 pt-2">
                            Notice: This diagnosis is a candidate recommendation formulated by TRACE's root-cause analyzer based on lexical failure signatures. It represents a predicted candidate, not a human-verified root cause.
                          </p>
                        </div>

                        {/* Failure Signature */}
                        <div className="space-y-1">
                          <span className="text-xs font-semibold text-slate-300 font-mono">Detected Failure Signature:</span>
                          <pre className="bg-slate-950 p-2.5 rounded border border-slate-800 text-xs font-mono text-rose-300 overflow-x-auto whitespace-pre-wrap">
                            {activeIncident.detected_signature}
                          </pre>
                        </div>

                        {/* Full Evidence Text */}
                        {activeIncident.evidence_text && (
                          <div className="space-y-1">
                            <span className="text-xs font-semibold text-slate-300 font-mono">Complete Incident Evidence Text:</span>
                            <pre className="bg-slate-950 p-3 rounded border border-slate-800 text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap max-h-60">
                              {activeIncident.evidence_text}
                            </pre>
                          </div>
                        )}

                        {/* Jump to Parser button */}
                        <div className="pt-2 flex justify-end">
                          <button
                            onClick={() => {
                              if (activeIncident.file_id) {
                                setEventFileId(activeIncident.file_id.toString());
                              }
                              setActiveTab('parser');
                            }}
                            className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium transition flex items-center space-x-1.5"
                          >
                            <span>Inspect Surrounding Events in Parser</span>
                            <ArrowRight className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="h-96 border border-dashed border-slate-800 rounded-xl flex items-center justify-center text-center p-8 text-xs text-slate-500">
                      Select an incident from the left to inspect its root-cause analysis.
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* MODE 2: INTERACTIVE SNIPPET ANALYZER (BENCHMARK & AD-HOC) */}
            {rcaViewMode === 'interactive' && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-5 space-y-4">
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
                    <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                      <Terminal className="h-4 w-4 text-indigo-400" />
                      <span>Select Failure Benchmark Preset</span>
                    </h3>

                    <div className="space-y-1.5">
                      {AUTHENTIC_PRESETS.map((p, idx) => (
                        <button
                          key={idx}
                          onClick={() => setAnalysisInput(p.snippet)}
                          className={`w-full text-left p-2.5 rounded-lg text-xs transition border ${
                            analysisInput === p.snippet
                              ? 'bg-indigo-950/70 border-indigo-500/50 text-indigo-200'
                              : 'bg-slate-950/40 border-slate-800 text-slate-300 hover:bg-slate-800'
                          }`}
                        >
                          <p className="font-semibold text-slate-200 truncate">{p.title}</p>
                          <p className="text-[10px] text-slate-400 font-mono">{p.file}</p>
                        </button>
                      ))}
                    </div>

                    <div>
                      <label className="text-xs font-medium text-slate-400 block mb-1">
                        Log Text to Analyze On-Demand
                      </label>
                      <textarea
                        value={analysisInput}
                        onChange={(e) => setAnalysisInput(e.target.value)}
                        rows={7}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500 resize-none"
                      />
                    </div>

                    <button
                      onClick={handleRunAnalysis}
                      disabled={isAnalyzing}
                      className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow transition flex items-center justify-center space-x-2"
                    >
                      {isAnalyzing ? <span>Running Parser & Baseline Model...</span> : (
                        <>
                          <span>Analyze Failure & Root Cause Candidate</span>
                          <ArrowRight className="h-3.5 w-3.5" />
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <div className="lg:col-span-7 space-y-4">
                  {analysisError && (
                    <div className="bg-rose-950/80 border border-rose-500 p-4 rounded-xl text-xs text-rose-200 space-y-1">
                      <div className="flex items-center space-x-2 font-bold text-rose-400">
                        <AlertTriangle className="h-4 w-4" />
                        <span>Inference Error</span>
                      </div>
                      <p>{analysisError}</p>
                    </div>
                  )}

                  {analysisResult ? (
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-slate-400 font-mono">
                            Live Inference Result
                          </span>
                          <h2 className="text-lg font-bold text-amber-400 font-mono mt-0.5">
                            {analysisResult.classification.predicted_category}
                          </h2>
                        </div>
                        <div className="text-right">
                          <span className="text-xs text-slate-400 block font-sans">Confidence</span>
                          <span className="text-lg font-bold text-cyan-400 font-mono">
                            {(analysisResult.classification.confidence * 100).toFixed(1)}%
                          </span>
                        </div>
                      </div>

                      <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 space-y-2">
                        <span className="text-xs font-bold text-indigo-300 font-mono">
                          Root Cause Candidate Analysis
                        </span>
                        <p className="text-sm font-semibold text-white">
                          {analysisResult.root_cause.root_cause_candidate}
                        </p>
                        <p className="text-xs text-slate-400 leading-relaxed font-sans">
                          {analysisResult.root_cause.explanation}
                        </p>
                      </div>

                      <div>
                        <span className="text-xs text-slate-400 block mb-1.5 font-sans">Class Probabilities:</span>
                        <div className="space-y-1.5 font-mono text-xs">
                          {Object.entries(analysisResult.classification.top_probabilities).map(([cat, prob]: any) => (
                            <div key={cat} className="space-y-0.5">
                              <div className="flex justify-between text-[11px] text-slate-400">
                                <span className="truncate max-w-sm">{cat}</span>
                                <span className="text-slate-200 font-semibold">{(prob * 100).toFixed(1)}%</span>
                              </div>
                              <div className="w-full bg-slate-800 rounded-full h-1.5">
                                <div 
                                  className="bg-indigo-500 h-1.5 rounded-full transition-all" 
                                  style={{ width: `${prob * 100}%` }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="h-96 border border-dashed border-slate-800 rounded-xl flex items-center justify-center text-center p-8 text-xs text-slate-500">
                      Pick a preset on the left and click "Analyze Failure" to trigger live model inference.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* =========================================================================
            VIEW 7: MODEL EVALUATION
            ========================================================================= */}
        {activeTab === 'model' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="border-b border-slate-800 pb-3 flex flex-col md:flex-row md:items-center justify-between gap-2">
                <div>
                  <span className="text-xs font-mono text-indigo-400">Current Academic Baseline</span>
                  <h2 className="text-lg font-bold text-white">Offline Model Evaluation & Benchmark Metrics</h2>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-xs bg-slate-800 px-3 py-1 rounded text-slate-300 font-mono">
                    TF-IDF + Random Forest
                  </span>
                  <button
                    onClick={fetchHealthAndMetrics}
                    className="p-1.5 bg-slate-800 hover:bg-slate-700 rounded text-slate-300"
                    title="Refresh Metrics"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {/* Crucial Offline vs Live Notice */}
              <div className="bg-indigo-950/40 border border-indigo-500/30 rounded-lg p-3.5 text-xs text-slate-300 flex items-start space-x-2.5">
                <Info className="h-4 w-4 text-indigo-400 mt-0.5 flex-shrink-0" />
                <div className="space-y-0.5">
                  <span className="font-semibold text-white block">Offline Evaluation Integrity:</span>
                  <p className="text-slate-400 leading-relaxed">
                    These evaluation metrics are computed strictly on the held-out test partition (15% split) and persisted in <code className="text-indigo-300 font-mono">evaluation_manifest.json</code>. Real-time Jenkins build logs ingested during live operation are tracked in operational feeds and do not mutate or overwrite offline benchmark evaluation artifacts.
                  </p>
                </div>
              </div>

              {metricsData ? (
                <div className="space-y-6">
                  {/* Key Metrics Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono">
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-[10px] text-slate-500 block">Test Accuracy</span>
                      <span className="text-xl font-bold text-emerald-400">{(metricsData.accuracy * 100).toFixed(2)}%</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-[10px] text-slate-500 block">Test Macro F1</span>
                      <span className="text-xl font-bold text-cyan-400">{(metricsData.f1_macro * 100).toFixed(2)}%</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-[10px] text-slate-500 block">Test Macro Precision</span>
                      <span className="text-xl font-bold text-slate-200">{(metricsData.precision_macro * 100).toFixed(2)}%</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-[10px] text-slate-500 block">Mean Inference Latency</span>
                      <span className="text-xl font-bold text-amber-400">{metricsData.avg_latency_ms} ms</span>
                    </div>
                  </div>

                  {/* Partition & Evaluation Provenance */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs font-mono">
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-slate-400 block font-sans">Evaluated At</span>
                      <span className="text-indigo-300 font-bold">{metricsData.evaluated_at}</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-slate-400 block font-sans">Held-out Test Samples</span>
                      <span className="text-white font-bold">{metricsData.sample_count} incidents</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-slate-400 block font-sans">Feature Dimensions</span>
                      <span className="text-white font-bold">{metricsData.feature_dimension} n-grams</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-slate-400 block font-sans">P95 Inference Latency</span>
                      <span className="text-amber-300 font-bold">{metricsData.p95_latency_ms} ms</span>
                    </div>
                  </div>

                  {/* Per-Class Breakdown Table */}
                  <div>
                    <h3 className="text-xs font-bold text-white uppercase tracking-wider mb-2 font-mono">
                      Held-Out Test Performance by Failure Category
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                          <tr>
                            <th className="py-2 px-3">Failure Category</th>
                            <th className="py-2 px-3">Precision</th>
                            <th className="py-2 px-3">Recall</th>
                            <th className="py-2 px-3">F1-Score</th>
                            <th className="py-2 px-3">Support (N)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {Object.entries(metricsData.per_class_metrics || {}).map(([cat, m]: any) => (
                            <tr key={cat} className="hover:bg-slate-800/40">
                              <td className="py-2 px-3 text-slate-200">{cat}</td>
                              <td className="py-2 px-3 text-slate-300">{(m.precision * 100).toFixed(1)}%</td>
                              <td className="py-2 px-3 text-slate-300">{(m.recall * 100).toFixed(1)}%</td>
                              <td className="py-2 px-3 text-cyan-300 font-semibold">{(m.f1 * 100).toFixed(1)}%</td>
                              <td className="py-2 px-3 text-slate-400">{m.support}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Limitations & Roadmap */}
                  <div className="bg-slate-950 border border-slate-800 p-4 rounded-lg space-y-2">
                    <span className="text-xs font-bold text-amber-400 font-mono block">
                      Documented Baseline Limitations & Development Roadmap:
                    </span>
                    <ul className="list-disc pl-5 space-y-1 text-xs text-slate-400">
                      {metricsData.limitations?.map((lim: string, idx: number) => (
                        <li key={idx}>{lim}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 text-slate-500 font-mono text-xs">
                  {backendError ? "Unable to load evaluation manifest. Ensure backend is running." : "Loading evaluation metrics..."}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Professional Neutral Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-900/60 px-6 py-3.5 text-xs text-slate-400 flex flex-col md:flex-row items-center justify-between gap-2">
        <div className="font-medium">
          Automated Log Analysis and Root Cause Detection System using Machine Learning
        </div>
        <div className="text-slate-500 font-mono text-[11px]">
          Current Baseline: TF-IDF + Random Forest
        </div>
      </footer>
    </div>
  );
}
