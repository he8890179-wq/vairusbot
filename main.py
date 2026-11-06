import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime, random, aiosqlite, json


intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Database =====
async def init_db():
    async with aiosqlite.connect("database.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS levels (user_id INTEGER PRIMARY KEY, xp INTEGER, level INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS warns (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, reason TEXT, mod_id INTEGER, time TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admin_roles (role_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS automod_words (word TEXT PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS auto_messages (channel_id INTEGER, message TEXT)")
        await db.commit()

async def get_config(key):
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT value FROM config WHERE key=?", (key,)) as cur:
            r = await cur.fetchone()
            return int(r[0]) if r else None

async def set_config(key, val):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT OR REPLACE INTO config VALUES (?,?)", (key, str(val)))
        await db.commit()

def is_allowed():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator: return True
        async with aiosqlite.connect("database.db") as db:
            async with db.execute("SELECT role_id FROM admin_roles") as cur:
                rows = await cur.fetchall()
        if not rows: return True
        allowed = [r[0] for r in rows]
        if any(r.id in allowed for r in interaction.user.roles): return True
        await interaction.response.send_message("❌ مالكش صلاحية - خلي الادمن يعملك /setup_admin", ephemeral=True)
        return False
    return app_commands.check(predicate)

# ===== Views =====
class TicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.green, custom_id="ticket_all")
    async def open(self, interaction, button):
        cat_id = await get_config("ticket_category")
        category = interaction.guild.get_channel(cat_id) if cat_id else None
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True), interaction.guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)}
        async with aiosqlite.connect("database.db") as db:
            async with db.execute("SELECT role_id FROM admin_roles") as cur:
                async for (rid,) in cur:
                    role = interaction.guild.get_role(rid)
                    if role: overwrites[role] = discord.PermissionOverwrite(view_channel=True)
        ch = await interaction.guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites, category=category)
        await ch.send(f"{interaction.user.mention} تكتك اتفتح - الادارة هترد")
        await interaction.response.send_message(f"تم {ch.mention}", ephemeral=True)

class ApplyModal(discord.ui.Modal, title="نظام التقديم"):
    q1 = discord.ui.TextInput(label="اسمك وسنك؟")
    q2 = discord.ui.TextInput(label="خبرتك؟", style=discord.TextStyle.paragraph)
    q3 = discord.ui.TextInput(label="ليه عايز تبقي اداري؟", style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction):
        log_id = await get_config("log")
        log = interaction.guild.get_channel(log_id) if log_id else interaction.channel
        embed = discord.Embed(title="📝 تقديم جديد", color=0x00ff00, timestamp=datetime.datetime.now())
        embed.add_field(name="المتقدم", value=interaction.user.mention)
        embed.add_field(name="الاسم والسن", value=self.q1.value, inline=False)
        embed.add_field(name="الخبرة", value=self.q2.value, inline=False)
        embed.add_field(name="السبب", value=self.q3.value, inline=False)
        await log.send(embed=embed)
        await interaction.response.send_message("تقديمك اتبعت للادارة ✅", ephemeral=True)

class ApplyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="التقديم 📝", style=discord.ButtonStyle.blurple, custom_id="apply_all")
    async def apply(self, interaction, button): await interaction.response.send_modal(ApplyModal())

@bot.event
async def on_ready():
    await init_db()
    bot.add_view(TicketView())
    bot.add_view(ApplyView())
    await bot.tree.sync()
    auto_msg_loop.start()
    print(f"ONLINE {bot.user} - كل الانظمة جاهزة")

@bot.event
async def on_member_join(member):
    wid = await get_config("welcome")
    if wid:
        ch = bot.get_channel(wid)
        if ch:
            embed = discord.Embed(title=f"نورت {member.guild.name}!", description=f"اهلا {member.mention} ❤️ انت العضو رقم {member.guild.member_count}", color=0x2b2d31)
            embed.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=embed)
    aid = await get_config("autorole")
    if aid:
        role = member.guild.get_role(aid)
        if role:
            try: await member.add_roles(role)
            except: pass
    log_id = await get_config("log")
    if log_id:
        log = bot.get_channel(log_id)
        if log: await log.send(embed=discord.Embed(description=f"📥 {member.mention} دخل", color=0x00ff00, timestamp=datetime.datetime.now()))

