import discord
from discord.ext import commands, tasks
import sqlite3
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import random

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

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

    conn.commit()
    conn.close()


def save_birthday(guild_id, user_id, day, month, year, role_type, private):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO birthdays
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (guild_id, user_id, day, month, year, role_type, private))

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
    SELECT user_id, day, month, year, role_type, private
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
    INSERT INTO settings (guild_id, birthday_channel)
    VALUES (?, ?)
    ON CONFLICT(guild_id) DO UPDATE SET birthday_channel = excluded.birthday_channel
    """, (guild_id, channel_id))

    conn.commit()
    conn.close()


def get_birthday_channel_id(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT birthday_channel FROM settings
    WHERE guild_id = ?
    """, (guild_id,))

    data = cur.fetchone()
    conn.close()

    return data[0] if data and data[0] else None


def set_custom_message(guild_id, message):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO settings (guild_id, custom_message)
    VALUES (?, ?)
    ON CONFLICT(guild_id) DO UPDATE SET custom_message = excluded.custom_message
    """, (guild_id, message))

    conn.commit()
    conn.close()


def get_custom_message(guild_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT custom_message FROM settings
    WHERE guild_id = ?
    """, (guild_id,))

    data = cur.fetchone()
    conn.close()

    return data[0] if data and data[0] else None


def add_active_role(guild_id, user_id, role_name, remove_time):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT OR REPLACE INTO active_roles
    VALUES (?, ?, ?, ?)
    """, (guild_id, user_id, role_name, remove_time))

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
    VALUES (?, ?, ?)
    """, (guild_id, user_id, today))

    conn.commit()
    conn.close()


# ================= HELPERS =================
def parse_date(text):
    match = re.match(r"^(\d{1,2})[\/\-\s](\d{1,2})[\/\-\s](\d{4})$", text.strip())

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

    if year < 1900 or year > datetime.now().year:
        return None

    try:
        datetime(year, month, day)
        return day, month, year
    except ValueError:
        return None


def calculate_age(year):
    return datetime.now().year - year


def get_role_name(role_type):
    role_type = role_type.lower()

    if role_type == "boy":
        return ROLE_BOY
    if role_type == "girl":
        return ROLE_GIRL

    return ROLE_GANG


def valid_role_type(role_type):
    role_type = role_type.lower()

    if role_type not in ["gang", "boy", "girl"]:
        return "gang"

    return role_type


def days_until_birthday(day, month):
    today = datetime.now().date()

    try:
        bday = datetime(today.year, month, day).date()
    except ValueError:
        return 9999

    if bday < today:
        bday = datetime(today.year + 1, month, day).date()

    return (bday - today).days


async def get_or_create_role(guild, role_name):
    role = discord.utils.get(guild.roles, name=role_name)

    if role:
        return role

    return await guild.create_role(name=role_name, reason="Birthday role created by bot")


async def get_birthday_channel(guild):
    channel_id = get_birthday_channel_id(guild.id)

    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            return channel

    if guild.system_channel:
        return guild.system_channel

    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            return channel

    return None


def fit_text(draw, text, font_path, max_width, start_size, min_size=22):
    size = start_size

    while size >= min_size:
        try:
            font = ImageFont.truetype(font_path, size)
        except:
            font = ImageFont.load_default()

        box = draw.textbbox((0, 0), text, font=font)
        width = box[2] - box[0]

        if width <= max_width:
            return font

        size -= 2

    return ImageFont.load_default()


async def circular_image_from_asset(asset, size):
    image_bytes = await asset.replace(size=256).read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    image = image.resize((size, size))

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)

    return image, mask


