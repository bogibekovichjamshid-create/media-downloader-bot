from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def build_quality_keyboard(qualities: dict) -> InlineKeyboardMarkup:
    buttons = []
    
    row = []
    for q_name in qualities.keys():
        row.append(InlineKeyboardButton(text=f"🚀 {q_name}", callback_data=f"dl:{q_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(text="🎵 Video audiosi", callback_data="dl:mp3"),
        InlineKeyboardButton(text="🖼 Prevyu", callback_data="dl:thumb")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔇 Ovozni o'chirish", callback_data="dl:mute"),
        InlineKeyboardButton(text="🔍 Videodagi qo'shiq...", callback_data="dl:shazam")
    ])
    buttons.append([
        InlineKeyboardButton(text="✂️ Qirqib olish", callback_data="dl:crop_menu")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_crop_quality_keyboard(qualities: dict) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for q_name in qualities.keys():
        row.append(InlineKeyboardButton(text=f"✂️ {q_name}", callback_data=f"crop_q:{q_name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Video yuklash"), KeyboardButton(text="🎵 Musiqa qidirish")],
            [KeyboardButton(text="✂️ Video qirqish"), KeyboardButton(text="🔇 Ovozsiz qilish")],
            [KeyboardButton(text="📖 Qo'llanma"), KeyboardButton(text="☎️ Qo'llab-quvvatlash")]
        ],
        resize_keyboard=True
    )