# OCR Translator - Sync to GitHub (PowerShell version)
Write-Host "===============================================" -ForegroundColor Green
Write-Host "        OCR Translator - Sync to GitHub" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""

Write-Host "Step 0: Changing to repository directory..." -ForegroundColor Cyan
try {
    Set-Location "D:\GitHub\OCR_Translator_GitHub_v3"
    Write-Host "Current directory: $(Get-Location)" -ForegroundColor Yellow
} catch {
    Write-Host "Failed to change to repository directory" -ForegroundColor Red
    exit 1
}
Write-Host ""

Write-Host "Step 1: Fetching latest from remote..." -ForegroundColor Cyan
$fetchResult = git fetch 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to fetch from remote" -ForegroundColor Red
    Write-Host $fetchResult -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 2: Checking repository status..." -ForegroundColor Cyan
git status

Write-Host ""
Write-Host "Step 3: Checking for unpushed commits..." -ForegroundColor Cyan
$unpushedCommits = git log --oneline origin/main..HEAD
if ($unpushedCommits) {
    Write-Host $unpushedCommits -ForegroundColor Yellow
} else {
    Write-Host "No unpushed commits" -ForegroundColor Green
}

Write-Host ""
Write-Host "Step 4: Checking for local changes..." -ForegroundColor Cyan

# Check for uncommitted changes
git diff --quiet
$uncommittedChanges = $LASTEXITCODE -ne 0

# Check for staged changes
git diff --cached --quiet
$stagedChanges = $LASTEXITCODE -ne 0

# Check for untracked files
$untrackedFiles = (git ls-files --others --exclude-standard) -ne $null

# Count unpushed commits
$unpushedCount = (git rev-list --count origin/main..HEAD)

Write-Host ""
Write-Host "Repository Analysis:" -ForegroundColor Magenta
if ($unpushedCount -gt 0) {
    Write-Host "  - $unpushedCount unpushed commit(s) found" -ForegroundColor Yellow
} else {
    Write-Host "  - No unpushed commits" -ForegroundColor Green
}

if ($uncommittedChanges) {
    Write-Host "  - Uncommitted changes detected" -ForegroundColor Yellow
} else {
    Write-Host "  - No uncommitted changes" -ForegroundColor Green
}

if ($stagedChanges) {
    Write-Host "  - Staged changes detected" -ForegroundColor Yellow
} else {
    Write-Host "  - No staged changes" -ForegroundColor Green
}

if ($untrackedFiles) {
    Write-Host "  - Untracked files detected" -ForegroundColor Yellow
} else {
    Write-Host "  - No untracked files" -ForegroundColor Green
}

Write-Host ""
Write-Host "Step 5: Processing changes..." -ForegroundColor Cyan

# Handle uncommitted/untracked changes first
if ($uncommittedChanges -or $untrackedFiles) {
    Write-Host "Adding changes..." -ForegroundColor Yellow
    git add .
}

# Check if we need to commit
git diff --cached --quiet
$needsCommit = $LASTEXITCODE -ne 0

if ($needsCommit) {
    Write-Host ""
    Write-Host "Committing new changes..." -ForegroundColor Yellow
    $commitMessage = Read-Host "Enter commit message for new changes"
    $commitResult = git commit -m "$commitMessage" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Commit failed" -ForegroundColor Red
        Write-Host $commitResult -ForegroundColor Red
        exit 1
    }
    $newCommit = $true
} else {
    $newCommit = $false
}

Write-Host ""
Write-Host "Step 6: Pushing to GitHub..." -ForegroundColor Cyan

# Always attempt to push (covers both new commits and existing unpushed commits)
$pushResult = git push origin main 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Push failed. Checking for conflicts..." -ForegroundColor Yellow
    Write-Host "Attempting to pull with rebase..." -ForegroundColor Yellow
    $rebaseResult = git pull --rebase origin main 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Rebase failed. Manual intervention required." -ForegroundColor Red
        Write-Host $rebaseResult -ForegroundColor Red
        exit 1
    }
    Write-Host ""
    Write-Host "Retrying push after rebase..." -ForegroundColor Yellow  
    $pushResult2 = git push origin main 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Push still failed after rebase. Check for conflicts manually." -ForegroundColor Red
        Write-Host $pushResult2 -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Step 7: Final verification..." -ForegroundColor Cyan
git status
Write-Host ""
$remainingCommits = git log --oneline origin/main..HEAD 2>&1

Write-Host ""
if (-not $remainingCommits -or $remainingCommits -eq "") {
    Write-Host "===============================================" -ForegroundColor Green
    Write-Host "        Sync completed successfully!" -ForegroundColor Green
    Write-Host "        All changes pushed to GitHub." -ForegroundColor Green
    Write-Host "===============================================" -ForegroundColor Green
} else {
    Write-Host "===============================================" -ForegroundColor Yellow
    Write-Host "        Warning: Some commits may still be local" -ForegroundColor Yellow
    Write-Host "        Please check the output above" -ForegroundColor Yellow
    Write-Host "===============================================" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
