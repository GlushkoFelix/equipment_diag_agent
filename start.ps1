# 设备故障诊断智能体一键启动（AC-SY-04）
# 用法：
#   .\start.ps1                  # 后端 8000，前端 5173
#   .\start.ps1 -Port 8010 -FrontendPort 5174
#   .\start.ps1 -SkipFrontend    # 仅启动后端
param(
    [int]$Port = 8000,
    [int]$FrontendPort = 5173,
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-PortInUse([int]$TargetPort) {
    try {
        $listener = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction Stop
        return $null -ne $listener
    } catch {
        return $false
    }
}

if (Test-PortInUse $Port) {
    Write-Host "[错误] 端口 $Port 已被占用。" -ForegroundColor Red
    Write-Host "请更换端口后重试，例如： .\start.ps1 -Port 8010 -FrontendPort 5174" -ForegroundColor Yellow
    exit 1
}

if (-not $SkipFrontend -and (Test-PortInUse $FrontendPort)) {
    Write-Host "[错误] 前端端口 $FrontendPort 已被占用。" -ForegroundColor Red
    Write-Host "请更换端口后重试，例如： .\start.ps1 -Port 8010 -FrontendPort 5174" -ForegroundColor Yellow
    exit 1
}

$Python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    $Python = 'python'
}

Write-Host "启动后端：http://127.0.0.1:$Port" -ForegroundColor Green
$backend = Start-Process -FilePath $Python `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port") `
    -WorkingDirectory (Join-Path $Root 'backend') `
    -PassThru -NoNewWindow

try {
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/health" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            # 服务尚未就绪，继续等待
        }
    }
    if (-not $ready) {
        Write-Host "[警告] 后端健康检查未在 30s 内通过，请查看上方日志。" -ForegroundColor Yellow
    }

    if (-not $SkipFrontend) {
        $Frontend = Join-Path $Root 'frontend'
        if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
            Write-Host "[提示] 未安装前端依赖，跳过前端；如需启动请先执行 npm install。" -ForegroundColor Yellow
        } else {
            Write-Host "启动前端：http://127.0.0.1:$FrontendPort" -ForegroundColor Green
            Push-Location $Frontend
            try {
                & npm run dev -- --port "$FrontendPort" --host 127.0.0.1
            } finally {
                Pop-Location
            }
        }
    } else {
        Wait-Process -Id $backend.Id
    }
} finally {
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}
