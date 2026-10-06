# 웹 의존성 설치 실패와 잠금파일 복원

확인일: 2026-10-06. 분류: 웹 빌드·배포 / 의존성 설치.
Kalshi·Alpaca API 접근 문제와 별개의 문제다.

## 증상과 발생 지점

Actions 실행 `37423791581`의 웹 작업에서 `npm --prefix apps/web ci`가 EUSAGE로 실패했다.
웹 타입 검사·빌드는 설치 실패 때문에 시작되지 않았다. API 품질 검사·테스트는 통과했다.

오류는 유효한 `package-lock.json` 또는 `npm-shrinkwrap.json`이 필요하다는 내용이었다.
원격 잠금파일 객체 `6ab531ec681945986087efca91aa92da70d25cfe`는 UTF-8 JSON으로 읽을 수
없었다. 최초 업로드 경위는 확인하지 못했으므로 누가 언제 손상시켰다고 단정하지 않는다.

## 처리

1. 기존 원격 파일을 Base64로 읽어 실제 바이트를 확인했다.
2. 로컬 잠금파일이 JSON이고 `lockfileVersion=3`인지 확인했다.
3. manifest와 함께 오프라인 `npm ci --dry-run`을 통과했다.
4. 해당 잠금파일을 정상 UTF-8 내용으로 업로드하고 웹 CI를 다시 실행한다.

```bash
npm --prefix apps/web ci --dry-run --ignore-scripts --offline --no-audit --no-fund
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

잠금 버전은 Next.js 16.3.6, Chakra UI 3.37.0, React 19.3.0이다. 기존 로컬 빌드에서 사용한
버전이며 새 기능 때문에 의존성 범위를 확장한 것은 아니다. 오프라인 dry-run은 파일
일관성을 확인하며 실제 다운로드 성공까지 입증하지 않는다. 다운로드·설치·빌드는
후속 GitHub Actions에서 별도로 확인한다.

## 재발 방지

`npm ci`를 설치·CI·컨테이너 경로에 유지한다. 오류를 감추기 위해 `npm install`로 바꾸거나
잠금파일을 제거하지 않는다. GitHub 객체 업로드 시 텍스트는 `encoding=utf-8`을 사용하고,
Base64 인코딩을 선택하면 실제 Base64 문자열을 전달한다.
