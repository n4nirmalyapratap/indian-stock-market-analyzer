<#
.SYNOPSIS
    Build, tag, and push the backend image with a rollback anchor.

.DESCRIPTION
    Pushing only ":latest" overwrites the single image tag, so a bad deploy
    leaves no known-good image to roll back to. This script tags every build
    with BOTH ":latest" (what Azure Container Apps auto-deploys) and
    ":<git-short-sha>" (a permanent, immutable rollback anchor retained in
    Docker Hub).

    Build context is artifacts/python-backend (matches docker-compose.yml).

.PARAMETER NoCache
    Pass --no-cache to docker build (full rebuild from current source on disk).

.EXAMPLE
    ./scripts/deploy-backend.ps1
    ./scripts/deploy-backend.ps1 -NoCache

.NOTES
    Rollback: re-tag a known-good sha as latest and push it, e.g.
        docker pull  n4nirmalyapratap/nifty-backend:<good-sha>
        docker tag   n4nirmalyapratap/nifty-backend:<good-sha> n4nirmalyapratap/nifty-backend:latest
        docker push  n4nirmalyapratap/nifty-backend:latest
#>
param(
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"

$Repo    = "n4nirmalyapratap/nifty-backend"
$Context = "artifacts/python-backend"

# Resolve to the repo root regardless of where the script is invoked from.
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# --no-cache rebuilds from whatever is on disk RIGHT NOW. If the working tree is
# dirty, you may bake untested changes into :latest. Warn loudly.
$dirty = git status --porcelain
if ($dirty) {
    Write-Warning "Working tree has uncommitted changes — these WILL be baked into the image:"
    git status --short
}

$Sha = (git rev-parse --short HEAD).Trim()
Write-Host "Building $Repo  (tags: latest, $Sha)" -ForegroundColor Cyan

$tagArgs = @("-t", "${Repo}:latest", "-t", "${Repo}:$Sha")
if ($NoCache) {
    docker build --no-cache @tagArgs $Context
} else {
    docker build @tagArgs $Context
}
if ($LASTEXITCODE -ne 0) { throw "docker build failed" }

docker push "${Repo}:latest"
if ($LASTEXITCODE -ne 0) { throw "docker push :latest failed" }
docker push "${Repo}:$Sha"
if ($LASTEXITCODE -ne 0) { throw "docker push :$Sha failed" }

Write-Host ""
Write-Host "Pushed ${Repo}:latest and ${Repo}:$Sha" -ForegroundColor Green
Write-Host "Azure Container Apps auto-deploys :latest. Rollback anchor: $Sha" -ForegroundColor Green