# ================= CLEAR PREMIUM BANNER =================
async def make_card(member, age_text):
    width = 1280
    height = 640

    img = Image.new("RGB", (width, height), (35, 20, 80))
    draw = ImageDraw.Draw(img)

    # Smooth readable gradient
    for y in range(height):
        r = int(35 + (y / height) * 65)
        g = int(25 + (y / height) * 35)
        b = int(95 + (y / height) * 85)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Soft glow background
    glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow = ImageDraw.Draw(glow_layer)

    glow.ellipse((-120, -120, 360, 360), fill=(255, 105, 180, 120))
    glow.ellipse((930, -90, 1390, 370), fill=(255, 210, 80, 115))
    glow.ellipse((850, 360, 1300, 790), fill=(80, 240, 220, 80))

    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(28))
    img = Image.alpha_composite(img.convert("RGBA"), glow_layer).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Fonts
    try:
        title_path = "arialbd.ttf"
        regular_path = "arial.ttf"

        title_font = ImageFont.truetype(title_path, 76)
        name_font = fit_text(draw, member.display_name, title_path, 610, 64, 34)
        age_font = ImageFont.truetype(regular_path, 36)
        small_font = ImageFont.truetype(regular_path, 27)
        server_font = fit_text(draw, member.guild.name, title_path, 700, 34, 22)
        tag_font = ImageFont.truetype(title_path, 26)
    except:
        title_font = ImageFont.load_default()
        name_font = ImageFont.load_default()
        age_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
        server_font = ImageFont.load_default()
        tag_font = ImageFont.load_default()

    # Main card shadow
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)

    shadow_draw.rounded_rectangle(
        (92, 92, 1188, 548),
        radius=45,
        fill=(0, 0, 0, 130)
    )

    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img.convert("RGBA"), shadow).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Main white card
    draw.rounded_rectangle(
        (90, 80, 1190, 540),
        radius=45,
        fill=(255, 255, 255),
        outline=(255, 220, 90),
        width=6
    )

    # Header bar
    draw.rounded_rectangle(
        (90, 80, 1190, 170),
        radius=45,
        fill=(255, 82, 155)
    )
    draw.rectangle((90, 125, 1190, 170), fill=(255, 82, 155))

    # Server logo
    logo_x, logo_y, logo_size = 125, 98, 58

    draw.ellipse(
        (logo_x - 7, logo_y - 7, logo_x + logo_size + 7, logo_y + logo_size + 7),
        fill=(255, 255, 255)
    )

    try:
        if member.guild.icon:
            server_icon, server_mask = await circular_image_from_asset(member.guild.icon, logo_size)
            img.paste(server_icon, (logo_x, logo_y), server_mask)
        else:
            draw.ellipse((logo_x, logo_y, logo_x + logo_size, logo_y + logo_size), fill=(90, 70, 150))
            draw.text((logo_x + 18, logo_y + 14), "S", font=tag_font, fill=(255, 255, 255))
    except:
        draw.ellipse((logo_x, logo_y, logo_x + logo_size, logo_y + logo_size), fill=(90, 70, 150))

    # Server name in header
    # ===== CLEAR SERVER NAME =====

server_name = member.guild.name.upper()

# Background glow for readability
for offset in range(8, 0, -2):
    draw.text(
        (205 - offset, 108 - offset),
        server_name,
        font=server_font,
        fill=(120, 30, 160)
    )

# Main clean text
draw.text(
    (205, 110),
    server_name,
    font=server_font,
    fill=(255, 255, 255)
)

