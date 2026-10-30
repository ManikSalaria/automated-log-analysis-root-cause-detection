$ErrorActionPreference = 'Stop'

try {
    if (-not $env:BUILD_URL -or -not $env:JOB_NAME -or -not $env:BUILD_NUMBER) {
        throw 'Jenkins build metadata is incomplete.'
    }

    $consoleUrl = $env:BUILD_URL.TrimEnd('/') + '/consoleText'
    Write-Output "TRACE is capturing the complete current Jenkins console for $($env:JOB_NAME) #$($env:BUILD_NUMBER)."
    $consoleLog = (Invoke-WebRequest -Uri $consoleUrl -TimeoutSec 90 -UseBasicParsing).Content
    if ([string]::IsNullOrWhiteSpace($consoleLog)) {
        throw 'Jenkins returned an empty console log; refusing to replace the console with build metadata.'
    }
    $consoleByteCount = [System.Text.Encoding]::UTF8.GetByteCount($consoleLog)
    if ($consoleByteCount -gt 20MB) {
        throw "Jenkins console log is $consoleByteCount bytes, above TRACE's 20 MB ingestion limit. No content was truncated."
    }

    $branch = $env:BRANCH_NAME
    if ([string]::IsNullOrWhiteSpace($branch)) {
        $branch = $env:GIT_BRANCH
    }

    $payload = @{
        job_name = $env:JOB_NAME
        build_number = $env:BUILD_NUMBER
        build_status = $env:TRACE_BUILD_RESULT
        build_url = $env:BUILD_URL
        repo_url = $env:GIT_URL
        git_commit = $env:GIT_COMMIT
        git_branch = $branch
        console_log = $consoleLog
    } | ConvertTo-Json -Depth 5 -Compress
    $target = if ($env:TRACE_INGEST_URL) { $env:TRACE_INGEST_URL } else { 'http://127.0.0.1:8000/api/v1/ingest/jenkins' }
    $response = Invoke-RestMethod -Uri $target -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 240
    # Keep the captured log identical to the content posted. Any success output
    # after the consoleText fetch would otherwise be present only in Jenkins.
    exit 0
} catch {
    Write-Warning "Could not send this build log to TRACE: $($_.Exception.Message)"
    exit 1
}