@bot.event
async def on_member_remove(member):
    log_id = await get_config("log")
    if log_id:
        log = bot.get_channel(log_id)
        if log: await log.send(embed=discord.Embed(description=f"📤 {member.mention} خرج", color=0xff0000))

@bot.event
async def on_message(message):
    if message.author.bot: return
    # اوتو مود
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT word FROM automod_words") as cur:
            words = [r[0] async for r in cur]
    if any(w.lower() in message.content.lower() for w in words):
        await message.delete()
        await message.channel.send(f"{message.author.mention} ممنوع الكلمة دي!", delete_after=5)
        return
    # ليفل
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT xp, level FROM levels WHERE user_id=?", (message.author.id,)) as cur:
            row = await cur.fetchone()
            xp = (row[0]+random.randint(5,15) if row else 10)
            lvl = (row[1] if row else 0)
            new_lvl = int(xp//100)
            if new_lvl > lvl:
                lid = await get_config("level")
                ch = bot.get_channel(lid) if lid else message.channel
                await ch.send(f"🎉 {message.author.mention} وصل ليفل **{new_lvl}**!")
            await db.execute("INSERT OR REPLACE INTO levels VALUES (?,?,?)", (message.author.id, xp, new_lvl))
            await db.commit()
    await bot.process_commands(message)

@tasks.loop(minutes=60)
async def auto_msg_loop():
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT channel_id, message FROM auto_messages") as cur:
            async for cid, msg in cur:
                ch = bot.get_channel(cid)
                if ch:
                    try: await ch.send(msg)
                    except: pass

# ===== SETUP - كلها سلاش =====
@bot.tree.command(name="setup_admin", description="اضافة رتبة تتحكم في البوت")
@app_commands.checks.has_permissions(administrator=True)
async def setup_admin(interaction: discord.Interaction, role: discord.Role):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT OR REPLACE INTO admin_roles VALUES (?)", (role.id,))
        await db.commit()
    await interaction.response.send_message(f"✅ {role.mention} بقت تتحكم", ephemeral=True)

@bot.tree.command(name="setup_remove_admin", description="سحب رتبة من التحكم")
@app_commands.checks.has_permissions(administrator=True)
async def setup_remove_admin(interaction: discord.Interaction, role: discord.Role):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("DELETE FROM admin_roles WHERE role_id=?", (role.id,))
        await db.commit()
    await interaction.response.send_message(f"❌ سحبت {role.mention}", ephemeral=True)

@bot.tree.command(name="setup_welcome", description="تحديد روم الترحيب")
@is_allowed()
async def setup_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_config("welcome", channel.id)
    await interaction.response.send_message(f"✅ الترحيب {channel.mention}", ephemeral=True)

@bot.tree.command(name="setup_logs", description="تحديد روم اللوجات")
@is_allowed()
async def setup_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_config("log", channel.id)
    await interaction.response.send_message(f"✅ اللوجات {channel.mention}", ephemeral=True)

@bot.tree.command(name="setup_level", description="تحديد روم الليفل")
@is_allowed()
async def setup_level(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_config("level", channel.id)
    await interaction.response.send_message(f"✅ الليفل {channel.mention}", ephemeral=True)

@bot.tree.command(name="setup_autorole", description="تحديد اوتو رول")
@is_allowed()
async def setup_autorole(interaction: discord.Interaction, role: discord.Role):
    await set_config("autorole", role.id)
    await interaction.response.send_message(f"✅ الاوتو رول {role.mention}", ephemeral=True)

@bot.tree.command(name="setup_tickets", description="تحديد كاتيجوري التكتات")
@is_allowed()
async def setup_tickets(interaction: discord.Interaction, category: discord.CategoryChannel):
    await set_config("ticket_category", category.id)
    await interaction.response.send_message(f"✅ كاتيجوري {category.name}", ephemeral=True)

# ===== MODERATION =====
@bot.tree.command(name="ban", description="باند")
@is_allowed()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str="لا يوجد"):
    await member.ban(reason=reason)
    await interaction.response.send_message(embed=discord.Embed(title="🔨 Ban", description=f"{member.mention} - {reason}", color=0xff0000))
    try: await member.send(f"باند من {interaction.guild.name}: {reason}")
    except: pass

@bot.tree.command(name="kick", description="كيك")
@is_allowed()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str="لا يوجد"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 طردت {member.mention}")

@bot.tree.command(name="timeout", description="تايم اوت")
@is_allowed()
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str="لا يوجد"):
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    await interaction.response.send_message(f"⏰ {member.mention} تايم {minutes}د - {reason}")

