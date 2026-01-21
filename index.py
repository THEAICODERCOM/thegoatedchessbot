import discord
import re
import ssl
import pathlib
import aiohttp
from discord import app_commands
from discord.ext import commands

# GLOBAL SSL BYPASS for macOS
class UnverifiedConnector(aiohttp.TCPConnector):
    def __init__(self, *args, **kwargs):
        kwargs['ssl'] = False
        super().__init__(*args, **kwargs)

aiohttp.TCPConnector = UnverifiedConnector

# Read token
token_path = pathlib.Path(__file__).with_name("token.txt")
token_raw = token_path.read_text().strip()
token = "".join(token_raw.split()).replace('"', '').replace("'", "")

# --- HARDCODED CONFIGURATION ---
ALLOWED_MOD_ROLE_ID = 1437874945722945608
PREVIEW_CHANNEL_ID = 1274914201206394979

# Role -> Points mapping
ROLE_POINTS = {
    1437864107201134835: 1,  # 1 Point role
    1437863482476199976: 3,  # 3 Points role A
    1275870420129677352: 3,  # 3 Points role B
    1274914201206394975: 2   # 2 Points role
}

# Target channel options for the slash command
TARGET_CHANNELS = {
    "Announcements": 1462656663419883612,
    "Information": 1274914201563037791
}
# -------------------------------

intents = discord.Intents.default()
intents.members = False
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)

# Store preview states: { message_id: { "text": str, "target_channel_id": int, "points": int, "voters": set } }
message_states = {}

class AcceptView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="accept_button")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = message_states.get(interaction.message.id)
        if not state:
            await interaction.response.send_message("This preview has expired or is invalid.", ephemeral=True)
            return

        if interaction.user.id in state["voters"]:
            await interaction.response.send_message("You have already voted on this announcement.", ephemeral=True)
            return

        # Calculate points based on user's roles (Highest role overwrites others)
        user_points = 0
        for role in interaction.user.roles:
            pts = ROLE_POINTS.get(role.id, 0)
            if pts > user_points:
                user_points = pts

        if user_points <= 0:
            await interaction.response.send_message("You do not have a role permitted to approve announcements.", ephemeral=True)
            return

        state["voters"].add(interaction.user.id)
        state["points"] += user_points

        if state["points"] >= 3:
            channel = bot.get_channel(state["target_channel_id"])
            if channel:
                await channel.send(state["text"])
                button.disabled = True
                button.label = f"Approved ({state['points']} pts)"
                button.style = discord.ButtonStyle.secondary
                await interaction.message.edit(view=self)
                message_states.pop(interaction.message.id, None)
                await interaction.response.send_message(f"Threshold reached! Your {user_points} pts sent it to {channel.mention}.", ephemeral=True)
                return
        
        await interaction.response.send_message(f"Vote added! You contributed {user_points} points. Current total: {state['points']}/3", ephemeral=True)

class AnnouncementModal(discord.ui.Modal, title='Create Announcement'):
    def __init__(self, target_channel_id):
        super().__init__()
        self.target_channel_id = target_channel_id

    text_input = discord.ui.TextInput(
        label='Announcement Content',
        style=discord.TextStyle.paragraph,
        placeholder='Type your announcement message here...',
        required=True,
        min_length=1,
        max_length=2000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        preview_channel = bot.get_channel(PREVIEW_CHANNEL_ID)
        if not preview_channel:
            await interaction.response.send_message("Error: Preview channel not found. Please check the bot's configuration.", ephemeral=True)
            return

        content = self.text_input.value
        target_channel = bot.get_channel(self.target_channel_id)
        target_name = target_channel.name if target_channel else "Unknown"

        embed = discord.Embed(
            title="Announcement Preview",
            description=content,
            color=0x2B2D31
        )
        embed.set_footer(text=f"Target: #{target_name} | Needs 3 points to send")
        
        view = AcceptView()
        preview_msg = await preview_channel.send(embed=embed, view=view)
        
        message_states[preview_msg.id] = {
            "text": content,
            "target_channel_id": self.target_channel_id,
            "points": 0,
            "voters": set()
        }
        await interaction.response.send_message(f"Preview sent to {preview_channel.mention}!", ephemeral=True)

@bot.tree.command(name="announcement", description="Send an announcement for approval")
@app_commands.describe(destination="Where should the announcement be sent after approval?")
@app_commands.choices(destination=[
    app_commands.Choice(name="Announcements", value="1462656663419883612"),
    app_commands.Choice(name="Information", value="1274914201563037791")
])
async def announcement(interaction: discord.Interaction, destination: app_commands.Choice[str]):
    # Hardcoded role check
    has_role = any(role.id == ALLOWED_MOD_ROLE_ID for role in interaction.user.roles)
    if not has_role and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)
        return

    await interaction.response.send_modal(AnnouncementModal(int(destination.value)))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()
    print("Bot is ready and commands are synced!")

if __name__ == "__main__":
    bot.run(token)
