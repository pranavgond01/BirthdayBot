import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
import re
from PIL import Image, ImageDraw, ImageFont
import io
import random

# ================= LOAD ENV =================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ================= CONFIG =================
DB_NAME = "birthdays.db"

ROLE_GANG = "🎂 Birthday Gang"
ROLE_BOY = "🎉 Birthday Boy"
ROLE_GIRL = "🎀 Birthday Girl"

DEFAULT_WISH = (
    "🎉🎂 **Happiest Birthday {mention}!** 🎂🎉\n\n"
    "🥳 Congratulations for being **{age} years old!**\n"
    "✨ Wishing you happiness, success, love & amazing memories!\n\n"
    "🎁 You got the **{role}** role for 24 hours!"
)

PRIVATE_WISH = (
    "🎉🎂 **Happiest Birthday {mention}!** 🎂🎉\n\n"
    "✨ Wishing you happiness, success & endless joy!\n\n"
    "🎁 You got the **{role}** role for 24 hours!"
)

# ================= DISCORD =================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS birthdays (
        guild_id INTEGER,
        user_id INTEGER,
        day INTEGER,
        month INTEGER,
        year INTEGER,
        role_type TEXT DEFAULT 'gang',
        private INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        guild_id INTEGER PRIMARY KEY,
        birthday_channel INTEGER,
        custom_message TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS active_roles (
        guild_id INTEGER,
        user_id INTEGER,
        role_name TEXT,
        remove_time TEXT
    )
    """)

    conn.commit()
    conn.close()

def save_birthday(guild_id, user_id, day, month, year, role_type, private):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO birthdays
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        guild_id,
        user_id,
        day,
        month,
        year,
        role_type,
        private
    ))

    conn.commit()
    conn.close()

def get_user_birthday(guild_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT day, month, year, role_type, private
    FROM birthdays
    WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))

    data = cur.fetchone()

    conn.close()
    return data

def get_today_birthdays(day, month):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT guild_id, user_id, year, role_type, private
    FROM birthdays
    WHERE day = ? AND month = ?
    """, (day, month))

    data = cur.fetchall()

    conn.close()
    return data

def get_all_birthdays(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT user_id, day, month, year
    FROM birthdays
    WHERE guild_id = ?
    """, (guild_id,))

    data = cur.fetchall()

    conn.close()
    return data

def set_birthday_channel(guild_id, channel_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO settings
    (guild_id, birthday_channel)
    VALUES (?, ?)
    """, (guild_id, channel_id))

    conn.commit()
    conn.close()

def get_birthday_channel(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT birthday_channel
    FROM settings
    WHERE guild_id = ?
    """, (guild_id,))

    data = cur.fetchone()

    conn.close()

    if data:
        return data[0]

    return None

def set_custom_message(guild_id, message):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO settings
    (guild_id, custom_message)
    VALUES (?, ?)
    """, (guild_id, message))

    conn.commit()
    conn.close()

