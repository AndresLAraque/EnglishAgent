"""
Run this script to create the 3 Notion databases for EnglishAgent.

Usage:
    python setup_notion.py

You need:
1. A Notion integration token (https://www.notion.so/my-integrations)
2. A parent page shared with that integration
3. The parent page ID (from the URL)
"""
import os
import sys
from notion_client import Client
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from english_agent import topics as topics_data  # noqa: E402

load_dotenv()

STATUS_OPTIONS = [
    {"name": "learning", "color": "yellow"},
    {"name": "reviewing", "color": "blue"},
    {"name": "mastered", "color": "green"},
    {"name": "forgotten", "color": "red"},
]


def create_database(client: Client, parent_id: str, title: str, properties: dict) -> str:
    db = client.databases.create(
        parent={"type": "page_id", "page_id": parent_id},
        title=[{"type": "text", "text": {"content": title}}],
        properties=properties,
    )
    return db["id"]


def main():
    token = os.getenv("NOTION_TOKEN")
    if not token:
        print("ERROR: NOTION_TOKEN not found in .env file.")
        print("1. Copy .env.example → .env")
        print("2. Add your Notion integration token")
        return

    client = Client(auth=token)
    parent_id = input("Parent page ID (shared with your integration): ").strip()
    if not parent_id:
        print("No page ID. Exiting.")
        return

    # ── 1. Words database ──────────────────────────────────────
    print("\nCreating 'English Vocabulary' database...")
    words_id = create_database(client, parent_id, "English Vocabulary", {
        "Word": {"title": {}},
        "Translation": {"rich_text": {}},
        "Definition": {"rich_text": {}},
        "Example": {"rich_text": {}},
        "Status": {"select": {"options": STATUS_OPTIONS}},
        "Date Added": {"date": {}},
        "Last Reviewed": {"date": {}},
        "Times Correct": {"number": {}},
        "Times Wrong": {"number": {}},
        "Tags": {"multi_select": {}},
        "Source": {"select": {"options": [
            {"name": "manual", "color": "blue"},
            {"name": "extracted", "color": "green"},
        ]}},
    })
    print(f"  ✅ Words DB ID: {words_id}")

    # ── 2. Readings database ───────────────────────────────────
    print("\nCreating 'Readings' database...")
    readings_id = create_database(client, parent_id, "Readings", {
        "Title": {"title": {}},
        "Content": {"rich_text": {}},
        "Date Added": {"date": {}},
        "Difficulty": {"select": {"options": [
            {"name": "beginner", "color": "green"},
            {"name": "intermediate", "color": "yellow"},
            {"name": "advanced", "color": "red"},
        ]}},
        "Tags": {"multi_select": {}},
    })
    print(f"  ✅ Readings DB ID: {readings_id}")

    # ── 3. Activity Log database ──────────────────────────────
    print("\nCreating 'Activity Log' database...")
    activity_id = create_database(client, parent_id, "Activity Log", {
        "Name": {"title": {}},
        "Timestamp": {"date": {}},
        "Correct": {"checkbox": {}},
        "Hour": {"number": {}},
    })
    print(f"  ✅ Activity DB ID: {activity_id}")

    print("\nAdding Word relation to Activity Log...")
    client.databases.update(activity_id, properties={
        "Word": {"relation": {"database_id": words_id, "type": "single_property", "single_property": {}}},
    })

    # ── Add relation in Words → Readings ────────────────────
    print("\nAdding Source Text relation to Words database...")
    client.databases.update(words_id, properties={
        "Source Text": {"relation": {"database_id": readings_id, "type": "single_property", "single_property": {}}},
    })

    # ── 4. Writing Topics database ──────────────────────────────
    print("\nCreating 'Writing Topics' database...")
    topics_id = create_database(client, parent_id, "Writing Topics", {
        "Name": {"title": {}},
        "Week": {"number": {}},
        "Status": {"select": {"options": [
            {"name": "available", "color": "green"},
            {"name": "used", "color": "gray"},
        ]}},
        "Times Practiced": {"number": {}},
        "Last Practiced": {"date": {}},
    })
    print(f"  ✅ Writing Topics DB ID: {topics_id}")

    print("  Seeding topics from the 5-week curriculum...")
    seeded = 0
    for week, names in topics_data.WEEKS.items():
        for name in names:
            client.pages.create(
                parent={"database_id": topics_id},
                properties={
                    "Name": {"title": [{"text": {"content": name}}]},
                    "Week": {"number": week},
                    "Status": {"select": {"name": "available"}},
                    "Times Practiced": {"number": 0},
                },
            )
            seeded += 1
    print(f"  ✅ Seeded {seeded} topics")

    # ── 5. Writing Submissions database ─────────────────────────
    print("\nCreating 'Writing Submissions' database...")
    submissions_id = create_database(client, parent_id, "Writing Submissions", {
        "Name": {"title": {}},
        "Week": {"number": {}},
        "Original Text": {"rich_text": {}},
        "Corrected Text": {"rich_text": {}},
        "Feedback": {"rich_text": {}},
        "Score": {"number": {}},
        "Mistake Count": {"number": {}},
        "Strengths": {"rich_text": {}},
        "Hour": {"number": {}},
        "Provider": {"select": {"options": [
            {"name": "deepseek", "color": "blue"},
            {"name": "ollama", "color": "green"},
        ]}},
        "AI Model": {"select": {"options": [
            {"name": "deepseek-chat", "color": "blue"},
        ]}},
        "User ID": {"number": {}},
        "Date": {"date": {}},
    })
    print(f"  ✅ Writing Submissions DB ID: {submissions_id}")

    print("\nAdding Topic relation to Writing Submissions...")
    client.databases.update(submissions_id, properties={
        "Topic": {"relation": {"database_id": topics_id, "type": "single_property", "single_property": {}}},
    })

    # ── 6. Mistakes Bank database ───────────────────────────────
    print("\nCreating 'Mistakes Bank' database...")
    mistakes_id = create_database(client, parent_id, "Mistakes Bank", {
        "Name": {"title": {}},
        "Wrong": {"rich_text": {}},
        "Correct": {"rich_text": {}},
        "Explanation": {"rich_text": {}},
        "Category": {"select": {"options": [
            {"name": "grammar", "color": "red"},
            {"name": "vocabulary", "color": "blue"},
            {"name": "word-order", "color": "orange"},
            {"name": "preposition", "color": "purple"},
            {"name": "verb-tense", "color": "yellow"},
            {"name": "other", "color": "gray"},
        ]}},
        "Status": {"select": {"options": [
            {"name": "new", "color": "yellow"},
            {"name": "reviewing", "color": "blue"},
            {"name": "mastered", "color": "green"},
        ]}},
        "Times Reviewed": {"number": {}},
        "Times Correct": {"number": {}},
        "Date Added": {"date": {}},
        "Last Reviewed": {"date": {}},
    })
    print(f"  ✅ Mistakes Bank DB ID: {mistakes_id}")

    print("\nAdding Source Submission relation to Mistakes Bank...")
    client.databases.update(mistakes_id, properties={
        "Source Submission": {"relation": {"database_id": submissions_id, "type": "single_property", "single_property": {}}},
    })

    # ── 7. Reading Games database ────────────────────────────
    print("\nCreating 'Reading Games' database...")
    topic_options = [{"name": v, "color": "blue"} for v in topics_data.READING_TOPICS.values()]
    reading_game_id = create_database(client, parent_id, "Reading Games", {
        "Name": {"title": {}},
        "Content": {"rich_text": {}},
        "Level": {"select": {"options": [
            {"name": "IELTS (4.0-5.0)", "color": "yellow"},
            {"name": "IELTS (5.5-6.0)", "color": "orange"},
            {"name": "IELTS (6.5-7.0)", "color": "red"},
            {"name": "IELTS (7.5-9.0)", "color": "purple"},
            {"name": "TOEFL (40-60)", "color": "yellow"},
            {"name": "TOEFL (61-80)", "color": "orange"},
            {"name": "TOEFL (81-100)", "color": "red"},
            {"name": "TOEFL (101-120)", "color": "purple"},
            {"name": "General", "color": "green"},
        ]}},
        "Topic": {"select": {"options": topic_options}},
        "Questions": {"rich_text": {}},
        "Key Words": {"multi_select": {}},
        "Times Played": {"number": {}},
        "Best Score": {"number": {}},
        "Best Time": {"number": {}},
        "Date Added": {"date": {}},
        "Last Played": {"date": {}},
        "Source": {"select": {"options": [
            {"name": "ai_generated", "color": "blue"},
            {"name": "imported", "color": "green"},
        ]}},
    })
    print(f"  ✅ Reading Games DB ID: {reading_game_id}")

    print()
    print("=" * 60)
    print("All 7 databases created successfully!")
    print()
    print("Add these to your .env file:")
    print(f"NOTION_WORDS_DB={words_id}")
    print(f"NOTION_READINGS_DB={readings_id}")
    print(f"NOTION_ACTIVITY_DB={activity_id}")
    print(f"NOTION_TOPICS_DB={topics_id}")
    print(f"NOTION_SUBMISSIONS_DB={submissions_id}")
    print(f"NOTION_MISTAKES_DB={mistakes_id}")
    print(f"NOTION_READING_GAMES_DB={reading_game_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
