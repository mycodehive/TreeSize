# Windows 빌드와 업데이트 배포

## 사용자가 설치하는 방법

1. 저장소의 **Releases**에서 `TreeSizeExplorer-Setup-1.0.2.exe`처럼 현재 버전의 설치 파일을 받습니다.
2. 설치 마법사를 실행합니다. 현재 Windows 사용자에게 설치하므로 일반적으로 관리자 권한이 필요하지 않습니다.
3. 프로그램의 설정에서 업데이트 저장소를 확인합니다. 기본값은 `mycodehive/TreeSize`입니다.

설치 버전은 `%LOCALAPPDATA%\Programs\TreeSizeExplorer`에 배치됩니다. 사용자 설정과 다운로드 캐시는 별도의 `%LOCALAPPDATA%\TreeSizeExplorer`에 저장되어 프로그램을 업데이트해도 유지됩니다.

`TreeSizeExplorer-Portable-<version>-win-x64.zip`은 압축을 푼 폴더에서 실행할 수 있습니다. 앱의 업데이트 다운로드 기능은 설치 마법사를 제공하므로, 계속 휴대용으로 사용하려면 새 휴대용 ZIP을 직접 받아 교체합니다. 파일 분석 결과와 사용자 파일은 GitHub로 전송하지 않습니다.

## 비공개 저장소의 업데이트

현재 기본 저장소가 비공개라면 로그인하지 않은 GitHub API 호출로 릴리스에 접근할 수 없습니다.

1. GitHub에서 fine-grained personal access token을 만듭니다.
2. Repository access에 `mycodehive/TreeSize`만 선택하고 **Contents: Read-only** 권한을 부여합니다.
3. 앱의 설정에 토큰을 입력합니다. 토큰은 Windows 자격 증명 저장소에 보관하며 일반 설정 파일이나 소스 코드에 넣지 않습니다.
4. **업데이트 확인**을 눌러 접근을 확인합니다. 토큰이 만료되거나 취소되면 설정에서 교체합니다.

토큰 없이 배포하려면 별도의 공개 배포 저장소에 동일한 파일명 규칙의 GitHub Release를 게시하고 앱 설정의 저장소 주소를 해당 `owner/repository`로 바꿉니다. 소스 저장소를 공개로 전환할 필요는 없습니다. 다른 공개 저장소로 자동 복사하는 작업은 이 워크플로에 포함되어 있지 않습니다.

## 로컬 Windows 빌드

필요 환경: Windows 10/11 x64, Python 3.11 이상, Inno Setup 6. 설치 후 PowerShell에서 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
python -m unittest discover -s tests -v
$env:QT_QPA_PLATFORM = "offscreen"
python scripts/smoke_gui.py
Remove-Item Env:QT_QPA_PLATFORM
.\scripts\build_windows.ps1 -SkipInstall
```

`dist/release`에 다음 세 파일이 생성됩니다.

| 파일 | 용도 |
| --- | --- |
| `TreeSizeExplorer-Setup-<version>.exe` | 설치 및 앱 내 업데이트 |
| `TreeSizeExplorer-Portable-<version>-win-x64.zip` | 설치 없이 실행 |
| `SHA256SUMS.txt` | 다운로드 무결성 검증 |

빌드 시 생성하는 아이콘은 프로젝트 자체 도형입니다. PyInstaller는 한 폴더 배포 방식으로 Qt 라이브러리를 분리하며, 배포 폴더의 `third_party_licenses`에 패키지 라이선스 파일도 수집합니다.

## GitHub Actions 자동 릴리스

`main`에 푸시하면 Windows 테스트, GUI 스모크 테스트, EXE 및 ZIP 빌드가 실행됩니다. 패키징한 EXE도 `--self-test`로 직접 실행해 화면·분석·정렬·Windows 자격 증명 모듈을 검사합니다. GitHub Actions에서는 설치 파일의 무인 설치·재설치와 설치된 앱의 자체 검사까지 수행합니다. 테스트가 실패하면 릴리스를 게시하지 않습니다. 각 빌드 결과는 Actions의 아티팩트로도 30일간 제공됩니다.

`src/treesize/__init__.py`의 `VERSION = "1.0.2"` 값을 읽어 `v1.0.2` 태그가 없을 때 해당 커밋의 새 릴리스를 자동으로 게시합니다. 기존 태그가 있으면 해당 버전의 자산을 덮어쓰지 않습니다. 다음 버전을 배포하려면 기능 수정과 함께 `VERSION`을 `1.0.2`처럼 올려 `main`에 푸시합니다. 수동 **Run workflow**도 지원하지만 릴리스 게시는 `main`에서만 실행합니다.

Actions에는 저장소의 `contents: write` 권한이 필요합니다. 워크플로의 기본 `GITHUB_TOKEN`을 사용하므로 별도 배포용 토큰은 필요하지 않습니다. 저장소 또는 조직 정책으로 Actions가 비활성화되어 있으면 먼저 허용해야 합니다.

설치 파일은 현재 코드 서명 인증서로 서명하지 않습니다. Windows SmartScreen이 게시자를 확인하지 못할 수 있습니다. SHA-256 검증은 파일 손상 여부를 확인하며 게시자 신원 인증을 대신하지 않습니다. 정식 외부 배포 시에는 Windows 코드 서명 인증서와 타임스탬프를 빌드 과정에 추가하는 것을 권장합니다.

## 릴리스 후 확인

- 새 Windows 환경에서 설치·실행·폴더 분석·종료를 확인합니다.
- 구버전 설정의 업데이트 저장소에서 새 버전 알림과 설치 파일 다운로드가 동작하는지 확인합니다.
- 실행 직후 업데이트 확인과 실행 중 4시간 간격 확인이 활성화되어 있는지 확인합니다.
- 새 설치 파일로 업그레이드한 뒤 버전과 사용자 설정 유지 여부를 확인합니다.

Linux에서 수행한 소스 테스트나 GUI 스모크 테스트만으로 실제 Windows 설치·교체 동작까지 검증했다고 볼 수 없습니다. 실제 Windows 검증 결과와 CI 결과를 따로 기록합니다.
