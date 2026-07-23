@echo off
chcp 65001 >nul
REM ============================================================
REM  월간 자동 실행 (Windows 작업 스케줄러에 등록해서 사용)
REM  - 안전을 위해 '자동 매매'는 하지 않는다. 리포트만 텔레그램으로 보내고,
REM    사람이 검토 후 직접 `python scripts\paper_trade.py --execute` 한다.
REM  - 완전 자동매매로 가려면 아래 advisory 줄을
REM    `python scripts\paper_trade.py --execute --notify` 로 바꾸면 된다(자기 책임).
REM ============================================================
cd /d "C:\Users\smhrd\Desktop\주식예측모델"

echo [%date% %time%] 자문 리포트 실행 >> "reports\cron.log"
python scriptsdvisory.py --notify  >> "reports\cron.log" 2>&1
python scripts\monitor.py  --notify  >> "reports\cron.log" 2>&1
echo [%date% %time%] 완료 >> "reports\cron.log"
