<#  run.ps1
    Usage examples:
      powershell -ExecutionPolicy Bypass -File .\run.ps1
      .\run.ps1 -App "tools\app.py" -Port 8502 -VenvDir ".venv-prod"
      .\run.ps1 -Port 8502 -- --server.headless true
#>

param(
  [string]$App     = $(if ($env:APP)      { $env:APP }      else { "ui.py" }),
  [string]$VenvDir = $(if ($env:VENV_DIR) { $env:VENV_DIR } else { ".venv" }),
  [int]   $Port    = $(if ($env:PORT)     { [int]$env:PORT } else { 8501 }),

  # Anything after `--` is passed to Streamlit:
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ExtraArgs
)

$ErrorActionPreference = 'Stop'

function Fail($msg) { Write-Error $msg; exit 1 }

# Return a hashtable with Exe + Args so "py -3" works correctly
function Resolve-Python {
  if ($env:PYTHON) {
    $cand = $env:PYTHON
    if (Get-Command $cand -ErrorAction SilentlyContinue) { return @{ Exe = $cand; Args = @() } }
    Write-Warning "PYTHON='$cand' not found on PATH, ignoring."
  }
  if (Get-Command py -ErrorAction SilentlyContinue)       { return @{ Exe = "py";      Args = @("-3") } } # Windows launcher
  if (Get-Command python3 -ErrorAction SilentlyContinue)  { return @{ Exe = "python3"; Args = @() } }
  if (Get-Command python -ErrorAction SilentlyContinue)   { return @{ Exe = "python";  Args = @() } }
  Fail "Python not found. Please install Python 3.9+."
}

# --- Checks ---
if (-not (Test-Path $App)) { Fail "App file '$App' not found. Place it at .\$App or pass -App." }

# --- Create venv if missing ---
$pyInfo = Resolve-Python
$pyExe  = $pyInfo.Exe
$pyArgs = $pyInfo.Args

if (-not (Test-Path $VenvDir)) {
  Write-Host "Creating virtualenv at '$VenvDir'"
  & $pyExe @pyArgs -m venv $VenvDir
} else {
  Write-Host "Reusing virtualenv '$VenvDir'"
}

# Use venv tools directly (no activate needed)
$PyInVenv        = Join-Path $VenvDir "Scripts\python.exe"
$StreamlitInVenv = Join-Path $VenvDir "Scripts\streamlit.exe"
if (-not (Test-Path $PyInVenv)) { Fail "Virtualenv looks broken. Missing $PyInVenv" }

# --- Install deps ---
Write-Host "Upgrading pip/wheel/setuptools..."
& $PyInVenv -m pip install --upgrade pip wheel setuptools | Out-Null

if (Test-Path "requirements.txt") {
  Write-Host "Installing dependencies from requirements.txt"
  & $PyInVenv -m pip install -r requirements.txt
} else {
  Write-Warning "requirements.txt not found. Installing Streamlit only."
  & $PyInVenv -m pip install streamlit
}

if (-not (Test-Path $StreamlitInVenv)) { Fail "Streamlit not found after install. Check requirements or network." }

# --- Launch ---
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"
Write-Host "Starting Streamlit ($App) at http://localhost:$Port"
& $StreamlitInVenv run $App --server.port $Port @ExtraArgs
