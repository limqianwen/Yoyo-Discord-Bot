import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
from groq import (Groq, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError, InternalServerError)
from database import connect_database, create_profile
from discord.ext import tasks
from flask import Flask
import threading

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY=os.getenv("GROQ_API_KEY")

client_ai = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

app = Flask(__name__)

@app.route("/")
def home():
    return "Yoyo Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")

    await bot.change_presence(
        status=discord.Status.online, 
        activity=discord.Activity(type=discord.ActivityType.watching, name="Type !help")
    )

    if not reminder_check.is_running():
        reminder_check.start()

    if not missed_tasks_check.is_running():
        missed_tasks_check.start()

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: Shows Bot Commands. [!help]
@bot.command()
async def help(ctx):
    create_profile(ctx.author)

    embed = discord.Embed(
        title = "📚 Yoyo's Bot Commands 📚",
        description = "Prefix = !",
        color = discord.Color.yellow()
    )

    embed.add_field(
        name = "AI Learning Tutor",
        value = "`ask <question>` - Ask Yoyo anything!\n",
        inline = False
    )

    embed.add_field(
        name = "Study Materials",
        value = (
            "`summary <topic>` - Generates a summary.\n"
            "`flashcard <topic>` - Generates 5 flashcards.\n"
            "`quiz <topic>` - Generates a quiz (5 questions).\n"
        ),
        inline = False
    )

    embed.add_field(
        name = "Assignment & Study Planner",
        value = (
            "`viewtask` - View your tasks.\n"
            "`addtask` - Add a task.\n"
            "`deltask <task ID>` - Delete a task.\n"
            "`check <task ID>` - Mark task as done.\n"
            "`missed` - View your missed tasks.\n"
        ),
        inline = False
    )

    embed.add_field(
        name = "Dashboard",
        value = (
            "`profile` - View your profile.\n"
        ),
        inline = False
    )

    await ctx.send(embed=embed)

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: Check if the bot is running. [!ping]
@bot.command()
async def ping(ctx):
    create_profile(ctx.author)

    await ctx.send("Pong! 🏓")

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: Groq AI Study Tutor. [!ask {question}]
@bot.command()
async def ask(ctx, *, question):
    create_profile(ctx.author)

    try:
        msg = await ctx.send("Thinking... 🧠")

        response = client_ai.chat.completions.create(
            model = "llama-3.1-8b-instant",
            messages = [
                {
                    "role": "system",
                    "content": "You are an AI study tutor helping students. Explain clearly and simply with emojis to the question in 2-3 sentences and provide one example."
                },
                {
                    "role": "user",
                    "content": question
                }
            ]
        )

        answer = response.choices[0].message.content
        await msg.delete()

        embed = discord.Embed(
        title = question.title(),
        description = answer,
        color = discord.Color.yellow()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")

        await ctx.send(embed=embed)
    
    except Exception as error:
        await send_ai_error(ctx, msg, error)

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: Groq AI Summary. [!summary {topic}]
@bot.command()
async def summary(ctx, *, topic):
    create_profile(ctx.author)

    try:
        msg = await ctx.send("Generating summary... ✏️")

        response = client_ai.chat.completions.create(
            model = "llama-3.1-8b-instant",
            messages = [
                {
                    "role":"system",
                    "content":"You are a study assistant. Provide a clear, short, structured summary in bullet points."
                },
                {
                    "role":"user",
                    "content": topic
                }
            ]
        )

        answer = response.choices[0].message.content
        await msg.delete()

        embed = discord.Embed(
        title = f"Summary of {topic.title()}",
        description = answer,
        color = discord.Color.yellow()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        
        await ctx.send(embed=embed)

    except Exception as error:
        await send_ai_error(ctx, msg, error)

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: Groq AI Flashcards. [!flashcard {topic}]
@bot.command()
async def flashcard(ctx, *, topic):
    create_profile(ctx.author)

    try:
        msg = await ctx.send("Generating flashcards... 🃏")

        response = client_ai.chat.completions.create(
            model = "llama-3.1-8b-instant",
            messages = [
                {
                    "role":"system",
                    "content":(
                        "Generate EXACTLY 5 flashcards BASED ON THE TOPIC GIVEN BY THE USER.\n"
                        "Must return flashcards strictly in this format ONLY:\n"
                        "Q: ... | A: ...\n"
                    )
                },
                {
                    "role":"user",
                    "content": topic
                }
            ]
        )

        text = response.choices[0].message.content
        flashcards = []
        for line in text.split("\n"):
            if "|" in line:
                q, a = line.split("|")
                flashcards.append((q.replace("Q:", "").strip(), a.replace("A:", "").strip()))

        await msg.delete()

        view = FlashcardView(flashcards, ctx.author)
        q, a = flashcards[0]
        embed = discord.Embed(
            title="Flashcards 1/5",
            description=q,
            color=discord.Color.yellow()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")

        await ctx.send(embed=embed, view=view)

        db = connect_database()
        cursor = db.cursor()

        sql = """
        UPDATE users
        SET flashcards_reviewed = flashcards_reviewed + 1
        WHERE user_id = %s;
        """

        cursor.execute(sql, (ctx.author.id,))
        db.commit()

        cursor.close()
        db.close()

    except Exception as error:
        await send_ai_error(ctx, msg, error)

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: Groq AI Quiz. [!quiz {topic}]
@bot.command()
async def quiz(ctx, *, topic):
    create_profile(ctx.author)

    try:
        msg = await ctx.send("Generating quiz... 📝")

        response = client_ai.chat.completions.create(
            model = "llama-3.1-8b-instant",
            messages = [
                {
                    "role":"system",
                    "content":(
                        """
                            Generate EXACTLY 5 multiple-choice questions BASED ON THE TOPIC GIVEN BY THE USER.

                            STRICT FORMAT RULE (VERY IMPORTANT):
                            Each question MUST be on a single line.
                            Each line MUST follow this format exactly:

                            Question | Option A | Option B | Option C | Option D | Correct Answer Letter (A/B/C/D)\n

                            RULES:
                            - Do NOT number the questions.
                            - Do NOT add A/B/C/D in front of the options.
                            - Do NOT add explanations.
                            - Do NOT add extra text before or after.
                            - Do NOT use bullet points.
                            - Output ONLY the 5 lines.
                            - Ensure every line contains exactly 5 '|' symbols.
                            - The question must have exactly one correct answer.
                            - Verify the answer before responding.

                            Example:
                            What is Python? | A programming language | A snake | A car brand | A game | A
                            What is 2+2? | 1 | 2 | 3 | 4 | D
                        """
                    )
                },
                {
                    "role":"user",
                    "content": topic
                }
            ]
        )
        
        text = response.choices[0].message.content
        quiz = []
        for line in text.split("\n"):
            if "|" in line:
                q, option_a, option_b, option_c, option_d, a = line.split("|")
                quiz.append((q.strip(), option_a.strip(), option_b.strip(), option_c.strip(), option_d.strip(), a.strip()))

        await msg.delete()
        view = QuizView(quiz, ctx.author)
        q, option_a, option_b, option_c, option_d, a = quiz[0]
        embed = discord.Embed(
            title="Quiz (Question: 1/5)",
            description=(
                        f"""{q}


                        A: {option_a}
                        B: {option_b}
                        C: {option_c}
                        D: {option_d}
                        """
                    ),
            colour=discord.Color.yellow()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")

        await ctx.send(embed=embed, view=view)

        db = connect_database()
        cursor = db.cursor()

        sql = """
        UPDATE users
        SET quizzes_attempted = quizzes_attempted + 1
        WHERE user_id = %s;
        """

        cursor.execute(sql, (ctx.author.id,))
        db.commit()

        cursor.close()
        db.close()

    except Exception as error:
        await send_ai_error(ctx, msg, error)

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: Add Tasks. [!addtask]
@bot.command()
async def addtask(ctx):
    create_profile(ctx.author)

    await ctx.send("What task do you want to add?")

    def check(message):
        return message.author == ctx.author
    
    title_message  = await bot.wait_for(
        "message",
        check=check
    )

    title = title_message.content

    await ctx.send("When's the due date? (YYYY-MM-DD)")

    date_message = await bot.wait_for(
        "message",
        check=check
    )

    due_date = date_message.content

    db = connect_database()
    cursor = db.cursor()

    sql = """
    INSERT INTO tasks(user_id, title, due_date)
    VALUES(%s, %s, %s);
    """

    values = (
        ctx.author.id,
        title,
        due_date
    )

    cursor.execute(sql, values)
    db.commit()

    await ctx.send("✅ Task added!")

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: Delete Tasks. [!deltask]
@bot.command()
async def deltask(ctx, task_id:int):
    create_profile(ctx.author)

    db = connect_database()
    cursor = db.cursor()

    sql = """
    DELETE FROM tasks
    WHERE user_id = %s AND id = %s AND status = "Pending"
    """

    cursor.execute(sql, (ctx.author.id, task_id))
    db.commit()

    await ctx.send("✅ Task deleted!")

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: View Tasks. [!tasks]
@bot.command()
async def viewtask(ctx):
    create_profile(ctx.author)

    db = connect_database()
    cursor = db.cursor()

    sql = """
    SELECT id, title, due_date
    FROM tasks
    WHERE user_id = %s AND status = "Pending"
    ORDER BY due_date ASC;
    """

    cursor.execute(sql, (ctx.author.id,))

    tasks = cursor.fetchall()
    embed = discord.Embed(
        title="📋 Your Tasks 📋",
        color=discord.Color.blue()
    )
    index = 1

    if not tasks:
        embed.description = "🎉 You have no pending tasks!"
    else:
        for task in tasks:
            task_id = task[0]
            title = task[1]
            due_date = task[2]

            embed.add_field(
                name=f"{index}. {title}",
                value=(
                    f"**Task ID:** `{task_id}`\n"
                    f"**Due Date:** {due_date}"
                ),
                inline=False
            )

            index += 1    

    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)

    cursor.close()
    db.close()

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: Check Completed Task. [!check]
@bot.command()
async def check(ctx, task_id:int):
    create_profile(ctx.author)

    db = connect_database()
    cursor = db.cursor()

    sql = """
    UPDATE tasks
    SET status = "Completed"
    WHERE user_id = %s AND id = %s;
    """

    cursor.execute(sql, (ctx.author.id, task_id))

    sql = """
    UPDATE users
    SET completed_tasks = completed_tasks + 1
    WHERE user_id = %s;
    """

    cursor.execute(sql, (ctx.author.id,))
    db.commit()

    sql = """
    SELECT title FROM tasks
    WHERE user_id = %s AND id = %s;
    """

    cursor.execute(sql, (ctx.author.id, task_id))
    result = cursor.fetchone()

    if result is None:
        await ctx.send("❌ Task not found.")
        return
    
    title = result[0]
    await ctx.send(f"✅ Task '{title}' marked as done!")

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: View Missed Tasks. [!missed] 
@bot.command()
async def missed(ctx):
    create_profile(ctx.author)

    db = connect_database()
    cursor = db.cursor()

    sql = """
    SELECT title, due_date
    FROM tasks
    WHERE user_id = %s AND status = "Missed"
    ORDER BY due_date DESC;
    """

    cursor.execute(sql, (ctx.author.id,))

    missed_tasks = cursor.fetchall()
    embed = discord.Embed(
        title="❌ Missed Tasks ❌",
        color=discord.Color.red()
    )
    index = 1

    if not missed_tasks:
        embed.description = "🎉 You have no missed tasks!"
    else:
        for missed_task in missed_tasks:
            title = missed_task[0]
            due_date = missed_task[1]

            embed.add_field (
                name=f"{index}. {title}",
                value=f"Due Date: {due_date}",
                inline=False
            )

            index += 1

    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)
    
    cursor.close()
    db.close()

#----------------------------------------------------------------------------------------------------------------------------------------------
#Command: View Your Profile. [!profile] 
@bot.command()
async def profile(ctx):

    create_profile(ctx.author)

    db = connect_database()
    cursor = db.cursor()

    sql = """
    SELECT username,
           display_name,
           avatar_url,
           completed_tasks,
           missed_tasks,
           quizzes_attempted,
           flashcards_reviewed
    FROM users
    WHERE user_id = %s;
    """

    cursor.execute(sql, (ctx.author.id,))
    result = cursor.fetchone()

    if result is None:
        await ctx.send("Profile not found.")
        return

    username = result[0]
    display_name = result[1]
    avatar_url = result[2]
    completed_tasks = result[3]
    missed_tasks = result[4]
    quizzes_attempted = result[5]
    flashcards_reviewed = result[6]

    embed = discord.Embed(
        title=f"{display_name}'s Study Profile",
        color=discord.Color.yellow()
    )

    embed.set_thumbnail(url=avatar_url)

    embed.add_field(
        name="👤 User",
        value=f"Username: **{username}**",
        inline=False
    )

    embed.add_field(
        name="📋 Tasks",
        value=(
            f"✅ Completed: **{completed_tasks}**\n"
            f"❌ Missed: **{missed_tasks}**"
        ),
        inline=True
    )

    embed.add_field(
        name="🧠 Learning",
        value=(
            f"📝 Quizzes: **{quizzes_attempted}**\n"
            f"🃏 Flashcards: **{flashcards_reviewed}**"
        ),
        inline=True
    )

    await ctx.send(embed=embed)

    cursor.close()
    db.close()

#----------------------------------------------------------------------------------------------------------------------------------------------
#Send Error for AI Bot Function
async def send_ai_error(ctx, msg, error):
    if isinstance(error, BadRequestError):
        await msg.edit(content="Invalid Request ⏱: Please check your input.")
    
    elif isinstance(error, AuthenticationError):
        await msg.edit(content="Authentification Failed 🔑: Please contact the bot administrator.")
    
    elif isinstance(error, RateLimitError):
        await msg.edit(content="You've exceeded the allowed request ⏳: Please wait a moment and try again.")

    elif isinstance(error, APIConnectionError):
        await msg.edit(content="Connection Error 🌐: Check your internet connection.")

    elif isinstance(error, InternalServerError):
        await msg.edit(content="AI Server Unavailable ⛔: Please try again later.")
    
    else: 
        print(error)
        await msg.edit("An unexpected error occured! ⚠️")

#----------------------------------------------------------------------------------------------------------------------------------------------
#Flashcard UI
class FlashcardView(discord.ui.View):
    def __init__(self, flashcards, author):
        super().__init__()
        self.flashcards = flashcards
        self.author = author
        self.index = 0
        self.show_answer = False

    #Previous Button
    @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.grey)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index > 0:
            self.index -= 1
            self.show_answer = False

        await self.update(interaction)

    #Next Button
    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.grey)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index < len(self.flashcards) - 1:
            self.index += 1
            self.show_answer = False

        await self.update(interaction)

    #Flip Button
    @discord.ui.button(label="🔄 Flip", style=discord.ButtonStyle.green)
    async def flip(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.show_answer = not self.show_answer
        
        await self.update(interaction)

    #Update Display
    async def update(self, interaction):
        q, a = self.flashcards[self.index]

        content = q if not self.show_answer else a 

        embed = discord.Embed(
            title = f"Flashcard {self.index + 1}/{len(self.flashcards)}",
            description = content,
            color = discord.Color.yellow()
        )
        embed.set_footer(text=f"Requested by {self.author.display_name}")

        for child in self.children:
            if child.label == "⬅️ Prev":
                child.disabled = (self.index == 0)

            if child.label == "➡️ Next":
                child.disabled = (self.index == len(self.flashcards) - 1)

        await interaction.response.edit_message(embed=embed, view=self)

#----------------------------------------------------------------------------------------------------------------------------------------------
# Quiz UI
class QuizView(discord.ui.View):
    def __init__(self, quiz, author):
        super().__init__()
        self.quiz = quiz
        self.author = author
        self.index = 0
        self.answered = False

    # Option A
    @discord.ui.button(label="A", style=discord.ButtonStyle.grey)
    async def option_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_answer(interaction, "A")

    # Option B
    @discord.ui.button(label="B", style=discord.ButtonStyle.grey)
    async def option_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_answer(interaction, "B")

    # Option C
    @discord.ui.button(label="C", style=discord.ButtonStyle.grey)
    async def option_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_answer(interaction, "C")

    # Option D
    @discord.ui.button(label="D", style=discord.ButtonStyle.grey)
    async def option_d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_answer(interaction, "D")

    # Handle Answer
    async def handle_answer(self, interaction: discord.Interaction, user_answer: str):
        correct = self.quiz[self.index][5]

        if user_answer == correct:
            result = "✅ Correct!"
        else:
            result = f"❌ Incorrect! The correct answer is {correct}."

        self.answered = True

        await interaction.response.send_message(result, ephemeral=True)
        await self.update(interaction)

    # Next Button
    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.green)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not self.answered:
            return await interaction.response.send_message(
                "❌ Please answer first before going next!",
                ephemeral=True
            )

        if self.index < len(self.quiz) - 1:
            self.index += 1
            self.answered = False

        await self.update(interaction)

    # Button states
    def set_button_states(self):
        for child in self.children:
            if child.label == "➡️ Next":
                child.disabled = not self.answered

            if child.label in ["A", "B", "C", "D"]:
                child.disabled = self.answered

    # Update display
    async def update(self, interaction: discord.Interaction):
        q, option_a, option_b, option_c, option_d, a = self.quiz[self.index]

        content = f"""{q}

                    A: {option_a}
                    B: {option_b}
                    C: {option_c}
                    D: {option_d}
                    """

        embed = discord.Embed(
            title=f"Quiz (Question: {self.index + 1}/{len(self.quiz)})",
            description=content,
            color=discord.Color.yellow()
        )
        embed.set_footer(text=f"Requested by {self.author.display_name}")

        self.set_button_states()
        await interaction.message.edit(embed=embed, view=self)

