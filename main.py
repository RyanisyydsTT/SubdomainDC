import nextcord
from nextcord.ext import commands
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

intents = nextcord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Cloudflare API configuration
CLOUDFLARE_API_ENDPOINT = "https://api.cloudflare.com/client/v4"
ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

# Load or create the JSON file
def load_user_data():
    if os.path.exists('user_data.json'):
        with open('user_data.json', 'r') as f:
            return json.load(f)
    return {}

def save_user_data(data):
    with open('user_data.json', 'w') as f:
        json.dump(data, f)

user_data = load_user_data()

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')

def check_subdomain_availability(subdomain):
    url = f"{CLOUDFLARE_API_ENDPOINT}/zones/{ZONE_ID}/dns_records"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    params = {"name": subdomain}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return len(response.json()["result"]) == 0
    return False

def create_dns_record(record_type, name, content, priority=None):
    url = f"{CLOUDFLARE_API_ENDPOINT}/zones/{ZONE_ID}/dns_records"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "type": record_type,
        "name": name,
        "content": content,
        "ttl": 1
    }
    if priority is not None:
        data["priority"] = priority
    
    response = requests.post(url, headers=headers, json=data)
    return response.status_code == 200

@bot.slash_command(name="register", description="Register a subdomain or add records to an existing one")
async def register(interaction: nextcord.Interaction):
    user_id = str(interaction.user.id)
    
    class SubdomainModal(nextcord.ui.Modal):
        def __init__(self):
            super().__init__("Subdomain Registration")
            self.record_type = nextcord.ui.TextInput(label="Record Type", placeholder="e.g., A, CNAME, SRV")
            self.record_value = nextcord.ui.TextInput(label="Record Value", placeholder="e.g., 192.0.2.1")
            self.record_name = nextcord.ui.TextInput(label="Record Name", placeholder=f"e.g., subdomain{os.getenv("DOMAIN_SUFFIX")}")
            self.add_item(self.record_type)
            self.add_item(self.record_value)
            self.add_item(self.record_name)

        async def callback(self, interaction: nextcord.Interaction):
            user_id = str(interaction.user.id)
            subdomain = self.record_name.value

            # Check if the subdomain already exists
            if check_subdomain_availability(subdomain):
                # New subdomain
                if user_id not in user_data:
                    user_data[user_id] = []
                if len(user_data[user_id]) >= 5:
                    await interaction.response.send_message("You have reached the maximum limit of 5 subdomains.", ephemeral=True)
                    return
                user_data[user_id].append(subdomain)
            else:
                # Existing subdomain
                if not any(subdomain in subdomains for subdomains in user_data.values()):
                    await interaction.response.send_message("This subdomain is already registered by another user.", ephemeral=True)
                    return
                if subdomain not in user_data.get(user_id, []):
                    await interaction.response.send_message("You don't own this subdomain.", ephemeral=True)
                    return
            if os.getenv("DOMAIN_SUFFIX") not in subdomain:
                subdomain_formatted = subdomain + os.getenv("DOMAIN_SUFFIX")
            if create_dns_record(self.record_type.value, subdomain, self.record_value.value):
                save_user_data(user_data)
                await interaction.response.send_message(f"Record for {subdomain_formatted} has been added successfully!", ephemeral=True)
            else:
                await interaction.response.send_message("Failed to add the record. Please try again later.", ephemeral=True)

    modal = SubdomainModal()
    await interaction.response.send_modal(modal)

@bot.slash_command(name="list", description="List user's subdomains")
async def list_subdomains(interaction: nextcord.Interaction, discord_id: str):
    if os.getenv("ADMIN_ROLEID") not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    if discord_id in user_data:
        subdomains = user_data[discord_id]
        embed = nextcord.Embed(title=f"Subdomains for user {discord_id}", color=0x00ff00)
        for subdomain in subdomains:
            embed.add_field(name="Subdomain", value=subdomain, inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"No subdomains found for user {discord_id}", ephemeral=True)

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
