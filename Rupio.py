import asyncio
import os
import sqlite3
import matplotlib.pyplot as plt
from datetime import datetime
from datetime import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.ext import MessageHandler, filters
from telegram import ReplyKeyboardMarkup
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

conn = sqlite3.connect("expenses.db", check_same_thread=False)
cursor = conn.cursor()

# EXPENSES TABLE (YOU FORGOT THIS)
cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    amount REAL,
    category TEXT,
    account TEXT,
    description TEXT,
    date TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user INTEGER,
    to_user INTEGER,
    amount REAL,
    description TEXT,
    date TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS recurring (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    amount REAL,
    category TEXT,
    account TEXT,
    description TEXT,
    day INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS goals (
    user_id INTEGER,
    target REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS lending (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    person TEXT,
    type TEXT,
    amount REAL,
    date TEXT,
    note TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS autopay_log (
    user_id INTEGER,
    recurring_id INTEGER,
    month TEXT
)
""")

conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
    """, (user.id, user.username, user.first_name))

    conn.commit()

    await update.message.reply_text(
        "💼 Welcome to Expense Tracker\n\nChoose an option:",
        reply_markup=main_menu()
    )

def main_menu():
    keyboard = [
        ["➕ Add Expense", "💰 Add Income"],
        ["📊 Report", "📜 History"],
        ["🔁 Add Autopay", "📋 View Autopay"],
        ["🗑 Delete Autopay"],
        ["💳 Balance" , "🎯 Goal"],
        ["📊 Chart" , "📄 PDF"],
        ["💵 Lend", "💰 Receive"],
        ["📜 Lend History", "📊 Lend Status"],
        ["➗ Split Expense", "📊 My Split Status"]   # NEW
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def lend_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        person = context.args[0]
        amount = float(context.args[1])
        note = " ".join(context.args[2:]) if len(context.args) > 2 else ""
        date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT INTO lending (user_id, person, type, amount, date, note)
            VALUES (?, ?, 'lent', ?, ?, ?)
        """, (user_id, person, amount, date, note))

        conn.commit()

        await update.message.reply_text(f"💵 Lent ₹{amount} to {person}")

    except:
        await update.message.reply_text("Usage:\n/lend Rahul 2000 book_money")

async def split_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        payer_id = update.effective_user.id
        amount = float(context.args[0])
        description = context.args[1]

        usernames = context.args[2:]  # @rahul @sameer

        total_people = len(usernames) + 1  # including payer
        share = amount / total_people
        date = datetime.now().strftime("%Y-%m-%d")

        for username in usernames:
            username = username.replace("@", "")

            cursor.execute(
                "SELECT user_id FROM users WHERE username=?",
                (username,)
            )
            user = cursor.fetchone()

            if user:
                debtor_id = user[0]

                cursor.execute("""
                    INSERT INTO debts (from_user, to_user, amount, description, date)
                    VALUES (?, ?, ?, ?, ?)
                """, (debtor_id, payer_id, share, description, date))

                # Notify debtor
                await context.bot.send_message(
                    chat_id=debtor_id,
                    text=f"💰 You owe {update.effective_user.first_name} ₹{share:.2f} for {description}"
                )

        conn.commit()

        await update.message.reply_text(
            f"✅ Split done.\nEach person owes ₹{share:.2f}"
        )

    except:
        await update.message.reply_text(
            "Usage:\n/split 900 Dinner @rahul @sameer"
        )

async def lend_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("""
        SELECT person,
        SUM(CASE WHEN type='lent' THEN amount ELSE -amount END)
        FROM lending
        WHERE user_id=?
        GROUP BY person
    """, (user_id,))

    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No lending records.")
        return

    msg = "💰 Lending Status:\n\n"
    for row in data:
        if row[1] != 0:
            msg += f"{row[0]} → ₹{row[1]}\n"

    await update.message.reply_text(msg)

async def lend_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    person = context.args[0]

    cursor.execute("""
        SELECT type, amount, date, note
        FROM lending
        WHERE user_id=? AND person=?
        ORDER BY date DESC
    """, (user_id, person))

    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No history for this person.")
        return

    msg = f"📜 History for {person}:\n\n"

    total = 0
    for row in data:
        if row[0] == "lent":
            total += row[1]
            msg += f"➕ Lent ₹{row[1]} | {row[2]} | {row[3]}\n"
        else:
            total -= row[1]
            msg += f"➖ Received ₹{row[1]} | {row[2]} | {row[3]}\n"

    msg += f"\n💳 Outstanding: ₹{total}"

    await update.message.reply_text(msg)

async def received_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        person = context.args[0]
        amount = float(context.args[1])
        note = " ".join(context.args[2:]) if len(context.args) > 2 else ""
        date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT INTO lending (user_id, person, type, amount, date, note)
            VALUES (?, ?, 'received', ?, ?, ?)
        """, (user_id, person, amount, date, note))

        conn.commit()

        await update.message.reply_text(f"💰 Received ₹{amount} from {person}")

    except:
        await update.message.reply_text("Usage:\n/received Rahul 1000 note")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "➕ Add Expense":
        await update.message.reply_text("Enter expense like:\n/add 200 food HDFC lunch")

    elif text == "💰 Add Income":
        await update.message.reply_text("Enter income like:\n/income 5000 salary HDFC stipend")

    elif text == "📊 Report":
        await report(update, context)

    elif text == "📜 History":
        await history(update, context)
    elif text == "🔁 Add Autopay":
        await update.message.reply_text(
        "Format:\n/autopay expense 8000 rent HDFC house_rent 5")

    elif text == "📋 View Autopay":
        await list_autopay(update, context)

    elif text == "🗑 Delete Autopay":
        await update.message.reply_text(
        "Use:\n/deleteautopay id")
    elif text == "💳 Balance":
        await account_balance(update, context)

    elif text == "🎯 Goal":
        await update.message.reply_text(
            "Set goal:\n/setgoal 50000\n\nCheck progress:\n/goal"
        )
    elif text == "💵 Lend":
        await update.message.reply_text(
        "Use:\n/lend Rahul 2000 book_money"
        )

    elif text == "💰 Receive":
        await update.message.reply_text(
            "Use:\n/received Rahul 1000 partial_payment"
        )

    elif text == "📜 Lend History":
        await update.message.reply_text(
        "Use:\n/lendhistory Rahul"
        )

    elif text == "📊 Lend Status":
        await lend_status(update, context)
    elif text == "📊 Chart":
        await chart_report(update, context)

    elif text == "📄 PDF":
        await monthly_pdf(update, context)
    elif text == "➗ Split Expense":
        await update.message.reply_text(
        "Use:\n/split 900 Dinner @rahul @sameer"
        )

    elif text == "📊 My Split Status":
        await my_debts(update, context)

    else:
        await update.message.reply_text("❌ Unknown option. Press /start to see menu.")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """
🤖 I didn't understand that command.

Here are available commands:

/add amount category account description
Example:
 /add 200 food HDFC lunch at cafe

/income amount category account description
Example:
 /income 5000 salary HDFC stipend

/report - Monthly report
/accounts - Account summary
/categories - Category summary
/history - Monthly history
/delete id - Delete expense

Please use proper format 😊
"""
    )

TOKEN = os.getenv("BOT_TOKEN")

async def check_autopay(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now()
    day_today = today.day
    month_str = today.strftime("%Y-%m")
    date_str = today.strftime("%Y-%m-%d")

    cursor.execute("SELECT * FROM recurring WHERE day=?", (day_today,))
    recurring_data = cursor.fetchall()

    for row in recurring_data:
        recurring_id = row[0]
        user_id = row[1]
        pay_type = row[2]
        amount = row[3]
        category = row[4]
        account = row[5]
        description = row[6]

        # Check if already executed this month
        cursor.execute("""
            SELECT * FROM autopay_log
            WHERE recurring_id=? AND month=?
        """, (recurring_id, month_str))

        if cursor.fetchone():
            continue  # already executed this month

        # Insert expense/income
        cursor.execute("""
            INSERT INTO expenses (user_id, type, amount, category, account, description, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, pay_type, amount, category, account, description, date_str))

        # Log execution
        cursor.execute("""
            INSERT INTO autopay_log (user_id, recurring_id, month)
            VALUES (?, ?, ?)
        """, (user_id, recurring_id, month_str))

        conn.commit()

        await context.bot.send_message(
            chat_id=user_id,
            text=f"🔁 AutoPay Executed: {pay_type} ₹{amount}"
        )

async def account_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("""
        SELECT account,
        SUM(CASE WHEN type='income' THEN amount ELSE -amount END)
        FROM expenses
        WHERE user_id=?
        GROUP BY account
    """, (user_id,))

    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No transactions yet.")
        return

    msg = "💳 Account Balances:\n\n"
    for row in data:
        msg += f"{row[0]} → ₹{row[1]}\n"

    await update.message.reply_text(msg)


async def list_autopay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT id, type, amount, category, day
        FROM recurring
        WHERE user_id=?
    """, (update.effective_user.id,))

    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No autopay set.")
        return

    msg = "🔁 Your AutoPays:\n\n"
    for row in data:
        msg += f"ID:{row[0]} | {row[1]} ₹{row[2]} | {row[3]} | Day:{row[4]}\n"

    await update.message.reply_text(msg)

async def delete_autopay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rid = int(context.args[0])
        cursor.execute("""
            DELETE FROM recurring
            WHERE id=? AND user_id=?
        """, (rid, update.effective_user.id))
        conn.commit()

        await update.message.reply_text("🗑 Autopay deleted.")
    except:
        await update.message.reply_text("Usage: /deleteautopay id")





async def add_autopay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 6:
        await update.message.reply_text(
            "Usage:\n/autopay expense 8000 rent HDFC house_rent 5"
        )
        return

    try:
        user_id = update.effective_user.id
        pay_type = context.args[0].lower()

        if pay_type not in ["expense", "income"]:
            await update.message.reply_text(
                "Type must be 'expense' or 'income'"
            )
            return

        amount = float(context.args[1])
        category = context.args[2]
        account = context.args[3]

        # Support multi-word description
        description = " ".join(context.args[4:-1])

        day = int(context.args[-1])
        if not 1 <= day <= 31:
            await update.message.reply_text("Day must be between 1 and 31.")
            return

        cursor.execute("""
            INSERT INTO recurring (user_id, type, amount, category, account, description, day)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, pay_type, amount, category, account, description, day))

        conn.commit()

        await update.message.reply_text(
            f"🔁 AutoPay added:\n"
            f"₹{amount} {pay_type}\n"
            f"Every month on day {day}"
        )

    except ValueError:
        await update.message.reply_text("Amount and day must be numbers.")
    except Exception as e:
        print("Autopay Error:", e)
        await update.message.reply_text("Something went wrong.")

async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target = float(context.args[0])
        cursor.execute("DELETE FROM goals WHERE user_id=?", (update.effective_user.id,))
        cursor.execute("INSERT INTO goals VALUES (?, ?)", (update.effective_user.id, target))
        conn.commit()
        await update.message.reply_text(f"🎯 Savings goal set to ₹{target}")
    except:
        await update.message.reply_text("Usage: /setgoal amount")

async def goal_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT target FROM goals WHERE user_id=?", (user_id,))
    goal = cursor.fetchone()

    if not goal:
        await update.message.reply_text("No goal set.")
        return

    target = goal[0]

    cursor.execute("""
        SELECT SUM(CASE WHEN type='income' THEN amount ELSE -amount END)
        FROM expenses WHERE user_id=?
    """, (user_id,))

    balance = cursor.fetchone()[0] or 0

    percent = (balance / target) * 100 if target > 0 else 0

    await update.message.reply_text(
        f"🎯 Goal: ₹{target}\n💰 Current: ₹{balance}\n📊 Progress: {percent:.2f}%"
    )

async def chart_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    month = datetime.now().strftime("%Y-%m")

    cursor.execute("""
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id=? AND type='expense' AND date LIKE ?
        GROUP BY category
    """, (user_id, f"{month}%"))

    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No expense data.")
        return

    labels = [row[0] for row in data]
    values = [row[1] for row in data]

    plt.figure()
    plt.pie(values, labels=labels, autopct="%1.1f%%")
    plt.title("Monthly Expense Distribution")
    plt.savefig("chart.png")
    plt.close()

    await update.message.reply_photo(photo=open("chart.png", "rb"))

async def monthly_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    month = datetime.now().strftime("%Y-%m")

    cursor.execute("""
        SELECT type, amount, category, date
        FROM expenses
        WHERE user_id=? AND date LIKE ?
    """, (user_id, f"{month}%"))

    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No data this month.")
        return

    doc = SimpleDocTemplate("monthly_report.pdf")
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"Monthly Report - {month}", styles["Heading1"]))
    elements.append(Spacer(1, 12))

    for row in data:
        line = f"{row[3]} | {row[0]} | ₹{row[1]} | {row[2]}"
        elements.append(Paragraph(line, styles["Normal"]))
        elements.append(Spacer(1, 8))

    doc.build(elements)

    await update.message.reply_document(document=open("monthly_report.pdf", "rb"))

# ADD Expences
async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Usage:\n/add amount category account description")
        return

    try:
        user_id = update.effective_user.id
        amount = float(context.args[0])
        category = context.args[1]
        account = context.args[2]
        description = " ".join(context.args[3:]) if len(context.args) > 3 else ""
        date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT INTO expenses (user_id, type, amount, category, account, description, date)
            VALUES (?, 'expense', ?, ?, ?, ?, ?)
        """, (user_id, amount, category, account, description, date))

        conn.commit()

        await update.message.reply_text(f"💸 Expense Added ₹{amount}")

    except ValueError:
        await update.message.reply_text("Amount must be a number.")
# ================= MONTH FILTER =================
def current_month():
    return datetime.now().strftime("%Y-%m")

# ================= REPORT =================
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    month = datetime.now().strftime("%Y-%m")

    cursor.execute("""
        SELECT type, SUM(amount) FROM expenses
        WHERE user_id=? AND date LIKE ?
        GROUP BY type
    """, (user_id, f"{month}%"))

    data = cursor.fetchall()

    income = 0
    expense = 0

    for row in data:
        if row[0] == "income":
            income = row[1]
        else:
            expense = row[1]

    income = income or 0
    expense = expense or 0
    net = income - expense

    await update.message.reply_text(
        f"""📊 Monthly Report
        💰 Income: ₹{income}
        💸 Expense: ₹{expense}
        📈 Net Balance: ₹{net}"""
    )

# ================= ACCOUNT SUMMARY =================
async def accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    month = current_month()

    cursor.execute("""
        SELECT account, SUM(amount) FROM expenses
        WHERE user_id=? AND date LIKE ?
        GROUP BY account
    """, (user_id, f"{month}%"))

    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No expenses this month.")
        return

    msg = "🏦 Account Summary:\n\n"
    for account, total in data:
        msg += f"{account} → ₹{total}\n"

    await update.message.reply_text(msg)

# ================= CATEGORY SUMMARY =================
async def categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    month = current_month()

    cursor.execute("""
        SELECT category, SUM(amount) FROM expenses
        WHERE user_id=? AND date LIKE ?
        GROUP BY category
    """, (user_id, f"{month}%"))

    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No expenses this month.")
        return

    msg = "📂 Category Summary:\n\n"
    for category, total in data:
        msg += f"{category} → ₹{total}\n"

    await update.message.reply_text(msg)

# ================= HISTORY =================
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    month = current_month()

    cursor.execute("""
        SELECT id, amount, category, account, description, date FROM expenses
        WHERE user_id=? AND date LIKE ?
        ORDER BY date DESC
    """, (user_id, f"{month}%"))

    data = cursor.fetchall()

    if not data:
        await update.message.reply_text("No expenses this month.")
        return

    msg = "📜 Monthly History:\n\n"
    for row in data:
        msg += f"ID:{row[0]} | ₹{row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]}\n"

    await update.message.reply_text(msg)

# ================= DELETE =================
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        expense_id = int(context.args[0])
        user_id = update.effective_user.id

        cursor.execute("""
            DELETE FROM expenses WHERE id=? AND user_id=?
        """, (expense_id, user_id))
        conn.commit()

        await update.message.reply_text(f"🗑 Deleted expense ID {expense_id}")

    except:
        await update.message.reply_text("Usage: /delete id")

async def my_debts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Amount you owe others
    cursor.execute("""
        SELECT users.first_name, SUM(amount)
        FROM debts
        JOIN users ON debts.to_user = users.user_id
        WHERE from_user=?
        GROUP BY to_user
    """, (user_id,))

    owe = cursor.fetchall()

    # Amount others owe you
    cursor.execute("""
        SELECT users.first_name, SUM(amount)
        FROM debts
        JOIN users ON debts.from_user = users.user_id
        WHERE to_user=?
        GROUP BY from_user
    """, (user_id,))

    collect = cursor.fetchall()

    msg = "📊 Splitwise Status\n\n"

    if owe:
        msg += "💸 You owe:\n"
        for row in owe:
            msg += f"{row[0]} → ₹{row[1]:.2f}\n"
        msg += "\n"

    if collect:
        msg += "💰 You should collect:\n"
        for row in collect:
            msg += f"{row[0]} → ₹{row[1]:.2f}\n"

    if not owe and not collect:
        msg += "No pending balances."

    await update.message.reply_text(msg)

#ADD MONTHLY INCOME
async def add_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Usage:\n/income amount category account description")
        return

    try:
        user_id = update.effective_user.id
        amount = float(context.args[0])
        category = context.args[1]
        account = context.args[2]
        description = " ".join(context.args[3:]) if len(context.args) > 3 else ""
        date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT INTO expenses (user_id, type, amount, category, account, description, date)
            VALUES (?, 'income', ?, ?, ?, ?, ?)
        """, (user_id, amount, category, account, description, date))

        conn.commit()

        await update.message.reply_text(f"💰 Income Added ₹{amount}")

    except ValueError:
        await update.message.reply_text("Amount must be a number.")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Unknown command. Type /start to see commands.")

# ================= MAIN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_expense))
app.add_handler(CommandHandler("income", add_income))
app.add_handler(CommandHandler("report", report))
app.add_handler(CommandHandler("accounts", accounts))
app.add_handler(CommandHandler("categories", categories))
app.add_handler(CommandHandler("history", history))
app.add_handler(CommandHandler("delete", delete))

# LENDING
app.add_handler(CommandHandler("lend", lend_money))
app.add_handler(CommandHandler("received", received_money))
app.add_handler(CommandHandler("lendhistory", lend_history))
app.add_handler(CommandHandler("lendstatus", lend_status))
app.add_handler(CommandHandler("split", split_expense))

# AUTOPAY
app.add_handler(CommandHandler("autopay", add_autopay))
app.add_handler(CommandHandler("listautopay", list_autopay))
app.add_handler(CommandHandler("deleteautopay", delete_autopay))

app.add_handler(CommandHandler("balance", account_balance))
app.add_handler(CommandHandler("setgoal", set_goal))
app.add_handler(CommandHandler("goal", goal_progress))
app.add_handler(CommandHandler("mydebts", my_debts))
# TEXT BUTTONS
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

# UNKNOWN COMMAND (ALWAYS LAST)
app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
app.job_queue.run_daily(check_autopay, time=time(hour=0, minute=1))


print("Bot running...")

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

loop.run_until_complete(app.initialize())
loop.run_until_complete(app.start())
loop.run_until_complete(app.updater.start_polling())

loop.run_forever()