#----------------------------------------------------------------------------------------------------------------------------------------------
# Checking if Yoyo has sent a reminder.
@tasks.loop(minutes = 5)
async def reminder_check():
    db = connect_database()
    cursor = db.cursor()

    sql = """
    SELECT id, user_id, title, due_date
    FROM tasks
    WHERE status = 'Pending' 
    AND reminder_sent = FALSE 
    AND due_date = DATE_ADD(CURDATE(), INTERVAL 1 DAY);
    """

    cursor.execute(sql)
    tasks = cursor.fetchall()

    for task in tasks:
        task_id = task[0]
        user_id = task[1]
        title = task[2]
        user = await bot.fetch_user(user_id)

        embed = discord.Embed(
        title = "⏰ Reminder ⏰",
        description = f"Your task '{title}' is due tomorrow❗",
        color = discord.Color.red()
        )

        await user.send(embed=embed)

        update = """
                UPDATE tasks
                SET reminder_sent = TRUE
                WHERE id = %s;
        """

        cursor.execute(update,(task_id,))
        db.commit()

    cursor.close()
    db.close()

#----------------------------------------------------------------------------------------------------------------------------------------------
# Checking for Missed Tasks.
@tasks.loop(minutes = 1)
async def missed_tasks_check():
    db = connect_database()
    cursor = db.cursor()

    sql = """
    SELECT id, user_id
    FROM tasks
    WHERE due_date < CURDATE()
    AND status = 'Pending';
    """
    cursor.execute(sql)
    missed_tasks = cursor.fetchall()

    for missed_task in missed_tasks:
        task_id = missed_task[0]
        user_id = missed_task[1]

        sql = """
        UPDATE users
        SET missed_tasks = missed_tasks + 1
        WHERE user_id = %s;
        """

        cursor.execute(sql,(user_id,))

        sql = """
        UPDATE tasks
        SET status = 'Missed'
        WHERE id = %s;
        """

        cursor.execute(sql, (task_id,))
        db.commit()

    cursor.close()
    db.close()

threading.Thread(target=run_web, daemon=True).start()
bot.run(TOKEN)