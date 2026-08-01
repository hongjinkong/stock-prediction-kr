"""로컬 운용 서버 — 사이트를 띄우고, 브라우저의 '지금 갱신' 버튼으로 데이터를 다시 만든다.

    python scripts/serve.py                 # http://127.0.0.1:8000
    python scripts/serve.py --port 9000
    python scripts/serve.py --holdings holdings.json   # 실제 보유를 반영

추가 의존성 없음(표준 라이브러리 http.server). **127.0.0.1 에만 바인딩**하므로
같은 네트워크의 다른 기기에서는 접근할 수 없다 — 이 서버는 데이터 파이프라인을
실행시킬 수 있으므로 외부에 열지 말 것.

갱신은 시세 재수집 + 백테스트 약 60회(위상 21 + 파라미터 격자 36)를 전부 다시 돌린다.
수 분 걸리므로 백그라운드 스레드에서 실행하고, 브라우저는 /api/status 를 폴링한다.
"""
import argparse
import errno
import json
import os
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_site import build

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')


class Job:
    """갱신 작업 하나. 동시에 두 번 돌지 않도록 잠근다."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.pct = 0
        self.message = '대기 중'
        self.error = None
        self.finished_at = None
        self.info = None
        self.opts = {}

    def snapshot(self):
        return {
            'running': self.running, 'pct': round(self.pct, 1), 'message': self.message,
            'error': self.error, 'finished_at': self.finished_at, 'info': self.info,
        }

    def start(self):
        with self.lock:
            if self.running:
                return False
            self.running = True
            self.pct = 0
            self.message = '시작하는 중'
            self.error = None
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        t0 = time.time()
        try:
            def progress(pct, msg):
                self.pct = pct
                self.message = msg
                print(f'  [{pct:3.0f}%] {msg}', file=sys.stderr)

            _, info = build(use_cache=False, quick=self.opts.get('quick', False),
                            holdings_path=self.opts.get('holdings'), progress=progress)
            self.info = info
            self.message = f'완료 — 기준일 {info["as_of"]} ({time.time() - t0:.0f}초)'
            self.pct = 100
        except Exception as e:
            self.error = f'{type(e).__name__}: {e}'
            self.message = '실패'
            print(f'  [갱신 실패] {self.error}', file=sys.stderr)
        finally:
            self.running = False
            self.finished_at = time.time()


JOB = Job()


class Handler(SimpleHTTPRequestHandler):
    """site/ 를 서빙하면서 /api/* 만 가로챈다."""

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split('?')[0] == '/api/status':
            return self._json(JOB.snapshot())
        return super().do_GET()

    def do_POST(self):
        if self.path.split('?')[0] == '/api/refresh':
            started = JOB.start()
            return self._json({'started': started, **JOB.snapshot()},
                              200 if started else 409)
        self.send_error(404)

    def end_headers(self):
        # bundle.js 가 갱신돼도 브라우저가 옛 파일을 쓰지 않도록
        if self.path.endswith(('.js', '.html', '.css')):
            self.send_header('Cache-Control', 'no-cache, must-revalidate')
        super().end_headers()

    def log_message(self, fmt, *args):
        if '/api/status' not in (args[0] if args else ''):
            super().log_message(fmt, *args)


def main():
    ap = argparse.ArgumentParser(description='로컬 운용 서버 (사이트 + 갱신 버튼)')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--holdings', default=None, help='갱신 시 반영할 보유 JSON')
    ap.add_argument('--quick', action='store_true', help='갱신 시 파라미터 민감도 생략(빠름)')
    args = ap.parse_args()

    JOB.opts = {'holdings': args.holdings, 'quick': args.quick}

    if not os.path.exists(os.path.join(SITE, 'data', 'bundle.js')):
        print('site/data/bundle.js 가 없습니다. 먼저 만듭니다...', file=sys.stderr)
        build(use_cache=False, quick=args.quick, holdings_path=args.holdings,
              progress=lambda p, m: print(f'  [{p:3.0f}%] {m}', file=sys.stderr))

    handler = partial(Handler, directory=SITE)
    url = f'http://127.0.0.1:{args.port}'
    # 127.0.0.1 고정 — 이 서버는 파이썬 파이프라인을 실행시키므로 외부에 열지 않는다
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        # 거의 항상 "서버를 이미 켜놨다" 이다. 트레이스백 대신 다음에 할 일을 알려준다.
        print(f'\n포트 {args.port} 이(가) 이미 사용 중입니다.', file=sys.stderr)
        print(f'  이미 서버가 켜져 있을 수 있습니다 → {url} 를 브라우저에서 열어보세요.',
              file=sys.stderr)
        print(f'  다른 포트로 띄우려면 : python scripts/serve.py --port {args.port + 1}',
              file=sys.stderr)
        print(f'  기존 서버를 끄려면   : pkill -f "scripts/serve.py"', file=sys.stderr)
        return 1
    # flush=True — 출력을 파일/파이프로 넘겨도(tee, nohup) 배너가 바로 보이게
    print('=' * 60, flush=True)
    print(f' 추세추종 운용 서버 → {url}', flush=True)
    print(' 갱신: 사이트 우측 상단 "↻ 지금 갱신" 버튼 (약 100초)', flush=True)
    print(' 종료: Ctrl+C', flush=True)
    print('=' * 60, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n종료합니다.')
        srv.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
