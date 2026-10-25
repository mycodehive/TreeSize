# TreeSize Explorer

Windows 10/11 x64용 디스크 사용량 분석 프로그램입니다. 폴더별 용량을 크기순 트리와 공간 지도로 살펴보고, 큰 파일과 파일 유형별 점유율을 찾을 수 있습니다. 한국어 화면을 기본 제공합니다.

TreeSize의 공개 기능을 참고해 새로 작성한 독립 프로그램이며, JAM Software의 제품 또는 공식 배포판이 아닙니다. 상표·아이콘·원본 소스를 복제하지 않았습니다.

## 다운로드

**[최신 Windows 설치 파일과 휴대용 ZIP](https://github.com/mycodehive/TreeSize/releases/latest)**

- 설치: `TreeSizeExplorer-Setup-1.0.1.exe` 실행. Python을 별도로 설치할 필요가 없습니다.
- 휴대용: `TreeSizeExplorer-Portable-1.0.1-win-x64.zip` 전체를 압축 해제하고 폴더 안의 `TreeSizeExplorer.exe` 실행.
- 저장소가 비공개인 경우 GitHub 계정에 로그인해야 다운로드할 수 있습니다.
- 첫 소스 반영 후 **[Actions](https://github.com/mycodehive/TreeSize/actions)** 빌드가 성공해야 Releases에 설치 파일이 나타납니다.

## 주요 기능

| 기능 | 동작 |
| --- | --- |
| 폴더·드라이브 분석 | 드라이브, 사용자 폴더, 다운로드, 직접 입력한 로컬/UNC 폴더 |
| 용량 트리 | 파일 크기, 디스크 할당, 상위 폴더 대비 비율, 파일·폴더 수, 수정일 |
| 정렬·검색 | 열 제목 정렬, 파일·폴더 이름 필터, 상위 폴더 이동 |
| 공간 지도 | 선택 폴더의 하위 항목을 크기에 비례한 사각형으로 표시. 더블클릭 이동 |
| 큰 파일 찾기 | 전체 분석 결과에서 대용량 파일 TOP 100, 더블클릭으로 탐색기 위치 열기 |
| 파일 유형 통계 | 확장자별 크기·할당량·파일 수 |
| 오류 처리 | 접근 거부를 기록하고 계속 진행, 링크/연결 지점/클라우드 자리표시자 건너뛰기 |
| 백그라운드 실행 | 분석 중 화면 사용, 중지 후 현재까지의 부분 결과 확인 |
| 내보내기 | Excel용 UTF-8 BOM CSV, 깊은 트리를 지원하는 평면 JSON |
| GitHub 업데이트 | 시작 시 + 실행 중 4시간마다 새 안정 버전 확인, 배너·Windows 알림 |

우클릭 메뉴에서 탐색기 위치 열기, 경로 복사, 선택 폴더 재분석을 사용할 수 있습니다. 삭제·정리는 Windows 탐색기에서 수행합니다. 이 버전에는 중복 파일 검색, 예약 분석, MFT 직접 분석, 스냅샷 비교가 포함되지 않습니다.

## 업데이트 사용

기본 배포 주소는 **`mycodehive/TreeSize`**입니다. 설정에 `owner/repository` 또는 `https://github.com/owner/repository` 형식으로 다른 GitHub 배포 저장소를 지정할 수 있습니다.

1. 앱 실행 약 1.2초 후 백그라운드에서 확인하며, 실행 중에는 4시간 간격으로 확인합니다. 절전 복귀 시 지연된 타이머는 다시 처리됩니다. 종료 상태에서는 확인하지 않습니다.
2. 새 안정 버전이 있으면 상단 알림 배너와 Windows 알림을 표시합니다. 초안·시험 버전·동일/이전 버전은 업데이트하지 않습니다.
3. **다운로드 및 설치**를 선택하면 해당 릴리스의 설치 파일과 `SHA256SUMS.txt`를 받습니다.
4. SHA-256 검증 성공 후 다시 설치 여부를 묻습니다. 동의하면 앱을 종료하고 일반 설치 마법사를 실행합니다. 동의 없이 자동 교체하지 않습니다.
5. 설치형 업데이트는 기존 사용자 설정을 유지합니다. 휴대용 사용을 유지하려면 Releases에서 새 휴대용 ZIP을 받아 직접 교체합니다.

**비공개 저장소:** 설정의 GitHub 토큰에 해당 저장소만 선택한 fine-grained token을 입력하고 **Contents: Read-only** 권한을 부여하세요. 토큰은 Windows 자격 증명 관리자에 저장하며 JSON 설정이나 소스 코드에 쓰지 않습니다. 토큰 없이 자동 업데이트하려면 공개 배포 저장소를 별도로 사용하면 됩니다.

인터넷 연결 오류나 인증 실패는 상태 표시줄에 나타납니다. **업데이트 확인**을 누르면 상세 오류를 볼 수 있습니다. 프로그램 분석 기능은 인터넷 없이 사용할 수 있습니다.

## 정확도와 개인정보

- 파일 내용 대신 디렉터리 메타데이터만 읽습니다. 분석 결과와 경로를 외부 서버로 전송하지 않습니다. 네트워크 통신은 설정한 GitHub 저장소의 업데이트 조회와 다운로드에 사용합니다.
- 파일 크기는 논리 크기입니다. 디스크 할당은 Windows `GetCompressedFileSizeW`로 구하며 디렉터리 자체 메타데이터는 제외합니다. 조회 실패 시 논리 크기로 대체하고 접근 오류를 표시합니다.
- 하드 링크는 각 경로에서 계산하므로 드라이브 실제 사용량과 합계가 다를 수 있습니다. 파일시스템 메타데이터, 휴지통 접근 권한, 압축·희소 파일, 분석 중 변경도 차이를 만들 수 있습니다.
- 링크·재분석 지점·온라인 전용 파일은 건너뜁니다. 접근이 제한된 시스템 폴더는 오류 목록에 표시합니다. 오류 상세는 1,000건으로 제한합니다.
- 전체 폴더 트리는 메모리에 보관합니다. 수백만 항목의 디스크는 메모리를 많이 사용할 수 있습니다. NTFS MFT를 직접 읽는 상용 도구와 처리 속도가 같다고 보장하지 않습니다.
- CSV/JSON에는 로컬 경로가 포함됩니다. CSV의 수식으로 해석될 수 있는 텍스트는 안전하게 이스케이프합니다.

## 개발 실행

Python 3.11 이상. Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
python -m treesize
```

폴더 인자도 지원합니다: `python -m treesize "C:\Users"`. Linux의 테스트 실행에는 `QT_QPA_PLATFORM=offscreen`을 사용할 수 있으며, Windows 설치와 자격 증명 저장은 Windows 전용입니다.

```powershell
python -m unittest discover -s tests -v
$env:QT_QPA_PLATFORM = "offscreen"
python scripts/smoke_gui.py
```

## 빌드와 배포

`main` 반영 시 GitHub Actions가 Windows 테스트 → GUI 검사 → PyInstaller → Inno Setup → 릴리스 게시를 수행합니다. 새 버전은 `src/treesize/__init__.py`의 `VERSION`을 올려 배포합니다. 기존 버전의 릴리스 파일은 덮어쓰지 않습니다.

자세한 빌드·배포 절차와 비공개 저장소 설정은 **[배포 가이드](docs/RELEASING.md)**를 확인하세요. 설치 파일은 코드 서명되지 않았으며 Windows가 게시자 확인 알림을 표시할 수 있습니다.

| 파일 | 역할 |
| --- | --- |
| `scanner.py` | 취소 가능한 반복형 탐색·집계 |
| `models.py`, `treemap.py` | Qt 트리 모델·용량 시각화 |
| `app.py` | 한국어 화면·작업 스레드·업데이트 타이머 |
| `updater.py`, `settings.py` | GitHub Releases 조회·검증·OS 자격 증명 |
| `reports.py` | 원자적 CSV/JSON 내보내기 |
| `.github/workflows/windows.yml` | Windows 빌드 및 버전별 릴리스 |

공개 참고 문서: [TreeSize 기능 소개](https://www.jam-software.com/treesize), [Qt 모델/뷰](https://doc.qt.io/qtforpython-6.8/PySide6/QtCore/QAbstractItemModel.html), [GitHub Releases API](https://docs.github.com/en/rest/releases/releases), [릴리스 자산 API](https://docs.github.com/en/rest/releases/assets).