# Small underline
draw.rounded_rectangle(
    (205, 155, 205 + min(len(server_name) * 18, 500), 162),
    radius=5,
    fill=(255, 215, 0)
)

    draw.text(
        (940, 116),
        "BIRTHDAY CELEBRATION",
        font=tag_font,
        fill=(255, 255, 255)
    )

    # Clean light confetti only inside card
    for _ in range(45):
        x = random.randint(140, 1130)
        y = random.randint(195, 500)
        color = random.choice([
            (255, 215, 0),
            (255, 120, 180),
            (120, 210, 255),
            (160, 130, 255),
        ])
        size = random.randint(4, 8)
        draw.rounded_rectangle((x, y, x + size + 5, y + size), radius=3, fill=color)

    # Avatar area
    avatar_x, avatar_y, avatar_size = 145, 245, 210

    draw.ellipse(
        (avatar_x - 16, avatar_y - 16, avatar_x + avatar_size + 16, avatar_y + avatar_size + 16),
        fill=(255, 215, 0)
    )
    draw.ellipse(
        (avatar_x - 7, avatar_y - 7, avatar_x + avatar_size + 7, avatar_y + avatar_size + 7),
        fill=(255, 255, 255)
    )

    try:
        avatar, avatar_mask = await circular_image_from_asset(member.display_avatar, avatar_size)
        img.paste(avatar, (avatar_x, avatar_y), avatar_mask)
    except:
        draw.ellipse((avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size), fill=(230, 230, 230))

    # Text section
    draw.text(
        (410, 215),
        "🎂 HAPPY BIRTHDAY",
        font=title_font,
        fill=(35, 30, 70)
    )

    draw.text(
        (415, 315),
        member.display_name,
        font=name_font,
        fill=(255, 70, 145)
    )

    draw.text(
        (415, 395),
        age_text,
        font=age_font,
        fill=(70, 70, 95)
    )

    draw.text(
        (415, 455),
        "✨ Wishing you happiness, success & endless joy ✨",
        font=small_font,
        fill=(105, 105, 125)
    )

    draw.text(
        (415, 495),
        f"With love from {member.guild.name} community 💜",
        font=small_font,
        fill=(120, 120, 145)
    )

    # Small cake decoration
    draw.text((1050, 230), "🎁", font=title_font, fill=(35, 30, 70))
    draw.text((1080, 320), "🎉", font=title_font, fill=(35, 30, 70))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", quality=100)
    buffer.seek(0)

    return discord.File(buffer, filename="birthday_banner.png")


# ================= BIRTHDAY ACTION =================
async def give_role_and_wish(guild, member, year, role_type, private):
    if already_wished(guild.id, member.id):
        return False

    role_name = get_role_name(role_type)
    role = await get_or_create_role(guild, role_name)

    try:
        await member.add_roles(role, reason="Birthday role for 24 hours")
    except Exception as e:
        print(f"Role add error: {e}")
        return False

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
            username=member.display_name,
            age=age,
            role=role_name
        )

        age_text = f"Congratulations for being {age} years old!"

    card = await make_card(member, age_text)
    channel = await get_birthday_channel(guild)

    if channel:
        await channel.send(content=message, file=card)

    remove_time = datetime.now() + timedelta(hours=24)
    add_active_role(guild.id, member.id, role_name, remove_time.isoformat())
    mark_wished(guild.id, member.id)

    return True


# ================= EVENTS =================
@bot.event
async def on_ready():
    init_db()

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Slash sync error: {e}")

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
            f"Send your birthday in this format:\n"
            f"`DD/MM/YYYY`\n\n"
            f"Example: `25/12/2004`"
        )

        def check(msg):
            return msg.author == member and isinstance(msg.channel, discord.DMChannel)

        msg = await bot.wait_for("message", timeout=300, check=check)
        parsed = parse_date(msg.content)

        if not parsed:
            await member.send("❌ Invalid format. Use `/setbirthday DD/MM/YYYY` in server.")
            return

        day, month, year = parsed
        save_birthday(member.guild.id, member.id, day, month, year, "gang", 0)

        await member.send(f"✅ Birthday saved: **{day}/{month}/{year}** 🎂")

        today = datetime.now()

        if day == today.day and month == today.month:
            await give_role_and_wish(member.guild, member, year, "gang", 0)

    except asyncio.TimeoutError:
        try:
            await member.send("⏰ Time expired. Use `/setbirthday DD/MM/YYYY` later.")
        except:
            pass
    except Exception as e:
        print(f"Join DM error: {e}")


