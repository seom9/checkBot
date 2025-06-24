import discord 
from discord.ext import commands
import aiosqlite 
from datetime import datetime
from pathlib import Path
from datetime import datetime, date, timedelta
from openai import OpenAI
import os

# 디스코드 API에 접근하기 위한 설정 (유저 메시지를 읽기 위해 반드시 켜야 함)
intents = discord.Intents.default()
intents.message_content = True  # ← 이게 없으면 명령어 입력해도 봇이 못 읽음

# DB path
DB_PATH = "attendance.db"

# 봇 명령어 프리픽스 설정 (예: !hello)
bot = commands.Bot(command_prefix="!", intents=intents)

# 봇이 실행되면 터미널에 표시되는 문구
@bot.event
async def on_ready():
    print(f"{bot.user} 봇이 로그인했습니다!")

    async with aiosqlite.connect("attendance.db") as db:
        # 유저 테이블 (1인 1행)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            first_date TEXT
        )
        """)

        # 출석 기록 테이블 (여러 건 가능)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            date TEXT,
            UNIQUE(user_id, date)
        )
        """)

        await db.commit()

def get_week_number(start_date_str, current_date_str):
    start = datetime.strptime(start_date_str, "%Y-%m-%d")
    current = datetime.strptime(current_date_str, "%Y-%m-%d")
    return ((current - start).days // 7) + 1


# !hello 라고 입력했을 때 봇이 응답하는 명령어
@bot.command()
async def hello(ctx):
    await ctx.send("안녕하세요, 섬님!")


# 이번 주 월~목 날짜 구하기
def get_weekdays_monday_to_thursday():
    today = date.today()
    monday = today - timedelta(days=today.weekday())  # 월요일
    return [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(4)]  # 월~목

def format_header_dates():
    weekdays = get_weekdays_monday_to_thursday()
    return [datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d") for d in weekdays]

# 정렬된 유저 + 해당 주 출석 정보 조회
async def get_weekly_attendance():
    weekdays = get_weekdays_monday_to_thursday()
    async with aiosqlite.connect("attendance.db") as db:
        users = await db.execute("SELECT user_id, username, first_date FROM users ORDER BY first_date ASC")
        users = await users.fetchall()

        results = []
        for idx, (user_id, username, first_date) in enumerate(users, start=1):
            cursor = await db.execute(
                "SELECT date FROM attendance WHERE user_id = ? AND date IN ({})".format(",".join("?"*len(weekdays))),
                (user_id, *weekdays)
            )
            rows = await cursor.fetchall()
            dates = {r[0] for r in rows}
            week_number = get_week_number(first_date, date.today().strftime("%Y-%m-%d"))
            results.append((idx, username, [("O" if d in dates else "-") for d in weekdays], week_number))
        return results

# 출석 문자열 조립
def build_attendance_message(data, dates):
    today = date.today()
    month = today.month
    week = int(today.strftime("%U"))
    message = f"[:date: {month}월 {week}주차 출석부]\n\n"
    message += f" 0.   이름   | {' | '.join(dates)} \n"
    message += "=" * 56 + "\n"
    for idx, name, marks, week_num in data:
        line = f"{idx:2d}.   {name:<5} |   " + "   |   ".join(marks) + f"    => {week_num:2d}주째!"
        message += line + "\n"
    return message

# 출석 체크 명령어
@bot.command()
async def check(ctx):
    user_id = str(ctx.author.id)
    username = ctx.author.display_name
    today = date.today().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username, first_date) VALUES (?, ?, ?)",
                         (user_id, username, today))
        await db.execute("INSERT OR IGNORE INTO attendance (user_id, date) VALUES (?, ?)", (user_id, today))
        await db.commit()

    await ctx.send(f"{ctx.author.mention}님, 오늘 출석이 완료되었습니다! ✅")


@bot.command(name="출석부")
async def print_attendance(ctx):
    data = await get_weekly_attendance()
    dates = format_header_dates()
    msg = build_attendance_message(data, dates)
    await ctx.send(f"```\n{msg}```")


# properties 읽기
def load_properties(path):
    props = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.strip().split('=', 1)
                props[key.strip()] = value.strip()
    return props


props = load_properties(Path("config.properties"))
TOKEN = props.get("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = props.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)  # ← 여기 중요!


# 프롬포트
system_message = """
너는 'After Work Dev'라는 직장인 대상 퇴근 후 스터디의 운영 규칙을 잘 아는 도우미야.
이 스터디는 매일 1시간씩 꾸준히 공부하고 인증하는 것이 목표야. 아래는 해당 스터디의 규칙이야:

[스터디 규칙]

- 스터디 이름: After Work Dev
- 목표: 퇴근 후 개인 공부를 매일 1시간씩 간단하고 꾸준히 진행
- 일정: 매주 월~목, 저녁 9시~10시 (코어타임 필수 참여)
- 시작일: 3/17
- 예상 인원: 10명 이하
- 플랫폼: Discord
- 참여 조건: 화면 공유 기본, 개인 업무 시 캠만 켜두면 됨
- 기술 잡담 허용: 공부하기 싫은 날은 기술 관련 잡담 가능
- 인증: Github 레포에 오늘 한 일과 내일 계획 commit
- 출석: 주 3회 이상 참여, 지각 3번 = 결석 1번, 9시 10분에 출석체크
- 페널티: 한 달 3회 이상 결석 시 강퇴
- 지원 방법: 오픈채팅방(https://open.kakao.com/o/sCH6KMkh)

사용자가 이 규칙에 대해 궁금한 점을 물어보면 명확하고 친절하게 답변해 줘.  
규칙과 관련 없는 질문이 들어오면 "이건 스터디 규칙과는 관련 없는 질문이야"라고 안내해 줘.
"""

# gpt 에게 질문하기
def ask_study_bot(question: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4",  # 또는 "gpt-3.5-turbo"
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": question}
        ],
        temperature=0.5, # 창의성, 다양성 조절 높을수록 창의력 높음
        max_tokens=100, # 응답 글자 수 제한
    )
    return response.choices[0].message.content



# AI 에게 질문하기 명령 등록
@bot.command(name="질문")
async def 질문(ctx, *, user_question):
    await ctx.send("스터디 규칙을 확인 중입니다...")
    try:
        answer = ask_study_bot(user_question)
        await ctx.send(answer)
    except Exception as e:
        await ctx.send(f"⚠️ 오류가 발생했어요: {e}")


# 토큰 로딩
props = load_properties(Path("config.properties"))
TOKEN = props.get("DISCORD_BOT_TOKEN")

bot.run(TOKEN)