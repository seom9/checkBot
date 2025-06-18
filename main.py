import discord 
from discord.ext import commands
import aiosqlite 
from datetime import datetime
from pathlib import Path
from datetime import datetime, date, timedelta

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
        line = f"{idx:2d}.   {name:<5} | " + " | ".join(marks) + f" => {week_num:2d}주째!"
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

# 토큰 로딩
props = load_properties(Path("config.properties"))
TOKEN = props.get("DISCORD_BOT_TOKEN")

bot.run(TOKEN)