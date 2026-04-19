# Todo GUI

`PySide6`로 만든 개인용 할 일 보드입니다.

## 실행

```bash
python main.py
```

## EXE 빌드

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

- 빌드 결과물: `dist\ToDoList.exe`
- EXE 실행 시 데이터는 `%LOCALAPPDATA%\ToDoList\tasks.json`에 저장됩니다.

## 구성

- 고정 할 일 / 수시 할 일 / 메모장을 세로 분할로 나눠서 봅니다.
- 분할선은 드래그해서 높이를 자유롭게 조절할 수 있습니다.
- 메모장은 자동 저장됩니다.
- 일정은 우클릭으로 삭제할 수 있습니다.

## 자동 확인

- 앱 상단에서 원하는 시간을 선택한 뒤 윈도우 작업 스케줄러에 등록할 수 있습니다.
- 등록 스크립트:

```powershell
powershell -ExecutionPolicy Bypass -File .\register_daily_task.ps1
```

- 앱 안의 `등록` 버튼으로도 바로 등록할 수 있습니다.

## 데이터 파일

- `python main.py`로 실행하면 같은 폴더의 `tasks.json`에 저장됩니다.
- `ToDoList.exe`로 실행하면 `%LOCALAPPDATA%\ToDoList\tasks.json`에 저장됩니다.
- `tasks.json`과 `__pycache__`는 Git에 포함하지 않습니다.