# ================= SLASH COMMANDS =================
@bot.tree.command(name="setbirthday", description="Set your birthday")
async def setbirthday(
    interaction: discord.Interaction,
    date: str,
    role_type: str = "gang",
    private: bool = False
):
    parsed = parse_date(date)

    if not parsed:
        await interaction.response.send_message(
            "❌ Invalid format. Use `DD/MM/YYYY`, example: `25/12/2004`",
            ephemeral=True
        )
        return

    role_type = valid_role_type(role_type)
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
        await give_role_and_wish(
            interaction.guild,
            interaction.user,
            year,
            role_type,
            1 if private else 0
        )


@bot.tree.command(name="mybirthday", description="Check your saved birthday")
async def mybirthday(interaction: discord.Interaction):
    data = get_user_birthday(interaction.guild.id, interaction.user.id)

    if not data:
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
        f"🎭 Role: **{role_type}**\n"
        f"🔒 Private age: **{bool(private)}**",
        ephemeral=True
    )


@bot.tree.command(name="removebirthday", description="Remove your saved birthday")
async def removebirthday(interaction: discord.Interaction):
    delete_user_birthday(interaction.guild.id, interaction.user.id)

    await interaction.response.send_message(
        "✅ Your birthday has been removed.",
        ephemeral=True
    )


@bot.tree.command(name="upcomingbirthdays", description="Show upcoming birthdays")
async def upcomingbirthdays(interaction: discord.Interaction):
    data = get_all_birthdays(interaction.guild.id)

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
            next_age = datetime.now().year - year
            if left != 0:
                next_age += 1
            msg += f"• {name} — **{day}/{month}** — turning **{next_age}** — in **{left} days**\n"

    await interaction.response.send_message(msg)


@bot.tree.command(name="nextbirthday", description="Show your birthday countdown")
async def nextbirthday(interaction: discord.Interaction):
    data = get_user_birthday(interaction.guild.id, interaction.user.id)

    if not data:
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
async def setbirthdaychannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    set_birthday_channel(interaction.guild.id, channel.id)

    await interaction.response.send_message(
        f"✅ Birthday channel set to {channel.mention}",
        ephemeral=True
    )


@bot.tree.command(name="setwishmessage", description="Admin: set custom birthday wish")
async def setwishmessage(interaction: discord.Interaction, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    set_custom_message(interaction.guild.id, message)

    await interaction.response.send_message(
        "✅ Custom wish saved.\n"
        "Use placeholders: `{mention}`, `{username}`, `{age}`, `{role}`",
        ephemeral=True
    )


@bot.tree.command(name="testbirthday", description="Admin: test birthday wish")
async def testbirthday(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    data = get_user_birthday(interaction.guild.id, member.id)

    if not data:
        await interaction.response.send_message("❌ This user has no saved birthday.", ephemeral=True)
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
        f"✅ Birthday test sent for {member.mention}",
        ephemeral=True
    )


@bot.tree.command(name="birthdayhelp", description="Show birthday bot commands")
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
        "**Custom placeholders:** `{mention}`, `{username}`, `{age}`, `{role}`"
    )


# ================= TASKS =================
@tasks.loop(hours=24)
async def birthday_checker():
    today = datetime.now()

    birthdays = get_today_birthdays(today.day, today.month)

    for guild_id, user_id, year, role_type, private in birthdays:
        guild = bot.get_guild(guild_id)

        if not guild:
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

        role = discord.utils.get(guild.roles, name=role_name)

        if not role:
            continue

        try:
            member = await guild.fetch_member(user_id)

            if role in member.roles:
                await member.remove_roles(role, reason="Birthday role expired")
        except:
            pass

        cur.execute("""
        DELETE FROM active_roles
        WHERE guild_id = ? AND user_id = ? AND role_name = ?
        """, (guild_id, user_id, role_name))

    conn.commit()
    conn.close()


@role_remover.before_loop
async def before_role_remover():
    await bot.wait_until_ready()


bot.run(TOKEN)
