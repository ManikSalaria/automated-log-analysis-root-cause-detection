$ErrorActionPreference = 'Stop'

try {
    if (-not $env:BUILD_URL -or -not $env:JOB_NAME -or -not $env:BUILD_NUMBER) {
        throw 'Jenkins build metadata is incomplete.'
    }

    $consoleUrl = $env:BUILD_URL.TrimEnd('/') + '/consoleText'
    $consoleLog = (Invoke-WebRequest -Uri $consoleUrl -TimeoutSec 20 -UseBasicParsing).Content
    if ([string]::IsNullOrWhiteSpace($consoleLog)) {
        $consoleLog = "Jenkins job $($env:JOB_NAME) build $($env:BUILD_NUMBER) completed with status $($env:TRACE_BUILD_RESULT)."
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
    $response = Invoke-RestMethod -Uri $target -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 60
    Write-Host "TRACE accepted $($env:JOB_NAME) #$($env:BUILD_NUMBER): file $($response.file_id), $($response.incidents_detected) incident(s)."
    exit 0
} catch {
    Write-Warning "Could not send this build log to TRACE: $($_.Exception.Message)"
    exit 1
}
