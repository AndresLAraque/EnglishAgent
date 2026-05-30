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
from notion_client import Client
from dotenv import load_dotenv

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

    print()
    print("=" * 60)
    print("All 3 databases created successfully!")
    print()
    print("Add these to your .env file:")
    print(f"NOTION_WORDS_DB={words_id}")
    print(f"NOTION_READINGS_DB={readings_id}")
    print(f"NOTION_ACTIVITY_DB={activity_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
