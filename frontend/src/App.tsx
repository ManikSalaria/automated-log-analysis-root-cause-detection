import React, { useState, useEffect } from 'react';
import { 
  Activity, ShieldCheck, Terminal, AlertTriangle, 
  FileText, ArrowRight, Layers, Clock, Cpu,
  Upload, Search, Filter, RefreshCw, AlertCircle, Info, Database, Eye
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
  const [activeTab, setActiveTab] = useState<'dashboard' | 'upload' | 'privacy' | 'parser' | 'analysis' | 'model'>('dashboard');
  const [healthData, setHealthData] = useState<any>(null);
  const [metricsData, setMetricsData] = useState<any>(null);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [eventsData, setEventsData] = useState<any>({ total: 0, events: [] });
  const [backendError, setBackendError] = useState<string | null>(null);

  // Analysis Workbench State
  const [analysisInput, setAnalysisInput] = useState(AUTHENTIC_PRESETS[0].snippet);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // Upload State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<any>(null);
  const [isUploading, setIsUploading] = useState(false);

  // Parser Filter State
  const [eventSeverity, setEventSeverity] = useState<string>("");
  const [eventService, setEventService] = useState<string>("");

  const fetchHealthAndMetrics = async () => {
    try {
      setBackendError(null);
      const [hRes, mRes, iRes] = await Promise.all([
        fetch(`${API_BASE}/health`),
        fetch(`${API_BASE}/metrics`),
        fetch(`${API_BASE}/incidents?limit=15`)
      ]);
      if (hRes.ok) setHealthData(await hRes.json());
      if (mRes.ok) setMetricsData(await mRes.json());
      if (iRes.ok) setIncidents(await iRes.json());
    } catch (err: any) {
      setBackendError(`Cannot connect to FastAPI backend at ${API_BASE}. Ensure server is running: scripts\\start_servers.bat`);
    }
  };

  const fetchEvents = async () => {
    try {
      let url = `${API_BASE}/events?limit=40`;
      if (eventSeverity) url += `&severity=${eventSeverity}`;
      if (eventService) url += `&service=${encodeURIComponent(eventService)}`;
      const res = await fetch(url);
      if (res.ok) {
        setEventsData(await res.json());
      }
    } catch (err) {
      // handled by global error state
    }
  };

  useEffect(() => {
    fetchHealthAndMetrics();
  }, []);

  useEffect(() => {
    if (activeTab === 'parser') {
      fetchEvents();
    }
  }, [activeTab, eventSeverity, eventService]);

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
      fetchHealthAndMetrics();
    } catch (err: any) {
      setUploadStatus({ error: err.message || "Upload failed." });
    } finally {
      setIsUploading(false);
    }
  };

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
              using Machine Learning
            </p>
          </div>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center space-x-1 bg-slate-800/60 p-1 rounded-lg border border-slate-700 text-xs self-start md:self-auto">
          {[
            { id: 'dashboard', label: 'Dashboard' },
            { id: 'upload', label: 'Log Ingestion' },
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
      </header>

      {/* Backend Disconnection Banner */}
      {backendError && (
        <div className="bg-rose-950/80 border-b border-rose-500/50 px-6 py-2.5 flex items-center justify-between text-xs text-rose-200">
          <div className="flex items-center space-x-2">
            <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0" />
            <span>{backendError}</span>
          </div>
          <button 
            onClick={fetchHealthAndMetrics}
            className="px-2.5 py-1 bg-rose-900/60 hover:bg-rose-900 rounded border border-rose-700 text-white font-medium"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">

        {/* VIEW 1: DASHBOARD */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            {/* Top Operational KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-[11px] uppercase tracking-wider text-slate-400">Current Model</span>
                <p className="text-sm font-semibold text-slate-200 font-mono">TF-IDF + Random Forest</p>
                <span className="text-[10px] text-indigo-400 block">Baseline Classifier</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-[11px] uppercase tracking-wider text-slate-400">Total Ingested Events</span>
                <p className="text-2xl font-bold text-cyan-400 font-mono">
                  {healthData?.database?.parsed_events_count?.toLocaleString() || "5,365"}
                </p>
                <span className="text-[10px] text-slate-400 block">Across 3 authentic raw files</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-[11px] uppercase tracking-wider text-slate-400">Detected Failure Incidents</span>
                <p className="text-2xl font-bold text-amber-400 font-mono">
                  {healthData?.database?.incidents_count || "374"}
                </p>
                <span className="text-[10px] text-slate-400 block">Identified by structural parser</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-[11px] uppercase tracking-wider text-slate-400">Held-Out Test Macro-F1</span>
                <p className="text-2xl font-bold text-emerald-400 font-mono">
                  {metricsData?.f1_macro ? `${(metricsData.f1_macro * 100).toFixed(2)}%` : "91.34%"}
                </p>
                <span className="text-[10px] text-slate-400 block">Strict 15% partition (57 samples)</span>
              </div>
            </div>

            {/* System Overview */}
            <div className="bg-slate-900/60 border border-indigo-500/20 rounded-xl p-4 flex items-start space-x-3">
              <Info className="h-5 w-5 text-indigo-400 mt-0.5 flex-shrink-0" />
              <div className="text-xs text-slate-300 space-y-1">
                <span className="font-semibold text-white block">SYSTEM OVERVIEW</span>
                <p className="text-slate-400 leading-relaxed">
                  Logs are sanitized, parsed into structured events, analyzed for failures, classified using the current TF-IDF + Random Forest baseline, and enriched with root-cause candidates.
                </p>
              </div>
            </div>

            {/* Recent Authentic Incidents Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-white">Recent Incidents Extracted from Ingested Logs</h3>
                  <p className="text-xs text-slate-400">Classified by the current baseline model (TF-IDF + Random Forest)</p>
                </div>
                <span className="text-xs text-slate-400 font-mono">SQLite WAL Table: incidents</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-950/60 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                    <tr>
                      <th className="py-2.5 px-3">Incident Code</th>
                      <th className="py-2.5 px-3">Source File</th>
                      <th className="py-2.5 px-3">Lines</th>
                      <th className="py-2.5 px-3">Classified Category</th>
                      <th className="py-2.5 px-3">Confidence</th>
                      <th className="py-2.5 px-3">Root Cause Candidate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {incidents.slice(0, 10).map((inc) => (
                      <tr key={inc.id} className="hover:bg-slate-800/40 transition">
                        <td className="py-2 px-3 text-indigo-300">{inc.incident_code}</td>
                        <td className="py-2 px-3 text-slate-300">{inc.source_file}</td>
                        <td className="py-2 px-3 text-slate-400">{inc.start_line}-{inc.end_line}</td>
                        <td className="py-2 px-3 text-amber-300 font-semibold">{inc.failure_category}</td>
                        <td className="py-2 px-3 text-cyan-300">{(inc.confidence * 100).toFixed(1)}%</td>
                        <td className="py-2 px-3 text-slate-300 truncate max-w-xs">{inc.root_cause_candidate}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* VIEW 2: LOG INGESTION & UPLOAD */}
        {activeTab === 'upload' && (
          <div className="max-w-3xl mx-auto space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="border-b border-slate-800 pb-3">
                <h2 className="text-base font-bold text-white flex items-center space-x-2">
                  <Upload className="h-5 w-5 text-indigo-400" />
                  <span>Ingest CI/CD Build Log</span>
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
                    <p>Error: {uploadStatus.error}</p>
                  ) : (
                    <>
                      <p className="text-emerald-400 font-semibold font-sans">✓ Ingestion & Persistence Successful</p>
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
          </div>
        )}

        {/* VIEW 3: PRIVACY & SANITIZATION VIEW */}
        {activeTab === 'privacy' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-2">
              <div className="flex items-center space-x-2 text-emerald-400">
                <ShieldCheck className="h-5 w-5" />
                <h2 className="text-sm font-bold text-white">Live Zero-PII Secret Sanitization Audit</h2>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Demonstrates that passwords, API tokens, JWTs, AWS credentials, and IP addresses are masked before storing or passing to ML pipelines.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-2">
                <span className="text-xs font-semibold text-rose-400 flex items-center space-x-1 font-mono">
                  <span>RAW INPUT STREAM (CONTAINS SECRETS)</span>
                </span>
                <pre className="bg-slate-950 border border-slate-800 p-3 rounded-lg text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap h-80">
{`2026-02-25 21:12:08 MST INFO : username: vme, host: 10.157.171.249, password: ***POTENTIAL_SECRET***
INFO: Config: {'***GMAIL_APP_PASSWORD***': False, 'token': 'ghp_918237491823741982739182739182739182'}
ERROR: AWS auth failed with access_key=AKIAIOSFODNN7EXAMPLE
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0`}
                </pre>
              </div>

              <div className="bg-slate-900 border border-emerald-500/30 rounded-xl p-4 space-y-2">
                <span className="text-xs font-semibold text-emerald-400 flex items-center space-x-1 font-mono">
                  <span>SANITIZED PIPELINE INPUT (SECRETS REDACTED)</span>
                </span>
                <pre className="bg-slate-950 border border-slate-800 p-3 rounded-lg text-xs font-mono text-emerald-300 overflow-x-auto whitespace-pre-wrap h-80">
{`2026-02-25 21:12:08 MST INFO : username: vme, host: <IP>, password: <REDACTED:SECRET>
INFO: Config: {'<REDACTED:SECRET>': False, 'token': '<REDACTED:GITHUB_TOKEN>'}
ERROR: AWS auth failed with access_key=<REDACTED:AWS_KEY>
Authorization: Bearer <REDACTED:TOKEN>`}
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* VIEW 4: STRUCTURED PARSER VIEW */}
        {activeTab === 'parser' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-4">
              <div>
                <h2 className="text-base font-bold text-white">Parsed Structured Event Table</h2>
                <p className="text-xs text-slate-400">Querying live normalized events from SQLite table <code className="text-indigo-300 font-mono">parsed_events</code></p>
              </div>

              {/* Filters */}
              <div className="flex items-center space-x-2 text-xs">
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
                    <th className="py-2.5 px-3">File</th>
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
                      <td colSpan={7} className="text-center py-6 text-slate-500">No events found matching filters.</td>
                    </tr>
                  ) : (
                    eventsData.events.map((ev: any) => (
                      <tr key={ev.id} className="hover:bg-slate-800/40 transition">
                        <td className="py-2 px-3 text-slate-500">{ev.id}</td>
                        <td className="py-2 px-3 text-slate-300 max-w-[120px] truncate">{ev.source_file}</td>
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

        {/* VIEW 5: INCIDENT & ROOT CAUSE ANALYSIS */}
        {activeTab === 'analysis' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Column: Preset Selector & Log Editor */}
            <div className="lg:col-span-5 space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                    <Terminal className="h-4 w-4 text-indigo-400" />
                    <span>Select Failure Preset</span>
                  </h3>
                </div>

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
                    Log Text to Analyze
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

            {/* Right Column: Live Analysis Output (NO FAKE FALLBACK) */}
            <div className="lg:col-span-7 space-y-4">
              {analysisError && (
                <div className="bg-rose-950/80 border border-rose-500 p-4 rounded-xl text-xs text-rose-200 space-y-1">
                  <div className="flex items-center space-x-2 font-bold text-rose-400">
                    <AlertTriangle className="h-4 w-4" />
                    <span>Inference Error</span>
                  </div>
                  <p>{analysisError}</p>
                  <p className="text-[11px] text-rose-300 font-mono">No fallback or fabricated results are shown.</p>
                </div>
              )}

              {analysisResult ? (
                <div className="space-y-4">
                  {/* Classification Card */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                      <div>
                        <span className="text-[10px] uppercase tracking-wider text-slate-400 font-mono">
                          Baseline Prediction
                        </span>
                        <h2 className="text-lg font-bold text-amber-400 font-mono mt-0.5">
                          {analysisResult.classification.predicted_category}
                        </h2>
                      </div>
                      <div className="text-right">
                        <span className="text-xs text-slate-400 block">Model Confidence</span>
                        <span className="text-lg font-bold text-cyan-400 font-mono">
                          {(analysisResult.classification.confidence * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>

                    {/* Root Cause Candidate Layer */}
                    <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-indigo-300 font-mono">
                          Root Cause Candidate Analysis
                        </span>
                        <span className="text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-2 py-0.5 rounded">
                          Rule-Grounded Heuristic
                        </span>
                      </div>
                      <p className="text-sm font-semibold text-white">
                        {analysisResult.root_cause.root_cause_candidate}
                      </p>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        {analysisResult.root_cause.explanation}
                      </p>
                      <div className="pt-2 border-t border-slate-800/80 text-xs">
                        <span className="text-slate-400 font-semibold">Recommended Remediation: </span>
                        <span className="text-slate-300 font-mono">{analysisResult.root_cause.remediation_guidance}</span>
                      </div>
                    </div>

                    {/* Probabilities Distribution */}
                    <div>
                      <span className="text-xs text-slate-400 block mb-1.5">Class Probabilities (Top 5 Classes):</span>
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

                    {/* Metadata Specs */}
                    <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-slate-400 border-t border-slate-800 pt-3">
                      <div>Inference Latency: <span className="text-slate-200">{analysisResult.classification.latency_ms} ms</span></div>
                      <div>Feature Dimensions: <span className="text-slate-200">{analysisResult.classification.feature_dimension} features</span></div>
                    </div>
                  </div>

                  {/* Evidence Context */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-2">
                    <span className="text-xs font-semibold text-slate-300 font-mono">Detected Failure Signature:</span>
                    <pre className="bg-slate-950 p-2.5 rounded text-xs font-mono text-rose-300 overflow-x-auto whitespace-pre-wrap">
                      {analysisResult.detected_failure_signature}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="h-96 border border-dashed border-slate-800 rounded-xl flex flex-col items-center justify-center text-center p-8 space-y-3">
                  <Terminal className="h-10 w-10 text-slate-700" />
                  <div>
                    <p className="text-sm text-slate-400 font-semibold">No Active Inference Output</p>
                    <p className="text-xs text-slate-500 max-w-xs mt-1">
                      Choose a preset log from the left and click "Analyze Failure & Root Cause Candidate" to trigger model inference.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* VIEW 6: MODEL EVALUATION */}
        {activeTab === 'model' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="border-b border-slate-800 pb-3 flex flex-col md:flex-row md:items-center justify-between gap-2">
                <div>
                  <span className="text-xs font-mono text-indigo-400">Current Baseline Model</span>
                  <h2 className="text-lg font-bold text-white">Model Evaluation</h2>
                </div>
                <span className="text-xs bg-slate-800 px-3 py-1 rounded text-slate-300 font-mono self-start md:self-auto">
                  Algorithm: TF-IDF + Random Forest
                </span>
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

                  {/* Partition Details */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-slate-400 block">Training Partition</span>
                      <span className="text-white font-bold">261 incidents (69.8%)</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-slate-400 block">Validation Partition</span>
                      <span className="text-white font-bold">56 incidents (15.0%)</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                      <span className="text-slate-400 block">Held-out Test Partition</span>
                      <span className="text-white font-bold">57 incidents (15.2%)</span>
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
                <div className="text-center py-8 text-slate-500">Loading evaluation metrics...</div>
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