def get_custom_message(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT custom_message
    FROM settings
    WHERE guild_id = ?
    """, (guild_id,))

    data = cur.fetchone()

    conn.close()

    if data:
        return data[0]

    return None

# ================= HELPERS =================
def parse_date(text):
    match = re.match(r"^(\d{1,2})\/(\d{1,2})\/(\d{4})$", text)

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

    try:
        datetime(year, month, day)
        return day, month, year
    except:
        return None

def calculate_age(year):
    return datetime.now().year - year

def get_role_name(role_type):
    if role_type == "boy":
        return ROLE_BOY
    elif role_type == "girl":
        return ROLE_GIRL
    else:
        return ROLE_GANG

async def create_role_if_missing(guild, role_name):
    role = discord.utils.get(guild.roles, name=role_name)

    if role:
        return role

    return await guild.create_role(name=role_name)

# ================= PREMIUM CARD =================
async def make_card(member, age_text):
    width = 1200
    height = 600

    img = Image.new("RGB", (width, height), (25, 20, 55))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(height):
        r = int(45 + (y / height) * 120)
        g = int(25 + (y / height) * 65)
        b = int(95 + (y / height) * 120)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Fonts
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 78)
        name_font = ImageFont.truetype("arialbd.ttf", 58)
        text_font = ImageFont.truetype("arial.ttf", 34)
        small_font = ImageFont.truetype("arial.ttf", 26)
        server_font = ImageFont.truetype("arialbd.ttf", 30)
    except:
        title_font = ImageFont.load_default()
        name_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
        server_font = ImageFont.load_default()

    # Glow circles
    glow_items = [
        (40, 40, 240, (255, 105, 180)),
        (900, 40, 260, (255, 215, 0)),
        (830, 380, 260, (120, 255, 220)),
        (90, 400, 180, (180, 130, 255)),
    ]

    for x, y, size, color in glow_items:
        draw.ellipse((x, y, x + size, y + size), fill=color)

    # Main card
    draw.rounded_rectangle(
        (80, 80, 1120, 520),
        radius=45,
        fill=(255, 255, 255),
        outline=(255, 220, 90),
        width=6
    )

    # Header
    draw.rounded_rectangle(
        (80, 80, 1120, 155),
        radius=45,
        fill=(255, 105, 180)
    )

    draw.rectangle((80, 125, 1120, 155), fill=(255, 105, 180))

    # Confetti
    for _ in range(100):
        x = random.randint(80, 1120)
        y = random.randint(80, 520)

        color = random.choice([
            (255, 215, 0),
            (255, 105, 180),
            (120, 255, 220),
            (130, 130, 255),
            (255, 255, 255),
        ])

        size = random.randint(4, 9)

        draw.ellipse((x, y, x + size, y + size), fill=color)

    # Server logo
    try:
        if member.guild.icon:
            server_icon_bytes = await member.guild.icon.replace(size=256).read()

            server_icon = Image.open(io.BytesIO(server_icon_bytes)).convert("RGBA")
            server_icon = server_icon.resize((70, 70))

            server_mask = Image.new("L", (70, 70), 0)
            server_mask_draw = ImageDraw.Draw(server_mask)
            server_mask_draw.ellipse((0, 0, 70, 70), fill=255)

            draw.ellipse((105, 92, 185, 172), fill=(255, 255, 255))

            img.paste(server_icon, (110, 97), server_mask)

    except Exception as e:
        print(e)

    # Server name
    draw.text(
        (200, 110),
        member.guild.name,
        font=server_font,
        fill=(255, 255, 255)
    )

    # Avatar
    try:
        avatar_bytes = await member.display_avatar.replace(size=256).read()

        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize((200, 200))

        mask = Image.new("L", (200, 200), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, 200, 200), fill=255)

        avatar_x = 135
        avatar_y = 225

        draw.ellipse(
            (avatar_x - 12, avatar_y - 12, avatar_x + 212, avatar_y + 212),
            fill=(255, 215, 0)
        )

        img.paste(avatar, (avatar_x, avatar_y), mask)

    except Exception as e:
        print(e)

    # Title
    draw.text(
        (390, 200),
        "🎂 HAPPY BIRTHDAY",
        font=title_font,
        fill=(35, 35, 60)
    )

    # Username
    draw.text(
        (395, 300),
        member.display_name,
        font=name_font,
        fill=(255, 80, 160)
    )

    # Age text
    draw.text(
        (395, 375),
        age_text,
        font=text_font,
        fill=(75, 75, 90)
    )

    # Footer
    draw.text(
        (395, 435),
        "✨ Wishing you happiness, success & endless joy ✨",
        font=small_font,
        fill=(105, 105, 120)
    )

    draw.text(
        (395, 475),
        f"With love from {member.guild.name} community 💜",
        font=small_font,
        fill=(130, 130, 145)
    )

    buffer = io.BytesIO()

    img.save(buffer, format="PNG", quality=100)

    buffer.seek(0)

    return discord.File(buffer, filename="birthday_card.png")

# ================= BIRTHDAY SYSTEM =================
async def give_role_and_wish(guild, member, year, role_type, private):
    role_name = get_role_name(role_type)

    role = await create_role_if_missing(guild, role_name)

    try:
        await member.add_roles(role)
    except Exception as e:
        print(e)

    age = calculate_age(year)

    if private:
        message = PRIVATE_WISH.format(
            mention=member.mention,
            role=role_name
        )

        age_text = "Have an amazing birthday!"
    else:
        custom = get_custom_message(guild.id)

        template = custom if custom else DEFAULT_WISH

        message = template.format(
            mention=member.mention,
            age=age,
            role=role_name
        )

        age_text = f"Congratulations for being {age} years old!"

    card = await make_card(member, age_text)

    channel_id = get_birthday_channel(guild.id)

    if channel_id:
        channel = guild.get_channel(channel_id)
    else:
        channel = guild.system_channel

    if channel:
        await channel.send(content=message, file=card)

    remove_time = datetime.now() + timedelta(hours=24)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO active_roles
    VALUES (?, ?, ?, ?)
    """, (
        guild.id,
        member.id,
        role_name,
        remove_time.isoformat()
    ))

    conn.commit()
    conn.close()

# ================= EVENTS =================
@bot.event
async def on_ready():
    init_db()

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

    birthday_checker.start()
    role_remover.start()

    print(f"Logged in as {bot.user}")

