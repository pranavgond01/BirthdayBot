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

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

DB_NAME = "birthdays.db"

ROLE_GANG = "🎂 Birthday Gang"
ROLE_BOY = "🎉 Birthday Boy"
ROLE_GIRL = "🎀 Birthday Girl"

DEFAULT_WISH = (
    "🎉🎂 **Happiest Birthday {mention}!** 🎂🎉\n\n"
    "🥳 Congratulations for being **{age} years old!**\n"
    "May your day be filled with happiness, success, love, and amazing memories! ✨\n\n"
    "🎁 You got the **{role}** role for 24 hours!"
)

PRIVATE_WISH = (
    "🎉🎂 **Happiest Birthday {mention}!** 🎂🎉\n\n"
    "🥳 Wishing you happiness, success, love, and amazing memories! ✨\n\n"
    "🎁 You got the **{role}** role for 24 hours!"
)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS birthdays (
        guild_id INTEGER,
        user_id INTEGER,
        day INTEGER,
        month INTEGER,
        year INTEGER DEFAULT 2000,
        role_type TEXT DEFAULT 'gang',
        private INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """)

    cur.execute("PRAGMA table_info(birthdays)")
    cols = [c[1] for c in cur.fetchall()]

    if "year" not in cols:
        cur.execute("ALTER TABLE birthdays ADD COLUMN year INTEGER DEFAULT 2000")
    if "role_type" not in cols:
        cur.execute("ALTER TABLE birthdays ADD COLUMN role_type TEXT DEFAULT 'gang'")
    if "private" not in cols:
        cur.execute("ALTER TABLE birthdays ADD COLUMN private INTEGER DEFAULT 0")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS active_roles (
        guild_id INTEGER,
        user_id INTEGER,
        role_name TEXT,
        remove_time TEXT,
        PRIMARY KEY (guild_id, user_id, role_name)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS wished_today (
        guild_id INTEGER,
        user_id INTEGER,
        date TEXT,
        PRIMARY KEY (guild_id, user_id, date)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        guild_id INTEGER PRIMARY KEY,
        birthday_channel_id INTEGER,
        custom_wish TEXT
    )
    """)

    conn.commit()
    conn.close()


def save_birthday(guild_id, user_id, day, month, year, role_type="gang", private=0):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO birthdays
    (guild_id, user_id, day, month, year, role_type, private)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (guild_id, user_id, day, month, year, role_type, private))

    conn.commit()
    conn.close()


def get_user_birthday(guild_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT day, month, year, role_type, private FROM birthdays
    WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))

    data = cur.fetchone()
    conn.close()
    return data


def delete_user_birthday(guild_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    DELETE FROM birthdays
    WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))

    conn.commit()
    conn.close()


def get_today_birthdays(day, month):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT guild_id, user_id, year, role_type, private FROM birthdays
    WHERE day = ? AND month = ?
    """, (day, month))

    data = cur.fetchall()
    conn.close()
    return data


def get_guild_birthdays(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT user_id, day, month, year, role_type, private FROM birthdays
    WHERE guild_id = ?
    """, (guild_id,))

    data = cur.fetchall()
    conn.close()
    return data


def add_active_role(guild_id, user_id, role_name, remove_time):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO active_roles
    (guild_id, user_id, role_name, remove_time)
    VALUES (?, ?, ?, ?)
    """, (guild_id, user_id, role_name, remove_time))

    conn.commit()
    conn.close()


def get_expired_roles():
    now = datetime.now().isoformat()

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT guild_id, user_id, role_name FROM active_roles
    WHERE remove_time <= ?
    """, (now,))

    data = cur.fetchall()
    conn.close()
    return data


def remove_active_role_record(guild_id, user_id, role_name):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    DELETE FROM active_roles
    WHERE guild_id = ? AND user_id = ? AND role_name = ?
    """, (guild_id, user_id, role_name))

    conn.commit()
    conn.close()


def already_wished(guild_id, user_id):
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT 1 FROM wished_today
    WHERE guild_id = ? AND user_id = ? AND date = ?
    """, (guild_id, user_id, today))

    result = cur.fetchone()
    conn.close()
    return result is not None


