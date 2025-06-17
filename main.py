import discord 
from discord.ext import commands
import aiosqlite 
from datetime import datetime
from pathlib import Path

# 디스코드 API에 접근하기 위한 설정 (유저 메시지를 읽기 위해 반드시 켜야 함)
intents = discord.Intents.default()
intents.message_content = True  # ← 이게 없으면 명령어 입력해도 봇이 못 읽어요

# 봇 명령어 프리픽스 설정 (예: !hello)
bot = commands.Bot(command_prefix="!", intents=intents)

# 봇이 실행되면 터미널에 표시되는 문구
@bot.event
async def on_ready():
    print(f"{bot.user} 봇이 로그인했습니다!")

    async with aiosqlite.connect("attendance.db") as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                username TEXT,
                date TEXT
            )
        ''')
        await db.commit()
    

# !hello 라고 입력했을 때 봇이 응답하는 명령어
@bot.command()
async def hello(ctx):
    await ctx.send("안녕하세요, 섬님!")

@bot.command()
async def check(ctx):
    user_id = str(ctx.author.id)
    username = ctx.author.display_name
    mention = ctx.author.mention
    today = datetime.now().strftime('%Y-%m-%d')

    async with aiosqlite.connect("attendance.db") as db:
        cursor = await db.execute(
            "SELECT * FROM attendance WHERE user_id = ? AND date = ?", (user_id, today)
        )
        row = await cursor.fetchone()

        if row:
            await ctx.send(f"{mention}님, 오늘 이미 출석하셨어요 ✅")
        else:
            await db.execute(
                "INSERT INTO attendance (user_id, username, date) VALUES (?, ?, ?)",
                (user_id, username, today)
            )
            await db.commit()
            await ctx.send(f"{mention}님, 출석이 완료되었습니다! 🗓️")

@bot.command()
async def ranking(ctx):
    async with aiosqlite.connect("attendance.db") as db:
        cursor = await db.execute("""
            SELECT user_id, username, COUNT(*) as count
            FROM attendance
            GROUP BY user_id
            ORDER BY count DESC
        """)
        rows = await cursor.fetchall()

    if not rows:
        await ctx.send("아직 아무도 출석하지 않았어요 😢")
        return

    message = "📊 **출석 랭킹**\n"
    for i, row in enumerate(rows, start=1):
        user_id, username, count = row
        mention = f"<@{user_id}>"
        message += f"{i}. {mention} - {count}회\n"

    await ctx.send(message)


@bot.command(name="출석일수")
async def attendance_count(ctx):
    user_id = str(ctx.author.id)

    async with aiosqlite.connect("attendance.db") as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM attendance WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()

    count = row[0] if row else 0
    await ctx.send(f"{ctx.author.mention}님의 총 출석 횟수는 **{count}일**입니다!")

@bot.command()
async def last(ctx):
    user_id = str(ctx.author.id)

    async with aiosqlite.connect("attendance.db") as db:
        cursor = await db.execute(
            "SELECT date FROM attendance WHERE user_id = ? ORDER BY date DESC LIMIT 1", (user_id,)
        )
        row = await cursor.fetchone()

    if row:
        await ctx.send(f"{ctx.author.mention}님의 마지막 출석일은 **{row[0]}**입니다!")
    else:
        await ctx.send(f"{ctx.author.mention}님은 아직 출석한 기록이 없습니다.")

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