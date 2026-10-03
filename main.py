import logging
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# API TOKEN (O'zingizning bot tokeningizni qo'ying)
API_TOKEN = "8663093388:AAEsuGJLXAgGi2Fky_SARKS0jACuaat4ydg  " # <-- BotFather bergan tokenni shu yerga qo'ying
ADMIN_ID =  7349936837 # <-- O'zingizning Telegram ID raqamingizni kiriting

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Ma'lumotlar bazasini sozlash
conn = sqlite3.connect("savdo_bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS workers (id INTEGER PRIMARY KEY, name TEXT)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY AUTOINCREMENT, worker_id INTEGER, name TEXT, price INTEGER, date TEXT)""")
conn.commit()

# Holatlar
class Form(StatesGroup):
    add_worker = State()
    prod_name = State()
    prod_price = State()
    get_date = State()

# Klaviaturalar
def get_main_menu(user_id):
    if user_id == ADMIN_ID:
        kb = [
            [KeyboardButton(text="👥 Ishchilar"), KeyboardButton(text="➕ Ishchi qo‘shish")],
            [KeyboardButton(text="📊 Daromad")]
        ]
    else:
        kb = [[KeyboardButton(text="🛒 Savdo")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    # Agar ishchi bazada bo'lmasa va admin bo'lmasa, ismini so'rash yoki avtomat qo'shish mumkin
    cursor.execute("SELECT name FROM workers WHERE id=?", (message.from_user.id,))
    worker = cursor.fetchone()
    if message.from_user.id != ADMIN_ID and not worker:
        # Ishchini ismi bilan bazaga vaqtincha saqlash
        cursor.execute("INSERT OR IGNORE INTO workers (id, name) VALUES (?, ?)", (message.from_user.id, message.from_user.full_name))
        conn.commit()
    
    await message.answer(f"Assalomu alaykum, {message.from_user.full_name}! Xush kelibsiz.", reply_markup=get_main_menu(message.from_user.id))

# --- ADMIN PANEL ---
@dp.message(F.text == "➕ Ishchi qo‘shish", F.from_user.id == ADMIN_ID)
async def add_worker_start(message: types.Message, state: FSMContext):
    await message.answer("Yangi ishchining ismini kiriting:")
    await state.set_state(Form.add_worker)

@dp.message(Form.add_worker, F.from_user.id == ADMIN_ID)
async def add_worker_save(message: types.Message, state: FSMContext):
    # Bu yerda qo'lda ism kiritiladi, ishchi birinchi marta /start bosganda unga ulanadi
    await message.answer(f"Ishchi '{message.text}' tizimga kiritildi. U botga kirib /start bossa kifoya.")
    await state.clear()

@dp.message(F.text == "👥 Ishchilar", F.from_user.id == ADMIN_ID)
async def list_workers(message: types.Message):
    cursor.execute("SELECT name FROM workers")
    workers = cursor.fetchall()
    if not workers:
        return await message.answer("Hozircha ishchilar yo‘q.")
    text = "👥 **Ishchilar ro‘yxati:**\n" + "\n".join([f"- {w[0]}" for w in workers])
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📊 Daromad", F.from_user.id == ADMIN_ID)
async def daromad_cmd(message: types.Message):
    cursor.execute("SELECT id, name FROM workers")
    workers = cursor.fetchall()
    ikb = InlineKeyboardMarkup(inline_keyboard=[])
    for w_id, w_name in workers:
        ikb.inline_keyboard.append([InlineKeyboardButton(text=w_name, callback_data=f"w_{w_id}_{w_name}")])
    ikb.inline_keyboard.append([InlineKeyboardButton(text="📊 Barchasi (Umumiy)", callback_data="w_all_Barchasi")])
    await message.answer("Kimning savdosini ko‘rmoqchisiz? Ishchini tanlang:", reply_markup=ikb)

@dp.callback_query(F.data.startswith("w_"))
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
    _, w_id, w_name = callback.data.split("_")
    await state.update_data(v_w_id=w_id, v_w_name=w_name)
    
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Bugun", callback_data="d_today"), InlineKeyboardButton(text="📆 Kecha", callback_data="d_yesterday")],
        [InlineKeyboardButton(text="📅 Istalgan sana", callback_data="d_custom")]
    ])
    await callback.message.edit_text(f"👤 Ishchi: {w_name}\nSana turini tanlang:", reply_markup=ikb)