def mark_wished(guild_id, user_id):
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT OR IGNORE INTO wished_today
    (guild_id, user_id, date)
    VALUES (?, ?, ?)
    """, (guild_id, user_id, today))

    conn.commit()
    conn.close()


def set_birthday_channel(guild_id, channel_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO settings (guild_id, birthday_channel_id)
    VALUES (?, ?)
    ON CONFLICT(guild_id) DO UPDATE SET birthday_channel_id = excluded.birthday_channel_id
    """, (guild_id, channel_id))

    conn.commit()
    conn.close()


def set_custom_wish(guild_id, message):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO settings (guild_id, custom_wish)
    VALUES (?, ?)
    ON CONFLICT(guild_id) DO UPDATE SET custom_wish = excluded.custom_wish
    """, (guild_id, message))

    conn.commit()
    conn.close()


def get_settings(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT birthday_channel_id, custom_wish FROM settings
    WHERE guild_id = ?
    """, (guild_id,))

    data = cur.fetchone()
    conn.close()

    if data is None:
        return None, None

    return data[0], data[1]


# ---------------- HELPERS ----------------
def parse_date(text):
    match = re.match(r"^(\d{1,2})[\/\-\s](\d{1,2})[\/\-\s](\d{4})$", text.strip())

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    current_year = datetime.now().year

    if year < 1900 or year > current_year:
        return None

    try:
        datetime(year, month, day)
        return day, month, year
    except ValueError:
        return None


def calculate_age(year):
    return datetime.now().year - year


def role_name_from_type(role_type):
    role_type = role_type.lower()

    if role_type == "boy":
        return ROLE_BOY
    if role_type == "girl":
        return ROLE_GIRL

    return ROLE_GANG


def validate_role_type(role_type):
    role_type = role_type.lower()
    if role_type not in ["gang", "boy", "girl"]:
        return "gang"
    return role_type


async def get_or_create_role(guild, role_name):
    role = discord.utils.get(guild.roles, name=role_name)

    if role:
        return role

    return await guild.create_role(
        name=role_name,
        reason="Birthday role created automatically"
    )


async def get_birthday_channel(guild):
    channel_id, _ = get_settings(guild.id)

    if channel_id:
        channel = guild.get_channel(int(channel_id))
        if channel:
            return channel

    if guild.system_channel:
        return guild.system_channel

    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            return channel

    return None


