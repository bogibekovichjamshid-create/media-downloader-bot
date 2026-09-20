import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@admin_username")
# VIP foydalanuvchilarni ro'yxat qilib olish
VIP_USERS = [x.strip() for x in os.getenv("VIP_USERS", "").split(",") if x.strip()]