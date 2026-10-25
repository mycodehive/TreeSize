[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if ($PSVersionTable.PSEdition -ne 'Desktop' -and -not $IsWindows) {
        throw 'The executable must be built on Windows.'
    }
    if (-not $SkipInstall) {
        python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
        python -m pip install -r requirements-dev.txt
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
        python -m pip install --no-deps -e .
        if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    }
    $version = python -c "import ast,pathlib; t=ast.parse(pathlib.Path('src/treesize/__init__.py').read_text(encoding='utf-8')); print(next(ast.literal_eval(n.value) for n in t.body if isinstance(n, ast.Assign) and any(isinstance(x,ast.Name) and x.id=='VERSION' for x in n.targets)))"
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
        throw 'VERSION must be a stable numeric version such as 1.0.0.'
    }
    python scripts/make_icon.py build/app.ico
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
    python -m PyInstaller --noconfirm --clean --onedir --windowed --name TreeSizeExplorer --paths src --icon build/app.ico --collect-submodules keyring.backends --add-data "build/app.ico;." packaging/launcher.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

    # Include Python-package licenses with the portable and installed distributions.
    $licenseScript = @'
import importlib.metadata as metadata
from pathlib import Path
import shutil
target = Path('dist/TreeSizeExplorer/third_party_licenses')
for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'keyring', 'pyinstaller'):
    distribution = metadata.distribution(package)
    for entry in distribution.files or ():
        if any('license' in part.lower() or 'copying' in part.lower() for part in entry.parts):
            origin = Path(distribution.locate_file(entry))
            if origin.is_file():
                destination = target / package / Path(*entry.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origin, destination)
'@
    python -c $licenseScript
    if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
    Copy-Item README.md dist/TreeSizeExplorer/README.md
    if (Test-Path THIRD_PARTY_NOTICES.md) {
        Copy-Item THIRD_PARTY_NOTICES.md dist/TreeSizeExplorer/THIRD_PARTY_NOTICES.md
    }
    if (Test-Path dist/release) {
        Remove-Item dist/release -Recurse -Force
    }
    New-Item -ItemType Directory -Force dist/release | Out-Null
    $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($compiler) {
        $iscc = $compiler.Source
    } else {
        $iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
    }
    if (-not (Test-Path $iscc)) {
        throw 'Install Inno Setup 6 or add ISCC.exe to PATH.'
    }
    & $iscc "/DAppVersion=$version" "/DProjectRoot=$projectRoot" packaging/windows.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    $portablePath = "dist/release/TreeSizeExplorer-Portable-$version-win-x64.zip"
    if (Test-Path $portablePath) { Remove-Item $portablePath }
    Compress-Archive -Path dist/TreeSizeExplorer -DestinationPath $portablePath -CompressionLevel Optimal
    $sums = @(
        Get-ChildItem dist/release -File | Where-Object { $_.Name -match "^(TreeSizeExplorer-Setup-$([regex]::Escape($version))\.exe|TreeSizeExplorer-Portable-$([regex]::Escape($version))-win-x64\.zip)$" } | Sort-Object Name | ForEach-Object {
            '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $_.Name
        }
    )
    if ($sums.Count -ne 2) { throw 'The installer and portable ZIP must both exist.' }
    [IO.File]::WriteAllText((Join-Path $projectRoot 'dist/release/SHA256SUMS.txt'), ($sums -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
    Write-Host "Built TreeSize Explorer $version in dist/release."
} finally {
    Pop-Location
}
