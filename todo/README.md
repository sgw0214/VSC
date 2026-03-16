# Todo GUI

`tkinter`로 만든 개인용 월간 할 일 보드입니다.

## 실행

```bash
python main.py
```

## 구성

- 매월 고정 할 일: 이번 달에 한 번 체크하는 반복 항목입니다.
- 수시 할 일: 필요할 때 추가하고 완료 체크 후 정리할 수 있습니다.
- 메모장: 자유 메모를 적고 자동 저장합니다.

## 자동 확인

- 매일 `08:00`에 윈도우 작업 스케줄러로 앱을 실행해 창을 앞으로 띄울 수 있습니다.
- 등록 스크립트:

```powershell
powershell -ExecutionPolicy Bypass -File .\register_daily_task.ps1
```

- 앱 안의 `8시 등록` 버튼으로도 등록할 수 있습니다.

## 데이터 파일

- 로컬 데이터는 같은 폴더의 `tasks.json`에 저장됩니다.
- `tasks.json`과 `__pycache__`는 Git에 포함하지 않습니다.