@bot.event
async def on_member_join(member):
    try:
        await member.send(
            "🎂 Welcome!\n\nSend birthday:\n`25/12/2004`"
        )

        def check(msg):
            return (
                msg.author == member and
                isinstance(msg.channel, discord.DMChannel)
            )

        msg = await bot.wait_for(
            "message",
            timeout=300,
            check=check
        )

        parsed = parse_date(msg.content)

        if not parsed:
            await member.send("❌ Invalid format.")
            return

        day, month, year = parsed

        save_birthday(
            member.guild.id,
            member.id,
            day,
            month,
            year,
            "gang",
            0
        )

        await member.send("✅ Birthday saved!")

        today = datetime.now()

        if day == today.day and month == today.month:
            await give_role_and_wish(
                member.guild,
                member,
                year,
                "gang",
                0
            )

    except asyncio.TimeoutError:
        pass

# ================= COMMANDS =================
@bot.tree.command(name="setbirthday")
async def setbirthday(
    interaction: discord.Interaction,
    date: str,
    role_type: str = "gang",
    private: bool = False
):
    parsed = parse_date(date)

    if not parsed:
        await interaction.response.send_message(
            "❌ Use DD/MM/YYYY",
            ephemeral=True
        )
        return

    day, month, year = parsed

    save_birthday(
        interaction.guild.id,
        interaction.user.id,
        day,
        month,
        year,
        role_type,
        1 if private else 0
    )

    await interaction.response.send_message(
        "✅ Birthday saved!",
        ephemeral=True
    )

@bot.tree.command(name="mybirthday")
async def mybirthday(interaction: discord.Interaction):
    data = get_user_birthday(
        interaction.guild.id,
        interaction.user.id
    )

    if not data:
        await interaction.response.send_message(
            "❌ No birthday saved.",
            ephemeral=True
        )
        return

    day, month, year, role_type, private = data

    await interaction.response.send_message(
        f"🎂 {day}/{month}/{year}\n"
        f"🎭 Role: {role_type}\n"
        f"🔒 Private: {bool(private)}",
        ephemeral=True
    )

@bot.tree.command(name="upcomingbirthdays")
async def upcomingbirthdays(interaction: discord.Interaction):
    data = get_all_birthdays(interaction.guild.id)

    if not data:
        await interaction.response.send_message("❌ No birthdays.")
        return

    msg = "🎂 Upcoming Birthdays\n\n"

    for user_id, day, month, year in data[:10]:
        member = interaction.guild.get_member(user_id)

        if member:
            msg += f"• {member.mention} → {day}/{month}/{year}\n"

    await interaction.response.send_message(msg)

@bot.tree.command(name="setbirthdaychannel")
async def setbirthdaychannel(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Admin only.",
            ephemeral=True
        )
        return

    set_birthday_channel(
        interaction.guild.id,
        channel.id
    )

    await interaction.response.send_message(
        f"✅ Birthday channel set to {channel.mention}"
    )

@bot.tree.command(name="testbirthday")
async def testbirthday(
    interaction: discord.Interaction,
    member: discord.Member
):
    data = get_user_birthday(
        interaction.guild.id,
        member.id
    )

    if not data:
        await interaction.response.send_message(
            "❌ User has no birthday saved."
        )
        return

    day, month, year, role_type, private = data

    await give_role_and_wish(
        interaction.guild,
        member,
        year,
        role_type,
        private
    )

    await interaction.response.send_message(
        "✅ Birthday test sent."
    )

# ================= TASKS =================
@tasks.loop(hours=24)
async def birthday_checker():
    today = datetime.now()

    birthdays = get_today_birthdays(
        today.day,
        today.month
    )

    for guild_id, user_id, year, role_type, private in birthdays:
        guild = bot.get_guild(guild_id)

        if not guild:
            continue

        try:
            member = await guild.fetch_member(user_id)
        except:
            continue

        await give_role_and_wish(
            guild,
            member,
            year,
            role_type,
            private
        )

@tasks.loop(minutes=10)
async def role_remover():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    now = datetime.now().isoformat()

    cur.execute("""
    SELECT guild_id, user_id, role_name
    FROM active_roles
    WHERE remove_time <= ?
    """, (now,))

    expired = cur.fetchall()

    for guild_id, user_id, role_name in expired:
        guild = bot.get_guild(guild_id)

        if not guild:
            continue

        role = discord.utils.get(
            guild.roles,
            name=role_name
        )

        if not role:
            continue

        try:
            member = await guild.fetch_member(user_id)

            if role in member.roles:
                await member.remove_roles(role)

        except:
            pass

    cur.execute("""
    DELETE FROM active_roles
    WHERE remove_time <= ?
    """, (now,))

    conn.commit()
    conn.close()

# ================= RUN =================
bot.run(TOKEN)