@bot.tree.command(name="unmute", description="فك التايم اوت / الميوت")
@is_allowed()
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(f"✅ فكيت {member.mention}")

@bot.tree.command(name="purge", description="مسح رسائل 1-500")
@is_allowed()
async def purge(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=min(amount,500))
    await interaction.followup.send(f"مسحت {len(deleted)} رسالة ✅", ephemeral=True)

@bot.tree.command(name="role_give", description="اعطاء رتبة - رول جيف")
@is_allowed()
async def role_give(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    await interaction.response.send_message(f"✅ اديت {role.mention} لـ {member.mention}", ephemeral=True)

@bot.tree.command(name="role_remove", description="سحب رتبة - رول ريموف")
@is_allowed()
async def role_remove(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    await interaction.response.send_message(f"❌ سحبت {role.mention} من {member.mention}", ephemeral=True)

@bot.tree.command(name="move", description="نقل عضو بين الكولات - موف")
@is_allowed()
async def move(interaction: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
    await member.move_to(channel)
    await interaction.response.send_message(f"نقلت {member.mention} لـ {channel.name}")

@bot.tree.command(name="warn", description="نظام الوارنات - اعطاء وارن")
@is_allowed()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT INTO warns (user_id, reason, mod_id, time) VALUES (?,?,?,?)", (member.id, reason, interaction.user.id, str(datetime.datetime.now().date())))
        await db.commit()
    await interaction.response.send_message(f"⚠️ {member.mention} وارن: {reason}")

@bot.tree.command(name="warns", description="عرض وارنات عضو")
@is_allowed()
async def warns(interaction: discord.Interaction, member: discord.Member):
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT reason, time, id FROM warns WHERE user_id=?", (member.id,)) as cur:
            rows = await cur.fetchall()
    if not rows: await interaction.response.send_message("معندوش وارنات")
    else:
        embed = discord.Embed(title=f"وارنات {member}", color=0xffa500)
        for r,t,i in rows: embed.add_field(name=f"#{i} - {t}", value=r, inline=False)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="clearwarns", description="مسح كل وارنات عضو")
@is_allowed()
async def clearwarns(interaction: discord.Interaction, member: discord.Member):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("DELETE FROM warns WHERE user_id=?", (member.id,))
        await db.commit()
    await interaction.response.send_message(f"مسحت وارنات {member.mention}")

# ===== رسائل وادارة =====
@bot.tree.command(name="say", description="البوت يبعت رسالة في السيرفر")
@is_allowed()
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message("تم", ephemeral=True)
    await interaction.channel.send(message)

@bot.tree.command(name="embed", description="رسالة امبد")
@is_allowed()
async def embed_cmd(interaction: discord.Interaction, title: str, description: str, channel: discord.TextChannel = None):
    ch = channel or interaction.channel
    embed = discord.Embed(title=title, description=description, color=0x2b2d31, timestamp=datetime.datetime.now())
    embed.set_footer(text=f"بواسطة {interaction.user}")
    await ch.send(embed=embed)
    await interaction.response.send_message(f"بعت الامبد في {ch.mention}", ephemeral=True)

@bot.tree.command(name="dm", description="البوت يبعت DM لشخص")
@is_allowed()
async def dm(interaction: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f"📩 رسالة من {interaction.guild.name}: {message}")
        await interaction.response.send_message(f"بعت DM لـ {member.mention}", ephemeral=True)
    except: await interaction.response.send_message("قافل الـ DM", ephemeral=True)

@bot.tree.command(name="automod_add", description="اضافة كلمة للاوتو مود")
@is_allowed()
async def automod_add(interaction: discord.Interaction, word: str):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT OR REPLACE INTO automod_words VALUES (?)", (word.lower(),))
        await db.commit()
    await interaction.response.send_message(f"✅ ضفت كلمة {word} للاوتو مود", ephemeral=True)

@bot.tree.command(name="automod_remove", description="حذف كلمة من الاوتو مود")
@is_allowed()
async def automod_remove(interaction: discord.Interaction, word: str):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("DELETE FROM automod_words WHERE word=?", (word.lower(),))
        await db.commit()
    await interaction.response.send_message(f"❌ شلت {word}", ephemeral=True)

@bot.tree.command(name="auto_message", description="رسالة اوتو كل ساعة في روم")
@is_allowed()
async def auto_message(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT INTO auto_messages VALUES (?,?)", (channel.id, message))
        await db.commit()
    await interaction.response.send_message(f"✅ هبعت كل ساعة في {channel.mention}: {message}", ephemeral=True)

# ===== تكتات وتقديمات =====
@bot.tree.command(name="ticket_panel", description="بانل تكتات بكليك")
@is_allowed()
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="الدعم الفني 🎫", description="دوس على الزرار تحت لفتح تذكرة وهيجيلك الادارة", color=0x00ff00)
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ عملت بانل التكتات", ephemeral=True)

@bot.tree.command(name="apply_panel", description="بانل تقديمات بكليك")
@is_allowed()
async def apply_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="التقديم للإدارة 📝", description="دوس على الزرار للتقديم وهيتبعت للوج", color=0x0000ff)
    await interaction.channel.send(embed=embed, view=ApplyView())
    await interaction.response.send_message("✅ عملت بانل التقديمات", ephemeral=True)

# ===== ليفل والالعاب =====
@bot.tree.command(name="rank", description="نظام ليفل - شوف ليفلك")
async def rank(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT xp, level FROM levels WHERE user_id=?", (member.id,)) as cur:
            row = await cur.fetchone()
    if not row: await interaction.response.send_message("لسه معندكش XP - اتكلم شوية")
    else: await interaction.response.send_message(f"🏆 {member.mention} | Level **{row[1]}** | XP **{row[0]}**")

@bot.tree.command(name="8ball", description="لعبة - اسأل البوت")
async def eightball(interaction: discord.Interaction, question: str):
    await interaction.response.send_message(f"🎱 **{question}**\n➡️ {random.choice(['اكيد','مستحيل','اسأل تاني','ايوه','لا','100%','فكك'])}")

@bot.tree.command(name="coinflip", description="لعبة - طرة ولا نقش")
async def coinflip(interaction: discord.Interaction):
    await interaction.response.send_message(f"🪙 طلعت **{random.choice(['طرة','نقش'])}**!")

@bot.tree.command(name="rps", description="لعبة - حجر ورقة مقص")
async def rps(interaction: discord.Interaction, choice: str):
    bot_choice = random.choice(["حجر","ورقة","مقص"])
    await interaction.response.send_message(f"انت: {choice} | انا: {bot_choice}")

@bot.tree.command(name="help", description="بانل شرح كل امر بيعمل ايه")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 لوحة الأوامر الكاملة - كله سلاش", color=0x2b2d31)
    embed.add_field(name="⚙️ Setup - الاعداد", value="`/setup_admin /setup_remove_admin /setup_welcome /setup_logs /setup_level /setup_autorole /setup_tickets`", inline=False)
    embed.add_field(name="🛡️ Moderation - موديريشن", value="`/ban /kick /timeout /unmute /purge 500 /role_give /role_remove /move`", inline=False)
    embed.add_field(name="⚠️ Warns - نظام الوارنات", value="`/warn /warns /clearwarns`", inline=False)
    embed.add_field(name="💬 رسائل - امبد و DM", value="`/say /embed /dm /auto_message`", inline=False)
    embed.add_field(name="🎫 Systems - تكتات وتقديمات", value="`/ticket_panel /apply_panel`", inline=False)
    embed.add_field(name="🛡️ AutoMod - اوتو مود", value="`/automod_add /automod_remove`", inline=False)
    embed.add_field(name="🏆 Level & Games - ليفل والعاب", value="`/rank /8ball /coinflip /rps`", inline=False)
    embed.set_footer(text="البوت لا يعمل الا للرتب اللي تعملها بـ /setup_admin")
    await interaction.response.send_message(embed=embed)

bot.run(os.getenv("TOKEN"))