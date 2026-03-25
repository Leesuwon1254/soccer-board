# ⚽ 가상 연예인 축구단 포메이션 보드 구현 지시서

---

## 📋 작업 개요

연예인 100명 회원 DB(`celebrity_soccer.db`)를 기반으로  
**4-4-2 포메이션 전술 보드 웹 페이지**를 구현해줘.

---

## 🎨 디자인 스펙

### 경기장 스타일
- 밝고 선명한 초록 잔디 (`#3a9e4f` ~ `#2e8b40` 그라디언트)
- 반복 줄무늬 (repeating-linear-gradient, 90deg, 55px 간격)
- 흰색 반투명 경기장 라인 (`rgba(255,255,255,0.55)`)
- SVG로 경기장 라인 렌더링:
  - 외곽선, 하프라인, 센터 서클, 페널티 박스(양쪽), 골 박스(양쪽), 코너 아크(4개), 페널티 스팟

### 선수 카드 스타일
- 흰 배경, 둥근 모서리(8px), 그림자, 흰 테두리
- **GK만 파란 배경** (`#2563eb`)
- 카드 내부: 이름(굵게, 11.5px) + 포지션 레이블(회색, 10px)
- 호버 시 그림자 강조

### 상단 UI
- 좌측: 제목 `보드(한 팀) · 2번 FORM:4-4-2`, 서브타이틀 `선수 칩을 드래그하여 포지션을 변경할 수 있습니다.`
- 우측: `경기기록` / `초기배치 재설정` 버튼 (흰 배경, 회색 테두리)

---

## 👥 선수 배치 규칙

### 핵심 제약
> **모든 선수는 하프라인(필드 가로 50%)을 넘지 않는 왼쪽 절반에만 배치**

### 4-4-2 포지션 레이아웃 (left% / top%)

| 포지션 | 선수 수 | left 범위 | 배치 방식 |
|--------|---------|-----------|-----------|
| GK     | 1명     | ~7%       | 세로 중앙(50%) |
| DF     | 4명     | ~21%      | 세로 4등분 (18/38/62/82%) |
| MF     | 4명     | ~35%      | 세로 4등분 (22/42/60/78%) |
| FW     | 2명     | ~47%      | 세로 2등분 (30/70%) |

### DB에서 선수 선발 로직
```python
# celebrity_soccer.db의 members 테이블에서 선발
# 포지션1 또는 포지션2가 해당 포지션인 멤버 우선
# 기량 A > B > C 순으로 우선 선발
# 동점 시 랜덤

SELECT * FROM members
WHERE position1 = ? OR position2 = ?
ORDER BY CASE skill WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 3 END
LIMIT ?
```

---

## 🖱️ 인터랙션

### 드래그 기능
```javascript
// 마우스 & 터치 모두 지원
// 제약: x 좌표 4% ~ 49% (하프라인 넘기 금지)
// 제약: y 좌표 5% ~ 95%
x = Math.max(4, Math.min(49, x));
y = Math.max(5, Math.min(95, y));
```

### 초기배치 재설정 버튼
- 클릭 시 모든 선수 카드를 초기 좌표로 복귀

---

## 🗂️ 파일 구조

```
project/
├── celebrity_soccer.db      ← 기존 DB (입력)
├── app.py                   ← Flask 서버
├── templates/
│   └── board.html           ← 메인 페이지
└── static/
    └── style.css            ← 선택적 분리
```

---

## 🛠️ 기술 스택

- **백엔드**: Python Flask
- **DB**: SQLite3 (`celebrity_soccer.db`)
- **프론트엔드**: HTML + CSS + Vanilla JS (라이브러리 없이)
- **폰트**: Google Fonts — `Noto Sans KR`

---

## 🔌 Flask API 엔드포인트

```python
# GET /  → board.html 렌더링
# GET /api/lineup?formation=4-4-2  → 11명 선수 JSON 반환
# POST /api/reset  → 초기배치 재설정 트리거
```

### `/api/lineup` 응답 예시
```json
{
  "formation": "4-4-2",
  "players": [
    {"name": "강호동", "position": "GK", "skill": "B", "left": 7, "top": 50},
    {"name": "이낙훈", "position": "DF", "skill": "C", "left": 21, "top": 18},
    ...
  ]
}
```

---

## 📤 최종 산출물

1. `app.py` — Flask 앱 (DB 연결 + API)
2. `templates/board.html` — 전술 보드 UI
3. 실행 방법 안내 (`python app.py` → `http://localhost:5000`)

---

## ⚠️ 주의사항

- `celebrity_soccer.db`는 스크립트와 **같은 폴더**에 있다고 가정
- DB에 선수가 부족한 포지션은 **랜덤 선발**로 채워줘
- 선수 이름이 길 경우 카드 너비 자동 조정 (`white-space: nowrap` 유지)
- 모바일 터치 드래그도 반드시 지원할 것

---

## 🏷️ 버전 관리 규칙 (Semantic Versioning)

버전 형식: `vMAJOR.MINOR.PATCH` (예: `v3.2.0`)

| 버전 구분 | 올리는 조건 | 예시 |
|-----------|------------|------|
| **patch** (`v3.2.x`) | 오타 수정, 문구 변경, 색상 변경 등 아주 작은 수정 | v3.2.0 → v3.2.1 |
| **minor** (`v3.x.0`) | 기능 추가, UI 개선, 새로운 탭/모달 추가 등 중간 업데이트 | v3.2.0 → v3.3.0 |
| **major** (`vX.0.0`) | 전체 개편, 구조 변경, 파일명 변경 등 큰 변화 | v3.2.0 → v4.0.0 |

### 버전 올릴 때 수정해야 하는 파일

1. **`soccer_board_v3.html`** 하단 `#app-version` div 텍스트
2. **`config.json`** → `"version"` 및 `"updated"` 필드
3. **`service-worker.js`** → `CACHE_NAME` 값 (`soccer-board-vX.X.X`)

### 커밋 메시지 규칙

```
vX.X.X: 변경 내용 한 줄 요약
```

예시:
- `v3.2.1: 보드 안내 문구 오타 수정`
- `v3.3.0: 출석 탭 통계 차트 추가`
- `v4.0.0: 전체 UI 개편 및 다중 팀 지원`

### GitHub 릴리스 태그

- 버전 올릴 때마다 `git tag vX.X.X` 후 `git push origin vX.X.X`
- major / minor 업데이트는 GitHub Releases에 릴리스 노트 작성 권장
