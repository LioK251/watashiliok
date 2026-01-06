import discord
from discord.ext import commands
import re
import os
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
from flask import Flask
from threading import Thread

# ==================== FLASK SERVER FOR UPTIMEROBOT ====================
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/health')
def health():
    return "OK", 200

def run_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server)
    t.daemon = True
    t.start()

# ==================== BOT CONFIGURATION ====================
# Use environment variable for token (NEVER hardcode in production!)
TOKEN = os.environ.get('DISCORD_TOKEN', '')
PREFIX = ""

OUTPUT_MODE = os.environ.get('OUTPUT_MODE', 'embed')  # "image" or "embed"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EMOJI_DIR = os.path.join(SCRIPT_DIR, "Emojis")

# ==================== ITEM DATA ====================
def load_item_data():
    json_path = os.path.join(SCRIPT_DIR, "item_data.json")
    with open(json_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    
    item_values = {}
    emoji_map = {}
    display_names = {}  # Maps alias -> proper display name
    
    for item_id, item_data in data['items'].items():
        value = item_data['value']
        emoji = item_data['emoji']
        names = item_data['names']
        
        # Convert item_id to display name (e.g., "all_seeing_eye" -> "All Seeing Eye")
        display_name = item_id.replace('_', ' ').title()
        
        for name in names:
            item_values[name.lower()] = value
            emoji_map[name.lower()] = emoji
            display_names[name.lower()] = display_name
    
    return item_values, emoji_map, display_names

ITEM_VALUES, EMOJI_MAP, DISPLAY_NAMES = load_item_data()

# ==================== DISCORD BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def parse_items(item_string):
    items = []
    parts = [p.strip() for p in item_string.split(",")]
    
    for part in parts:
        part = part.strip().lower()
        if not part:
            continue
            
        quantity = 1
        match = re.match(r'^(\d+)\s*x?\s+(.+)$', part)
        if match:
            quantity = int(match.group(1))
            part = match.group(2).strip()
        else:
            match = re.match(r'^x\s*(\d+)\s+(.+)$', part)
            if match:
                quantity = int(match.group(1))
                part = match.group(2).strip()
        
        items.append((part, quantity))
    
    return items

def get_item_value(item_name):
    item_name = item_name.lower().strip()
    return ITEM_VALUES.get(item_name)

def get_display_name(item_name):
    """Get the proper display name for an item."""
    item_name_lower = item_name.lower().strip()
    return DISPLAY_NAMES.get(item_name_lower, item_name.title())

def get_item_emoji_path(item_name):
    item_name_lower = item_name.lower().strip()
    emoji_name = EMOJI_MAP.get(item_name_lower, item_name_lower)
    
    for ext in ['.png', '.gif', '.jpg', '.jpeg']:
        path = os.path.join(EMOJI_DIR, emoji_name + ext)
        if os.path.exists(path):
            return path
    
    if os.path.exists(EMOJI_DIR):
        for filename in os.listdir(EMOJI_DIR):
            name_without_ext = os.path.splitext(filename)[0]
            if name_without_ext.lower() == emoji_name.lower():
                return os.path.join(EMOJI_DIR, filename)
    
    return None

def get_item_emoji(item_name, guild_emojis):
    item_name_lower = item_name.lower().strip()
    emoji_name = EMOJI_MAP.get(item_name_lower, item_name_lower)
    
    for emoji in guild_emojis:
        if emoji.name.lower() == emoji_name.lower():
            return str(emoji)
    
    for emoji in bot.emojis:
        if emoji.name.lower() == emoji_name.lower():
            return str(emoji)
    
    display_name = get_display_name(item_name)
    return f"**{display_name}**"

def get_risk_emoji(risk_level):
    if risk_level == "Low":
        return "🟢"
    elif risk_level == "Medium":
        return "🟡"
    else:
        return "🔴"

def calculate_inventory_risk(total_value):
    if total_value < 5000:
        return "Low", (76, 175, 80)
    elif total_value < 20000:
        return "Medium", (255, 193, 7)
    else:
        return "High", (244, 67, 54)

def calculate_trade_risk(your_total, their_total):
    if your_total == 0 or their_total == 0:
        return "Low", (76, 175, 80)
    
    diff_percent = abs(your_total - their_total) / max(your_total, their_total) * 100
    
    if diff_percent < 15:
        return "Low", (76, 175, 80)
    elif diff_percent < 30:
        return "Medium", (255, 193, 7)
    else:
        return "High", (244, 67, 54)

def create_trade_image(username, avatar_url, your_items, their_items, your_total, their_total):
    width = 700
    base_height = 550
    item_height = 55
    max_items = max(len(your_items), len(their_items))
    height = base_height + (max_items * item_height)
    
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    for y in range(height):
        ratio = y / height
        r = int(30 + (20 - 30) * ratio)
        g = int(25 + (25 - 25) * ratio)
        b = int(50 + (60 - 50) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    
    for y in range(100):
        alpha = int(30 * (1 - y / 100))
        draw.line([(0, y), (width, y)], fill=(100, 50, 150, alpha))
    
    try:
        title_font = ImageFont.truetype("arial.ttf", 32)
        header_font = ImageFont.truetype("arial.ttf", 24)
        text_font = ImageFont.truetype("arial.ttf", 20)
        small_font = ImageFont.truetype("arial.ttf", 18)
        value_font = ImageFont.truetype("arial.ttf", 26)
    except:
        title_font = ImageFont.load_default()
        header_font = title_font
        text_font = title_font
        small_font = title_font
        value_font = title_font
    
    border_color = (80, 60, 120, 255)
    draw.rounded_rectangle([(10, 10), (width-10, height-10)], radius=15, outline=border_color, width=2)
    
    draw.rounded_rectangle([(15, 15), (width-15, 85)], radius=10, fill=(50, 40, 80, 200))
    
    draw.text((25, 22), "Trade Comparison", fill=(255, 255, 255), font=title_font)
    draw.text((25, 58), f"@{username}", fill=(180, 180, 200), font=small_font)
    
    net_value = their_total - your_total
    net_percent = abs(net_value) / your_total * 100 if your_total > 0 else 0
    
    if their_total > your_total:
        result_text = "YOU ARE WINNING!"
        result_color = (76, 175, 80)
    elif their_total < your_total:
        result_text = "YOU ARE LOSING!"
        result_color = (244, 67, 54)
    else:
        result_text = "FAIR TRADE!"
        result_color = (255, 193, 7)
    
    col_width = (width - 40) // 2
    y_start = 100
    
    draw.rounded_rectangle([(20, y_start), (20 + col_width - 10, y_start + 45)], radius=8, fill=(60, 50, 100, 200))
    draw.text((30, y_start + 10), "Your Trade", fill=(100, 180, 255), font=header_font)
    
    draw.rounded_rectangle([(20 + col_width, y_start), (width - 20, y_start + 45)], radius=8, fill=(60, 50, 100, 200))
    draw.text((30 + col_width, y_start + 10), "Their Trade", fill=(255, 180, 100), font=header_font)
    
    y_pos = y_start + 55
    icon_size = 42
    
    for i in range(max_items):
        if i < len(your_items):
            item_name, quantity, value = your_items[i]
            emoji_path = get_item_emoji_path(item_name)
            
            draw.rounded_rectangle([(25, y_pos), (20 + col_width - 15, y_pos + 50)], radius=5, fill=(40, 35, 70, 150))
            
            icon_x = 30
            if emoji_path:
                try:
                    emoji_img = Image.open(emoji_path).convert('RGBA')
                    emoji_img = emoji_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
                    img.paste(emoji_img, (icon_x, y_pos + 4), emoji_img)
                except:
                    pass
            
            qty_text = f"x{quantity}"
            draw.text((icon_x + icon_size + 12, y_pos + 14), qty_text, fill=(200, 200, 200), font=text_font)
        
        if i < len(their_items):
            item_name, quantity, value = their_items[i]
            emoji_path = get_item_emoji_path(item_name)
            
            draw.rounded_rectangle([(25 + col_width, y_pos), (width - 25, y_pos + 50)], radius=5, fill=(40, 35, 70, 150))
            
            icon_x = 30 + col_width
            if emoji_path:
                try:
                    emoji_img = Image.open(emoji_path).convert('RGBA')
                    emoji_img = emoji_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
                    img.paste(emoji_img, (icon_x, y_pos + 4), emoji_img)
                except:
                    pass
            
            qty_text = f"x{quantity}"
            draw.text((icon_x + icon_size + 12, y_pos + 14), qty_text, fill=(200, 200, 200), font=text_font)
        
        y_pos += item_height
    
    y_pos += 20
    draw.line([(20, y_pos), (width - 20, y_pos)], fill=(80, 60, 120), width=2)
    y_pos += 20
    
    draw.rounded_rectangle([(20, y_pos), (20 + col_width - 10, y_pos + 55)], radius=8, fill=(40, 35, 70, 200))
    draw.text((30, y_pos + 5), "Your Total", fill=(150, 150, 170), font=small_font)
    your_total_color = (76, 175, 80) if their_total >= your_total else (244, 67, 54)
    draw.text((30, y_pos + 26), f"{your_total:,}", fill=your_total_color, font=value_font)
    
    draw.rounded_rectangle([(20 + col_width, y_pos), (width - 20, y_pos + 55)], radius=8, fill=(40, 35, 70, 200))
    draw.text((30 + col_width, y_pos + 5), "Their Total", fill=(150, 150, 170), font=small_font)
    their_total_color = (244, 67, 54) if their_total >= your_total else (76, 175, 80)
    draw.text((30 + col_width, y_pos + 26), f"{their_total:,}", fill=their_total_color, font=value_font)
    
    y_pos += 65
    
    draw.rounded_rectangle([(20, y_pos), (width - 20, y_pos + 45)], radius=8, fill=(50, 45, 85, 200))
    draw.text((30, y_pos + 10), f"Summary: Net {abs(net_value):,} • {net_percent:.1f}%", fill=(200, 200, 220), font=text_font)
    
    y_pos += 55
    
    your_inv_risk, your_inv_color = calculate_inventory_risk(your_total)
    their_inv_risk, their_inv_color = calculate_inventory_risk(their_total)
    trade_risk, trade_risk_color = calculate_trade_risk(your_total, their_total)
    
    draw.rounded_rectangle([(20, y_pos), (width - 20, y_pos + 65)], radius=8, fill=(40, 35, 70, 200))
    draw.text((30, y_pos + 5), "Inventory Risk", fill=(180, 180, 200), font=small_font)
    draw.ellipse([(30, y_pos + 30), (46, y_pos + 46)], fill=your_inv_color)
    draw.text((54, y_pos + 28), f"Your: {your_inv_risk}", fill=(200, 200, 200), font=small_font)
    draw.ellipse([(200, y_pos + 30), (216, y_pos + 46)], fill=their_inv_color)
    draw.text((224, y_pos + 28), f"Their: {their_inv_risk}", fill=(200, 200, 200), font=small_font)
    
    y_pos += 75
    
    draw.rounded_rectangle([(20, y_pos), (width - 20, y_pos + 45)], radius=8, fill=(40, 35, 70, 200))
    draw.text((30, y_pos + 10), "Trade Risk:", fill=(180, 180, 200), font=small_font)
    draw.ellipse([(145, y_pos + 12), (163, y_pos + 30)], fill=trade_risk_color)
    draw.text((172, y_pos + 10), trade_risk, fill=(200, 200, 200), font=small_font)
    
    y_pos += 55
    
    draw.rounded_rectangle([(20, y_pos), (width - 20, y_pos + 55)], radius=10, fill=(*result_color, 200))
    
    result_bbox = draw.textbbox((0, 0), result_text, font=title_font)
    result_width = result_bbox[2] - result_bbox[0]
    result_x = (width - result_width) // 2
    draw.text((result_x, y_pos + 12), result_text, fill=(255, 255, 255), font=title_font)
    
    y_pos += 65
    
    footer_text = f"Watashi LioK • {datetime.now().strftime('%B %d, %Y')}"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=small_font)
    footer_width = footer_bbox[2] - footer_bbox[0]
    draw.text(((width - footer_width) // 2, y_pos), footer_text, fill=(120, 120, 140), font=small_font)
    
    return img

@bot.command(name='items')
async def list_items(ctx):
    if ctx.author.id != 437943086048608266:
        return
    
    json_path = os.path.join(SCRIPT_DIR, "item_data.json")
    with open(json_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    
    lines = []
    for item_id, item_data in data['items'].items():
        value = item_data['value']
        names = item_data['names']
        names_str = ", ".join(names)
        lines.append(f"**{item_id}** ({value:,}) - {names_str}")
    
    chunks = []
    current_chunk = "**All Items**\n\n"
    
    for line in lines:
        if len(current_chunk) + len(line) + 1 > 1900:
            chunks.append(current_chunk)
            current_chunk = ""
        current_chunk += line + "\n"
    
    if current_chunk:
        chunks.append(current_chunk)
    
    for i, chunk in enumerate(chunks):
        await ctx.send(chunk)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')
    print(f'Output mode: {OUTPUT_MODE}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    content = message.content.strip()
    
    if content.lower().startswith('v '):
        items_str = content[2:].strip()
        items = parse_items(items_str)
        
        if not items:
            return
        
        guild_emojis = message.guild.emojis if message.guild else []
        
        items_display = ""
        total_value = 0
        unknown_items = []
        
        for item_name, quantity in items:
            value = get_item_value(item_name)
            if value is not None:
                item_total = value * quantity
                total_value += item_total
                emoji = get_item_emoji(item_name, guild_emojis)
                display_name = get_display_name(item_name)
                if quantity > 1:
                    items_display += f"{emoji} **x{quantity}** — `{item_total:,}`, each - `{value:,}`\n"
                else:
                    items_display += f"{emoji} — `{value:,}`\n"
            else:
                unknown_items.append(item_name)
        
        if unknown_items:
            await message.channel.send(f"❌ Unknown items: {', '.join(unknown_items)}")
            return
        
        if not items_display:
            return
        
        embed = discord.Embed(
            title="💎 Value Check 💎",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name=f"{items_display}",
            value="",
            inline=False
        )
        
        if len(items) > 1:
            embed.add_field(
                name=f"💰 Total Value - **{total_value:,}**",
                value="",
                inline=False
            )
        
        
        await message.reply(embed=embed)
        return
    
    match = re.match(r'^(.+?)\s+for\s+(.+)$', content, re.IGNORECASE)
    
    if match:
        your_items_str = match.group(1)
        their_items_str = match.group(2)
        
        your_items = parse_items(your_items_str)
        their_items = parse_items(their_items_str)
        
        your_total = 0
        their_total = 0
        your_items_valid = []
        their_items_valid = []
        unknown_items = []
        
        for item_name, quantity in your_items:
            value = get_item_value(item_name)
            if value is not None:
                your_items_valid.append((item_name, quantity, value * quantity))
                your_total += value * quantity
            else:
                unknown_items.append(item_name)
        
        for item_name, quantity in their_items:
            value = get_item_value(item_name)
            if value is not None:
                their_items_valid.append((item_name, quantity, value * quantity))
                their_total += value * quantity
            else:
                unknown_items.append(item_name)
        
        if unknown_items:
            await message.channel.send(f"❌ Unknown items: {', '.join(unknown_items)}")
            return
        
        if not your_items_valid or not their_items_valid:
            return
        
        if OUTPUT_MODE == "image":
            trade_img = create_trade_image(
                message.author.display_name,
                str(message.author.display_avatar.url) if message.author.display_avatar else None,
                your_items_valid,
                their_items_valid,
                your_total,
                their_total
            )
            
            img_buffer = io.BytesIO()
            trade_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            file = discord.File(img_buffer, filename='trade_comparison.png')
            await message.reply(file=file)
        
        else:  # OUTPUT_MODE == "embed"
            net_value = their_total - your_total
            if your_total > 0:
                net_percent = abs(net_value) / your_total * 100
            else:
                net_percent = 0
            
            if their_total > your_total:
                result_text = "🎉 YOU ARE WINNING! 🎉"
                embed_color = discord.Color.green()
                your_check = "✅"
                their_check = "❌"
                net_emoji = "📈"
                diff_text = f"+{abs(net_value):,}"
            elif their_total < your_total:
                result_text = "⚠️ YOU ARE LOSING! ⚠️"
                embed_color = discord.Color.red()
                your_check = "❌"
                their_check = "✅"
                net_emoji = "📉"
                diff_text = f"-{abs(net_value):,}"
            else:
                result_text = "⚖️ FAIR TRADE! ⚖️"
                embed_color = discord.Color.gold()
                your_check = "✅"
                their_check = "✅"
                net_emoji = "🔄"
                diff_text = "0"
            
            your_inv_risk, _ = calculate_inventory_risk(your_total)
            their_inv_risk, _ = calculate_inventory_risk(their_total)
            trade_risk, _ = calculate_trade_risk(your_total, their_total)
            
            your_inv_emoji = get_risk_emoji(your_inv_risk)
            their_inv_emoji = get_risk_emoji(their_inv_risk)
            trade_risk_emoji = get_risk_emoji(trade_risk)
            
            guild_emojis = message.guild.emojis if message.guild else []
            
            your_items_display = ""
            for item_name, quantity, item_value in your_items_valid:
                emoji = get_item_emoji(item_name, guild_emojis)
                your_items_display += f"{emoji} **x{quantity}** `{item_value:,}`\n"
            
            their_items_display = ""
            for item_name, quantity, item_value in their_items_valid:
                emoji = get_item_emoji(item_name, guild_emojis)
                their_items_display += f"{emoji} **x{quantity}** `{item_value:,}`\n"

            embed = discord.Embed(
                title="⚔️ Trade Comparison ⚔️",
                description=f"```\n{'═' * 30}\n```",
                color=embed_color
            )
            embed.set_author(
                name=f"Trade by {message.author.display_name}", 
                icon_url=message.author.display_avatar.url
            )
            
            embed.add_field(
                name="🎁 Your Trade", 
                value=your_items_display if your_items_display else "None", 
                inline=True
            )
            
            embed.add_field(
                name="🎁 Their Trade", 
                value=their_items_display if their_items_display else "None", 
                inline=True
            )
            
            embed.add_field(name="\u200b", value="\u200b", inline=False)
            
            embed.add_field(
                name="💰 Your Total", 
                value=f"{your_check} **{your_total:,}**", 
                inline=True
            )
            embed.add_field(
                name="💰 Their Total", 
                value=f"{their_check} **{their_total:,}**", 
                inline=True
            )
            
            embed.add_field(
                name=f"{net_emoji} Net Difference", 
                value=f"**{diff_text}** ({net_percent:.1f}%)", 
                inline=True
            )
            
            risk_display = (
                f"```\n"
                f"📊 Risk Analysis\n"
                f"{'─' * 25}\n"
                f"Your Inventory:  {your_inv_risk:>8}\n"
                f"Their Inventory: {their_inv_risk:>8}\n"
                f"Trade Risk:      {trade_risk:>8}\n"
                f"```"
            )
            embed.add_field(name="\u200b", value=risk_display, inline=False)
            
            embed.add_field(
                name=f"**{result_text}**",
                value="",
                inline=False
            )
            
            embed.set_footer(
                text=f"Watashi LioK • {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
                icon_url=bot.user.display_avatar.url if bot.user.display_avatar else None
            )
            
            if message.author.display_avatar:
                embed.set_thumbnail(url=message.author.display_avatar.url)
            
            await message.reply(embed=embed)
        
    await bot.process_commands(message)

# ==================== MAIN ====================
if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set!")
        exit(1)
    
    # Start the Flask server for UptimeRobot
    keep_alive()
    
    # Run the bot
    bot.run(TOKEN)