async def make_card(member, age_text):
    width = 1100
    height = 550

    # Background image
    img = Image.new("RGB", (width, height), (18, 18, 35))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(height):
        r = int(80 + (y / height) * 120)
        g = int(40 + (y / height) * 60)
        b = int(170 + (y / height) * 50)

        draw.line(
            [(0, y), (width, y)],
            fill=(r, g, b)
        )

    # Decorative glow circles
    glow_colors = [
        (255, 105, 180),
        (255, 215, 0),
        (120, 255, 200),
        (180, 120, 255)
    ]

    circles = [
        (50, 50, 180),
        (850, 40, 200),
        (780, 340, 220),
        (120, 350, 160),
    ]

    for i, (x, y, size) in enumerate(circles):
        color = glow_colors[i % len(glow_colors)]

        draw.ellipse(
            (x, y, x + size, y + size),
            fill=color
        )

    # Transparent overlay effect
    overlay = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    overlay_draw.rounded_rectangle(
        (70, 70, 1030, 480),
        radius=45,
        fill=(255, 255, 255, 220),
        outline=(255, 215, 0),
        width=6
    )

    img = Image.alpha_composite(
        img.convert("RGBA"),
        overlay
    ).convert("RGB")

    draw = ImageDraw.Draw(img)

    # Left accent bar
    draw.rounded_rectangle(
        (70, 70, 120, 480),
        radius=45,
        fill=(255, 105, 180)
    )

    # Fonts
    try:
        title_font = ImageFont.truetype("arial.ttf", 72)
        name_font = ImageFont.truetype("arial.ttf", 56)
        text_font = ImageFont.truetype("arial.ttf", 34)
        small_font = ImageFont.truetype("arial.ttf", 26)
        emoji_font = ImageFont.truetype("seguiemj.ttf", 48)
    except:
        title_font = ImageFont.load_default()
        name_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
        emoji_font = ImageFont.load_default()

    # Confetti particles
    import random

    for _ in range(80):
        x = random.randint(0, width)
        y = random.randint(0, height)

        color = random.choice([
            (255, 215, 0),
            (255, 105, 180),
            (120, 255, 200),
            (255, 255, 255),
        ])

        size = random.randint(4, 10)

        draw.ellipse(
            (x, y, x + size, y + size),
            fill=color
        )

    # Avatar
    try:
        avatar_asset = member.display_avatar.replace(size=256)
        avatar_bytes = await avatar_asset.read()

        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize((190, 190))

        # Circular mask
        mask = Image.new("L", (190, 190), 0)
        mask_draw = ImageDraw.Draw(mask)

        mask_draw.ellipse(
            (0, 0, 190, 190),
            fill=255
        )

        avatar_x = 150
        avatar_y = 180

        # Avatar border glow
        draw.ellipse(
            (
                avatar_x - 10,
                avatar_y - 10,
                avatar_x + 200,
                avatar_y + 200
            ),
            fill=(255, 215, 0)
        )

        draw.ellipse(
            (
                avatar_x - 4,
                avatar_y - 4,
                avatar_x + 194,
                avatar_y + 194
            ),
            fill=(255, 255, 255)
        )

        img.paste(
            avatar,
            (avatar_x, avatar_y),
            mask
        )

    except Exception as e:
        print(f"Avatar error: {e}")

    # Title glow
    for offset in range(8, 0, -2):
        draw.text(
            (355 - offset, 105 - offset),
            "HAPPY BIRTHDAY",
            font=title_font,
            fill=(255, 105, 180)
        )

    # Main title
    draw.text(
        (355, 105),
        "HAPPY BIRTHDAY",
        font=title_font,
        fill=(35, 35, 55)
    )

    # Username
    draw.text(
        (360, 220),
        member.display_name,
        font=name_font,
        fill=(255, 105, 180)
    )

    # Age message
    draw.text(
        (360, 305),
        age_text,
        font=text_font,
        fill=(70, 70, 80)
    )

    # Footer
    draw.text(
        (360, 375),
        "✨ Wishing you happiness, success & endless joy ✨",
        font=small_font,
        fill=(100, 100, 110)
    )

    # Server branding
    server_name = member.guild.name

    draw.text(
        (360, 430),
        f"From {server_name} community 💜",
        font=small_font,
        fill=(120, 120, 130)
    )

    # Decorative emojis
    draw.text(
        (900, 120),
        "🎂",
        font=emoji_font,
        fill=(255, 255, 255)
    )

    draw.text(
        (940, 210),
        "🎉",
        font=emoji_font,
        fill=(255, 255, 255)
    )

    draw.text(
        (880, 320),
        "🎁",
        font=emoji_font,
        fill=(255, 255, 255)
    )

    # Save image
    buffer = io.BytesIO()

    img.save(
        buffer,
        format="PNG",
        quality=100
    )

    buffer.seek(0)

    return discord.File(
        buffer,
        filename="birthday_card.png"
    )


async def give_role_and_wish(guild, member, year, role_type, private):
    if already_wished(guild.id, member.id):
        return False

    role_name = role_name_from_type(role_type)
    role = await get_or_create_role(guild, role_name)

    try:
        await member.add_roles(role, reason="Birthday role for 24 hours")
    except Exception as e:
        print(f"Role add error: {e}")
        return False

    remove_time = datetime.now() + timedelta(hours=24)
    add_active_role(guild.id, member.id, role_name, remove_time.isoformat())

    age = calculate_age(year)
    channel = await get_birthday_channel(guild)

    _, custom_wish = get_settings(guild.id)

    if private:
        message = PRIVATE_WISH.format(
            mention=member.mention,
            username=member.display_name,
            age=age,
            role=role_name
        )
        age_text = "Have an amazing birthday!"
    else:
        template = custom_wish if custom_wish else DEFAULT_WISH
        message = template.format(
            mention=member.mention,
            username=member.display_name,
            age=age,
            role=role_name
        )
        age_text = f"Congratulations for being {age} years old!"

    if channel:
        card = await make_card(member, age_text)
        await channel.send(content=message, file=card)

    mark_wished(guild.id, member.id)
    return True


def days_until_birthday(day, month):
    today = datetime.now().date()
    year = today.year

    try:
        birthday = datetime(year, month, day).date()
    except ValueError:
        return 9999

    if birthday < today:
        birthday = datetime(year + 1, month, day).date()

    return (birthday - today).days


# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    init_db()

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Slash sync error: {e}")

    if not birthday_checker.is_running():
        birthday_checker.start()

    if not role_remover.is_running():
        role_remover.start()

    print(f"✅ Logged in as {bot.user}")


