"""텔레그램 알림 — 자문/리밸런싱 리포트를 휴대폰으로 받기.
외부 라이브러리 없이 표준 urllib 사용. 키는 .env/환경변수에서만 읽음.

설정:
  1) 텔레그램에서 @BotFather 검색 → /newbot → 봇 토큰 발급
  2) 만든 봇과 대화 시작(아무 메시지 전송) 후, chat_id 확인
     (https://api.telegram.org/bot<토큰>/getUpdates 접속 → result[].message.chat.id)
  3) .env 에 아래 추가:
       TELEGRAM_BOT_TOKEN=...
       TELEGRAM_CHAT_ID=...
미설정 시 조용히 건너뜀(에러 아님)."""
import os
import urllib.parse
import urllib.request


def _load_dotenv():
    if os.path.exists('.env'):
        with open('.env', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())


def send_telegram(text):
    """텔레그램으로 text 전송. 성공 True / 미설정·실패 False."""
    _load_dotenv()
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return False
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': chat, 'text': text}).encode('utf-8')
    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as resp:
            resp.read()
        return True
    except Exception as e:
        print('  [notify] 텔레그램 전송 실패:', e)
        return False