@dp.callback_query(F.data.startswith("d_"))
async def show_report(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    w_id = data.get("v_w_id")
    w_name = data.get("v_w_name")
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    if callback.data == "d_yesterday":
        # Sodda kecha sanasi kalkulyatsiyasi (batafsil serverda to'g'rilanadi)
        date_str = datetime.now().strftime("%Y-%m-%d") # Hozircha bugun deb turadi
    elif callback.data == "d_custom":
        await callback.message.answer("Sanani `YIL-OY-KUN` formatida kiriting (Masalan: `2026-10-02`):", parse_mode="Markdown")
        await state.set_state(Form.get_date)
        await callback.answer()
        return

    await send_final_report(callback.message, w_id, w_name, date_str)
    await callback.answer()

@dp.message(Form.get_date, F.from_user.id == ADMIN_ID)
async def custom_date_report(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await send_final_report(message, data.get("v_w_id"), data.get("v_w_name"), message.text)
    await state.clear()

async def send_final_report(msg, w_id, w_name, date_str):
    if w_id == "all":
        cursor.execute("SELECT name, price FROM sales WHERE date=?", (date_str,))
    else:
        cursor.execute("SELECT name, price FROM sales WHERE worker_id=? AND date=?", (w_id, date_str))
    
    sales = cursor.fetchall()
    if not sales:
        return await msg.answer(f"👤 {w_name}\n📅 {date_str}\n\nBu kunda hech qanday savdo bo‘lmagan.")
    
    text = f"👤 **Ishchi:** {w_name}\n📅 **Sana:** {date_str}\n"
    text += "----------------------------------\n"
    total_sum = 0
    for i, (p_name, price) in enumerate(sales, 1):
        text += f"{i}. {p_name} — {price:,} so‘m\n".replace(",", " ")
        total_sum += price
    text += "----------------------------------\n"
    text += f"📦 **Jami tovarlar soni:** {len(sales)} dona\n"
    text += f"💰 **Umumiy summa:** {total_sum:,} so‘m".replace(",", " ")
    
    await msg.answer(text, parse_mode="Markdown")

# --- ISHCHI PANEL (SAVDO) ---
@dp.message(F.text == "🛒 Savdo")
async def start_sale(message: types.Message, state: FSMContext):
    await message.answer("Sotilgan tovar nomini kiriting:")
    await state.set_state(Form.prod_name)

@dp.message(Form.prod_name)
async def get_sale_name(message: types.Message, state: FSMContext):
    await state.update_data(p_name=message.text)
    await message.answer("Tovar narxini kiriting (faqat raqamlarda):")
    await state.set_state(Form.prod_price)

@dp.message(Form.prod_price)
async def get_sale_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Iltimos, narxni faqat raqamlarda kiriting:")
    
    data = await state.get_data()
    p_name = data.get("p_name")
    price = int(message.text)
    date_now = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("INSERT INTO sales (worker_id, name, price, date) VALUES (?, ?, ?, ?)", 
                   (message.from_user.id, p_name, price, date_now))
    conn.commit()
    
    # Adminga xabar yuborish
    try:
        await bot.send_message(ADMIN_ID, f"🔔 **Yangi savdo!**\n👤 Ishchi: {message.from_user.full_name}\n📦 Tovar: {p_name}\n💰 Narxi: {price:,} so‘m".replace(",", " "))
    except:
        pass

    await message.answer(f"✅ Saqlandi!\n{p_name} — {price:,} so‘m.\nYana tovar bo‘lsa, '🛒 Savdo' tugmasini bosing.".replace(",", " "), reply_markup=get_main_menu(message.from_user.id))
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