@bot.event
async def on_member_join(member):
    try:
        await member.send(
            f"👋 Welcome to **{member.guild.name}**!\n\n"
            f"Send your birthday like this:\n"
            f"`DD/MM/YYYY`\n\n"
            f"Example: `25/12/2004`"
        )

        def check(msg):
            return msg.author == member and isinstance(msg.channel, discord.DMChannel)

        msg = await bot.wait_for("message", timeout=300, check=check)
        parsed = parse_date(msg.content)

        if parsed is None:
            await member.send("❌ Invalid format. Use `/setbirthday DD/MM/YYYY` in server.")
            return

        day, month, year = parsed
        save_birthday(member.guild.id, member.id, day, month, year, "gang", 0)

        await member.send(f"✅ Birthday saved: **{day}/{month}/{year}** 🎂")

        today = datetime.now()
        if day == today.day and month == today.month:
            await give_role_and_wish(member.guild, member, year, "gang", 0)
            await member.send(f"🎉 Happiest Birthday! You got the **{ROLE_GANG}** role for 24 hours!")

    except asyncio.TimeoutError:
        try:
            await member.send("⏰ Time expired. Use `/setbirthday DD/MM/YYYY` later.")
        except:
            pass
    except Exception as e:
        print(f"Join birthday DM error: {e}")


# ---------------- COMMANDS ----------------
@bot.tree.command(name="setbirthday", description="Set your birthday")
@app_commands.describe(
    date="Example: 25/12/2004",
    role_type="gang, boy, or girl",
    private="Hide your age in public wishes?"
)
async def setbirthday(
    interaction: discord.Interaction,
    date: str,
    role_type: str = "gang",
    private: bool = False
):
    parsed = parse_date(date)

    if parsed is None:
        await interaction.response.send_message(
            "❌ Invalid format. Use `DD/MM/YYYY`, example: `25/12/2004`",
            ephemeral=True
        )
        return

    role_type = validate_role_type(role_type)
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
        f"✅ Birthday saved: **{day}/{month}/{year}**\n"
        f"🎭 Role type: **{role_type}**\n"
        f"🔒 Private age: **{private}**",
        ephemeral=True
    )

    today = datetime.now()
    if day == today.day and month == today.month:
        await give_role_and_wish(interaction.guild, interaction.user, year, role_type, 1 if private else 0)


@bot.tree.command(name="mybirthday", description="Check your birthday")
async def mybirthday(interaction: discord.Interaction):
    data = get_user_birthday(interaction.guild.id, interaction.user.id)

    if data is None:
        await interaction.response.send_message(
            "❌ No birthday saved. Use `/setbirthday DD/MM/YYYY`",
            ephemeral=True
        )
        return

    day, month, year, role_type, private = data
    age = calculate_age(year)

    await interaction.response.send_message(
        f"🎂 Birthday: **{day}/{month}/{year}**\n"
        f"🎉 Age: **{age}**\n"
        f"🎭 Role type: **{role_type}**\n"
        f"🔒 Private age: **{bool(private)}**",
        ephemeral=True
    )


@bot.tree.command(name="removebirthday", description="Remove your birthday")
async def removebirthday(interaction: discord.Interaction):
    delete_user_birthday(interaction.guild.id, interaction.user.id)

    await interaction.response.send_message(
        "✅ Your birthday has been removed.",
        ephemeral=True
    )


@bot.tree.command(name="upcomingbirthdays", description="Show upcoming birthdays")
async def upcomingbirthdays(interaction: discord.Interaction):
    data = get_guild_birthdays(interaction.guild.id)

    if not data:
        await interaction.response.send_message("❌ No birthdays saved yet.")
        return

    sorted_data = sorted(data, key=lambda x: days_until_birthday(x[1], x[2]))[:10]

    msg = "🎂 **Upcoming Birthdays**\n\n"

    for user_id, day, month, year, role_type, private in sorted_data:
        member = interaction.guild.get_member(user_id)
        name = member.mention if member else f"`User ID: {user_id}`"
        left = days_until_birthday(day, month)

        if private:
            msg += f"• {name} — **{day}/{month}** — in **{left} days** 🔒\n"
        else:
            age = datetime.now().year - year
            msg += f"• {name} — **{day}/{month}** — turning **{age + 1 if left != 0 else age}** — in **{left} days**\n"

    await interaction.response.send_message(msg)


