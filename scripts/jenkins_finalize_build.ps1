param(
    [Parameter(Mandatory = $true)][string]$BuildUrl,
    [Parameter(Mandatory = $true)][string]$JobName,
    [Parameter(Mandatory = $true)][string]$BuildNumber,
    [Parameter(Mandatory = $true)][string]$BuildResult,
    [string]$RepoUrl = '',
    [string]$CommitSha = '',
    [string]$GitBranch = ''
)

$ErrorActionPreference = 'Stop'

try {
    $baseUrl = $BuildUrl.TrimEnd('/')
    $apiUrl = "$baseUrl/api/json?tree=building"
    $deadline = [DateTime]::UtcNow.AddMinutes(10)
    do {
        $state = Invoke-RestMethod -Uri $apiUrl -TimeoutSec 30
        if (-not $state.building) { break }
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "Timed out waiting for source build $JobName #$BuildNumber to finish."
        }
        Start-Sleep -Seconds 3
    } while ($true)

    $consoleLog = (Invoke-WebRequest -Uri "$baseUrl/consoleText" -TimeoutSec 90 -UseBasicParsing).Content
    if ([string]::IsNullOrWhiteSpace($consoleLog)) {
        throw "Jenkins returned an empty completed console for $JobName #$BuildNumber."
    }
    $consoleByteCount = [System.Text.Encoding]::UTF8.GetByteCount($consoleLog)
    if ($consoleByteCount -gt 20MB) {
        throw "Completed Jenkins console is $consoleByteCount bytes, above TRACE's 20 MB ingestion limit; content was not truncated."
    }

    $payload = @{
        job_name = $JobName
        build_number = $BuildNumber
        build_status = $BuildResult
        build_url = $BuildUrl
        repo_url = $RepoUrl
        git_commit = $CommitSha
        git_branch = $GitBranch
        console_log = $consoleLog
    } | ConvertTo-Json -Depth 5 -Compress
    $target = if ($env:TRACE_INGEST_URL) { $env:TRACE_INGEST_URL } else { 'http://127.0.0.1:8000/api/v1/ingest/jenkins' }
    $response = Invoke-RestMethod -Uri $target -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 240
    Write-Output "TRACE captured completed Jenkins console for $JobName #$BuildNumber ($consoleByteCount UTF-8 bytes)."
    exit 0
} catch {
    Write-Warning "Could not capture completed Jenkins console for $JobName #$BuildNumber`: $($_.Exception.Message)"
    exit 1
}
