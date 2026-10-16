param(
    [string]$CacheDirectory = "",
    [switch]$SkipSelfTest
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($env:OS -ne "Windows_NT" -or -not [Environment]::Is64BitOperatingSystem) {
    throw "Windows 10/11 x64 is required."
}
$Root = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($CacheDirectory)) { $CacheDirectory = Join-Path $Root ".cache" }
$CacheDirectory = [IO.Path]::GetFullPath($CacheDirectory)
[IO.Directory]::CreateDirectory($CacheDirectory) | Out-Null
$Lock = Get-Content -LiteralPath (Join-Path $Root "dependencies.lock.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$PythonSpec = @($Lock.dependencies | Where-Object { $_.id -eq "python" })[0]
$PythonRoot = Join-Path $Root "runtime\python"
$PythonExe = Join-Path $PythonRoot "python.exe"
$Marker = Join-Path $PythonRoot ".dependency.json"
function Invoke-LocalPython {
    param([string[]]$PythonArguments)
    $Quoted = foreach ($Argument in $PythonArguments) {
        if ($Argument.Contains('"')) { throw "Unexpected quote in Python argument." }
        '"' + ($Argument -replace '(\\+)$', '$1$1') + '"'
    }
    $Process = Start-Process -FilePath $PythonExe -ArgumentList ($Quoted -join ' ') -WorkingDirectory $Root -NoNewWindow -Wait -PassThru
    if ($Process.ExitCode -ne 0) { throw "Python command failed with exit code $($Process.ExitCode)." }
}
if (-not (Test-Path -LiteralPath $PythonRoot)) {
    $Archive = Join-Path $CacheDirectory $PythonSpec.archive_name
    if (-not (Test-Path -LiteralPath $Archive)) {
        $Part = $Archive + ".part-" + [Guid]::NewGuid().ToString("N")
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $PythonSpec.url -OutFile $Part -UseBasicParsing
            $Digest = (Get-FileHash -LiteralPath $Part -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($Digest -ne $PythonSpec.sha256) { throw "Python archive SHA-256 mismatch; no installation performed." }
            Move-Item -LiteralPath $Part -Destination $Archive
        } finally {
            if (Test-Path -LiteralPath $Part) { Remove-Item -LiteralPath $Part }
        }
    }
    $Digest = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Digest -ne $PythonSpec.sha256) { throw "Cached Python archive SHA-256 mismatch; cache preserved." }
    $Runtime = Join-Path $Root "runtime"
    [IO.Directory]::CreateDirectory($Runtime) | Out-Null
    $Stage = Join-Path $Runtime (".python-stage-" + [Guid]::NewGuid().ToString("N"))
    try {
        Expand-Archive -LiteralPath $Archive -DestinationPath $Stage
        $Pth = @(Get-ChildItem -LiteralPath $Stage -Filter "python*._pth")
        if ($Pth.Count -ne 1) { throw "Unexpected embedded Python layout." }
        Add-Content -LiteralPath $Pth[0].FullName -Encoding ASCII -Value @("../../tools", "../../tools/windows_mgba")
        $EntryHash = (Get-FileHash -LiteralPath (Join-Path $Stage "python.exe") -Algorithm SHA256).Hash.ToLowerInvariant()
        $Record = @{ id="python"; version=$PythonSpec.version; archive_sha256=$Digest; entrypoints=@{"python.exe"=$EntryHash} }
        $Json = $Record | ConvertTo-Json -Depth 6
        [IO.File]::WriteAllText((Join-Path $Stage ".dependency.json"), $Json, (New-Object Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $Stage -Destination $PythonRoot
    } finally {
        if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse }
    }
} else {
    if (-not (Test-Path -LiteralPath $Marker)) { throw "Existing runtime/python has no install marker; refusing to overwrite it." }
    $Record = Get-Content -LiteralPath $Marker -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Record.archive_sha256 -ne $PythonSpec.sha256) { throw "Existing Python belongs to another locked version." }
    $Digest = (Get-FileHash -LiteralPath $PythonExe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Digest -ne $Record.entrypoints.'python.exe') { throw "Existing Python executable changed; refusing to run it." }
}
Push-Location $Root
try {
    Invoke-LocalPython -PythonArguments @('-X', 'utf8', 'tools/bootstrap_environment.py', '--cache-dir', $CacheDirectory)
    $ReportRoot = Join-Path $Root "reports"
    [IO.Directory]::CreateDirectory($ReportRoot) | Out-Null
    $Run = [Guid]::NewGuid().ToString("N")
    Invoke-LocalPython -PythonArguments @('-X', 'utf8', 'tools/check_environment.py', '--report', (Join-Path $ReportRoot ("environment_" + $Run + ".json")))
    if (-not $SkipSelfTest) {
        Invoke-LocalPython -PythonArguments @('-X', 'utf8', 'tools/self_test.py', '--report', (Join-Path $ReportRoot ("self_test_" + $Run + ".json")))
    }
    Write-Host "Core environment ready. Custom headless backend is optional and checked separately."
} finally {
    Pop-Location
}