@bot.tree.command(name="nextbirthday", description="Show your next birthday countdown")
async def nextbirthday(interaction: discord.Interaction):
    data = get_user_birthday(interaction.guild.id, interaction.user.id)

    if data is None:
        await interaction.response.send_message(
            "❌ No birthday saved. Use `/setbirthday DD/MM/YYYY`",
            ephemeral=True
        )
        return

    day, month, year, role_type, private = data
    left = days_until_birthday(day, month)

    if left == 0:
        await interaction.response.send_message("🎉 Today is your birthday! Happiest Birthday! 🎂")
    else:
        await interaction.response.send_message(
            f"🎂 Your next birthday is in **{left} days**!",
            ephemeral=True
        )


@bot.tree.command(name="setbirthdaychannel", description="Admin: set birthday wish channel")
@app_commands.describe(channel="Channel where birthday wishes will be sent")
async def setbirthdaychannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can use this.", ephemeral=True)
        return

    set_birthday_channel(interaction.guild.id, channel.id)

    await interaction.response.send_message(
        f"✅ Birthday wishes channel set to {channel.mention}",
        ephemeral=True
    )


@bot.tree.command(name="setwishmessage", description="Admin: set custom birthday wish")
@app_commands.describe(message="Use {mention}, {username}, {age}, {role}")
async def setwishmessage(interaction: discord.Interaction, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can use this.", ephemeral=True)
        return

    set_custom_wish(interaction.guild.id, message)

    await interaction.response.send_message(
        "✅ Custom birthday wish saved.\n"
        "Placeholders: `{mention}`, `{username}`, `{age}`, `{role}`",
        ephemeral=True
    )


@bot.tree.command(name="testbirthday", description="Admin: test birthday wish")
async def testbirthday(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can use this.", ephemeral=True)
        return

    data = get_user_birthday(interaction.guild.id, member.id)

    if data is None:
        await interaction.response.send_message("❌ This user has no saved birthday.", ephemeral=True)
        return

    day, month, year, role_type, private = data
    success = await give_role_and_wish(interaction.guild, member, year, role_type, private)

    if success:
        await interaction.response.send_message(f"✅ Birthday wish sent for {member.mention}", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ Already wished today or role permission issue.", ephemeral=True)


@bot.tree.command(name="birthdayhelp", description="Show birthday bot help")
async def birthdayhelp(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**🎂 Birthday Bot Commands**\n\n"
        "`/setbirthday 25/12/2004 gang false`\n"
        "`/mybirthday`\n"
        "`/removebirthday`\n"
        "`/upcomingbirthdays`\n"
        "`/nextbirthday`\n"
        "`/setbirthdaychannel #channel` admin\n"
        "`/setwishmessage message` admin\n"
        "`/testbirthday @user` admin\n\n"
        "**Role types:** `gang`, `boy`, `girl`\n"
        "**Custom message placeholders:** `{mention}`, `{username}`, `{age}`, `{role}`"
    )


# ---------------- LOOPS ----------------
@tasks.loop(hours=24)
async def birthday_checker():
    today = datetime.now()
    birthdays = get_today_birthdays(today.day, today.month)

    for guild_id, user_id, year, role_type, private in birthdays:
        guild = bot.get_guild(guild_id)
        if guild is None:
            continue

        try:
            member = await guild.fetch_member(user_id)
        except:
            continue

        await give_role_and_wish(guild, member, year, role_type, private)


@birthday_checker.before_loop
async def before_birthday_checker():
    await bot.wait_until_ready()


@tasks.loop(minutes=10)
async def role_remover():
    expired = get_expired_roles()

    for guild_id, user_id, role_name in expired:
        guild = bot.get_guild(guild_id)

        if guild is None:
            remove_active_role_record(guild_id, user_id, role_name)
            continue

        role = discord.utils.get(guild.roles, name=role_name)

        try:
            member = await guild.fetch_member(user_id)
        except:
            remove_active_role_record(guild_id, user_id, role_name)
            continue

        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Birthday role expired after 24 hours")
            except Exception as e:
                print(f"Role remove error: {e}")

        remove_active_role_record(guild_id, user_id, role_name)


@role_remover.before_loop
async def before_role_remover():
    await bot.wait_until_ready()


bot.run(TOKEN)
